"""Modal dialogs: report export with redaction, change confirmation and About.

The export dialog is the only place that decides what leaves the machine: it
lists every identifying value found in the report and lets the user redact any
of them before a file is written.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app import APP_NAME, APP_URL, APP_VERSION
from app.optimization.models import NetworkAction
from app.reporting import (
    FIELD_LABELS,
    FORMAT_LABELS,
    ReportFormat,
    collect_sensitive_fields,
    default_selection,
    report_to_dict,
)
from app.ui.widgets import body, muted, section_label


class ExportDialog(QDialog):
    """Choose a report format and which identifying values to redact."""

    def __init__(
        self,
        report: Any,
        parent: QWidget | None = None,
        suggested_format: ReportFormat = ReportFormat.HTML,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export report")
        self.setMinimumWidth(620)
        self._report_data = report_to_dict(report)
        self._fields = collect_sensitive_fields(self._report_data)
        preselected = default_selection(self._fields)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        layout.addWidget(section_label("Format"))
        self.format_combo = QComboBox()
        for fmt in ReportFormat:
            self.format_combo.addItem(FORMAT_LABELS[fmt], fmt.value)
        index = self.format_combo.findData(suggested_format.value)
        self.format_combo.setCurrentIndex(max(0, index))
        layout.addWidget(self.format_combo)

        layout.addWidget(section_label("What is included"))
        layout.addWidget(
            body(
                "NetPulse lists everything in this report that could identify you or your network. "
                "Clear a checkbox to replace those values with a neutral placeholder before the file "
                "is written. Nothing is uploaded: the report is written to the path you choose."
            )
        )

        self._checkboxes: dict[str, QCheckBox] = {}
        list_holder = QWidget()
        list_layout = QVBoxLayout(list_holder)
        list_layout.setContentsMargins(10, 8, 10, 8)
        list_layout.setSpacing(8)
        for item in self._fields:
            box = QCheckBox(FIELD_LABELS.get(item.key, item.key))
            box.setChecked(item.key in preselected)
            box.setEnabled(item.has_values)
            if item.description:
                box.setToolTip(item.description)
            list_layout.addWidget(box)
            detail = muted(
                item.display_values() if item.has_values else "not present in this report",
                wrap=True,
            )
            detail.setIndent(22)
            list_layout.addWidget(detail)
            self._checkboxes[item.key] = box
        list_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.StyledPanel)
        scroll.setWidget(list_holder)
        scroll.setMinimumHeight(240)
        layout.addWidget(scroll, 1)

        selectors = QHBoxLayout()
        select_all = QPushButton("Redact everything listed")
        select_all.clicked.connect(lambda: self._set_all(True))
        select_none = QPushButton("Redact nothing")
        select_none.clicked.connect(lambda: self._set_all(False))
        selectors.addWidget(select_all)
        selectors.addWidget(select_none)
        selectors.addStretch(1)
        layout.addLayout(selectors)

        self.note_label = muted(
            "Ticked items are replaced with placeholders such as [redacted-ssid]."
        )
        layout.addWidget(self.note_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Choose file and export...")
        buttons.button(QDialogButtonBox.StandardButton.Save).setProperty("accent", "true")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all(self, checked: bool) -> None:
        for key, box in self._checkboxes.items():
            if box.isEnabled():
                box.setChecked(checked)
            elif checked:
                box.setChecked(False)

    def chosen_format(self) -> ReportFormat:
        return ReportFormat(self.format_combo.currentData())

    def chosen_keys(self) -> list[str]:
        return [key for key, box in self._checkboxes.items() if box.isChecked()]

    def report_data(self) -> dict[str, Any]:
        return self._report_data


class ConfirmActionDialog(QDialog):
    """Explain one Windows change, its trade-offs and the exact command."""

    def __init__(self, action: NetworkAction, command: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Confirm change")
        self.setMinimumWidth(560)
        self._action = action

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        heading = QLabel(action.title)
        heading.setProperty("role", "headline")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        risk = {
            "low": "Low risk",
            "medium": "Medium risk",
            "high": "High risk",
        }.get(action.risk, action.risk)
        meta = muted(f"{action.category}  |  {risk}" + ("  |  restart required" if action.requires_reboot else ""))
        layout.addWidget(meta)

        layout.addWidget(section_label("What this does"))
        layout.addWidget(body(action.summary))

        layout.addWidget(section_label("Why NetPulse offers it"))
        layout.addWidget(body(action.why))

        if action.tradeoffs:
            layout.addWidget(section_label("Trade-offs and risks"))
            for item in action.tradeoffs:
                bullet = muted(f"- {item}")
                bullet.setWordWrap(True)
                layout.addWidget(bullet)

        if action.documentation:
            layout.addWidget(section_label("Documented command"))
            doc = QLabel(action.documentation)
            doc.setProperty("role", "mono")
            doc.setWordWrap(True)
            doc.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(doc)

        if command:
            layout.addWidget(section_label("Exact command that will run"))
            command_label = QLabel(command)
            command_label.setProperty("role", "mono")
            command_label.setWordWrap(True)
            command_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            command_label.setFrameShape(QFrame.Shape.StyledPanel)
            command_label.setContentsMargins(8, 6, 8, 6)
            layout.addWidget(command_label)

        if action.is_destructive:
            warning = body(
                "This change cannot be undone automatically. NetPulse records what it did, but it "
                "cannot restore the previous state."
            )
            warning.setStyleSheet("color: #f2555a; font-weight: 600;")
            layout.addWidget(warning)
            self.ack = QCheckBox("I understand this cannot be undone and I want to continue")
            layout.addWidget(self.ack)
        else:
            self.ack = None

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Apply
        )
        apply_button = buttons.button(QDialogButtonBox.StandardButton.Apply)
        apply_button.setText("Apply change" if not action.is_destructive else "Apply destructive change")
        apply_button.setProperty("accent", "true")
        if action.is_destructive:
            apply_button.setProperty("danger", "true")
            apply_button.setEnabled(False)
            self.ack.toggled.connect(apply_button.setEnabled)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class AboutDialog(QDialog):
    """Short, honest description of what NetPulse is and is not."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel(f"{APP_NAME} {APP_VERSION}")
        title.setProperty("role", "headline")
        layout.addWidget(title)
        layout.addWidget(muted(APP_URL))

        layout.addWidget(section_label("What NetPulse is"))
        layout.addWidget(
            body(
                "An open-source diagnostic tool. It measures the link, your router, the internet path "
                "and DNS resolution, then explains what it found in plain language."
            )
        )

        layout.addWidget(section_label("What NetPulse is not"))
        layout.addWidget(
            body(
                "It is not an internet booster and it does not promise faster internet. NetPulse cannot "
                "fix ISP congestion, radio interference, a damaged cable or router hardware, and it "
                "never claims to."
            )
        )

        layout.addWidget(section_label("Privacy"))
        layout.addWidget(
            body(
                "No telemetry, no accounts and no automatic uploads. Settings, history and snapshots "
                "are stored locally and reports are only written when you export them."
            )
        )

        layout.addWidget(section_label("License"))
        layout.addWidget(body("Released under the MIT License. Use it at your own risk."))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)


__all__ = ["AboutDialog", "ConfirmActionDialog", "ExportDialog"]
