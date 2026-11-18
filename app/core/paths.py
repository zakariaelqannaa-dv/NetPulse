"""Filesystem locations used by NetPulse.

Everything NetPulse writes stays on the local machine. The base directory can
be overridden with the ``NETPULSE_DATA_DIR`` environment variable, which is
used by the test suite to keep test artefacts out of the real user profile.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_DATA_DIR = "NETPULSE_DATA_DIR"


def app_data_dir() -> Path:
    """Return the per-user NetPulse data directory (not created)."""
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return Path(override)

    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return Path(base) / "NetPulse"
        return Path.home() / "AppData" / "Local" / "NetPulse"

    return Path.home() / ".local" / "share" / "netpulse"


def ensure_app_data_dir() -> Path:
    """Create and return the per-user NetPulse data directory."""
    path = app_data_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path


def settings_path() -> Path:
    return app_data_dir() / "settings.json"


def history_path() -> Path:
    return app_data_dir() / "history.json"


def snapshots_dir() -> Path:
    return app_data_dir() / "snapshots"


def reports_dir() -> Path:
    return app_data_dir() / "reports"


def ensure_reports_dir() -> Path:
    path = reports_dir()
    path.mkdir(parents=True, exist_ok=True)
    return path
