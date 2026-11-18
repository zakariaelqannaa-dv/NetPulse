"""The NetPulse main window: navigation, diagnosis lifecycle, export and About.

The window owns the single background diagnosis worker, keeps the pages in sync
and is the only place that starts a run or writes a report file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QStackedWidget,
    QStatusBar,
    QWidget,
)

from app import APP_NAME, APP_VERSION
from app.core.models import ChangeRecord, DiagnosticReport
from app.core.paths import ensure_reports_dir
from app.core.settings import AppSettings
from app.network.privileges import is_admin
from app.reporting import (
    FILE_DIALOG_FILTER,
    FORMAT_EXTENSIONS,
    FORMAT_LABELS,
    default_filename,
    export_report,
)
from app.ui import theme as theme_module
from app.ui import widgets as widgets_module
from app.ui.dialogs import AboutDialog, ExportDialog
from app.ui.pages import DashboardPage, HistoryPage, NetworkSettingsPage, SettingsPage
from app.ui.runner import DiagnosisWorker

_PAGES = ("Dashboard", "History", "Windows network", "Settings")


class MainWindow(QMainWindow):
    """Top-level window wiring every page together."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__()
        self.settings = (settings or AppSettings().load()).normalized()
        self._worker: DiagnosisWorker | None = None
        self._applied_changes: list[ChangeRecord] = []

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1180, 820)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(12)

        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(196)
        for name in _PAGES:
            self.nav.addItem(QListWidgetItem(name))
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav)

        self.stack = QStackedWidget()
        self.dashboard = DashboardPage(self.settings)
        self.history_page = HistoryPage(self.settings)
        self.network_page = NetworkSettingsPage(self.settings)
        self.settings_page = SettingsPage(self.settings)
        for page in (self.dashboard, self.history_page, self.network_page, self.settings_page):
            self.stack.addWidget(page)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self._build_menu()
        self._build_status_bar()
        self._connect_signals()

        self.nav.setCurrentRow(0)
        self.apply_theme(self.settings.theme)
        self._status(
            f"Ready. {'Administrator' if is_admin() else 'Standard user'} session. "
            "Select Start diagnosis to measure your connection."
        )

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        export_action = QAction("&Export report...", self)
        export_action.setShortcut("Ctrl+E")
        export_action.triggered.connect(lambda: self._export(self.dashboard.report))
        file_menu.addAction(export_action)
        file_menu.addSeparator()
        quit_action = QAction("E&xit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        view_menu = self.menuBar().addMenu("&View")
        dark_action = QAction("&Dark theme", self)
        dark_action.triggered.connect(lambda: self._set_theme(theme_module.DARK))
        light_action = QAction("&Light theme", self)
        light_action.triggered.connect(lambda: self._set_theme(theme_module.LIGHT))
        view_menu.addAction(dark_action)
        view_menu.addAction(light_action)

        help_menu = self.menuBar().addMenu("&Help")
        about_action = QAction(f"&About {APP_NAME}", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_status_bar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.status_label = QLabel("")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFixedWidth(180)
        self.progress.setVisible(False)
        self.privilege_label = QLabel("Administrator" if is_admin() else "Standard user")
        bar.addWidget(self.status_label, 1)
        bar.addPermanentWidget(self.progress)
        bar.addPermanentWidget(self.privilege_label)

    def _connect_signals(self) -> None:
        self.dashboard.run_requested.connect(self.start_diagnosis)
        self.dashboard.stop_requested.connect(self.stop_diagnosis)
        self.dashboard.export_requested.connect(lambda: self._export(self.dashboard.report))
        self.history_page.export_requested.connect(self._export)
        self.settings_page.settings_saved.connect(self._on_settings_saved)
        self.network_page.change_applied.connect(self._on_change_applied)

    # ------------------------------------------------------------------ #
    # Navigation / theme
    # ------------------------------------------------------------------ #

    def _on_nav_changed(self, index: int) -> None:
        if index < 0:
            return
        self.stack.setCurrentIndex(index)
        if index == 1:
            self.history_page.refresh()
        elif index == 2:
            self.network_page.refresh_snapshots()

    def apply_theme(self, theme: str) -> None:
        widgets_module.set_active_theme(theme)
        application = QApplication.instance()
        if application is not None:
            theme_module.apply_theme(application, theme)

    def _set_theme(self, theme: str) -> None:
        if theme == self.settings.theme:
            return
        self.settings.theme = theme
        try:
            self.settings.save()
        except OSError as exc:
            self._status(f"The theme was applied but could not be saved: {exc}")
        self.apply_theme(theme)
        self.settings_page.load_from_settings(self.settings)

    # ------------------------------------------------------------------ #
    # Diagnosis
    # ------------------------------------------------------------------ #

    def start_diagnosis(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.dashboard.reset()
        self.dashboard.set_running(True)
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._status("Diagnosis running...")

        worker = DiagnosisWorker(
            self.settings,
            applied_changes=self._applied_changes,
            parent=self,
        )
        worker.progressed.connect(self.dashboard.set_progress)
        worker.progressed.connect(self._on_progress)
        worker.section_ready.connect(self._on_section)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        worker.start()

    def stop_diagnosis(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._status("Stopping after the current probe...")

    def _on_progress(self, percent: int, task: str) -> None:
        self.progress.setValue(max(0, min(100, percent)))
        if task and task != "finished":
            self.status_label.setText(f"Running: {task}")

    def _on_section(self, name: str, payload: Any) -> None:
        self.dashboard.apply_section(name, payload)
        if name == "adapters":
            adapter = getattr(payload, "active_adapter", None)
            self.network_page.set_adapter_context(
                getattr(payload, "active_name", None),
                getattr(adapter, "link_speed_mbps", None) if adapter is not None else None,
                bool(getattr(adapter, "is_wireless", False)) if adapter is not None else False,
            )

    def _on_completed(self, report: DiagnosticReport) -> None:
        self.dashboard.show_report(report)
        self.history_page.record(report)
        adapter = report.active_adapter
        self.network_page.set_adapter_context(
            report.active_adapter_name,
            adapter.link_speed_mbps if adapter is not None else None,
            bool(adapter.is_wireless) if adapter is not None else False,
        )
        summary = report.headline or "Diagnosis finished."
        self._status(
            f"{summary}  |  {len(report.diagnoses)} finding(s)  |  "
            f"{report.duration_ms / 1000.0:.1f} s"
        )

    def _on_failed(self, message: str) -> None:
        self._status(f"Diagnosis failed: {message}")
        QMessageBox.warning(
            self,
            "Diagnosis failed",
            "NetPulse could not complete the diagnosis.\n\n"
            f"{message}\n\n"
            "This is normally caused by a missing network adapter or a blocked PowerShell call.",
        )

    def _on_worker_finished(self) -> None:
        self.dashboard.set_running(False)
        self.progress.setVisible(False)
        self._worker = None

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #

    def _on_settings_saved(self, settings: AppSettings) -> None:
        self.settings = settings.normalized()
        self.apply_theme(self.settings.theme)
        self._status("Settings saved.")

    def _on_change_applied(self, record: Any) -> None:
        if isinstance(record, ChangeRecord) and record.applied:
            self._applied_changes.append(record)
            self._status(
                "A Windows change was applied. It will be listed in the next exported report "
                "and can be reverted from the Windows network page."
            )

    # ------------------------------------------------------------------ #
    # Export / About
    # ------------------------------------------------------------------ #

    def _export(self, report: Any) -> None:
        if report is None:
            QMessageBox.information(
                self,
                "Nothing to export",
                "Run a diagnosis first, or select a stored run in the History page.",
            )
            return
        dialog = ExportDialog(report, self)
        if dialog.exec() != ExportDialog.DialogCode.Accepted:
            return
        fmt = dialog.chosen_format()
        report_data = dialog.report_data()
        suggested = default_filename(report_data, fmt)
        try:
            directory = ensure_reports_dir()
        except OSError:
            directory = Path.home()
        selected_filter = f"{FORMAT_LABELS[fmt]} (*{FORMAT_EXTENSIONS[fmt]})"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export report",
            str(directory / suggested),
            FILE_DIALOG_FILTER,
            selected_filter,
        )
        if not path:
            return
        try:
            target = export_report(report_data, fmt, path, dialog.chosen_keys())
        except OSError as exc:
            QMessageBox.critical(
                self, "Report not written", f"The report could not be written:\n{exc}"
            )
            return
        self._status(f"Report written to {target}")
        QMessageBox.information(self, "Report exported", f"The report was written to:\n{target}")

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    # ------------------------------------------------------------------ #

    def _status(self, message: str) -> None:
        self.status_label.setText(message)

    def closeEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        if self._worker is not None and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)
        super().closeEvent(event)


__all__ = ["MainWindow"]
