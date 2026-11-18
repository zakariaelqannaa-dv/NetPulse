"""Latency, jitter and packet-loss mathematics.

This module is intentionally free of any I/O so the statistics can be tested
exhaustively. See :class:`app.core.models.LatencyStats` for the documented
formulas.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence

from app.core.models import LatencyStats, PingSample

#: Thresholds used to translate numbers into Good / Warning / Critical ratings.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "latency_warn_ms": 80.0,
    "latency_critical_ms": 150.0,
    "jitter_warn_ms": 30.0,
    "jitter_critical_ms": 60.0,
    "loss_warn_percent": 1.0,
    "loss_critical_percent": 5.0,
    "gateway_latency_warn_ms": 10.0,
    "gateway_latency_critical_ms": 30.0,
    "gateway_loss_warn_percent": 1.0,
    "gateway_loss_critical_percent": 5.0,
    "dns_warn_ms": 150.0,
    "dns_critical_ms": 400.0,
    "wifi_signal_warn_percent": 55.0,
    "wifi_signal_critical_percent": 35.0,
    "ethernet_slow_link_mbps": 100.0,
}


def mean_absolute_consecutive_difference(values: Sequence[float]) -> float | None:
    """Jitter = mean absolute difference between consecutive successful RTTs.

    Lost samples are skipped by the caller: they are *not* substituted with
    0 ms, because that would fabricate a large artificial jitter spike.
    """
    if len(values) < 2:
        return None
    total = 0.0
    for previous, current in zip(values, values[1:]):
        total += abs(current - previous)
    return total / (len(values) - 1)


def summarize_rtts(rtts: Iterable[float | None], sent: int | None = None) -> LatencyStats:
    """Build :class:`LatencyStats` from a per-probe RTT series.

    ``rtts`` must contain exactly one entry per probe, using ``None`` for a
    lost/timed-out probe. ``sent`` defaults to ``len(rtts)`` but can be given
    explicitly when the caller knows how many probes were attempted.
    """
    series = list(rtts)
    sent_count = len(series) if sent is None else max(int(sent), 0)
    successful = [float(v) for v in series if v is not None]

    stats = LatencyStats(sent=sent_count)
    stats.received = len(successful)
    stats.lost = max(sent_count - stats.received, 0)
    if sent_count > 0:
        stats.loss_percent = round(stats.lost / sent_count * 100.0, 3)

    if not successful:
        return stats

    stats.min_ms = round(min(successful), 3)
    stats.max_ms = round(max(successful), 3)
    stats.mean_ms = round(statistics.fmean(successful), 3)
    stats.median_ms = round(statistics.median(successful), 3)
    stats.stdev_ms = round(statistics.pstdev(successful), 3) if len(successful) > 1 else 0.0
    jitter = mean_absolute_consecutive_difference(successful)
    stats.jitter_ms = round(jitter, 3) if jitter is not None else None
    return stats


def samples_to_rtts(samples: Sequence[PingSample]) -> list[float | None]:
    return [s.rtt_ms for s in samples]


def summarize_samples(samples: Sequence[PingSample], sent: int | None = None) -> LatencyStats:
    return summarize_rtts(samples_to_rtts(samples), sent=sent)


def rate_latency(value_ms: float | None, thresholds: dict[str, float] | None = None) -> str:
    """Rate a latency number as ``good`` / ``warning`` / ``critical`` / ``unknown``."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    if value_ms is None:
        return "unknown"
    if value_ms >= thresholds["latency_critical_ms"]:
        return "critical"
    if value_ms >= thresholds["latency_warn_ms"]:
        return "warning"
    return "good"


def rate_jitter(value_ms: float | None, thresholds: dict[str, float] | None = None) -> str:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    if value_ms is None:
        return "unknown"
    if value_ms >= thresholds["jitter_critical_ms"]:
        return "critical"
    if value_ms >= thresholds["jitter_warn_ms"]:
        return "warning"
    return "good"


def rate_loss(value_percent: float | None, thresholds: dict[str, float] | None = None) -> str:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    if value_percent is None:
        return "unknown"
    if value_percent >= thresholds["loss_critical_percent"]:
        return "critical"
    if value_percent >= thresholds["loss_warn_percent"]:
        return "warning"
    return "good"


def rate_gateway_latency(value_ms: float | None, thresholds: dict[str, float] | None = None) -> str:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    if value_ms is None:
        return "unknown"
    if value_ms >= thresholds["gateway_latency_critical_ms"]:
        return "critical"
    if value_ms >= thresholds["gateway_latency_warn_ms"]:
        return "warning"
    return "good"


def rate_gateway_loss(value_percent: float | None, thresholds: dict[str, float] | None = None) -> str:
    thresholds = thresholds or DEFAULT_THRESHOLDS
    if value_percent is None:
        return "unknown"
    if value_percent >= thresholds["gateway_loss_critical_percent"]:
        return "critical"
    if value_percent >= thresholds["gateway_loss_warn_percent"]:
        return "warning"
    return "good"


def worst_rating(*ratings: str) -> str:
    order = {"unknown": 0, "good": 1, "warning": 2, "critical": 3}
    best = "unknown"
    for rating in ratings:
        if order.get(rating, 0) > order.get(best, 0):
            best = rating
    return best
