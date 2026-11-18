"""Light and dark themes for the NetPulse interface.

The visual language is deliberately restrained: flat surfaces, one accent
colour, no gradients and no "gaming booster" styling. Severity colours are
reserved for status only.
"""

from __future__ import annotations

from string import Template

from PySide6.QtWidgets import QApplication

DARK = "dark"
LIGHT = "light"

PALETTES: dict[str, dict[str, str]] = {
    DARK: {
        "bg": "#16191d",
        "surface": "#1e2227",
        "surface_alt": "#23282e",
        "border": "#333a42",
        "border_strong": "#454d57",
        "text": "#e6edf3",
        "muted": "#98a2ad",
        "accent": "#4c8dff",
        "accent_text": "#ffffff",
        "good": "#3fb950",
        "info": "#58a6ff",
        "warning": "#d29922",
        "critical": "#f2555a",
        "unknown": "#8b949e",
    },
    LIGHT: {
        "bg": "#f2f4f7",
        "surface": "#ffffff",
        "surface_alt": "#f6f8fa",
        "border": "#d6dce3",
        "border_strong": "#b8c0ca",
        "text": "#1f2328",
        "muted": "#5c6672",
        "accent": "#1f6feb",
        "accent_text": "#ffffff",
        "good": "#1a7f37",
        "info": "#0969da",
        "warning": "#9a6700",
        "critical": "#cf222e",
        "unknown": "#6e7781",
    },
}

#: Keys that map one-to-one onto :class:`app.core.models.Severity` values.
SEVERITY_KEYS = ("good", "info", "warning", "critical", "unknown")

_QSS = Template(
    """
* { outline: none; }

QWidget {
    background: $bg;
    color: $text;
    font-family: "Segoe UI", "Inter", Arial, sans-serif;
    font-size: 13px;
}

QMainWindow, QDialog { background: $bg; }

QFrame[card="true"] {
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
}

QLabel[role="title"] { font-size: 15px; font-weight: 600; }
QLabel[role="subtitle"] { color: $muted; font-size: 12px; }
QLabel[role="muted"] { color: $muted; }
QLabel[role="section"] {
    font-size: 11px;
    font-weight: 600;
    color: $muted;
    letter-spacing: 1px;
}
QLabel[role="hero"] { font-size: 44px; font-weight: 600; }
QLabel[role="heroUnit"] { font-size: 15px; color: $muted; }
QLabel[role="headline"] { font-size: 16px; font-weight: 600; }
QLabel[role="mono"] { font-family: "Cascadia Mono", Consolas, monospace; font-size: 12px; }

QPushButton {
    background: $surface_alt;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 20px;
}
QPushButton:hover { border-color: $accent; }
QPushButton:pressed { background: $border; }
QPushButton:disabled { color: $muted; border-color: $border; }
QPushButton[accent="true"] {
    background: $accent;
    border-color: $accent;
    color: $accent_text;
    font-weight: 600;
}
QPushButton[accent="true"]:hover { background: $info; border-color: $info; }
QPushButton[accent="true"]:disabled { background: $border; border-color: $border; color: $muted; }
QPushButton[danger="true"]:hover { border-color: $critical; color: $critical; }

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {
    background: $surface;
    border: 1px solid $border_strong;
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: $accent;
    selection-color: $accent_text;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus { border-color: $accent; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background: $surface;
    border: 1px solid $border_strong;
    selection-background-color: $accent;
    selection-color: $accent_text;
}

QCheckBox, QRadioButton { spacing: 8px; }
QCheckBox::indicator, QRadioButton::indicator { width: 14px; height: 14px; }

QGroupBox {
    border: 1px solid $border;
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px;
    background: $surface;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: $muted;
    font-weight: 600;
}

QListWidget, QTreeWidget, QTableWidget {
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    gridline-color: $border;
    alternate-background-color: $surface_alt;
}
QTableWidget::item:selected, QListWidget::item:selected, QTreeWidget::item:selected {
    background: $accent;
    color: $accent_text;
}
QHeaderView::section {
    background: $surface_alt;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 6px 8px;
    font-weight: 600;
}

QListWidget#nav {
    background: $surface;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px;
}
QListWidget#nav::item {
    padding: 9px 12px;
    border-radius: 6px;
    color: $text;
}
QListWidget#nav::item:selected { background: $accent; color: $accent_text; }
QListWidget#nav::item:hover:!selected { background: $surface_alt; }

QProgressBar {
    background: $surface_alt;
    border: 1px solid $border;
    border-radius: 6px;
    text-align: center;
    height: 16px;
    color: $muted;
}
QProgressBar::chunk { background: $accent; border-radius: 5px; }

QScrollArea { border: none; }
QScrollBar:vertical {
    background: transparent; width: 10px; margin: 0;
}
QScrollBar::handle:vertical { background: $border_strong; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: $border_strong; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

QSplitter::handle { background: $border; width: 1px; height: 1px; }

QToolBar { background: $bg; border: none; spacing: 6px; padding: 4px; }
QStatusBar { background: $surface; color: $muted; border-top: 1px solid $border; }
QToolTip {
    background: $surface;
    color: $text;
    border: 1px solid $border_strong;
    padding: 4px 6px;
}
QMenu { background: $surface; border: 1px solid $border_strong; padding: 4px; }
QMenu::item { padding: 5px 18px; border-radius: 4px; }
QMenu::item:selected { background: $accent; color: $accent_text; }
"""
)


def palette(theme: str) -> dict[str, str]:
    """Return the colour dictionary for ``theme`` (falling back to dark)."""
    return PALETTES.get(theme, PALETTES[DARK])


def severity_color(theme: str, severity: str) -> str:
    """Colour used for one severity value; unknown severities fall back to muted."""
    colors = palette(theme)
    key = severity if severity in SEVERITY_KEYS else "unknown"
    return colors[key]


def stylesheet(theme: str) -> str:
    """Return the full Qt style sheet for ``theme``."""
    return _QSS.substitute(palette(theme))


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply ``theme`` to the running application."""
    app.setStyleSheet(stylesheet(theme))


__all__ = [
    "DARK",
    "LIGHT",
    "PALETTES",
    "SEVERITY_KEYS",
    "apply_theme",
    "palette",
    "severity_color",
    "stylesheet",
]
