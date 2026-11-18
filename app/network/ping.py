"""Latency measurement service built on top of the ICMP backends."""

from __future__ import annotations

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.core.cancellation import CancellationToken
from app.core.models import PingResult, PingSample, TestStatus
from app.core.stats import (
    DEFAULT_THRESHOLDS,
    rate_gateway_latency,
    rate_gateway_loss,
    rate_jitter,
    rate_latency,
    rate_loss,
    summarize_samples,
    worst_rating,
)
from app.network.icmp import BasePinger, create_pinger
from app.network.validation import is_valid_ip, validate_host

ProgressCallback = Callable[[int, int], None]


@dataclass
class PingConfig:
    """Probe parameters. Defaults follow the product requirements."""

    count: int = 30
    interval_ms: int = 1000
    timeout_ms: int = 1000

    def clamped(self) -> PingConfig:
        return PingConfig(
            count=max(1, min(int(self.count), 500)),
            interval_ms=max(50, min(int(self.interval_ms), 10000)),
            timeout_ms=max(100, min(int(self.timeout_ms), 10000)),
        )


def resolve_target(host: str) -> tuple[str | None, str | None]:
    """Resolve ``host`` to an IPv4/IPv6 address. Returns ``(address, error)``."""
    if is_valid_ip(host):
        return host, None
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        return None, f"Name resolution failed: {exc}"
    for family, _type, _proto, _canon, sockaddr in infos:
        if family in (socket.AF_INET, socket.AF_INET6):
            return str(sockaddr[0]), None
    return None, "No address returned by the resolver"


def measure_target(
    host: str,
    config: PingConfig | None = None,
    token: CancellationToken | None = None,
    pinger: BasePinger | None = None,
    progress: ProgressCallback | None = None,
    kind: str = "internet",
    thresholds: dict[str, float] | None = None,
) -> PingResult:
    """Probe ``host`` ``config.count`` times and return a fully populated result.

    Every probe gets its own timeout, the loop is cancellable between probes and
    there is a configurable delay between probes so NetPulse never floods a
    target with traffic.
    """
    config = (config or PingConfig()).clamped()
    thresholds = thresholds or DEFAULT_THRESHOLDS
    start = time.monotonic()

    try:
        host = validate_host(host)
    except ValueError as exc:
        return PingResult(target=host, status=TestStatus.ERROR, message=str(exc), kind=kind)

    resolved, resolve_error = resolve_target(host)
    if resolved is None:
        return PingResult(
            target=host,
            status=TestStatus.ERROR,
            message=resolve_error or "Could not resolve target",
            kind=kind,
            duration_ms=(time.monotonic() - start) * 1000.0,
        )

    own_pinger = pinger is None
    active_pinger = pinger or create_pinger(token)
    samples: list[PingSample] = []
    cancelled = False

    try:
        if not active_pinger.supports(resolved):
            return PingResult(
                target=host,
                resolved_ip=resolved,
                status=TestStatus.UNSUPPORTED,
                message="This ICMP backend cannot probe the resolved address family (IPv6).",
                kind=kind,
                duration_ms=(time.monotonic() - start) * 1000.0,
            )

        for index in range(config.count):
            if token is not None and token.is_cancelled():
                cancelled = True
                break
            reply = active_pinger.ping(resolved, timeout_ms=config.timeout_ms)
            if reply.ok:
                samples.append(PingSample(index=index, rtt_ms=round(float(reply.rtt_ms or 0.0), 3)))
            else:
                samples.append(PingSample(index=index, rtt_ms=None, error=reply.error))
            if progress is not None:
                progress(len(samples), config.count)
            if index < config.count - 1:
                if token is not None:
                    if token.wait(config.interval_ms / 1000.0):
                        cancelled = True
                        break
                else:
                    time.sleep(config.interval_ms / 1000.0)
    finally:
        if own_pinger:
            active_pinger.close()

    stats = summarize_samples(samples, sent=len(samples))
    result = PingResult(
        target=host,
        resolved_ip=resolved,
        samples=samples,
        stats=stats,
        kind=kind,
        duration_ms=(time.monotonic() - start) * 1000.0,
    )

    if cancelled:
        result.status = TestStatus.CANCELLED
        result.message = f"Stopped early after {stats.received}/{stats.sent} replies."
        result.icmp_may_be_blocked = stats.received == 0
        return result

    _apply_status(result, thresholds, kind)
    return result


def _apply_status(result: PingResult, thresholds: dict[str, float], kind: str) -> None:
    stats = result.stats
    if stats.received == 0:
        result.status = TestStatus.NOT_MEASURABLE
        result.icmp_may_be_blocked = True
        if kind == "gateway":
            result.message = (
                "No ICMP reply from the local gateway. Many routers block or deprioritise "
                "ping, so this does not by itself mean the router is faulty."
            )
        else:
            result.message = (
                "No ICMP reply. The target or a firewall on the path may be filtering ICMP; "
                "use the TCP checks to distinguish this from a real outage."
            )
        return

    if kind == "gateway":
        latency_rating = rate_gateway_latency(stats.mean_ms, thresholds)
        loss_rating = rate_gateway_loss(stats.loss_percent, thresholds)
    else:
        latency_rating = rate_latency(stats.mean_ms, thresholds)
        loss_rating = rate_loss(stats.loss_percent, thresholds)
    jitter_rating = rate_jitter(stats.jitter_ms, thresholds)
    rating = worst_rating(latency_rating, loss_rating, jitter_rating)

    result.status = {
        "good": TestStatus.OK,
        "warning": TestStatus.WARNING,
        "critical": TestStatus.CRITICAL,
    }.get(rating, TestStatus.OK)

    if stats.loss_percent > 0:
        result.message = f"{stats.lost} of {stats.sent} probes were lost."
    else:
        result.message = "All probes answered."
