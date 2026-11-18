"""Host and Windows version information for reports."""

from __future__ import annotations

import platform
import socket
import sys

from app.core.models import HostInfo
from app.network.privileges import is_admin


def collect_host_info() -> HostInfo:
    """Collect non-sensitive environment details used by the report header."""
    info = HostInfo()
    try:
        info.computer_name = socket.gethostname()
    except OSError:  # pragma: no cover - defensive
        info.computer_name = ""
    info.os_name = platform.system()
    info.os_version = platform.release()
    info.os_build = platform.version()
    info.architecture = platform.machine()
    info.python_version = platform.python_version() or sys.version.split()[0]
    info.is_admin = is_admin()
    return info


__all__ = ["collect_host_info"]
