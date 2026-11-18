"""Transparent, rule based diagnosis engine.

Every rule produces a :class:`~app.core.models.Diagnosis` containing:

1. the finding, 2. the measured evidence, 3. a confidence level, 4. what it may
mean, 5. the recommended next action, and 6. what NetPulse cannot verify.

The engine never claims to fix ISP congestion, radio problems, damaged cables or
router hardware. It separates *local link* symptoms (PC <-> router) from
*beyond the router* symptoms (ISP / WAN / upstream) and says explicitly when a
measurement is inconclusive.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.core.models import (
    Confidence,
    Diagnosis,
    DiagnosisSummary,
    DiagnosticReport,
    PingResult,
    Severity,
    TestStatus,
)
from app.core.stats import DEFAULT_THRESHOLDS

_SEVERITY_ORDER = {
    Severity.UNKNOWN: 0,
    Severity.INFO: 1,
    Severity.GOOD: 2,
    Severity.WARNING: 3,
    Severity.CRITICAL: 4,
}


@dataclass
class InternetAggregate:
    """Combined view over every public latency target."""

    targets: int = 0
    answered_targets: int = 0
    lossy_targets: int = 0
    worst_loss_percent: float = 0.0
    mean_latency_ms: float | None = None
    max_latency_ms: float | None = None
    worst_jitter_ms: float | None = None


def aggregate_internet(pings: Iterable[PingResult]) -> InternetAggregate:
    items = [p for p in pings if p is not None]
    aggregate = InternetAggregate(targets=len(items))
    means: list[float] = []
    for ping in items:
        stats = ping.stats
        if stats.received > 0:
            aggregate.answered_targets += 1
            if stats.mean_ms is not None:
                means.append(stats.mean_ms)
            if stats.max_ms is not None:
                aggregate.max_latency_ms = max(aggregate.max_latency_ms or 0.0, stats.max_ms)
            if stats.jitter_ms is not None:
                aggregate.worst_jitter_ms = max(aggregate.worst_jitter_ms or 0.0, stats.jitter_ms)
        if stats.loss_percent > 0:
            aggregate.lossy_targets += 1
        aggregate.worst_loss_percent = max(aggregate.worst_loss_percent, stats.loss_percent)
    if means:
        aggregate.mean_latency_ms = round(sum(means) / len(means), 3)
    return aggregate


def _fmt_ms(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.1f} ms"


def _thresholds(overrides: dict[str, float] | None) -> dict[str, float]:
    merged = dict(DEFAULT_THRESHOLDS)
    if overrides:
        merged.update({k: float(v) for k, v in overrides.items() if k in merged})
    return merged


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


def rule_local_link(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    out: list[Diagnosis] = []
    adapter = report.active_adapter

    if not report.adapters:
        out.append(
            Diagnosis(
                rule_id="NET-001",
                finding="No active network adapter was detected",
                evidence=["Windows reported no adapter with an active link."],
                confidence=Confidence.HIGH,
                severity=Severity.CRITICAL,
                meaning="The computer has no usable network connection, so every other test is meaningless.",
                recommendation=(
                    "Check that Wi-Fi is enabled or the Ethernet cable is plugged in, verify the "
                    "adapter is not disabled in Device Manager, then run the diagnosis again."
                ),
                cannot_verify="NetPulse cannot inspect hardware faults or driver-level failures.",
                category="local-link",
            )
        )
        return out

    if adapter is None:
        out.append(
            Diagnosis(
                rule_id="NET-002",
                finding="No adapter currently carries a default route",
                evidence=[f"{len(report.adapters)} adapter(s) are up but none has a usable gateway."],
                confidence=Confidence.MEDIUM,
                severity=Severity.WARNING,
                meaning="Traffic has no path to the internet even though a link is up.",
                recommendation="Reconnect the network, check DHCP on the router, then re-run the diagnosis.",
                cannot_verify="Router DHCP behaviour cannot be inspected from this PC.",
                category="local-link",
            )
        )
        return out

    if not adapter.ipv4 and not adapter.ipv6:
        out.append(
            Diagnosis(
                rule_id="NET-003",
                finding="The active adapter has no IP address",
                evidence=[f"Adapter {adapter.name} is {adapter.status or 'up'} but has no IPv4/IPv6 address."],
                confidence=Confidence.HIGH,
                severity=Severity.CRITICAL,
                meaning="The PC did not obtain an address, which is usually a DHCP or link problem.",
                recommendation="Reconnect the cable/Wi-Fi, then check the router's DHCP scope before rebooting anything.",
                cannot_verify="Whether the router's DHCP service is exhausted or misconfigured.",
                category="local-link",
            )
        )

    if not adapter.gateway:
        out.append(
            Diagnosis(
                rule_id="NET-004",
                finding="No default gateway is configured",
                evidence=[f"Adapter: {adapter.name}", f"IPv4: {', '.join(adapter.ipv4) or 'none'}"],
                confidence=Confidence.HIGH,
                severity=Severity.CRITICAL,
                meaning="Without a default gateway the PC cannot reach anything outside its own subnet.",
                recommendation=(
                    "Set the adapter back to automatic (DHCP) addressing, or configure the correct "
                    "gateway manually if your network requires a static address."
                ),
                cannot_verify="NetPulse cannot change IP configuration automatically; it only reports it.",
                category="local-link",
            )
        )

    speed = adapter.link_speed_mbps
    if (
        speed is not None
        and speed > 0
        and speed <= th["ethernet_slow_link_mbps"]
        and not adapter.is_wireless
    ):
        out.append(
            Diagnosis(
                rule_id="NET-005",
                finding=f"Ethernet link negotiated at {speed:.0f} Mbps",
                evidence=[
                    f"Adapter: {adapter.name}"
                    + (f" (interface index {adapter.if_index})" if adapter.if_index is not None else ""),
                    f"Negotiated link speed: {adapter.link_speed_text or f'{speed:.0f} Mbps'}",
                    "Latency is unaffected by link speed, but throughput is capped near this value.",
                ],
                confidence=Confidence.MEDIUM,
                severity=Severity.WARNING,
                meaning=(
                    "A 100 Mbps negotiation on gigabit hardware is most often caused by a damaged or "
                    "marginal cable (only two pairs working), an old Cat5 cable, or a 100 Mbps router/switch port."
                ),
                recommendation=(
                    "Try a known-good Cat5e/Cat6 cable and a different router port, then compare the "
                    "negotiated speed shown here. Do not force 1 Gbps in the driver: the physical link "
                    "cannot negotiate it."
                ),
                cannot_verify="Cable condition and router port capability can only be confirmed physically.",
                category="local-link",
            )
        )
    return out


def rule_wifi(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    out: list[Diagnosis] = []
    wifi = report.wifi
    adapter = report.active_adapter
    if wifi is None or not wifi.available:
        return out
    if adapter is not None and not adapter.is_wireless:
        out.append(
            Diagnosis(
                rule_id="WIFI-000",
                finding="Ethernet is the active connection",
                evidence=[f"Active adapter: {adapter.name} ({adapter.media_type})"],
                confidence=Confidence.HIGH,
                severity=Severity.INFO,
                meaning="A Wi-Fi interface is present but the current traffic does not use it.",
                recommendation="No action needed. Wi-Fi measurements below describe the radio, not the active path.",
                cannot_verify="Whether Wi-Fi quality differs at another location in the building.",
                category="wifi",
            )
        )

    signal = wifi.signal_percent
    if signal is not None and signal < th["wifi_signal_warn_percent"]:
        severity = Severity.CRITICAL if signal < th["wifi_signal_critical_percent"] else Severity.WARNING
        evidence = [
            f"SSID: {wifi.ssid or 'unknown'}",
            f"Signal: {signal}%",
            f"Radio: {wifi.radio_type or 'unknown'}, band {wifi.band or 'unknown'}, channel {wifi.channel or 'unknown'}",
        ]
        if wifi.receive_rate_mbps is not None:
            evidence.append(f"Wi-Fi receive rate: {wifi.receive_rate_mbps:g} Mbps (link rate, not internet speed)")
        out.append(
            Diagnosis(
                rule_id="WIFI-001",
                finding=f"Weak Wi-Fi signal ({signal}%)",
                evidence=evidence,
                confidence=Confidence.HIGH,
                severity=severity,
                meaning=(
                    "A weak radio link causes latency spikes, jitter and packet loss even when the "
                    "internet itself is healthy. Wi-Fi link rate is a radio negotiation figure and says "
                    "nothing about your internet bandwidth."
                ),
                recommendation=(
                    "Move closer to the access point, remove metal/obstructions, and test with an "
                    "Ethernet cable to isolate Wi-Fi from the WAN. Only change the router's channel "
                    "after measuring your own environment."
                ),
                cannot_verify=(
                    "NetPulse cannot measure interference or neighbour congestion from a single adapter; "
                    "those require a spectrum/Wi-Fi survey."
                ),
                category="wifi",
            )
        )
    return out


def rule_gateway(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    out: list[Diagnosis] = []
    gateway = report.gateway_ping
    if gateway is None:
        return out

    stats = gateway.stats
    if stats.received == 0:
        out.append(
            Diagnosis(
                rule_id="GW-001",
                finding="The local gateway did not answer ICMP",
                evidence=[
                    f"Target: {gateway.target}",
                    f"Probes sent: {stats.sent}, replies: {stats.received}",
                    gateway.message or "No reply received",
                ],
                confidence=Confidence.LOW,
                severity=Severity.INFO,
                meaning=(
                    "Many routers rate-limit or completely block ICMP echo. A silent gateway is "
                    "therefore not proof of a router failure."
                ),
                recommendation=(
                    "Treat the internet and TCP results as more meaningful here. If your connection also "
                    "fails in browsers, restart the router once and re-test."
                ),
                cannot_verify="NetPulse cannot distinguish ICMP filtering from a routing failure without router logs.",
                category="gateway",
            )
        )
        return out

    if stats.loss_percent >= th["gateway_loss_warn_percent"]:
        severity = (
            Severity.CRITICAL
            if stats.loss_percent >= th["gateway_loss_critical_percent"]
            else Severity.WARNING
        )
        evidence = [
            f"Target: {gateway.target}",
            f"Packet loss: {stats.loss_percent:.2f}% ({stats.lost} of {stats.sent} probes lost)",
            f"Average RTT: {_fmt_ms(stats.mean_ms)}",
        ]
        if report.wifi is not None and report.wifi.available and report.active_adapter and report.active_adapter.is_wireless:
            evidence.append("The active path is Wi-Fi, so the radio link is a likely contributor.")
        out.append(
            Diagnosis(
                rule_id="GW-002",
                finding="Packet loss between this PC and the local router",
                evidence=evidence,
                confidence=Confidence.HIGH,
                severity=severity,
                meaning=(
                    "Loss already exists inside the local network, so the fault is most likely between "
                    "the PC and the router (Wi-Fi, cable, port) or in the router itself. Anything beyond "
                    "the router will inherit this loss."
                ),
                recommendation=(
                    "Repeat the test on Ethernet if you are on Wi-Fi, replace or reseat the cable, try a "
                    "different router port, and only then reboot the router."
                ),
                cannot_verify="Router CPU load, firmware behaviour and cable/connector damage cannot be measured from software.",
                category="gateway",
            )
        )

    if stats.mean_ms is not None and stats.mean_ms >= th["gateway_latency_warn_ms"]:
        severity = (
            Severity.CRITICAL
            if stats.mean_ms >= th["gateway_latency_critical_ms"]
            else Severity.WARNING
        )
        out.append(
            Diagnosis(
                rule_id="GW-003",
                finding=f"High latency to the local router ({stats.mean_ms:.1f} ms average)",
                evidence=[
                    f"Target: {gateway.target}",
                    f"Average: {_fmt_ms(stats.mean_ms)}, median: {_fmt_ms(stats.median_ms)}, max: {_fmt_ms(stats.max_ms)}",
                    f"Jitter: {_fmt_ms(stats.jitter_ms)}",
                ],
                confidence=Confidence.MEDIUM,
                severity=severity,
                meaning=(
                    "A round trip to your own router should normally stay in the low single-digit "
                    "milliseconds. Higher values point at the local link or a busy router."
                ),
                recommendation=(
                    "Compare Ethernet and Wi-Fi, close heavy local transfers, and check the router's "
                    "uplink status. Unstable gateway latency will make every online service feel worse."
                ),
                cannot_verify="NetPulse cannot see router CPU utilisation, buffer state or Wi-Fi interference patterns.",
                category="gateway",
            )
        )
    return out


def rule_internet(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    out: list[Diagnosis] = []
    pings = report.internet_pings
    if not pings:
        return out
    aggregate = aggregate_internet(pings)
    gateway = report.gateway_ping
    gateway_ok = bool(gateway and gateway.stats.received > 0 and gateway.stats.loss_percent < th["gateway_loss_warn_percent"])
    tcp_ok = any(p.connected for p in report.tcp_probes)

    evidence_common = [
        f"{ping.target}: avg {_fmt_ms(ping.stats.mean_ms)}, loss {ping.stats.loss_percent:.2f}%, "
        f"jitter {_fmt_ms(ping.stats.jitter_ms)}"
        for ping in pings
    ]

    if aggregate.answered_targets == 0:
        if tcp_ok:
            out.append(
                Diagnosis(
                    rule_id="WAN-001",
                    finding="ICMP replies are blocked, but TCP connections still work",
                    evidence=evidence_common
                    + [
                        f"TCP handshake succeeded to {p.host}:{p.port} ({p.connect_ms:.0f} ms)"
                        if p.connect_ms else ""
                        for p in report.tcp_probes if p.connected
                    ],
                    confidence=Confidence.HIGH,
                    severity=Severity.INFO,
                    meaning=(
                        "Public ICMP echo is filtered somewhere on the path. Your internet is reachable, "
                        "so latency and loss numbers based on ICMP are not reliable here."
                    ),
                    recommendation="Use the TCP and DNS results in this report and repeat the diagnosis at another time.",
                    cannot_verify=(
                        "Which device filters ICMP, and the real latency of your applications, "
                        "which is destination specific."
                    ),
                    category="wan",
                )
            )
        elif gateway_ok:
            out.append(
                Diagnosis(
                    rule_id="WAN-002",
                    finding="No reply from any public target while the local router answers",
                    evidence=evidence_common,
                    confidence=Confidence.MEDIUM,
                    severity=Severity.CRITICAL,
                    meaning=(
                        "The local network is healthy but nothing beyond the router responds. This points "
                        "at the ISP access link, the router's WAN interface, or upstream routing."
                    ),
                    recommendation=(
                        "Check the router's WAN/status LEDs and its connection log, restart the router once, "
                        "and contact your ISP with this report if the problem persists."
                    ),
                    cannot_verify="NetPulse cannot read the router's WAN log or the ISP's line statistics.",
                    category="wan",
                )
            )
        else:
            out.append(
                Diagnosis(
                    rule_id="WAN-003",
                    finding="No ICMP reply from the router or any public target",
                    evidence=evidence_common + ["The default gateway also did not answer ICMP."],
                    confidence=Confidence.LOW,
                    severity=Severity.CRITICAL,
                    meaning=(
                        "Either the whole path is down or ICMP is blocked at multiple points. Both are "
                        "possible, so this result cannot be treated as definitive."
                    ),
                    recommendation="Verify with a browser or the TCP checks, then re-run the diagnosis twice to confirm.",
                    cannot_verify="Whether the outage is local, caused by the router or caused by the ISP.",
                    category="wan",
                )
            )
        return out

    if aggregate.worst_loss_percent >= th["loss_warn_percent"]:
        severity = (
            Severity.CRITICAL
            if aggregate.worst_loss_percent >= th["loss_critical_percent"]
            else Severity.WARNING
        )
        multiple = aggregate.lossy_targets > 1
        out.append(
            Diagnosis(
                rule_id="WAN-004" if multiple else "WAN-005",
                finding=(
                    "Packet loss towards several public targets"
                    if multiple
                    else "Packet loss towards a single public target"
                ),
                evidence=evidence_common
                + [f"Worst observed loss: {aggregate.worst_loss_percent:.2f}%"],
                confidence=Confidence.MEDIUM if multiple else Confidence.LOW,
                severity=severity,
                meaning=(
                    "Loss towards several destinations suggests upstream instability or congestion. "
                    "Loss towards one destination only can equally be caused by that destination's own "
                    "network or by ICMP rate limiting."
                    if not multiple
                    else "Loss towards several destinations suggests the problem is upstream "
                    "of your router rather than in one website."
                ),
                recommendation=(
                    "Repeat the diagnosis at different times of day, confirm with the TCP checks, and "
                    "include this report when contacting your ISP."
                ),
                cannot_verify=(
                        "NetPulse cannot attribute loss to a specific hop or to ISP congestion "
                        "from end-to-end measurements alone."
                    ),
                category="wan",
            )
        )

    if aggregate.mean_latency_ms is not None and aggregate.mean_latency_ms >= th["latency_warn_ms"]:
        severity = (
            Severity.CRITICAL
            if aggregate.mean_latency_ms >= th["latency_critical_ms"]
            else Severity.WARNING
        )
        if gateway_ok:
            finding = f"High internet latency ({aggregate.mean_latency_ms:.1f} ms average) with a healthy local link"
            meaning = (
                "The PC-to-router path is healthy, so the extra delay is introduced beyond the router: "
                "the ISP access link, upstream routing, congestion or the destination itself."
            )
        else:
            finding = f"High internet latency ({aggregate.mean_latency_ms:.1f} ms average)"
            meaning = (
                "High latency is present, and the local link could not be confirmed as clean, so part of "
                "the delay may already exist inside your own network."
            )
        out.append(
            Diagnosis(
                rule_id="WAN-006",
                finding=finding,
                evidence=evidence_common
                + (
                    [f"Gateway average: {_fmt_ms(gateway.stats.mean_ms)}" if gateway else ""]
                ),
                confidence=Confidence.MEDIUM,
                severity=severity,
                meaning=meaning,
                recommendation=(
                    "Note the time of day for a pattern, test over Ethernet if you are on Wi-Fi, and send "
                    "this report to your ISP if the delay is consistent."
                ),
                cannot_verify=(
                    "NetPulse cannot prove which hop adds the delay, and one public target's ICMP latency "
                    "is not the same as the latency your game or application will see."
                ),
                category="wan",
            )
        )

    if aggregate.worst_jitter_ms is not None and aggregate.worst_jitter_ms >= th["jitter_warn_ms"]:
        severity = (
            Severity.CRITICAL if aggregate.worst_jitter_ms >= th["jitter_critical_ms"] else Severity.WARNING
        )
        out.append(
            Diagnosis(
                rule_id="WAN-007",
                finding=f"Unstable latency (jitter {aggregate.worst_jitter_ms:.1f} ms)",
                evidence=evidence_common
                + [f"Worst jitter: {aggregate.worst_jitter_ms:.1f} ms (mean absolute difference between consecutive replies)"],
                confidence=Confidence.MEDIUM,
                severity=severity,
                meaning=(
                    "Jitter makes voice, video and gaming feel bad even when average ping looks acceptable. "
                    "It is typical of congested or wireless links."
                ),
                recommendation=(
                    "Check whether the jitter appears while someone else is downloading, prefer Ethernet "
                    "over Wi-Fi, and enable QoS for real-time traffic on the router if available."
                ),
                cannot_verify="NetPulse cannot see buffer bloat inside the router or the ISP's traffic shaping policy.",
                category="wan",
            )
        )
    return out


def rule_dns(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    out: list[Diagnosis] = []
    dns = report.dns
    if dns is None or not dns.queries:
        return out

    configured = [q for q in dns.queries if not q.is_public_resolver]
    failures = [q for q in configured if not q.ok]
    aggregate = aggregate_internet(report.internet_pings)
    latency_ok = aggregate.mean_latency_ms is None or aggregate.mean_latency_ms < th["latency_warn_ms"]
    dns_detail = (
        "DNS only affects the time needed to turn a name into an IP address; it does not change the "
        "ping to a server that has already been resolved."
    )

    if failures and len(failures) == len(configured):
        out.append(
            Diagnosis(
                rule_id="DNS-001",
                finding="DNS lookups failed on every configured resolver",
                evidence=[f"{q.hostname} via {q.server}: {q.error or 'failed'}" for q in configured[:6]],
                confidence=Confidence.MEDIUM,
                severity=Severity.CRITICAL,
                meaning="Name resolution is broken, so websites will not open even if raw IP connectivity exists.",
                recommendation=(
                    "Verify the DNS servers configured on the adapter, test a known public resolver for "
                    "comparison, and check the router's DNS forwarding settings."
                ),
                cannot_verify="Whether the resolver itself is overloaded or the router forwards queries incorrectly.",
                category="dns",
            )
        )
        return out

    if dns.average_ms is not None and dns.average_ms >= th["dns_warn_ms"] and latency_ok:
        severity = Severity.CRITICAL if dns.average_ms >= th["dns_critical_ms"] else Severity.WARNING
        out.append(
            Diagnosis(
                rule_id="DNS-002",
                finding=f"DNS resolution is slow ({dns.average_ms:.0f} ms average) while IP latency is stable",
                evidence=[
                    f"Average DNS lookup: {dns.average_ms:.0f} ms over {len(configured)} configured queries",
                    f"Slowest lookup: {dns.slowest.hostname} via {dns.slowest.server} at {_fmt_ms(dns.slowest.duration_ms)}"
                    if dns.slowest
                    else "Slowest lookup: unavailable",
                    f"Internet latency average: {_fmt_ms(aggregate.mean_latency_ms)}",
                    dns_detail,
                ],
                confidence=Confidence.MEDIUM,
                severity=severity,
                meaning=(
                    "Page loads and new connections feel slow, but latency to already-known IP addresses is "
                    "fine. This is a resolver performance symptom, not a bandwidth problem."
                ),
                recommendation=(
                    "Optionally test a public resolver for comparison. Changing DNS never lowers the ping to "
                    "a game server you are already connected to."
                ),
                cannot_verify="Resolver caching, upstream forwarding latency and any ISP-side DNS tampering.",
                category="dns",
            )
        )

    if dns.public_comparison_enabled:
        public = [q for q in dns.queries if q.is_public_resolver and q.ok and q.duration_ms is not None]
        if public and dns.average_ms:
            public_avg = sum(float(q.duration_ms or 0) for q in public) / len(public)
            if public_avg * 2 < dns.average_ms:
                out.append(
                    Diagnosis(
                        rule_id="DNS-003",
                        finding="Public resolvers answered much faster than the configured DNS servers",
                        evidence=[
                            f"Configured resolvers average: {dns.average_ms:.0f} ms",
                            f"Public resolvers average: {public_avg:.0f} ms",
                        ],
                        confidence=Confidence.MEDIUM,
                        severity=Severity.INFO,
                        meaning="Your configured resolver is measurably slower than the public resolvers tested.",
                        recommendation=(
                            "Changing DNS is optional and reversible. It can speed up name resolution, but it "
                            "does not improve ping to a server that is already resolved."
                        ),
                        cannot_verify="Whether the difference remains stable over time or under load.",
                        category="dns",
                    )
                )
    return out


def rule_route(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    out: list[Diagnosis] = []
    route = report.route
    if route is None:
        return out
    if route.status == TestStatus.UNSUPPORTED:
        out.append(
            Diagnosis(
                rule_id="RTE-000",
                finding="Route tracing is not available on this system",
                evidence=[route.message or "tracert could not be executed."],
                confidence=Confidence.HIGH,
                severity=Severity.INFO,
                meaning="Hops beyond the router cannot be inspected here.",
                recommendation="No action needed; the remaining measurements are still valid.",
                cannot_verify="Upstream routing behaviour.",
                category="route",
            )
        )
        return out
    if route.missing_hop_count:
        out.append(
            Diagnosis(
                rule_id="RTE-001",
                finding=f"{route.missing_hop_count} hop(s) did not return an ICMP reply",
                evidence=[
                    f"{len(route.hops)} hop(s) traced to {route.target}",
                    f"Hops with no reply: {', '.join(str(h.hop) for h in route.hops if h.timed_out) or 'none'}",
                ],
                confidence=Confidence.HIGH,
                severity=Severity.INFO,
                meaning=(
                    "Routers frequently deprioritise or block TTL-expired ICMP. A * hop therefore does not "
                    "prove packet loss for normal traffic; the trace simply became unknown there."
                ),
                recommendation=(
                    "Judge loss from the end-to-end latency tests rather than from single * hops. "
                    "Do not report a * hop as an ISP fault on its own."
                ),
                cannot_verify="Whether that router drops real traffic or just ICMP responses.",
                category="route",
            )
        )
    return out


def rule_isp_context(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    """Add fixed-wireless / upstream context when latency beyond the router is poor."""
    aggregate = aggregate_internet(report.internet_pings)
    if aggregate.answered_targets == 0:
        return []
    degraded = (aggregate.mean_latency_ms or 0) >= th["latency_warn_ms"] or (
        (aggregate.worst_jitter_ms or 0) >= th["jitter_warn_ms"]
    )
    if not degraded:
        return []
    return [
        Diagnosis(
            rule_id="ISP-001",
            finding="Symptoms are consistent with a problem beyond your router",
            evidence=[
                f"Internet average latency: {_fmt_ms(aggregate.mean_latency_ms)}",
                f"Worst jitter: {_fmt_ms(aggregate.worst_jitter_ms)}",
                f"Worst packet loss: {aggregate.worst_loss_percent:.2f}%",
                "Your local gateway measurements are reported separately above.",
            ],
            confidence=Confidence.LOW,
            severity=Severity.INFO,
            meaning=(
                "On fixed wireless, mobile (4G/5G) or some fibre/cable services, rain, wind, antenna "
                "alignment, line-of-sight obstruction, radio interference and sector congestion can all "
                "affect latency and loss. The same symptoms can also be caused by local Wi-Fi congestion."
            ),
            recommendation=(
                "Compare an Ethernet test at a different time of day, then ask your ISP for the radio-link "
                "metrics (signal quality, sector load, SNR). NetPulse cannot see those values."
            ),
            cannot_verify=(
                "NetPulse cannot confirm weather, radio-link quality, upstream congestion or ISP equipment "
                "state from ping data alone, and it makes no such claim."
            ),
            category="isp",
        )
    ]


def rule_tcp(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    out: list[Diagnosis] = []
    probes = report.tcp_probes
    if not probes:
        return out
    reachable = [p for p in probes if p.connected]
    if not reachable:
        out.append(
            Diagnosis(
                rule_id="TCP-001",
                finding="No TCP connection to the public endpoints could be established",
                evidence=[f"{p.host}:{p.port} -> {p.error or 'failed'}" for p in probes],
                confidence=Confidence.MEDIUM,
                severity=Severity.CRITICAL,
                meaning=(
                    "Real TCP traffic to well known public services is failing, which is a stronger signal "
                    "than missing ICMP replies."
                ),
                recommendation=(
                    "Check the router WAN status, retry in a few minutes, and contact your ISP with this "
                    "report if the failure persists."
                ),
                cannot_verify="Whether a local firewall or security product is blocking outbound traffic.",
                category="wan",
            )
        )
    return out


def rule_test_health(report: DiagnosticReport, th: dict[str, float]) -> list[Diagnosis]:
    """Report tests that could not run so nothing is silently hidden."""
    out: list[Diagnosis] = []
    problems: list[str] = []
    if report.gateway_ping is not None and report.gateway_ping.status == TestStatus.ERROR:
        problems.append(f"Gateway test: {report.gateway_ping.message}")
    for ping in report.internet_pings:
        if ping.status in (TestStatus.ERROR, TestStatus.UNSUPPORTED):
            problems.append(f"{ping.target}: {ping.message}")
    if report.dns is not None and report.dns.status in (TestStatus.ERROR, TestStatus.UNSUPPORTED):
        problems.append(f"DNS test: {report.dns.message}")
    if report.route is not None and report.route.status == TestStatus.ERROR:
        problems.append(f"Route trace: {report.route.message}")
    if problems:
        out.append(
            Diagnosis(
                rule_id="SYS-001",
                finding="Some tests could not be completed",
                evidence=problems[:8],
                confidence=Confidence.HIGH,
                severity=Severity.INFO,
                meaning="Missing results are reported explicitly instead of being presented as good news.",
                recommendation="Check the message above, then re-run the diagnosis.",
                cannot_verify="Whether the cause is a missing Windows tool, a firewall or a permissions issue.",
                category="system",
            )
        )
    return out


def rule_overall(report: DiagnosticReport, th: dict[str, float], existing: list[Diagnosis]) -> list[Diagnosis]:
    if report.cancelled:
        return [
            Diagnosis(
                rule_id="SYS-002",
                finding="The diagnosis was stopped before it finished",
                evidence=["The user cancelled the run, so results are partial."],
                confidence=Confidence.HIGH,
                severity=Severity.INFO,
                meaning="Conclusions below are based on partial measurements only.",
                recommendation="Run a complete diagnosis to get a reliable overall picture.",
                cannot_verify="Anything that was not measured.",
                category="system",
            )
        ]
    if existing:
        return []
    aggregate = aggregate_internet(report.internet_pings)
    evidence = [
        f"Gateway average: {_fmt_ms(report.gateway_ping.stats.mean_ms) if report.gateway_ping else 'unavailable'}",
        f"Internet average: {_fmt_ms(aggregate.mean_latency_ms)}",
        f"Worst loss: {aggregate.worst_loss_percent:.2f}%",
    ]
    return [
        Diagnosis(
            rule_id="OK-001",
            finding="No problems were detected in this run",
            evidence=evidence,
            confidence=Confidence.MEDIUM,
            severity=Severity.GOOD,
            meaning="Latency, jitter, packet loss and DNS all stayed within normal ranges during the test window.",
            recommendation=(
                "If a specific application still feels slow, note the exact time it happens and run the "
                "diagnosis again; intermittent problems need several samples."
            ),
            cannot_verify=(
                "A single short test cannot rule out problems that occur at other times of day, and one "
                "public target's latency is not the latency every application will see."
            ),
            category="general",
        )
    ]


RULES = (
    rule_local_link,
    rule_wifi,
    rule_gateway,
    rule_internet,
    rule_tcp,
    rule_dns,
    rule_route,
    rule_isp_context,
    rule_test_health,
)


def evaluate(report: DiagnosticReport, thresholds: dict[str, float] | None = None) -> DiagnosisSummary:
    """Run every rule and derive the overall status plus a headline."""
    th = _thresholds(thresholds)
    diagnoses: list[Diagnosis] = []
    for rule in RULES:
        try:
            diagnoses.extend(rule(report, th))
        except Exception as exc:  # pragma: no cover - a rule must never break the run
            diagnoses.append(
                Diagnosis(
                    rule_id="SYS-999",
                    finding=f"Rule {rule.__name__} failed",
                    evidence=[f"{type(exc).__name__}: {exc}"],
                    confidence=Confidence.LOW,
                    severity=Severity.INFO,
                    meaning="An internal analysis rule could not complete.",
                    recommendation="Re-run the diagnosis; if it repeats, report the issue.",
                    cannot_verify="The finding that this rule would have produced.",
                    category="system",
                )
            )
    diagnoses.extend(rule_overall(report, th, diagnoses))

    overall = Severity.UNKNOWN
    for diagnosis in diagnoses:
        if _SEVERITY_ORDER[diagnosis.severity] > _SEVERITY_ORDER[overall]:
            overall = diagnosis.severity

    headline = _headline(overall, diagnoses)
    summary = DiagnosisSummary(overall_status=overall, headline=headline, diagnoses=diagnoses)
    return summary


def _headline(overall: Severity, diagnoses: list[Diagnosis]) -> str:
    if overall == Severity.UNKNOWN:
        return "Not enough data to judge the connection."
    priority = {
        Severity.CRITICAL: "Critical problem detected: ",
        Severity.WARNING: "Attention recommended: ",
        Severity.INFO: "Information: ",
        Severity.GOOD: "Connection looks healthy: ",
    }
    for diagnosis in diagnoses:
        if diagnosis.severity == overall:
            return priority.get(overall, "") + diagnosis.finding
    return "Connection looks healthy."


__all__ = [
    "InternetAggregate",
    "RULES",
    "aggregate_internet",
    "evaluate",
    "rule_dns",
    "rule_gateway",
    "rule_internet",
    "rule_isp_context",
    "rule_local_link",
    "rule_overall",
    "rule_route",
    "rule_tcp",
    "rule_test_health",
    "rule_wifi",
]
