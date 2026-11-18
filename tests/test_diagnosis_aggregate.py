"""Unit tests for app.core.diagnosis — aggregate_internet helper.

Pure logic; no network or Windows required.
"""

from __future__ import annotations

from app.core.diagnosis import aggregate_internet
from app.core.models import LatencyStats, PingResult


def _ping(target: str, received: int, sent: int, loss: float, mean: float | None,
          max_ms: float | None, jitter: float | None) -> PingResult:
    stats = LatencyStats(
        sent=sent,
        received=received,
        lost=sent - received,
        loss_percent=loss,
        min_ms=mean,
        max_ms=max_ms,
        mean_ms=mean,
        median_ms=mean,
        stdev_ms=0.0,
        jitter_ms=jitter,
    )
    return PingResult(target=target, stats=stats)


def test_aggregate_internet_empty() -> None:
    agg = aggregate_internet([])
    assert agg.targets == 0
    assert agg.answered_targets == 0
    assert agg.lossy_targets == 0
    assert agg.worst_loss_percent == 0.0
    assert agg.mean_latency_ms is None
    assert agg.max_latency_ms is None
    assert agg.worst_jitter_ms is None


def test_aggregate_internet_mixed() -> None:
    pings = [
        _ping("1.1.1.1", received=30, sent=30, loss=0.0, mean=10.0, max_ms=12.0, jitter=2.0),
        _ping("8.8.8.8", received=28, sent=30, loss=6.67, mean=25.0, max_ms=40.0, jitter=8.0),
    ]
    agg = aggregate_internet(pings)
    assert agg.targets == 2
    assert agg.answered_targets == 2
    assert agg.lossy_targets == 1
    assert agg.worst_loss_percent == 6.67
    assert agg.mean_latency_ms == 17.5  # (10 + 25) / 2
    assert agg.max_latency_ms == 40.0
    assert agg.worst_jitter_ms == 8.0


def test_aggregate_internet_all_unanswered() -> None:
    pings = [
        _ping("1.1.1.1", received=0, sent=30, loss=100.0, mean=None, max_ms=None, jitter=None),
        _ping("8.8.8.8", received=0, sent=30, loss=100.0, mean=None, max_ms=None, jitter=None),
    ]
    agg = aggregate_internet(pings)
    assert agg.targets == 2
    assert agg.answered_targets == 0
    assert agg.lossy_targets == 2
    assert agg.worst_loss_percent == 100.0
    assert agg.mean_latency_ms is None
