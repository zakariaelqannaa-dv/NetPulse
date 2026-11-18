"""Unit tests for app.core.stats — pure latency / jitter / loss mathematics.

These tests exercise only the statistical functions and require neither a
network connection nor Windows.
"""

from __future__ import annotations

from app.core.models import PingSample
from app.core.stats import (
    DEFAULT_THRESHOLDS,
    mean_absolute_consecutive_difference,
    rate_gateway_latency,
    rate_gateway_loss,
    rate_jitter,
    rate_latency,
    rate_loss,
    summarize_rtts,
    summarize_samples,
    worst_rating,
)

# --------------------------------------------------------------------------- #
# summarize_rtts
# --------------------------------------------------------------------------- #

def test_summarize_rtts_empty() -> None:
    stats = summarize_rtts([])
    assert stats.sent == 0
    assert stats.received == 0
    assert stats.lost == 0
    assert stats.loss_percent == 0.0
    assert stats.mean_ms is None
    assert stats.jitter_ms is None


def test_summarize_rtts_all_lost() -> None:
    stats = summarize_rtts([None, None, None], sent=3)
    assert stats.sent == 3
    assert stats.received == 0
    assert stats.lost == 3
    assert stats.loss_percent == 100.0
    assert stats.mean_ms is None


def test_summarize_rtts_single_value() -> None:
    stats = summarize_rtts([12.5], sent=1)
    assert stats.sent == 1
    assert stats.received == 1
    assert stats.lost == 0
    assert stats.loss_percent == 0.0
    assert stats.mean_ms == 12.5
    assert stats.min_ms == 12.5
    assert stats.max_ms == 12.5
    assert stats.median_ms == 12.5
    assert stats.stdev_ms == 0.0
    assert stats.jitter_ms is None


def test_summarize_rtts_mixed() -> None:
    # 3 successful + 2 lost out of 5
    stats = summarize_rtts([10.0, None, 20.0, None, 30.0], sent=5)
    assert stats.sent == 5
    assert stats.received == 3
    assert stats.lost == 2
    assert stats.loss_percent == 40.0
    assert stats.mean_ms == 20.0
    assert stats.min_ms == 10.0
    assert stats.max_ms == 30.0
    assert stats.median_ms == 20.0
    # Jitter: |20-10| + |30-20| = 20, / 2 = 10.0
    assert stats.jitter_ms == 10.0


def test_summarize_rtts_skips_lost_for_jitter() -> None:
    # Lost probe in the middle must not fabricate a jitter spike.
    stats = summarize_rtts([10.0, None, 11.0], sent=3)
    assert stats.received == 2
    assert stats.jitter_ms == 1.0  # |11 - 10| / 1


def test_summarize_rtts_sent_defaults_to_len() -> None:
    stats = summarize_rtts([1.0, 2.0, 3.0])
    assert stats.sent == 3


def test_summarize_rtts_sent_explicit() -> None:
    stats = summarize_rtts([1.0, 2.0], sent=10)
    assert stats.sent == 10
    assert stats.received == 2
    assert stats.lost == 8
    assert stats.loss_percent == 80.0


def test_summarize_rtts_rounds_to_three_decimals() -> None:
    stats = summarize_rtts([1.005, 2.005], sent=2)
    assert stats.mean_ms == round((1.005 + 2.005) / 2, 3)


# --------------------------------------------------------------------------- #
# summarize_samples
# --------------------------------------------------------------------------- #

def test_summarize_samples_maps_ping_samples() -> None:
    samples = [
        PingSample(index=0, rtt_ms=5.0),
        PingSample(index=1, rtt_ms=None),
        PingSample(index=2, rtt_ms=15.0),
    ]
    stats = summarize_samples(samples, sent=3)
    assert stats.sent == 3
    assert stats.received == 2
    assert stats.lost == 1
    assert stats.mean_ms == 10.0


# --------------------------------------------------------------------------- #
# mean_absolute_consecutive_difference
# --------------------------------------------------------------------------- #

def test_mean_absolute_consecutive_difference_less_than_two() -> None:
    assert mean_absolute_consecutive_difference([5.0]) is None
    assert mean_absolute_consecutive_difference([]) is None


def test_mean_absolute_consecutive_difference_two() -> None:
    assert mean_absolute_consecutive_difference([10.0, 20.0]) == 10.0


def test_mean_absolute_consecutive_difference_three() -> None:
    # |20-10| + |15-20| = 10 + 5 = 15, / 2 = 7.5
    assert mean_absolute_consecutive_difference([10.0, 20.0, 15.0]) == 7.5


# --------------------------------------------------------------------------- #
# Rating functions
# --------------------------------------------------------------------------- #

def test_rate_latency_bands() -> None:
    thresholds = DEFAULT_THRESHOLDS
    assert rate_latency(None) == "unknown"
    assert rate_latency(10.0, thresholds) == "good"
    assert rate_latency(80.0, thresholds) == "warning"   # exactly warn
    assert rate_latency(100.0, thresholds) == "warning"
    assert rate_latency(150.0, thresholds) == "critical"  # exactly critical
    assert rate_latency(200.0, thresholds) == "critical"


def test_rate_jitter_bands() -> None:
    thresholds = DEFAULT_THRESHOLDS
    assert rate_jitter(None) == "unknown"
    assert rate_jitter(10.0, thresholds) == "good"
    assert rate_jitter(30.0, thresholds) == "warning"
    assert rate_jitter(60.0, thresholds) == "critical"


def test_rate_loss_bands() -> None:
    thresholds = DEFAULT_THRESHOLDS
    assert rate_loss(None) == "unknown"
    assert rate_loss(0.5, thresholds) == "good"
    assert rate_loss(1.0, thresholds) == "warning"
    assert rate_loss(5.0, thresholds) == "critical"


def test_rate_gateway_latency_bands() -> None:
    thresholds = DEFAULT_THRESHOLDS
    assert rate_gateway_latency(None) == "unknown"
    assert rate_gateway_latency(5.0, thresholds) == "good"
    assert rate_gateway_latency(10.0, thresholds) == "warning"
    assert rate_gateway_latency(30.0, thresholds) == "critical"


def test_rate_gateway_loss_bands() -> None:
    thresholds = DEFAULT_THRESHOLDS
    assert rate_gateway_loss(None) == "unknown"
    assert rate_gateway_loss(0.5, thresholds) == "good"
    assert rate_gateway_loss(1.0, thresholds) == "warning"
    assert rate_gateway_loss(5.0, thresholds) == "critical"


# --------------------------------------------------------------------------- #
# worst_rating
# --------------------------------------------------------------------------- #

def test_worst_rating() -> None:
    assert worst_rating("good", "good") == "good"
    assert worst_rating("warning", "good") == "warning"
    assert worst_rating("good", "critical") == "critical"
    assert worst_rating("unknown", "warning") == "warning"
    assert worst_rating("unknown", "unknown") == "unknown"


# --------------------------------------------------------------------------- #
# DEFAULT_THRESHOLDS sanity
# --------------------------------------------------------------------------- #

def test_default_thresholds_keys() -> None:
    expected = {
        "latency_warn_ms", "latency_critical_ms",
        "jitter_warn_ms", "jitter_critical_ms",
        "loss_warn_percent", "loss_critical_percent",
        "gateway_latency_warn_ms", "gateway_latency_critical_ms",
        "gateway_loss_warn_percent", "gateway_loss_critical_percent",
        "dns_warn_ms", "dns_critical_ms",
        "wifi_signal_warn_percent", "wifi_signal_critical_percent",
        "ethernet_slow_link_mbps",
    }
    assert set(DEFAULT_THRESHOLDS) == expected
