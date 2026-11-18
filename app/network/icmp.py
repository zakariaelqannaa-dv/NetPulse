"""ICMP echo implementations.

Two backends are provided:

* :class:`WindowsIcmpPinger` — uses the Windows IP Helper API
  (``IcmpCreateFile`` / ``IcmpSendEcho`` / ``IcmpCloseHandle``) through
  ``ctypes``. This needs **no administrator rights** on Windows 10/11, returns
  precise per-probe round-trip times and is completely independent of the
  display language (unlike parsing ``ping.exe`` text).
* :class:`SubprocessPinger` — fallback used on non-Windows development
  machines and when the IP Helper API is unavailable. It shells out to the
  platform ``ping`` command with an argument list and parses the output with
  :mod:`app.network.ping_parse`.

Both backends share the :class:`BasePinger` interface so tests can substitute a
deterministic fake.
"""

from __future__ import annotations

import ctypes
import os
import socket
import struct
import threading
from dataclasses import dataclass

from app.core.cancellation import CancellationToken
from app.network.ping_parse import expand_rtts, parse_ping_output
from app.network.proc import run_command
from app.network.validation import is_valid_ipv4, is_valid_ipv6

# --------------------------------------------------------------------------- #
# Result object
# --------------------------------------------------------------------------- #


@dataclass
class PingReply:
    """Outcome of a single ICMP echo request."""

    ok: bool
    rtt_ms: float | None = None
    error: str | None = None
    status_code: int | None = None
    #: True when the failure looks like ICMP filtering rather than a dead host.
    blocked_hint: bool = False


class BasePinger:
    """Interface implemented by every ICMP backend."""

    name = "base"

    def supports(self, host: str) -> bool:  # noqa: ARG002 - interface method
        return True

    def ping(self, host: str, timeout_ms: int = 1000) -> PingReply:  # noqa: ARG002
        raise NotImplementedError

    def close(self) -> None:  # noqa: B027 - optional hook
        return None

    def __enter__(self) -> BasePinger:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


# --------------------------------------------------------------------------- #
# Windows native ICMP (IP Helper API)
# --------------------------------------------------------------------------- #

IP_SUCCESS = 0
IP_DEST_NET_UNREACHABLE = 11002
IP_DEST_HOST_UNREACHABLE = 11003
IP_DEST_PROT_UNREACHABLE = 11004
IP_DEST_PORT_UNREACHABLE = 11005
IP_REQ_TIMED_OUT = 11010
IP_BAD_DESTINATION = 11018
IP_GENERAL_FAILURE = 11050

_STATUS_MESSAGES = {
    IP_SUCCESS: "Success",
    IP_DEST_NET_UNREACHABLE: "Destination network unreachable",
    IP_DEST_HOST_UNREACHABLE: "Destination host unreachable",
    IP_DEST_PROT_UNREACHABLE: "Destination protocol unreachable",
    IP_DEST_PORT_UNREACHABLE: "Destination port unreachable",
    IP_REQ_TIMED_OUT: "Request timed out",
    IP_BAD_DESTINATION: "Bad destination",
    IP_GENERAL_FAILURE: "General failure",
}


class _IP_OPTION_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("Ttl", ctypes.c_ubyte),
        ("Tos", ctypes.c_ubyte),
        ("Flags", ctypes.c_ubyte),
        ("OptionsSize", ctypes.c_ubyte),
        ("OptionsData", ctypes.c_void_p),
    ]


class _ICMP_ECHO_REPLY(ctypes.Structure):
    _fields_ = [
        ("Address", ctypes.c_ulong),
        ("Status", ctypes.c_ulong),
        ("RoundTripTime", ctypes.c_ulong),
        ("DataSize", ctypes.c_ushort),
        ("Reserved", ctypes.c_ushort),
        ("Data", ctypes.c_void_p),
        ("Options", _IP_OPTION_INFORMATION),
    ]


def _load_iphlpapi() -> ctypes.WinDLL | None:
    if os.name != "nt":
        return None
    try:
        dll = ctypes.WinDLL("iphlpapi.dll", use_last_error=True)  # type: ignore[attr-defined]
    except OSError:  # pragma: no cover - non Windows
        return None
    try:
        dll.IcmpCreateFile.restype = ctypes.c_void_p
        dll.IcmpCreateFile.argtypes = []
        dll.IcmpSendEcho.restype = ctypes.c_ulong
        dll.IcmpSendEcho.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_void_p,
            ctypes.c_ushort,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_ulong,
        ]
        dll.IcmpCloseHandle.restype = ctypes.c_bool
        dll.IcmpCloseHandle.argtypes = [ctypes.c_void_p]
    except AttributeError:  # pragma: no cover
        return None
    return dll


def ipv4_to_ulong(ip: str) -> int:
    """Convert an IPv4 string into the ``IPAddr`` (network order ``ULONG``) value."""
    return struct.unpack("<I", socket.inet_aton(ip))[0]


class WindowsIcmpPinger(BasePinger):
    """Native Windows ICMP echo backend (no administrator rights required)."""

    name = "windows-icmp"
    _PAYLOAD = b"netpulse-icmp-payload-0123456789"  # 32 bytes

    def __init__(self) -> None:
        self._dll = _load_iphlpapi()
        self._handle: int | None = None
        self._lock = threading.Lock()
        if self._dll is None:
            raise OSError("Windows IP Helper API (iphlpapi.dll) is not available")
        self._reply_buffer = ctypes.create_string_buffer(
            ctypes.sizeof(_ICMP_ECHO_REPLY) + len(self._PAYLOAD) + 8
        )

    def supports(self, host: str) -> bool:
        # IcmpSendEcho only handles IPv4; IPv6 targets need Icmp6SendEcho2.
        return not is_valid_ipv6(host)

    def _ensure_handle(self) -> int:
        if self._handle is None or self._handle == ctypes.c_void_p(-1).value:
            if self._dll is None:
                raise OSError("Windows IP Helper API (iphlpapi.dll) is not available")
            self._handle = self._dll.IcmpCreateFile()
            if not self._handle or self._handle == ctypes.c_void_p(-1).value:
                raise OSError("IcmpCreateFile failed")
        return self._handle

    def ping(self, host: str, timeout_ms: int = 1000) -> PingReply:
        if is_valid_ipv6(host):
            return PingReply(
                ok=False,
                error="IPv6 targets are not supported by the native ICMP backend",
            )
        if not is_valid_ipv4(host):
            try:
                host = socket.gethostbyname(host)
            except OSError as exc:
                return PingReply(ok=False, error=f"Name resolution failed: {exc}")

        if self._dll is None:
            return PingReply(
                ok=False,
                error="Windows IP Helper API (iphlpapi.dll) is not available",
            )
        payload = ctypes.create_string_buffer(self._PAYLOAD, len(self._PAYLOAD))
        options = _IP_OPTION_INFORMATION(Ttl=64, Tos=0, Flags=0, OptionsSize=0, OptionsData=None)
        timeout = max(int(timeout_ms), 1)

        with self._lock:
            try:
                handle = self._ensure_handle()
            except OSError as exc:
                return PingReply(ok=False, error=str(exc))

            count = self._dll.IcmpSendEcho(
                handle,
                ipv4_to_ulong(host),
                ctypes.byref(payload),
                len(self._PAYLOAD),
                ctypes.byref(options),
                ctypes.byref(self._reply_buffer),
                ctypes.sizeof(self._reply_buffer),
                timeout,
            )
            if not count:
                error_code = ctypes.get_last_error() if hasattr(ctypes, "get_last_error") else 0
                message = _STATUS_MESSAGES.get(
                    error_code, f"ICMP request failed (code {error_code})"
                )
                return PingReply(
                    ok=False,
                    error=message,
                    status_code=error_code,
                    blocked_hint=error_code in (IP_REQ_TIMED_OUT, IP_GENERAL_FAILURE),
                )

            reply = ctypes.cast(self._reply_buffer, ctypes.POINTER(_ICMP_ECHO_REPLY)).contents
            if reply.Status != IP_SUCCESS:
                message = _STATUS_MESSAGES.get(reply.Status, f"ICMP status {reply.Status}")
                return PingReply(
                    ok=False,
                    error=message,
                    status_code=int(reply.Status),
                    blocked_hint=reply.Status in (
                        IP_REQ_TIMED_OUT,
                        IP_DEST_HOST_UNREACHABLE,
                        IP_DEST_NET_UNREACHABLE,
                        IP_GENERAL_FAILURE,
                    ),
                )
            return PingReply(ok=True, rtt_ms=float(reply.RoundTripTime), status_code=IP_SUCCESS)

    def close(self) -> None:
        with self._lock:
            if self._handle and self._dll is not None:
                try:
                    self._dll.IcmpCloseHandle(self._handle)
                finally:
                    self._handle = None


# --------------------------------------------------------------------------- #
# Portable fallback (argument-list subprocess, localized-output aware)
# --------------------------------------------------------------------------- #


class SubprocessPinger(BasePinger):
    """Fallback backend that shells out to the platform ``ping`` command."""

    name = "subprocess-ping"

    def __init__(self, token: CancellationToken | None = None) -> None:
        self._token = token

    def _command(self, host: str, timeout_ms: int) -> list[str]:
        if os.name == "nt":
            return ["ping", "-n", "1", "-w", str(int(timeout_ms)), host]
        if os.uname().sysname == "Darwin":  # pragma: no cover - macOS only
            return ["ping", "-c", "1", "-W", str(int(timeout_ms)), host]
        return ["ping", "-c", "1", "-W", str(max(int(timeout_ms // 1000), 1)), host]

    def ping(self, host: str, timeout_ms: int = 1000) -> PingReply:
        result = run_command(
            self._command(host, timeout_ms),
            timeout=max(timeout_ms / 1000.0 + 2.0, 2.0),
            token=self._token,
        )
        if result.error and not result.timed_out and not result.cancelled:
            return PingReply(ok=False, error=result.error)

        parsed = parse_ping_output(result.combined)
        if parsed.rtts:
            return PingReply(ok=True, rtt_ms=parsed.rtts[0])
        if result.timed_out or parsed.timeouts:
            return PingReply(ok=False, error="Request timed out", blocked_hint=True)
        if parsed.unreachable:
            return PingReply(ok=False, error="Destination unreachable", blocked_hint=True)
        return PingReply(ok=False, error=parsed.message or "No reply parsed")


def create_pinger(token: CancellationToken | None = None) -> BasePinger:
    """Return the best available ICMP backend for this machine."""
    if os.name == "nt":
        try:
            return WindowsIcmpPinger()
        except OSError:
            pass
    return SubprocessPinger(token=token)


def native_icmp_available() -> bool:
    if os.name != "nt":
        return False
    return _load_iphlpapi() is not None


__all__ = [
    "BasePinger",
    "PingReply",
    "SubprocessPinger",
    "WindowsIcmpPinger",
    "create_pinger",
    "expand_rtts",
    "ipv4_to_ulong",
    "native_icmp_available",
]
