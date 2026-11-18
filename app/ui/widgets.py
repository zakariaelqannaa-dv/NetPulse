"""Reusable widgets shared by every NetPulse page.

The widgets are intentionally small and data-dense so the pages read like a
dashboard rather than a form.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.core.models import SEVERITY_LABELS, Diagnosis, Severity
from app.ui import theme as theme_module

UNAVAILABLE_TEXT = "Not available on this system"


def repolish(widget: QWidget) -> None:
    """Re-evaluate the style sheet after a dynamic property change."""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def severity_text(severity: Any) -> str:
    if isinstance(severity, Severity):
        return SEVERITY_LABELS[severity]
    raw = severity.value if hasattr(severity, "value") else str(severity)
    mapping = {
        "good": "Good",
        "info": "Informational",
        "warning": "Warning",
        "critical": "Critical",
    }
    return mapping.get(raw.lower(), str(raw).replace("_", " ").title())


def severity_key(severity: Any) -> str:
    raw = severity.value if hasattr(severity, "value") else str(severity)
    raw = raw.lower()
    return raw if raw in theme_module.SEVERITY_KEYS else "unknown"


def fmt_ms(value: float | None, digits: int = 1) -> str:
    return UNAVAILABLE_TEXT if value is None else f"{float(value):.{digits}f} ms"


def fmt_percent(value: float | None) -> str:
    return UNAVAILABLE_TEXT if value is None else f"{float(value):.2f}%"


def fmt_plain(value: Any) -> str:
    if value is None:
        return UNAVAILABLE_TEXT
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value).strip()
    return text or UNAVAILABLE_TEXT


# --------------------------------------------------------------------------- #
# Layout helpers
# --------------------------------------------------------------------------- #


class Card(QFrame):
    """A titled surface panel."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("card", "true")
        self.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(8)

        self._header = QWidget(self)
        header_layout = QVBoxLayout(self._header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(2)

        self.title_label = QLabel(title, self._header)
        self.title_label.setProperty("role", "title")
        self.subtitle_label = QLabel(subtitle, self._header)
        self.subtitle_label.setProperty("role", "subtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.subtitle_label)
        outer.addWidget(self._header)
        self._header.setVisible(bool(title or subtitle))

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(6)
        outer.addLayout(self.body)
        outer.addStretch(1)

    def set_title(self, title: str, subtitle: str = "") -> None:
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))
        self._header.setVisible(bool(title or subtitle))

    def add(self, widget: QWidget) -> None:
        self.body.addWidget(widget)

    def add_layout(self, layout: Any) -> None:
        self.body.addLayout(layout)


class StatusBadge(QLabel):
    """Small pill showing a Good / Warning / Critical rating."""

    def __init__(self, severity: Any = Severity.UNKNOWN, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(84)
        self.set_severity(severity)

    def set_severity(self, severity: Any) -> None:
        key = severity_key(severity)
        self.setProperty("severity", key)
        self.setText(severity_text(severity))
        self.setStyleSheet(
            "QLabel#statusBadge {"
            "  padding: 3px 10px; border-radius: 10px; font-size: 11px;"
            "  font-weight: 600; letter-spacing: 0.6px;"
            f"  border: 1px solid {_badge_color(key)};"
            f"  color: {_badge_color(key)};"
            "}"
        )


def _badge_color(key: str) -> str:
    return theme_module.severity_color(current_theme(), key)


_ACTIVE_THEME = theme_module.DARK


def set_active_theme(theme: str) -> None:
    """Remember the current theme so dynamically styled widgets can match it."""
    global _ACTIVE_THEME
    _ACTIVE_THEME = theme if theme in theme_module.PALETTES else theme_module.DARK


def current_theme() -> str:
    """The theme currently in use, for widgets that style themselves inline."""
    return _ACTIVE_THEME


# --------------------------------------------------------------------------- #
# Content helpers
# --------------------------------------------------------------------------- #


def kv_grid(pairs: Sequence[tuple[str, Any]]) -> QWidget:
    """Two-column label/value grid; missing values are shown explicitly."""
    holder = QWidget()
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(18)
    grid.setVerticalSpacing(4)
    grid.setColumnStretch(1, 1)
    for row, (label, value) in enumerate(pairs):
        name = QLabel(str(label))
        name.setProperty("role", "muted")
        text = fmt_plain(value)
        value_label = QLabel(text)
        value_label.setWordWrap(True)
        value_label.setProperty("role", "mono")
        if text == UNAVAILABLE_TEXT:
            value_label.setProperty("role", "muted")
        value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(value_label, row, 1)
    return holder


def muted(text: str, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setProperty("role", "muted")
    label.setWordWrap(wrap)
    return label


def body(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def section_label(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setProperty("role", "section")
    return label


class MetricTile(QFrame):
    """One headline number with a caption."""

    def __init__(
        self,
        caption: str,
        value: str = UNAVAILABLE_TEXT,
        unit: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setProperty("card", "true")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(2)
        self.caption = QLabel(caption)
        self.caption.setProperty("role", "section")
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.value = QLabel(value)
        self.value.setProperty("role", "title")
        self.value.setStyleSheet("font-size: 20px;")
        self.unit = QLabel(unit)
        self.unit.setProperty("role", "muted")
        row.addWidget(self.value)
        row.addWidget(self.unit)
        row.addStretch(1)
        layout.addWidget(self.caption)
        layout.addLayout(row)

    def set_value(self, value: str, severity: Any | None = None, unit: str = "") -> None:
        self.value.setText(value)
        if unit:
            self.unit.setText(unit)
        if severity is None:
            self.value.setStyleSheet("font-size: 20px;")
        else:
            color = theme_module.severity_color(current_theme(), severity_key(severity))
            self.value.setStyleSheet(f"font-size: 20px; font-weight: 600; color: {color};")


class LatencyBars(QWidget):
    """Compact bar chart of per-probe round trip times."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._samples: list[float | None] = []
        self._warn = 80.0
        self._critical = 150.0

    def set_samples(
        self,
        samples: Iterable[Any],
        warn_ms: float = 80.0,
        critical_ms: float = 150.0,
    ) -> None:
        values: list[float | None] = []
        for sample in samples:
            if isinstance(sample, dict):
                values.append(sample.get("rtt_ms"))
            else:
                values.append(getattr(sample, "rtt_ms", None))
        self._samples = values
        self._warn = max(1.0, float(warn_ms))
        self._critical = max(self._warn, float(critical_ms))
        self.update()

    def clear(self) -> None:
        self._samples = []
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        colors = theme_module.palette(current_theme())
        rect = self.rect().adjusted(0, 2, -1, -2)

        painter.fillRect(rect, QColor(colors["surface_alt"]))
        painter.setPen(QPen(QColor(colors["border"]), 1))
        painter.drawRect(rect)

        if not self._samples:
            painter.setPen(QColor(colors["muted"]))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No measurements yet")
            return

        peak = max((v for v in self._samples if v is not None), default=0.0)
        scale_max = max(peak * 1.15, self._critical)
        count = len(self._samples)
        slot = rect.width() / max(count, 1)
        bar_width = max(2.0, min(14.0, slot * 0.62))

        # Threshold guides.
        for value, color_key in ((self._warn, "warning"), (self._critical, "critical")):
            y = rect.bottom() - int(rect.height() * min(1.0, value / scale_max))
            pen = QPen(QColor(colors[color_key]), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(rect.left() + 1, y, rect.right() - 1, y)

        for index, value in enumerate(self._samples):
            center = rect.left() + slot * (index + 0.5)
            left = center - bar_width / 2
            if value is None:
                painter.fillRect(
                    int(left),
                    rect.bottom() - 3,
                    int(bar_width),
                    3,
                    QColor(colors["critical"]),
                )
                continue
            height = int(rect.height() * min(1.0, float(value) / scale_max))
            height = max(height, 2)
            if value <= self._warn:
                color_key = "good"
            elif value <= self._critical:
                color_key = "warning"
            else:
                color_key = "critical"
            painter.fillRect(
                int(left),
                rect.bottom() - height,
                int(bar_width),
                height,
                QColor(colors[color_key]),
            )


class FindingCard(QFrame):
    """Renders one transparent, rule-based diagnosis."""

    def __init__(self, diagnosis: Diagnosis, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("card", "true")
        key = severity_key(diagnosis.severity)
        color = theme_module.severity_color(current_theme(), key)
        self.setStyleSheet(
            "QFrame[card=\"true\"] {"
            f"  border: 1px solid {theme_module.palette(current_theme())['border']};"
            f"  border-left: 4px solid {color};"
            "  border-radius: 8px;"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(10)
        title = QLabel(diagnosis.finding)
        title.setProperty("role", "headline")
        title.setWordWrap(True)
        head.addWidget(title, 1)
        head.addWidget(StatusBadge(diagnosis.severity), 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)

        meta = QLabel(
            f"{diagnosis.rule_id}  |  {diagnosis.category}  |  "
            f"Confidence: {str(diagnosis.confidence.value).title()}"
        )
        meta.setProperty("role", "subtitle")
        layout.addWidget(meta)

        if diagnosis.evidence:
            layout.addWidget(section_label("Evidence"))
            for item in diagnosis.evidence:
                bullet = QLabel(f"- {item}")
                bullet.setProperty("role", "muted")
                bullet.setWordWrap(True)
                layout.addWidget(bullet)

        for caption, text in (
            ("What this may mean", diagnosis.meaning),
            ("Recommended next action", diagnosis.recommendation),
            ("What NetPulse cannot verify", diagnosis.cannot_verify),
        ):
            if not text:
                continue
            layout.addWidget(section_label(caption))
            layout.addWidget(body(text))


__all__ = [
    "UNAVAILABLE_TEXT",
    "Card",
    "FindingCard",
    "LatencyBars",
    "MetricTile",
    "StatusBadge",
    "body",
    "current_theme",
    "fmt_ms",
    "fmt_percent",
    "fmt_plain",
    "kv_grid",
    "muted",
    "repolish",
    "section_label",
    "set_active_theme",
    "severity_key",
    "severity_text",
]
