"""Windows Network Settings: read-only checks and explicitly confirmed changes.

The page follows the NetPulse safety contract:

* every observation is collected and explained *before* any change is possible;
* a change is only applied after a confirmation dialog that lists the exact
  command, the reason, the trade-offs and the risk;
* destructive resets need a second, explicit acknowledgement;
* a snapshot is written before every change and can be reverted from this page.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.core.models import ChangeRecord
from app.core.settings import AppSettings
from app.optimization import (
    ApplyResult,
    Snapshot,
    SnapshotStore,
    apply_action,
    build_checks,
    collect_state,
    environment_note,
    get_action,
    preview_command,
    restore_snapshot,
    validate_dns_servers,
)
from app.optimization.models import NetworkAction, NetworkCheck
from app.ui.dialogs import ConfirmActionDialog
from app.ui.runner import CallableWorker
from app.ui.widgets import Card, StatusBadge, body, kv_grid, muted, section_label

_RISK_LABELS = {"low": "Low risk", "medium": "Medium risk", "high": "High risk"}


class NetworkSettingsPage(QWidget):
    """Read Windows network settings, then optionally change one safely."""

    #: emitted with the ChangeRecord of every change that was actually applied
    change_applied = Signal(object)

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._store = SnapshotStore()
        self._adapter_name = ""
        self._link_speed_mbps: float | None = None
        self._is_wireless = False
        self._checks: list[NetworkCheck] = []
        self._worker: CallableWorker | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        root.addWidget(scroll)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        layout.addWidget(self._build_toolbar())

        self.environment_label = muted(environment_note())
        layout.addWidget(self.environment_label)

        self.checks_holder = QWidget()
        self.checks_layout = QVBoxLayout(self.checks_holder)
        self.checks_layout.setContentsMargins(0, 0, 0, 0)
        self.checks_layout.setSpacing(10)
        layout.addWidget(self.checks_holder)

        self.snapshots_card = Card(
            "Restore points",
            "A snapshot is written before every change so you can put the previous value back.",
        )
        layout.addWidget(self.snapshots_card)
        layout.addStretch(1)

        self._render_checks([])
        self.refresh_snapshots()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build_toolbar(self) -> QWidget:
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        heading = QLabel("Windows Network Settings")
        heading.setProperty("role", "title")
        subtitle = QLabel(
            "NetPulse reads these settings first and explains each one. It never disables the firewall, "
            "Defender or IPv6, never forces link speed or MTU, and never runs a reset on its own."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(heading)
        title_box.addWidget(subtitle)
        row.addLayout(title_box, 1)

        self.scan_button = QPushButton("Scan settings")
        self.scan_button.setProperty("accent", "true")
        self.scan_button.clicked.connect(self.scan)
        self.refresh_button = QPushButton("Refresh restore points")
        self.refresh_button.clicked.connect(self.refresh_snapshots)
        row.addWidget(self.scan_button, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.refresh_button, 0, Qt.AlignmentFlag.AlignTop)
        return holder

    # ------------------------------------------------------------------ #
    # Context from the dashboard
    # ------------------------------------------------------------------ #

    def set_adapter_context(
        self,
        name: str | None,
        link_speed_mbps: float | None,
        is_wireless: bool,
    ) -> None:
        """Remember which adapter the checks should target."""
        self._adapter_name = name or ""
        self._link_speed_mbps = link_speed_mbps
        self._is_wireless = bool(is_wireless)
        self.environment_label.setText(environment_note())

    # ------------------------------------------------------------------ #
    # Scanning
    # ------------------------------------------------------------------ #

    def scan(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Scanning...")
        self._render_message("Reading Windows network settings...")

        worker = CallableWorker(partial(collect_state, self._adapter_name), parent=self)
        worker.succeeded.connect(self._on_scan_finished)
        worker.failed.connect(self._on_scan_failed)
        worker.finished.connect(self._on_worker_done)
        self._worker = worker
        worker.start()

    def _on_scan_finished(self, state: Any) -> None:
        checks = build_checks(state, self._link_speed_mbps, self._is_wireless)
        self._checks = checks
        self._render_checks(checks)

    def _on_scan_failed(self, message: str) -> None:
        self._render_message(f"The settings could not be read: {message}")

    def _on_worker_done(self) -> None:
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Scan settings")
        self._worker = None

    # ------------------------------------------------------------------ #
    # Rendering
    # ------------------------------------------------------------------ #

    def _clear_checks(self) -> None:
        while self.checks_layout.count():
            item = self.checks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _render_message(self, text: str) -> None:
        self._clear_checks()
        self.checks_layout.addWidget(muted(text))

    def _render_checks(self, checks: Sequence[NetworkCheck]) -> None:
        self._clear_checks()
        if not checks:
            self.checks_layout.addWidget(
                muted("Run a scan to see what Windows is currently configured to do.")
            )
            return
        for check in checks:
            self.checks_layout.addWidget(self._build_check_card(check))

    def _build_check_card(self, check: NetworkCheck) -> QWidget:
        card = Card(check.title, check.category)
        header = QHBoxLayout()
        header.addWidget(StatusBadge(check.status))
        header.addStretch(1)
        card.add_layout(header)

        card.add(
            kv_grid(
                [
                    ("Current value", check.current_value),
                    ("Windows default", _yes_no(check.is_default)),
                ]
            )
        )
        if check.explanation:
            card.add(body(check.explanation))
        if check.finding:
            card.add(section_label("Finding"))
            card.add(body(check.finding))
        if check.recommendation:
            card.add(section_label("Recommended next step"))
            card.add(body(check.recommendation))

        action = get_action(check.action_id) if check.action_id else None
        if action is not None:
            card.add(section_label("Optional change"))
            card.add(muted(f"{action.summary}  ({_RISK_LABELS.get(action.risk, action.risk)})"))
            apply_button = QPushButton(f"Apply: {action.title}")
            apply_button.setProperty("accent", "true")
            if action.is_destructive:
                apply_button.setProperty("danger", "true")
            apply_button.clicked.connect(partial(self._apply_action, action, check))
            row = QHBoxLayout()
            row.addWidget(apply_button)
            row.addStretch(1)
            card.add_layout(row)
        return card

    # ------------------------------------------------------------------ #
    # Applying a change
    # ------------------------------------------------------------------ #

    def _apply_action(self, action: NetworkAction, check: NetworkCheck) -> None:
        options: dict[str, Any] = {}
        if action.action_id == "dns-set":
            text, accepted = QInputDialog.getText(
                self,
                "DNS servers",
                "Enter up to three DNS server addresses, separated by commas\n"
                "for example: 1.1.1.1, 8.8.8.8",
                text=", ".join(self._settings.public_dns_servers or ["1.1.1.1", "8.8.8.8"]),
            )
            if not accepted:
                return
            try:
                options["servers"] = validate_dns_servers(text)
            except ValueError as exc:
                QMessageBox.warning(self, "Invalid DNS servers", str(exc))
                return

        try:
            command = preview_command(action.action_id, self._adapter_name, options)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot build this change", str(exc))
            return

        dialog = ConfirmActionDialog(action, command, self)
        if dialog.exec() != ConfirmActionDialog.DialogCode.Accepted:
            return

        self._run_change(
            partial(
                apply_action,
                action.action_id,
                adapter_name=self._adapter_name,
                options=options,
                store=self._store,
                confirm_destructive=action.is_destructive,
            ),
            self._on_apply_finished,
        )

    def _run_change(self, function: Any, on_success: Any) -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "Please wait", "Another operation is still running.")
            return
        worker = CallableWorker(function, parent=self)
        worker.succeeded.connect(on_success)
        worker.failed.connect(lambda message: QMessageBox.critical(self, "Operation failed", message))
        worker.finished.connect(self._on_worker_done)
        worker.finished.connect(self.refresh_snapshots)
        self._worker = worker
        self.scan_button.setEnabled(False)
        worker.start()

    def _on_apply_finished(self, result: Any) -> None:
        if not isinstance(result, ApplyResult):
            return
        record: ChangeRecord = result.record
        if record.applied:
            message = f"{record.title}\n\nBefore: {record.before}\nAfter: {record.after}"
            if record.note:
                message += f"\n\n{record.note}"
            QMessageBox.information(self, "Change applied", message)
            self.change_applied.emit(record)
        else:
            QMessageBox.warning(
                self,
                "Change not applied",
                record.error or record.note or "The command did not report success.",
            )
        self.scan()

    # ------------------------------------------------------------------ #
    # Restore points
    # ------------------------------------------------------------------ #

    def refresh_snapshots(self) -> None:
        while self.snapshots_card.body.count():
            item = self.snapshots_card.body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        snapshots = self._store.list()
        if not snapshots:
            self.snapshots_card.add(muted("No change has been made yet."))
            return
        for snapshot in snapshots:
            self.snapshots_card.add(self._build_snapshot_row(snapshot))

    def _build_snapshot_row(self, snapshot: Snapshot) -> QWidget:
        row = QFrame()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(snapshot.description or "NetPulse change")
        title.setProperty("role", "title")
        text.addWidget(title)
        detail = ", ".join(snapshot.action_ids) or "-"
        text.addWidget(muted(f"{snapshot.created_display}  |  {detail}"))
        layout.addLayout(text, 1)

        restore_button = QPushButton("Restore")
        restore_button.clicked.connect(partial(self._restore, snapshot))
        layout.addWidget(restore_button)
        return row

    def _restore(self, snapshot: Snapshot) -> None:
        answer = QMessageBox.question(
            self,
            "Restore previous value",
            f"Put the setting back to its previous value?\n\n{snapshot.description}\n"
            f"{snapshot.created_display}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._run_change(
            partial(restore_snapshot, snapshot.snapshot_id, store=self._store),
            self._on_restore_finished,
        )

    def _on_restore_finished(self, records: Any) -> None:
        if not records:
            QMessageBox.information(self, "Restore", "Nothing needed to be restored.")
            return
        lines = []
        for record in records:  # type: ignore[union-attr]
            state = "restored" if record.applied else (record.error or record.note or "not restored")
            lines.append(f"- {record.title}: {state}")
        QMessageBox.information(self, "Restore finished", "\n".join(lines))
        self.scan()


def _yes_no(value: bool | None) -> str | None:
    if value is None:
        return "Not determined"
    return "Yes" if value else "No"


__all__ = ["NetworkSettingsPage"]
