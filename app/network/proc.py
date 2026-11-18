"""Safe subprocess execution.

Rules enforced here:

* subprocesses are always started with an argument list and ``shell=False``;
* every subprocess has a timeout and is killed when the timeout expires;
* cancellation is polled while the child runs, so the GUI Stop button works;
* stdout/stderr are captured and returned as structured data, never raised.
"""

from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.core.cancellation import CancellationToken

DEFAULT_TIMEOUT = 15.0
_POLL_INTERVAL = 0.15


@dataclass
class CommandResult:
    """Structured result of a subprocess execution."""

    args: list[str] = field(default_factory=list)
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False
    error: str | None = None
    duration_ms: float = 0.0
    encoding: str = ""

    @property
    def ok(self) -> bool:
        return self.error is None and not self.timed_out and not self.cancelled and self.returncode == 0

    @property
    def combined(self) -> str:
        if self.stderr and self.stdout:
            return self.stdout + "\n" + self.stderr
        return self.stdout or self.stderr

    def to_dict(self) -> dict[str, object]:
        return {
            "args": list(self.args),
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
        }


def _windows_code_page(kind: str) -> str | None:
    if os.name != "nt":
        return None
    try:
        if kind == "oem":
            code = ctypes.windll.kernel32.GetOEMCP()  # type: ignore[attr-defined]
        else:
            code = ctypes.windll.kernel32.GetACP()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - non Windows / restricted
        return None
    if not code:
        return None
    try:
        return f"cp{int(code)}"
    except (TypeError, ValueError):  # pragma: no cover
        return None


def decode_output(data: bytes) -> tuple[str, str]:
    """Decode console output robustly, including non-English Windows code pages.

    Returns a ``(text, encoding_used)`` tuple. UTF-8 is attempted first because
    PowerShell output is forced to UTF-8 by :func:`run_powershell`; console
    tools such as ``ping``/``tracert`` fall back to the active OEM code page.
    """
    if not data:
        return "", ""
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    for encoding in (_windows_code_page("oem"), _windows_code_page("ansi"), "cp1252"):
        if not encoding:
            continue
        try:
            return data.decode(encoding), encoding
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace"), "utf-8/replace"


def run_command(
    args: Sequence[str],
    timeout: float = DEFAULT_TIMEOUT,
    token: CancellationToken | None = None,
    input_text: str | None = None,
    cwd: str | None = None,
) -> CommandResult:
    """Run ``args`` and always return a :class:`CommandResult`."""
    argv = [str(a) for a in args]
    result = CommandResult(args=argv)
    if not argv:
        result.error = "No command supplied"
        return result

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    started = time.monotonic()
    try:
        process = subprocess.Popen(  # noqa: S603 - argument list, shell=False
            argv,
            stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            cwd=cwd,
            creationflags=creationflags,
        )
    except FileNotFoundError:
        result.error = f"Command not found: {argv[0]}"
        result.duration_ms = (time.monotonic() - started) * 1000.0
        return result
    except OSError as exc:  # pragma: no cover - platform specific
        result.error = f"Failed to start {argv[0]}: {exc}"
        result.duration_ms = (time.monotonic() - started) * 1000.0
        return result

    payload = input_text.encode("utf-8") if input_text is not None else None
    deadline = started + max(timeout, 0.0)
    stdout_raw = b""
    stderr_raw = b""

    try:
        while True:
            if token is not None and token.is_cancelled():
                _terminate(process)
                result.cancelled = True
                result.error = "Cancelled"
                break

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _terminate(process)
                result.timed_out = True
                result.error = f"Timed out after {timeout:g}s"
                break

            try:
                stdout_raw, stderr_raw = process.communicate(
                    input=payload, timeout=min(_POLL_INTERVAL, remaining)
                )
                break
            except subprocess.TimeoutExpired:
                payload = None
                continue
    except Exception as exc:  # pragma: no cover - defensive
        _terminate(process)
        result.error = f"Unexpected failure: {exc}"

    result.returncode = process.returncode
    result.duration_ms = (time.monotonic() - started) * 1000.0
    stdout_text, encoding = decode_output(stdout_raw or b"")
    stderr_text, _ = decode_output(stderr_raw or b"")
    result.stdout = stdout_text
    result.stderr = stderr_text
    result.encoding = encoding
    return result


def _terminate(process: subprocess.Popen) -> None:  # pragma: no cover - exercised on live systems
    try:
        process.kill()
    except Exception:
        pass
    try:
        process.communicate(timeout=2)
    except Exception:
        pass


def which(program: str) -> str | None:
    return shutil.which(program)


# --------------------------------------------------------------------------- #
# PowerShell helpers
# --------------------------------------------------------------------------- #

POWERSHELL = "powershell.exe" if os.name == "nt" else "pwsh"

#: Forces UTF-8 console output so non-English systems decode reliably.
_UTF8_PREAMBLE = (
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    "$OutputEncoding=[System.Text.Encoding]::UTF8;"
    "$ProgressPreference='SilentlyContinue';"
    "$ErrorActionPreference='SilentlyContinue';"
)


def powershell_available() -> bool:
    return which(POWERSHELL) is not None


def run_powershell(
    script: str,
    timeout: float = DEFAULT_TIMEOUT,
    token: CancellationToken | None = None,
) -> CommandResult:
    """Run a read-only PowerShell script and return its output."""
    args = [
        POWERSHELL,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        _UTF8_PREAMBLE + script,
    ]
    return run_command(args, timeout=timeout, token=token)
