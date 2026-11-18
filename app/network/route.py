"""Route diagnostics (``tracert`` on Windows, ``traceroute`` elsewhere).

Parsing is a pure function; the trace itself always has a hard timeout and is
cancellable. NetPulse explains that ``*`` hops are frequently caused by routers
deprioritising or blocking ICMP TTL-expired packets rather than by real loss.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

from app.core.cancellation import CancellationToken
from app.core.models import RouteHop, RouteTrace, TestStatus
from app.network.ping import resolve_target
from app.network.proc import run_command
from app.network.validation import validate_host

_IPV4_RE = re.compile(
    r"\b(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
    r"(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}\b"
)
_IPV6_RE = re.compile(r"\b(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}\b")
_HOP_RE = re.compile(r"^\s*(\d{1,3})\s+(.*)$")
#: One entry per probe of a hop: either an RTT token or a ``*`` placeholder.
_PROBE_TOKEN_RE = re.compile(r"([<]?\s*\d+(?:[.,]\d+)?\s*ms)|\*", re.IGNORECASE)
_HOSTNAME_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9\-]*(?:\.[A-Za-z0-9\-]+)+)\b")


@dataclass
class RouteConfig:
    target: str = "1.1.1.1"
    max_hops: int = 20
    probe_timeout_ms: int = 1000

    def clamped(self) -> RouteConfig:
        return RouteConfig(
            target=self.target,
            max_hops=max(1, min(int(self.max_hops), 64)),
            probe_timeout_ms=max(100, min(int(self.probe_timeout_ms), 5000)),
        )

    def total_timeout_s(self) -> float:
        self_c = self.clamped()
        return min(self_c.max_hops * 3 * (self_c.probe_timeout_ms / 1000.0) + 10.0, 150.0)


def build_trace_command(config: RouteConfig) -> list[str]:
    config = config.clamped()
    if os.name == "nt":
        return [
            "tracert",
            "-d",
            "-h",
            str(config.max_hops),
            "-w",
            str(config.probe_timeout_ms),
            config.target,
        ]
    return [
        "traceroute",
        "-n",
        "-m",
        str(config.max_hops),
        "-w",
        str(max(int(config.probe_timeout_ms / 1000), 1)),
        config.target,
    ]


def parse_rtt_token(comparator: str, raw: str) -> float:
    value = float(raw.replace(",", "."))
    if comparator == "<":
        return 0.5 if value <= 1 else value
    return value


def extract_address(remainder: str) -> str | None:
    """Find the hop address in a tracert line's remainder."""
    ipv4 = _IPV4_RE.search(remainder)
    if ipv4:
        return ipv4.group(0)
    ipv6 = _IPV6_RE.search(remainder)
    if ipv6:
        return ipv6.group(0)
    hostname = _HOSTNAME_RE.search(remainder)
    if hostname:
        candidate = hostname.group(1)
        if candidate.lower().endswith(("ms", "txt")):
            return None
        return candidate
    return None


def parse_tracert_output(text: str, target: str = "") -> RouteTrace:
    """Parse ``tracert``/``traceroute`` output into a :class:`RouteTrace`."""
    trace = RouteTrace(target=target)
    hops: dict[int, RouteHop] = {}
    order: list[int] = []

    for raw_line in (text or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        match = _HOP_RE.match(line)
        if match:
            hop_number = int(match.group(1))
            remainder = match.group(2)
            hop = RouteHop(hop=hop_number)
            _fill_hop(hop, remainder)
            if hop_number not in hops:
                order.append(hop_number)
            hops[hop_number] = hop
        elif order:
            # Continuation line of the previous hop (address wrapped).
            previous = hops[order[-1]]
            if previous.address is None:
                address = extract_address(line)
                if address:
                    previous.address = address
            _append_rtts(previous, line)

    trace.hops = [hops[i] for i in sorted(order, key=lambda n: n)]
    for hop in trace.hops:
        hop.timed_out = hop.address is None and not hop.has_reply
    trace.missing_hop_count = sum(1 for h in trace.hops if h.timed_out)
    if trace.hops:
        last = trace.hops[-1]
        trace.completed = last.address is not None and not last.timed_out
    return trace


def _fill_hop(hop: RouteHop, remainder: str) -> None:
    _append_rtts(hop, remainder)
    address = extract_address(remainder)
    hop.address = address
    hop.timed_out = address is None and not hop.has_reply


def _append_rtts(hop: RouteHop, remainder: str) -> None:
    """Append one entry per probe, preserving the ``*`` (timeout) positions."""
    if len(hop.rtts) >= 3:
        return
    for match in _PROBE_TOKEN_RE.finditer(remainder):
        token = match.group(1)
        if token is None:
            hop.rtts.append(None)
        else:
            comparator = "<" if token.strip().startswith("<") else ""
            number = token.strip().lstrip("<").strip()
            number = number[:-2].strip() if number.lower().endswith("ms") else number
            try:
                hop.rtts.append(parse_rtt_token(comparator, number))
            except ValueError:  # pragma: no cover - regex guarantees a number
                hop.rtts.append(None)
        if len(hop.rtts) >= 3:
            return


def run_route_trace(
    config: RouteConfig,
    token: CancellationToken | None = None,
) -> RouteTrace:
    """Run a route trace with a hard timeout and cancellation support."""
    config = config.clamped()
    started = time.monotonic()

    try:
        target = validate_host(config.target)
    except ValueError as exc:
        return RouteTrace(
            target=config.target, status=TestStatus.ERROR, message=str(exc)
        )
    config = RouteConfig(
        target=target,
        max_hops=config.max_hops,
        probe_timeout_ms=config.probe_timeout_ms,
    )

    resolved, resolve_error = resolve_target(target)
    if resolved is None:
        return RouteTrace(
            target=target,
            status=TestStatus.ERROR,
            message=resolve_error or "Unresolvable target",
        )

    result = run_command(
        build_trace_command(config),
        timeout=config.total_timeout_s(),
        token=token,
    )

    trace = parse_tracert_output(result.stdout or result.combined, target=target)
    trace.resolved_ip = resolved
    trace.duration_ms = (time.monotonic() - started) * 1000.0

    if result.cancelled:
        trace.status = TestStatus.CANCELLED
        trace.message = "Route trace was cancelled."
        return trace
    if result.error and "not found" in (result.error or "").lower():
        trace.status = TestStatus.UNSUPPORTED
        trace.message = "The route tracing tool is not available on this system."
        return trace
    if not trace.hops:
        trace.status = TestStatus.ERROR if result.error else TestStatus.NOT_MEASURABLE
        trace.message = result.error or "No hops could be parsed from the trace output."
        return trace

    if trace.missing_hop_count:
        trace.status = TestStatus.WARNING
        trace.message = (
            f"{trace.missing_hop_count} hop(s) returned no ICMP reply. Routers commonly "
            "deprioritise or block TTL-expired packets, so this alone is not proof of packet loss."
        )
    else:
        trace.status = TestStatus.OK
        trace.message = "Every hop answered."
    return trace


__all__ = [
    "RouteConfig",
    "build_trace_command",
    "extract_address",
    "parse_tracert_output",
    "run_route_trace",
]
