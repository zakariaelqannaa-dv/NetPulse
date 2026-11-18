"""Human-readable plain-text report writer."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from app import APP_DISPLAY_NAME
from app.reporting.formatting import (
    confidence_label,
    fmt_bool,
    fmt_bytes,
    fmt_ms,
    fmt_ms_precise,
    fmt_number,
    fmt_percent,
    fmt_plain,
    fmt_timestamp,
    human_duration_ms,
    sample_series_text,
    severity_label,
    status_label,
)

WIDTH = 78

_PREAMBLE = (
    "This report contains measurements taken on this computer only. NetPulse is a\n"
    "diagnostic tool: it explains what it measured and what it cannot measure. It\n"
    "does not claim to repair ISP congestion, radio signal, cabling or router\n"
    "hardware, and no setting on this PC was changed automatically."
)


def _rule(title: str, char: str = "-") -> list[str]:
    return [title, char * min(len(title), WIDTH)]


def _kv(label: str, value: Any, indent: int = 0) -> str:
    pad = " " * indent
    return f"{pad}{label}: {value}"


def _section(title: str) -> list[str]:
    return ["", title.upper(), "-" * min(len(title), WIDTH)]


def _indent(lines: Iterable[str], indent: int = 4) -> list[str]:
    pad = " " * indent
    return [pad + line if line else line for line in lines]


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def _header(data: dict[str, Any]) -> list[str]:
    lines = [f"{APP_DISPLAY_NAME} Diagnostic Report", "=" * WIDTH]
    lines.append(_kv("Generated", fmt_timestamp(data.get("finished_at") or data.get("started_at"))))
    lines.append(_kv("Started", fmt_timestamp(data.get("started_at"))))
    lines.append(_kv("Duration", human_duration_ms(data.get("duration_ms"))))
    lines.append(_kv("NetPulse version", fmt_plain(data.get("app_version"))))
    lines.append(_kv("Report format", "plain text"))
    if data.get("cancelled"):
        lines.append(
            "NOTE: the diagnosis was stopped early, so the results are partial."
        )
    redacted = data.get("redacted_fields") or []
    if redacted:
        lines.append(_kv("Redacted fields", ", ".join(str(r) for r in redacted)))
    lines += [""] + _rule("IMPORTANT") + _wrap(_PREAMBLE)
    return lines


def _summary(data: dict[str, Any]) -> list[str]:
    lines = _section("Summary")
    lines.append(_kv("Overall status", severity_label(data.get("overall_status"))))
    lines.append(_kv("Headline", fmt_plain(data.get("headline"))))
    diagnoses = data.get("diagnoses") or []
    lines.append(_kv("Findings", len(diagnoses)))
    return lines


def _host(data: dict[str, Any]) -> list[str]:
    host = data.get("host") or {}
    lines = _section("Host")
    lines.append(_kv("Computer name", fmt_plain(host.get("computer_name"))))
    lines.append(_kv("Operating system", fmt_plain(host.get("os_name"))))
    lines.append(_kv("Windows version", fmt_plain(host.get("os_version"))))
    lines.append(_kv("Windows build", fmt_plain(host.get("os_build"))))
    lines.append(_kv("Architecture", fmt_plain(host.get("architecture"))))
    lines.append(_kv("Python", fmt_plain(host.get("python_version"))))
    lines.append(_kv("Running as administrator", fmt_bool(host.get("is_admin"))))
    return lines


def _adapter_block(adapter: dict[str, Any], index: int, active: bool) -> list[str]:
    marker = " (active)" if active else ""
    lines = [f"[{index}] {fmt_plain(adapter.get('name'))}{marker}"]
    body = [
        _kv("Description", fmt_plain(adapter.get("description"))),
        _kv("Media type", fmt_plain(adapter.get("media_type"))),
        _kv("Status", fmt_plain(adapter.get("status"))),
        _kv("Link speed", fmt_plain(adapter.get("link_speed_text") or adapter.get("link_speed_mbps"))),
        _kv("MAC address", fmt_plain(adapter.get("mac_address"))),
        _kv("IPv4", ", ".join(adapter.get("ipv4") or []) or "unavailable"),
        _kv("IPv6", ", ".join(adapter.get("ipv6") or []) or "unavailable"),
        _kv("Default gateway", fmt_plain(adapter.get("gateway"))),
        _kv("DNS servers", ", ".join(adapter.get("dns_servers") or []) or "unavailable"),
        _kv("DHCP enabled", fmt_bool(adapter.get("dhcp_enabled"))),
        _kv("Interface index", fmt_plain(adapter.get("if_index"))),
        _kv("MTU", fmt_plain(adapter.get("mtu"))),
        _kv("Wireless", fmt_bool(adapter.get("is_wireless"))),
    ]
    lines += _indent(body)
    return lines


def _adapters(data: dict[str, Any]) -> list[str]:
    adapters = data.get("adapters") or []
    lines = _section(f"Network adapters ({len(adapters)})")
    if not adapters:
        lines.append("  No network adapter with an active link was detected.")
        return lines
    active_name = data.get("active_adapter_name")
    active = data.get("active_adapter") or {}
    for index, adapter in enumerate(adapters, start=1):
        is_active = bool(active_name and adapter.get("name") == active_name) or (
            bool(active) and adapter.get("mac_address") == active.get("mac_address")
        )
        lines += _adapter_block(adapter, index, is_active)
    return lines


def _latency_block(title: str, ping: dict[str, Any]) -> list[str]:
    stats = ping.get("stats") or {}
    lines = _section(title)
    lines.append(_kv("Target", fmt_plain(ping.get("target"))))
    lines.append(_kv("Resolved address", fmt_plain(ping.get("resolved_ip"))))
    lines.append(_kv("Status", status_label(ping.get("status"))))
    if ping.get("message"):
        lines.append(_kv("Message", fmt_plain(ping.get("message"))))
    lines.append(_kv("Duration", human_duration_ms(ping.get("duration_ms"))))
    lines.append("")
    lines.append("  Statistics")
    lines += _indent(
        [
            _kv("Probes", f"{stats.get('sent', 0)} sent, {stats.get('received', 0)} received"),
            _kv("Packet loss", fmt_percent(stats.get("loss_percent"))),
            _kv("Minimum RTT", fmt_ms_precise(stats.get("min_ms"))),
            _kv("Average RTT", fmt_ms_precise(stats.get("mean_ms"))),
            _kv("Median RTT", fmt_ms_precise(stats.get("median_ms"))),
            _kv("Maximum RTT", fmt_ms_precise(stats.get("max_ms"))),
            _kv("Standard deviation", fmt_ms_precise(stats.get("stdev_ms"))),
            _kv("Jitter", fmt_ms_precise(stats.get("jitter_ms"))
                + " (mean absolute difference between consecutive replies)"),
        ]
    )
    if ping.get("icmp_may_be_blocked"):
        lines.append("")
        lines.append("  NOTE: ICMP echo may be filtered somewhere on this path, so the")
        lines.append("        numbers above may understate the real latency or loss.")
    samples = ping.get("samples") or []
    if samples:
        lines.append("")
        lines.append("  Per-probe RTT")
        lines += _wrap(sample_series_text(samples), indent=4)
    return lines


def _gateway(data: dict[str, Any]) -> list[str]:
    ping = data.get("gateway_ping")
    if not ping:
        return _section("Local gateway") + ["  Not measured."]
    return _latency_block("Local gateway (PC to router)", ping)


def _internet(data: dict[str, Any]) -> list[str]:
    pings = data.get("internet_pings") or []
    if not pings:
        return _section("Internet latency targets") + ["  Not measured."]
    lines: list[str] = []
    for ping in pings:
        lines += _latency_block(f"Internet target {ping.get('target')}", ping)
    return lines


def _tcp(data: dict[str, Any]) -> list[str]:
    probes = data.get("tcp_probes") or []
    if not probes:
        return []
    lines = _section("TCP connectivity (independent of ICMP)")
    for probe in probes:
        state = "connected" if probe.get("connected") else "failed"
        detail = (
            fmt_ms(probe.get("connect_ms")) if probe.get("connected") else fmt_plain(probe.get("error"))
        )
        lines.append(f"  {probe.get('host')}:{probe.get('port')} -> {state} ({detail})")
    lines.append("")
    lines.append(
        "  A successful TCP handshake proves the destination is reachable even when"
    )
    lines.append("  ICMP echo is blocked. A failure can still be caused by a firewall.")
    return lines


def _dns(data: dict[str, Any]) -> list[str]:
    dns = data.get("dns")
    if not dns:
        return _section("DNS resolution") + ["  Not measured."]
    lines = _section("DNS resolution")
    lines.append(_kv("Status", status_label(dns.get("status"))))
    if dns.get("message"):
        lines.append(_kv("Message", fmt_plain(dns.get("message"))))
    lines.append(_kv("Configured resolvers", ", ".join(dns.get("configured_servers") or []) or "unavailable"))
    lines.append(_kv("Average lookup", fmt_ms(dns.get("average_ms"))))
    lines.append(_kv("Public comparison enabled", fmt_bool(dns.get("public_comparison_enabled"))))
    lines.append("")
    queries = dns.get("queries") or []
    if not queries:
        lines.append("  No DNS query was performed.")
        return lines
    lines.append("  Queries")
    for query in queries:
        kind = "public resolver" if query.get("is_public_resolver") else "configured"
        if query.get("ok"):
            outcome = f"{fmt_ms(query.get('duration_ms'))} -> {', '.join(query.get('addresses') or [])}"
        else:
            outcome = f"FAILED: {fmt_plain(query.get('error'))}"
        lines.append(f"    {query.get('hostname')} via {query.get('server')} ({kind}): {outcome}")
    return lines


def _route(data: dict[str, Any]) -> list[str]:
    route = data.get("route")
    if not route:
        return []
    lines = _section("Route trace")
    lines.append(_kv("Target", fmt_plain(route.get("target"))))
    lines.append(_kv("Status", status_label(route.get("status"))))
    if route.get("message"):
        lines.append(_kv("Message", fmt_plain(route.get("message"))))
    lines.append(_kv("Reached target", fmt_bool(route.get("completed"))))
    lines.append(_kv("Hops with no reply", fmt_plain(route.get("missing_hop_count"))))
    hops = route.get("hops") or []
    if hops:
        lines.append("")
        lines.append("  Hop   Address                RTT1     RTT2     RTT3")
        for hop in hops:
            rtts = list(hop.get("rtts") or []) + [None, None, None]
            cells = "  ".join(
                ("*".ljust(7) if rtts[i] is None else f"{float(rtts[i]):.1f}".ljust(7)) for i in range(3)
            )
            address = (hop.get("address") or "*").ljust(22)
            lines.append(f"  {str(hop.get('hop')).ljust(5)} {address} {cells}".rstrip())
        lines.append("")
        lines.append("  A '*' hop means that router did not return a TTL-expired ICMP reply.")
        lines.append("  It is not proof of packet loss for normal traffic.")
    return lines


def _wifi(data: dict[str, Any]) -> list[str]:
    wifi = data.get("wifi")
    if not wifi:
        return []
    lines = _section("Wi-Fi")
    if not wifi.get("available"):
        lines.append("  " + (fmt_plain(wifi.get("message")) or "No wireless interface was found."))
        return lines
    lines.append(_kv("SSID", fmt_plain(wifi.get("ssid"))))
    lines.append(_kv("BSSID", fmt_plain(wifi.get("bssid"))))
    lines.append(_kv("State", fmt_plain(wifi.get("state"))))
    signal = wifi.get("signal_percent")
    lines.append(_kv("Signal", "unavailable" if signal is None else f"{signal}%"))
    lines.append(_kv("Radio type", fmt_plain(wifi.get("radio_type"))))
    lines.append(_kv("Band", fmt_plain(wifi.get("band"))))
    lines.append(_kv("Channel", fmt_plain(wifi.get("channel"))))
    lines.append(_kv("Receive link rate", fmt_plain(wifi.get("receive_rate_mbps"))))
    lines.append(_kv("Transmit link rate", fmt_plain(wifi.get("transmit_rate_mbps"))))
    lines.append("")
    lines.append("  Wi-Fi link rates are radio negotiation figures, not internet bandwidth.")
    return lines


def _speed(data: dict[str, Any]) -> list[str]:
    speed = data.get("speed_test")
    if not speed:
        return []
    lines = _section("Optional download speed test")
    lines.append(_kv("Status", "completed" if speed.get("ok") else "not completed"))
    lines.append(_kv("URL", fmt_plain(speed.get("url"))))
    lines.append(_kv("Downloaded", fmt_bytes(speed.get("bytes_downloaded"))))
    lines.append(_kv("Duration", fmt_number(speed.get("duration_s"), 2) + " s"))
    speed_mbps = speed.get("megabits_per_second")
    lines.append(_kv("Throughput", "unavailable" if speed_mbps is None else f"{float(speed_mbps):.2f} Mbit/s"))
    lines.append(_kv("Stopped early", fmt_bool(speed.get("stopped_early"))))
    if speed.get("error"):
        lines.append(_kv("Error", fmt_plain(speed.get("error"))))
    if speed.get("privacy_note"):
        lines.append("")
        lines += _wrap(str(speed.get("privacy_note")), indent=2)
    return lines


def _changes(data: dict[str, Any]) -> list[str]:
    changes = data.get("applied_changes") or []
    if not changes:
        return []
    lines = _section("Configuration changes recorded by NetPulse")
    for change in changes:
        lines.append(f"  {fmt_plain(change.get('title'))} [{fmt_plain(change.get('action_id'))}]")
        body = [
            _kv("Target", fmt_plain(change.get("target"))),
            _kv("Applied", fmt_bool(change.get("applied"))),
            _kv("Requires administrator", fmt_bool(change.get("requires_admin"))),
            _kv("Before", fmt_plain(change.get("before"))),
            _kv("After", fmt_plain(change.get("after"))),
            _kv("When", fmt_plain(change.get("timestamp"))),
        ]
        if change.get("command"):
            body.append(_kv("Command", fmt_plain(change.get("command"))))
        if change.get("note"):
            body.append(_kv("Note", fmt_plain(change.get("note"))))
        if change.get("error"):
            body.append(_kv("Error", fmt_plain(change.get("error"))))
        lines += _indent(body, 6)
        lines.append("")
    return lines


def _diagnoses(data: dict[str, Any]) -> list[str]:
    diagnoses = data.get("diagnoses") or []
    lines = _section(f"Diagnosis ({len(diagnoses)} findings)")
    if not diagnoses:
        lines.append("  No finding was produced.")
        return lines
    for index, diagnosis in enumerate(diagnoses, start=1):
        lines.append(
            f"[{index}] {diagnosis.get('rule_id')} - {fmt_plain(diagnosis.get('finding'))}"
        )
        lines.append(
            f"    Severity: {severity_label(diagnosis.get('severity'))}    "
            f"Confidence: {confidence_label(diagnosis.get('confidence'))}    "
            f"Category: {fmt_plain(diagnosis.get('category'))}"
        )
        evidence = diagnosis.get("evidence") or []
        if evidence:
            lines.append("    Evidence:")
            for item in evidence:
                lines += _wrap(f"- {item}", indent=6)
        if diagnosis.get("meaning"):
            lines.append("    What this may mean:")
            lines += _wrap(str(diagnosis.get("meaning")), indent=6)
        if diagnosis.get("recommendation"):
            lines.append("    Recommended next action:")
            lines += _wrap(str(diagnosis.get("recommendation")), indent=6)
        if diagnosis.get("cannot_verify"):
            lines.append("    What NetPulse cannot verify:")
            lines += _wrap(str(diagnosis.get("cannot_verify")), indent=6)
        lines.append("")
    return lines


def _warnings(data: dict[str, Any]) -> list[str]:
    warnings = data.get("warnings") or []
    if not warnings:
        return []
    lines = _section("Warnings and limitations")
    for warning in warnings:
        lines += _wrap(f"- {warning}", indent=2)
    return lines


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _wrap(text: str, indent: int = 2, width: int = WIDTH) -> list[str]:
    pad = " " * indent
    out: list[str] = []
    for raw_line in str(text).splitlines() or [""]:
        remaining = raw_line.strip()
        if not remaining:
            out.append("")
            continue
        while len(remaining) > width - indent:
            cut = remaining.rfind(" ", 0, width - indent)
            if cut <= 0:
                cut = width - indent
            out.append(pad + remaining[:cut].rstrip())
            remaining = remaining[cut:].lstrip()
        out.append(pad + remaining)
    return out


# --------------------------------------------------------------------------- #

_SECTIONS = (
    _header,
    _summary,
    _host,
    _adapters,
    _gateway,
    _internet,
    _tcp,
    _dns,
    _route,
    _wifi,
    _speed,
    _changes,
    _diagnoses,
    _warnings,
)


def render_txt(report_data: dict[str, Any]) -> str:
    """Render ``report_data`` as a plain-text report."""
    lines: list[str] = []
    for section in _SECTIONS:
        lines += section(report_data)
    lines += [
        "",
        "=" * WIDTH,
        f"End of report. Generated by {APP_DISPLAY_NAME}.",
        "NetPulse is an open-source diagnostic tool and provides no guarantee of",
        "repair. Always verify findings before changing any hardware or service.",
    ]
    return "\n".join(lines) + "\n"


__all__ = ["render_txt"]
