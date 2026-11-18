"""Dataclass models for every diagnostic result produced by NetPulse.

The models are deliberately free of any GUI or Windows dependency so the whole
diagnostic pipeline can be unit tested without a display and without a live
network connection.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class Severity(str, Enum):
    """User facing rating used by cards, badges and the overall banner."""

    GOOD = "good"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


SEVERITY_LABELS: dict[Severity, str] = {
    Severity.GOOD: "Good",
    Severity.INFO: "Informational",
    Severity.WARNING: "Warning",
    Severity.CRITICAL: "Critical",
    Severity.UNKNOWN: "Unknown",
}


class TestStatus(str, Enum):
    """Execution status of a single diagnostic test."""

    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNSUPPORTED = "unsupported"
    NOT_MEASURABLE = "not_measurable"
    ERROR = "error"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def to_jsonable(value: Any) -> Any:
    """Recursively convert NetPulse models into JSON friendly primitives."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return value


# --------------------------------------------------------------------------- #
# Latency / packet statistics
# --------------------------------------------------------------------------- #


@dataclass
class PingSample:
    """One probe result. ``rtt_ms`` is ``None`` when the probe was lost."""

    index: int
    rtt_ms: float | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.rtt_ms is not None

    def to_dict(self) -> dict[str, Any]:
        return {"index": self.index, "rtt_ms": self.rtt_ms, "ok": self.ok, "error": self.error}


@dataclass
class LatencyStats:
    """Aggregate statistics for a series of probes.

    Formulas (also documented in docs/USER_GUIDE.md):

    * ``loss_percent``      = lost / sent * 100
    * ``mean_ms``           = arithmetic mean of the successful RTT samples
    * ``median_ms``         = statistical median of the successful RTT samples
    * ``stdev_ms``          = *population* standard deviation of successful RTTs
    * ``jitter_ms``         = mean absolute difference between consecutive
      *successful* RTT samples (RFC 3550 style smoothed jitter is not used).
      A single lost probe in the middle does not create a fake jitter spike
      because lost samples are skipped rather than treated as 0 ms.
    """

    sent: int = 0
    received: int = 0
    lost: int = 0
    loss_percent: float = 0.0
    min_ms: float | None = None
    max_ms: float | None = None
    mean_ms: float | None = None
    median_ms: float | None = None
    stdev_ms: float | None = None
    jitter_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass
class PingResult:
    """Result of a latency test against a single target."""

    target: str
    resolved_ip: str | None = None
    samples: list[PingSample] = field(default_factory=list)
    stats: LatencyStats = field(default_factory=LatencyStats)
    status: TestStatus = TestStatus.PENDING
    message: str = ""
    icmp_may_be_blocked: bool = False
    duration_ms: float = 0.0
    kind: str = "internet"  # "gateway" | "internet" | "dns-server"

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "kind": self.kind,
            "resolved_ip": self.resolved_ip,
            "status": self.status.value,
            "message": self.message,
            "icmp_may_be_blocked": self.icmp_may_be_blocked,
            "duration_ms": round(self.duration_ms, 2),
            "stats": self.stats.to_dict(),
            "samples": [s.to_dict() for s in self.samples],
        }


@dataclass
class TcpProbeResult:
    """TCP handshake probe used to separate ICMP filtering from real outages."""

    host: str
    port: int
    resolved_ip: str | None = None
    connected: bool = False
    connect_ms: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


# --------------------------------------------------------------------------- #
# Adapter / link / Wi-Fi
# --------------------------------------------------------------------------- #


@dataclass
class AdapterInfo:
    name: str
    description: str = ""
    media_type: str = ""  # "Ethernet" | "Wi-Fi" | "Other"/vendor text
    status: str = ""
    link_speed_mbps: float | None = None
    link_speed_text: str = ""
    mac_address: str = ""
    ipv4: list[str] = field(default_factory=list)
    ipv6: list[str] = field(default_factory=list)
    gateway: str | None = None
    dns_servers: list[str] = field(default_factory=list)
    dhcp_enabled: bool | None = None
    if_index: int | None = None
    mtu: int | None = None
    is_wireless: bool = False
    source: str = "powershell"

    @property
    def is_ethernet(self) -> bool:
        return not self.is_wireless and "wi-fi" not in self.media_type.lower() and "wireless" not in self.media_type.lower()

    @property
    def primary_ipv4(self) -> str | None:
        return self.ipv4[0] if self.ipv4 else None

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass
class WifiInfo:
    available: bool = False
    ssid: str | None = None
    bssid: str | None = None
    state: str | None = None
    signal_percent: int | None = None
    channel: int | None = None
    radio_type: str | None = None
    band: str | None = None
    receive_rate_mbps: float | None = None
    transmit_rate_mbps: float | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


# --------------------------------------------------------------------------- #
# DNS
# --------------------------------------------------------------------------- #


@dataclass
class DnsQueryResult:
    server: str
    hostname: str
    duration_ms: float | None = None
    addresses: list[str] = field(default_factory=list)
    ok: bool = False
    error: str | None = None
    is_public_resolver: bool = False

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass
class DnsTestResult:
    configured_servers: list[str] = field(default_factory=list)
    queries: list[DnsQueryResult] = field(default_factory=list)
    status: TestStatus = TestStatus.PENDING
    message: str = ""
    public_comparison_enabled: bool = False
    average_ms: float | None = None
    slowest: DnsQueryResult | None = None
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        data = to_jsonable(self)
        data["slowest"] = self.slowest.to_dict() if self.slowest else None
        return data


# --------------------------------------------------------------------------- #
# Route trace
# --------------------------------------------------------------------------- #


@dataclass
class RouteHop:
    hop: int
    rtts: list[float | None] = field(default_factory=list)
    address: str | None = None
    hostname: str | None = None
    timed_out: bool = False

    @property
    def average_ms(self) -> float | None:
        values = [v for v in self.rtts if v is not None]
        if not values:
            return None
        return sum(values) / len(values)

    @property
    def has_reply(self) -> bool:
        """True when at least one of the three probes of this hop answered."""
        return any(v is not None for v in self.rtts)

    def to_dict(self) -> dict[str, Any]:
        data = to_jsonable(self)
        data["average_ms"] = self.average_ms
        return data


@dataclass
class RouteTrace:
    target: str
    resolved_ip: str | None = None
    hops: list[RouteHop] = field(default_factory=list)
    completed: bool = False
    status: TestStatus = TestStatus.PENDING
    message: str = ""
    missing_hop_count: int = 0
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "resolved_ip": self.resolved_ip,
            "status": self.status.value,
            "message": self.message,
            "completed": self.completed,
            "missing_hop_count": self.missing_hop_count,
            "duration_ms": round(self.duration_ms, 2),
            "hops": [h.to_dict() for h in self.hops],
        }


# --------------------------------------------------------------------------- #
# Diagnosis
# --------------------------------------------------------------------------- #


@dataclass
class Diagnosis:
    """A single transparent, rule based conclusion."""

    rule_id: str
    finding: str
    evidence: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.LOW
    severity: Severity = Severity.UNKNOWN
    meaning: str = ""
    recommendation: str = ""
    cannot_verify: str = ""
    category: str = "general"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass
class DiagnosisSummary:
    overall_status: Severity = Severity.UNKNOWN
    headline: str = ""
    diagnoses: list[Diagnosis] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "headline": self.headline,
            "diagnoses": [d.to_dict() for d in self.diagnoses],
        }


# --------------------------------------------------------------------------- #
# Applied configuration changes
# --------------------------------------------------------------------------- #


@dataclass
class ChangeRecord:
    """Audit entry for anything NetPulse changed on the machine."""

    action_id: str
    title: str
    target: str = ""
    applied: bool = False
    requires_admin: bool = False
    before: str | None = None
    after: str | None = None
    note: str = ""
    error: str | None = None
    timestamp: str = ""
    command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


# --------------------------------------------------------------------------- #
# Host / environment
# --------------------------------------------------------------------------- #


@dataclass
class HostInfo:
    computer_name: str = ""
    os_name: str = ""
    os_version: str = ""
    os_build: str = ""
    architecture: str = ""
    python_version: str = ""
    is_admin: bool = False

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


# --------------------------------------------------------------------------- #
# Full report
# --------------------------------------------------------------------------- #


@dataclass
class DiagnosticReport:
    app_version: str = ""
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: float = 0.0
    host: HostInfo = field(default_factory=HostInfo)
    adapters: list[AdapterInfo] = field(default_factory=list)
    active_adapter_name: str | None = None
    active_adapter: AdapterInfo | None = None
    wifi: WifiInfo | None = None
    gateway_ping: PingResult | None = None
    internet_pings: list[PingResult] = field(default_factory=list)
    tcp_probes: list[TcpProbeResult] = field(default_factory=list)
    dns: DnsTestResult | None = None
    route: RouteTrace | None = None
    speed_test: SpeedTestResult | None = None
    applied_changes: list[ChangeRecord] = field(default_factory=list)
    diagnoses: list[Diagnosis] = field(default_factory=list)
    overall_status: Severity = Severity.UNKNOWN
    headline: str = ""
    cancelled: bool = False
    warnings: list[str] = field(default_factory=list)
    settings_snapshot: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "app_version": self.app_version,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": round(self.duration_ms, 2),
            "host": self.host.to_dict(),
            "adapters": [a.to_dict() for a in self.adapters],
            "active_adapter_name": self.active_adapter_name,
            "active_adapter": self.active_adapter.to_dict() if self.active_adapter else None,
            "wifi": self.wifi.to_dict() if self.wifi else None,
            "gateway_ping": self.gateway_ping.to_dict() if self.gateway_ping else None,
            "internet_pings": [p.to_dict() for p in self.internet_pings],
            "tcp_probes": [p.to_dict() for p in self.tcp_probes],
            "dns": self.dns.to_dict() if self.dns else None,
            "route": self.route.to_dict() if self.route else None,
            "speed_test": self.speed_test.to_dict() if self.speed_test else None,
            "applied_changes": [c.to_dict() for c in self.applied_changes],
            "diagnoses": [d.to_dict() for d in self.diagnoses],
            "overall_status": self.overall_status.value,
            "headline": self.headline,
            "cancelled": self.cancelled,
            "warnings": list(self.warnings),
            "settings_snapshot": to_jsonable(self.settings_snapshot),
        }

    # -- convenience accessors used by the rules engine -------------------- #

    def all_internet_ok(self) -> Iterable[PingResult]:
        return (p for p in self.internet_pings if p.stats.received > 0)


@dataclass
class SpeedTestResult:
    """Optional, explicitly consented download speed test against a user URL."""

    url: str = ""
    bytes_downloaded: int = 0
    duration_s: float = 0.0
    megabits_per_second: float | None = None
    ok: bool = False
    error: str | None = None
    stopped_early: bool = False
    privacy_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)
