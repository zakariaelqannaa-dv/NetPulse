"""TCP connectivity probes.

ICMP echo is frequently blocked while normal TCP traffic works fine. These
probes connect to well known TCP ports so NetPulse can distinguish "ICMP is
filtered" from "the internet is genuinely unreachable".
"""

from __future__ import annotations

import socket
import time
from collections.abc import Iterable

from app.core.models import TcpProbeResult
from app.network.ping import resolve_target
from app.network.validation import is_valid_host, validate_port

#: Default (host, port) pairs used to verify real TCP reachability.
DEFAULT_TCP_PROBES: tuple[tuple[str, int], ...] = (
    ("1.1.1.1", 443),
    ("8.8.8.8", 53),
)


def tcp_connect(host: str, port: int, timeout_s: float = 3.0) -> TcpProbeResult:
    """Attempt a TCP handshake and measure how long the connection took."""
    result = TcpProbeResult(host=host, port=int(port))
    if not is_valid_host(host):
        result.error = "Invalid host"
        return result
    try:
        result.port = validate_port(port)
    except ValueError as exc:
        result.error = str(exc)
        return result

    resolved, resolve_error = resolve_target(host)
    if resolved is None:
        result.error = resolve_error or "Could not resolve host"
        return result
    result.resolved_ip = resolved

    family = socket.AF_INET6 if ":" in resolved else socket.AF_INET
    address = (resolved, result.port, 0, 0) if family == socket.AF_INET6 else (resolved, result.port)
    started = time.monotonic()
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.settimeout(max(timeout_s, 0.2))
    try:
        sock.connect(address)
        result.connect_ms = (time.monotonic() - started) * 1000.0
        result.connected = True
    except OSError as exc:
        result.error = f"{type(exc).__name__}: {exc}"
    finally:
        sock.close()
    return result


def run_tcp_probes(
    probes: Iterable[tuple[str, int]] | None = None,
    timeout_s: float = 3.0,
) -> list[TcpProbeResult]:
    pairs = list(probes or DEFAULT_TCP_PROBES)
    results: list[TcpProbeResult] = []
    for host, port in pairs:
        results.append(tcp_connect(host, port, timeout_s=timeout_s))
    return results


def summarise_tcp(results: Iterable[TcpProbeResult]) -> str | None:
    items = list(results)
    if not items:
        return None
    reachable = [r for r in items if r.connected]
    if not reachable:
        return "No TCP endpoint could be reached."
    timings = [r.connect_ms for r in reachable if r.connect_ms is not None]
    if not timings:
        return f"{len(reachable)} of {len(items)} TCP endpoints reachable."
    return (
        f"{len(reachable)} of {len(items)} TCP endpoints reachable "
        f"(fastest handshake {min(timings):.0f} ms)."
    )


__all__ = ["DEFAULT_TCP_PROBES", "run_tcp_probes", "summarise_tcp", "tcp_connect"]
