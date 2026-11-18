"""PySide6 user interface for NetPulse.

The public entry points are :class:`~app.ui.main_window.MainWindow` and the
helpers in :mod:`app.ui.pages`.
"""

from __future__ import annotations

from app.ui.main_window import MainWindow
from app.ui.pages import DashboardPage, HistoryPage, NetworkSettingsPage, SettingsPage

__all__ = ["DashboardPage", "HistoryPage", "MainWindow", "NetworkSettingsPage", "SettingsPage"]
