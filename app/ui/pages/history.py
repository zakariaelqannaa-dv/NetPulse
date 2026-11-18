"""Diagnostics history.

Every completed diagnosis is summarised locally so the user can compare runs
over time. History never leaves the machine and can be cleared at any moment.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.history import HistoryEntry, HistoryStore
from app.core.models import Severity
from app.core.settings import AppSettings
from app.reporting import ReportFormat, render_report
from app.ui import theme as theme_module
from app.ui.widgets import current_theme, fmt_ms, fmt_percent, muted

_STATUS_LABELS = {
    Severity.GOOD.value: "Good",
    Severity.INFO.value: "Informational",
    Severity.WARNING.value: "Warning",
    Severity.CRITICAL.value: "Critical",
    Severity.UNKNOWN.value: "Unknown",
}

_COLUMNS = ["Time", "Rating", "Adapter", "Gateway", "Internet", "Loss", "Findings", "Headline"]


class HistoryPage(QWidget):
    """Table of past runs with a text preview of the stored report."""

    export_requested = Signal(object)

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._store = HistoryStore(limit=settings.history_limit)
        self._entries: list[HistoryEntry] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        layout.addWidget(self._build_toolbar())

        splitter = QSplitter(Qt.Orientation.Vertical, self)
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        splitter.addWidget(self.table)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select a run to see the stored report.")
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        self.note = muted(
            "History is stored locally in your NetPulse data folder. Clearing it deletes the file; "
            "exported reports are not affected."
        )
        layout.addWidget(self.note)

        self.refresh()

    # ------------------------------------------------------------------ #

    def _build_toolbar(self) -> QWidget:
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        heading = QLabel("Diagnostics history")
        heading.setProperty("role", "title")
        subtitle = QLabel("Compare earlier runs to see whether a problem is constant or intermittent.")
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(heading)
        title_box.addWidget(subtitle)
        row.addLayout(title_box, 1)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.export_button = QPushButton("Export selected...")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_selected)
        self.delete_button = QPushButton("Delete selected")
        self.delete_button.setEnabled(False)
        self.delete_button.setProperty("danger", "true")
        self.delete_button.clicked.connect(self._delete_selected)
        self.clear_button = QPushButton("Clear history")
        self.clear_button.setProperty("danger", "true")
        self.clear_button.clicked.connect(self._clear)

        for button in (self.refresh_button, self.export_button, self.delete_button, self.clear_button):
            row.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)
        return holder

    # ------------------------------------------------------------------ #

    def refresh(self) -> None:
        """Reload the history file and rebuild the table."""
        self._entries = self._store.entries()
        self.table.setRowCount(len(self._entries))
        for row, entry in enumerate(self._entries):
            values = [
                entry.timestamp_display,
                _STATUS_LABELS.get(entry.overall_status, entry.overall_status),
                entry.adapter_name or "-",
                fmt_ms(entry.gateway_mean_ms, 1) if entry.gateway_mean_ms is not None else "-",
                fmt_ms(entry.internet_mean_ms, 1) if entry.internet_mean_ms is not None else "-",
                fmt_percent(entry.internet_loss_percent) if entry.internet_loss_percent is not None else "-",
                str(entry.diagnosis_count),
                entry.headline,
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                if column == 1:
                    color = theme_module.severity_color(current_theme(), entry.overall_status)
                    item.setForeground(QColor(color))
                    item.setToolTip(text)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self._update_buttons()
        if not self._entries:
            self.preview.setPlainText("")

    def _selected_entry(self) -> HistoryEntry | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        index = rows[0].row()
        if 0 <= index < len(self._entries):
            return self._entries[index]
        return None

    def _update_buttons(self) -> None:
        has_selection = self._selected_entry() is not None
        self.export_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.clear_button.setEnabled(bool(self._entries))

    def _on_selection_changed(self) -> None:
        self._update_buttons()
        entry = self._selected_entry()
        if entry is None:
            self.preview.setPlainText("")
            return
        report = entry.report or {}
        try:
            self.preview.setPlainText(render_report(report, ReportFormat.TXT))
        except Exception as exc:  # noqa: BLE001 - never break the window on a bad record
            self.preview.setPlainText(f"This record could not be rendered: {exc}")

    def _export_selected(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            self.export_requested.emit(entry.report)

    def _delete_selected(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        if self._store.delete(entry.entry_id):
            self.refresh()

    def _clear(self) -> None:
        if not self._entries:
            return
        answer = QMessageBox.question(
            self,
            "Clear history",
            "Delete every stored diagnosis summary? Exported report files are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self._store.clear()
            self.refresh()

    # ------------------------------------------------------------------ #

    def record(self, report: object) -> None:
        """Store a freshly completed report (called by the main window)."""
        if not self._settings.history_enabled:
            return
        self._store.limit = max(1, int(self._settings.history_limit))
        try:
            self._store.add(report)  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001 - history is best effort only
            return
        self.refresh()


__all__ = ["HistoryPage"]
