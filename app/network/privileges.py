"""Administrator privilege helpers.

NetPulse never elevates on its own: :func:`relaunch_elevated` is only called
after the user explicitly confirms an action that genuinely requires
administrator rights.
"""

from __future__ import annotations

import ctypes
import os
import sys
from collections.abc import Sequence


def is_admin() -> bool:
    """True when the current process runs with administrator rights."""
    if os.name != "nt":
        try:
            return os.geteuid() == 0  # type: ignore[attr-defined]
        except AttributeError:  # pragma: no cover
            return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - defensive
        return False


def elevated_command(argv: Sequence[str]) -> list[str]:
    """Build the argument list that :func:`relaunch_elevated` should use."""
    if getattr(sys, "frozen", False):  # PyInstaller build
        return list(argv)
    return [sys.executable, *argv]


def relaunch_elevated(argv: Sequence[str] = ()) -> int | None:
    """Relaunch NetPulse through the UAC prompt.

    Returns the ``ShellExecuteW`` result code, or ``None`` when elevation is not
    available on this platform. The caller must obtain explicit user consent
    first.
    """
    if os.name != "nt":
        return None
    arguments = list(argv)
    if getattr(sys, "frozen", False):
        executable = sys.executable
        parameters = " ".join(f'"{a}"' for a in arguments)
    else:
        executable = sys.executable
        command = elevated_command(["-m", "app", *arguments])
        parameters = " ".join(f'"{a}"' for a in command[1:])
    try:
        result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
            None, "runas", executable, parameters, None, 1
        )
    except Exception:  # pragma: no cover - defensive
        return None
    return int(result)


def elevation_hint() -> str:
    return (
        "This change writes to a system-wide network setting, so Windows requires "
        "administrator rights. NetPulse will ask for consent before relaunching elevated."
    )
