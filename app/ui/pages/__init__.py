"""NetPulse pages: dashboard, history, Windows settings and application settings."""

from __future__ import annotations

from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.history import HistoryPage
from app.ui.pages.network import NetworkSettingsPage
from app.ui.pages.settings import SettingsPage

__all__ = ["DashboardPage", "HistoryPage", "NetworkSettingsPage", "SettingsPage"]
