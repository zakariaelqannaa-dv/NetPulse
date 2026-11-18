"""Well-formatted, printable HTML report writer.

The generated document is completely self-contained: all styling is inlined so
the file can be attached to an e-mail or opened offline and still print
correctly.
"""

from __future__ import annotations

from collections.abc import Iterable
from html import escape
from typing import Any

from app import APP_DISPLAY_NAME, APP_URL, APP_VERSION
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
    severity_label,
    status_label,
)

_CSS = """
:root {
  --good: #1a7f37;
  --info: #0969da;
  --warning: #9a6700;
  --critical: #cf222e;
  --unknown: #57606a;
  --border: #d0d7de;
  --muted: #57606a;
  --surface: #ffffff;
  --page: #f6f8fa;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 32px;
  background: var(--page);
  color: #1f2328;
  font-family: "Segoe UI", -apple-system, "Helvetica Neue", Arial, sans-serif;
  font-size: 14px;
  line-height: 1.5;
}
.report { max-width: 960px; margin: 0 auto; background: var(--surface);
  border: 1px solid var(--border); border-radius: 10px; padding: 32px 36px; }
h1 { font-size: 24px; margin: 0 0 4px; letter-spacing: -0.01em; }
h2 { font-size: 16px; margin: 32px 0 12px; padding-bottom: 6px;
  border-bottom: 1px solid var(--border); text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--muted); }
h3 { font-size: 14px; margin: 20px 0 8px; }
p { margin: 8px 0; }
a { color: var(--info); }
.meta { color: var(--muted); font-size: 13px; margin-bottom: 20px; }
.banner { border-left: 4px solid var(--unknown); border-radius: 6px;
  background: #f6f8fa; padding: 14px 18px; margin: 20px 0; }
.banner .status { font-size: 13px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.08em; }
.banner .headline { font-size: 17px; margin-top: 4px; }
.banner.good { border-left-color: var(--good); }
.banner.info { border-left-color: var(--info); }
.banner.warning { border-left-color: var(--warning); }
.banner.critical { border-left-color: var(--critical); }
.banner.good .status { color: var(--good); }
.banner.info .status { color: var(--info); }
.banner.warning .status { color: var(--warning); }
.banner.critical .status { color: var(--critical); }
.banner.unknown .status { color: var(--unknown); }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px; }
.card { border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px;
  background: var(--surface); }
.card.selected { border-color: #8c959f; }
.card h4 { margin: 0 0 2px; font-size: 14px; }
.card .sub { color: var(--muted); font-size: 12px; }
table { width: 100%; border-collapse: collapse; margin: 8px 0 4px; }
th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border);
  vertical-align: top; font-size: 13px; }
th { color: var(--muted); font-weight: 600; text-transform: uppercase;
  font-size: 11px; letter-spacing: 0.05em; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
dt { font-weight: 600; }
dl.kv { display: grid; grid-template-columns: 220px 1fr; gap: 4px 16px; margin: 8px 0; }
dl.kv dt { color: var(--muted); font-weight: 500; }
dl.kv dd { margin: 0; }
.pill { display: inline-block; padding: 1px 8px; border-radius: 999px;
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.05em; border: 1px solid var(--border); }
.pill.good { color: var(--good); border-color: var(--good); }
.pill.info { color: var(--info); border-color: var(--info); }
.pill.warning { color: var(--warning); border-color: var(--warning); }
.pill.critical { color: var(--critical); border-color: var(--critical); }
.pill.unknown { color: var(--unknown); }
.finding { border: 1px solid var(--border); border-left-width: 4px;
  border-radius: 8px; padding: 14px 18px; margin: 12px 0; }
.finding.good { border-left-color: var(--good); }
.finding.info { border-left-color: var(--info); }
.finding.warning { border-left-color: var(--warning); }
.finding.critical { border-left-color: var(--critical); }
.finding.unknown { border-left-color: var(--unknown); }
.finding .title { font-size: 15px; font-weight: 600; margin-bottom: 6px; }
.finding .tags { color: var(--muted); font-size: 12px; margin-bottom: 8px; }
.finding ul { margin: 6px 0; padding-left: 20px; }
.finding .label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--muted); margin-top: 10px; }
.note { background: #f6f8fa; border: 1px solid var(--border); border-radius: 6px;
  padding: 10px 14px; color: var(--muted); font-size: 13px; margin: 10px 0; }
.series { font-family: "Cascadia Mono", Consolas, "Courier New", monospace;
  font-size: 12px; color: var(--muted); word-break: break-word; }
footer { margin-top: 32px; padding-top: 16px; border-top: 1px solid var(--border);
  color: var(--muted); font-size: 12px; }
@media print {
  body { background: #fff; padding: 0; }
  .report { border: none; border-radius: 0; padding: 0; max-width: none; }
  .finding, .card { break-inside: avoid; }
}
"""


def _esc(value: Any) -> str:
    return escape(fmt_plain(value))


def _status_class(value: Any) -> str:
    text = value.value if hasattr(value, "value") else str(value)
    return text if text in {"good", "info", "warning", "critical"} else "unknown"


def _kv_list(pairs: Iterable[tuple[str, Any]]) -> str:
    rows = "".join(f"<dt>{escape(label)}</dt><dd>{_esc(value)}</dd>" for label, value in pairs)
    return f'<dl class="kv">{rows}</dl>'


def _table(headers: list[tuple[str, bool]], rows: list[list[str]]) -> str:
    head = "".join(
        f'<th class="{"num" if numeric else ""}">{escape(label)}</th>' for label, numeric in headers
    )
    body = "".join("<tr>" + "".join(cell for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _cell(value: Any, numeric: bool = False) -> str:
    return f'<td class="{"num" if numeric else ""}">{_esc(value)}</td>'


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #


def _header(data: dict[str, Any]) -> str:
    rows = [
        ("Generated", fmt_timestamp(data.get("finished_at") or data.get("started_at"))),
        ("Started", fmt_timestamp(data.get("started_at"))),
        ("Duration", human_duration_ms(data.get("duration_ms"))),
        ("NetPulse version", fmt_plain(data.get("app_version")) or APP_VERSION),
    ]
    redacted = data.get("redacted_fields") or []
    if redacted:
        rows.append(("Redacted fields", ", ".join(str(r) for r in redacted)))
    return (
        f'<h1>{escape(APP_DISPLAY_NAME)} diagnostic report</h1>'
        f'<div class="meta">Measured on this computer only. '
        f'<a href="{escape(APP_URL)}">{escape(APP_URL)}</a></div>'
        + _kv_list(rows)
    )


def _banner(data: dict[str, Any]) -> str:
    severity = _status_class(data.get("overall_status"))
    diagnosis_count = len(data.get("diagnoses") or [])
    partial = " This run was stopped early, so the results are partial." if data.get("cancelled") else ""
    return (
        f'<div class="banner {severity}">'
        f'<div class="status">{escape(severity_label(data.get("overall_status")))}</div>'
        f'<div class="headline">{_esc(data.get("headline"))}</div>'
        f'<div class="meta">{diagnosis_count} finding(s) recorded.{escape(partial)}</div>'
        "</div>"
        '<div class="note"><strong>Important:</strong> NetPulse diagnoses and explains. It does not '
        "repair ISP congestion, radio signal, damaged cabling or router hardware, and it never "
        "changes Windows network settings without your explicit confirmation.</div>"
    )


def _host_section(data: dict[str, Any]) -> str:
    host = data.get("host") or {}
    return "<h2>Host</h2>" + _kv_list(
        [
            ("Computer name", host.get("computer_name")),
            ("Operating system", host.get("os_name")),
            ("Windows version", host.get("os_version")),
            ("Windows build", host.get("os_build")),
            ("Architecture", host.get("architecture")),
            ("Python", host.get("python_version")),
            ("Administrator", fmt_bool(host.get("is_admin"))),
        ]
    )


def _adapters_section(data: dict[str, Any]) -> str:
    adapters = data.get("adapters") or []
    if not adapters:
        return "<h2>Network adapters</h2><p>No adapter with an active link was detected.</p>"
    active_name = data.get("active_adapter_name")
    cards: list[str] = []
    for adapter in adapters:
        selected = " selected" if active_name and adapter.get("name") == active_name else ""
        bits = [
            adapter.get("media_type"),
            adapter.get("link_speed_text") or (
                f"{fmt_number(adapter.get('link_speed_mbps'), 0)} Mbps"
                if adapter.get("link_speed_mbps") is not None
                else None
            ),
            adapter.get("status"),
        ]
        sub = " &middot; ".join(escape(str(b)) for b in bits if b)
        detail = _kv_list(
            [
                ("IPv4", ", ".join(adapter.get("ipv4") or []) or "unavailable"),
                ("IPv6", ", ".join(adapter.get("ipv6") or []) or "unavailable"),
                ("Gateway", adapter.get("gateway")),
                ("DNS", ", ".join(adapter.get("dns_servers") or []) or "unavailable"),
                ("Description", adapter.get("description")),
                ("MAC", adapter.get("mac_address")),
            ]
        )
        cards.append(
            f'<div class="card{selected}"><h4>{_esc(adapter.get("name"))}</h4>'
            f'<div class="sub">{sub or "unknown"}</div>{detail}</div>'
        )
    return f'<h2>Network adapters ({len(adapters)})</h2><div class="grid">{"".join(cards)}</div>'


def _latency_section(title: str, ping: dict[str, Any]) -> str:
    stats = ping.get("stats") or {}
    status = status_label(ping.get("status"))
    rows = [
        ["Probes sent", _cell(stats.get("sent", 0), True)],
        ["Probes received", _cell(stats.get("received", 0), True)],
        ["Packet loss", _cell(fmt_percent(stats.get("loss_percent")), True)],
        ["Minimum RTT", _cell(fmt_ms_precise(stats.get("min_ms")), True)],
        ["Average RTT", _cell(fmt_ms_precise(stats.get("mean_ms")), True)],
        ["Median RTT", _cell(fmt_ms_precise(stats.get("median_ms")), True)],
        ["Maximum RTT", _cell(fmt_ms_precise(stats.get("max_ms")), True)],
        ["Standard deviation", _cell(fmt_ms_precise(stats.get("stdev_ms")), True)],
        ["Jitter", _cell(fmt_ms_precise(stats.get("jitter_ms")), True)],
    ]
    table = _table([("Metric", False), ("Value", True)], rows)
    notes = ""
    if ping.get("message"):
        notes += f'<div class="note">{_esc(ping.get("message"))}</div>'
    if ping.get("icmp_may_be_blocked"):
        notes += (
            '<div class="note">ICMP echo may be filtered on this path, so these numbers may '
            "understate the real latency or loss. The TCP results are more reliable here.</div>"
        )
    samples = ping.get("samples") or []
    series = ""
    if samples:
        rendered: list[str] = []
        for sample in samples:
            rtt = sample.get("rtt_ms")
            rendered.append(f"{sample.get('index')}:{'lost' if rtt is None else format(float(rtt), '.1f')}")
        series = f'<h3>Per-probe RTT (ms)</h3><p class="series">{escape(", ".join(rendered))}</p>'
    return (
        f"<h2>{escape(title)}</h2>"
        + _kv_list(
            [
                ("Target", ping.get("target")),
                ("Resolved address", ping.get("resolved_ip")),
                ("Status", status),
                ("Test duration", human_duration_ms(ping.get("duration_ms"))),
            ]
        )
        + table
        + notes
        + series
    )


def _internet_section(data: dict[str, Any]) -> str:
    pings = data.get("internet_pings") or []
    if not pings:
        return "<h2>Internet latency targets</h2><p>Not measured.</p>"
    return "".join(_latency_section(f"Internet target {p.get('target')}", p) for p in pings)


def _tcp_section(data: dict[str, Any]) -> str:
    probes = data.get("tcp_probes") or []
    if not probes:
        return ""
    rows = []
    for probe in probes:
        state = "Connected" if probe.get("connected") else "Failed"
        value = fmt_ms(probe.get("connect_ms")) if probe.get("connected") else fmt_plain(probe.get("error"))
        rows.append(
            [
                _cell(f"{probe.get('host')}:{probe.get('port')}"),
                _cell(state),
                _cell(value, True),
            ]
        )
    return (
        "<h2>TCP connectivity (independent of ICMP)</h2>"
        + _table([("Endpoint", False), ("Result", False), ("Connect time", True)], rows)
        + '<div class="note">A successful TCP handshake proves the endpoint is reachable even when '
        "ICMP echo is blocked. A failure can still be caused by a local firewall or by the "
        "destination blocking that port.</div>"
    )


def _dns_section(data: dict[str, Any]) -> str:
    dns = data.get("dns")
    if not dns:
        return "<h2>DNS resolution</h2><p>Not measured.</p>"
    rows = []
    for query in dns.get("queries") or []:
        kind = "Public" if query.get("is_public_resolver") else "Configured"
        if query.get("ok"):
            outcome = ", ".join(query.get("addresses") or []) or "resolved"
        else:
            outcome = f"FAILED: {fmt_plain(query.get('error'))}"
        rows.append(
            [
                _cell(query.get("hostname")),
                _cell(query.get("server")),
                _cell(kind),
                _cell(fmt_ms(query.get("duration_ms")), True),
                _cell(outcome),
            ]
        )
    table = (
        _table(
            [("Hostname", False), ("Resolver", False), ("Type", False), ("Time", True), ("Result", False)],
            rows,
        )
        if rows
        else "<p>No DNS query was performed.</p>"
    )
    body = _kv_list(
        [
            ("Status", status_label(dns.get("status"))),
            ("Configured resolvers", ", ".join(dns.get("configured_servers") or []) or "unavailable"),
            ("Average lookup", fmt_ms(dns.get("average_ms"))),
            ("Public comparison", fmt_bool(dns.get("public_comparison_enabled"))),
        ]
    )
    note = (
        '<div class="note">DNS only affects the time needed to turn a name into an IP address. It '
        "does not change the ping to a server that has already been resolved.</div>"
    )
    message = f'<div class="note">{_esc(dns.get("message"))}</div>' if dns.get("message") else ""
    return f"<h2>DNS resolution</h2>{body}{message}{table}{note}"


def _route_section(data: dict[str, Any]) -> str:
    route = data.get("route")
    if not route:
        return ""
    rows = []
    for hop in route.get("hops") or []:
        rtts = list(hop.get("rtts") or []) + [None, None, None]
        rows.append(
            [
                _cell(hop.get("hop"), True),
                _cell(hop.get("address") or "*"),
                _cell("*" if rtts[0] is None else f"{float(rtts[0]):.1f}", True),
                _cell("*" if rtts[1] is None else f"{float(rtts[1]):.1f}", True),
                _cell("*" if rtts[2] is None else f"{float(rtts[2]):.1f}", True),
            ]
        )
    table = (
        _table(
            [("Hop", True), ("Address", False), ("Probe 1", True), ("Probe 2", True), ("Probe 3", True)],
            rows,
        )
        if rows
        else ""
    )
    body = _kv_list(
        [
            ("Target", route.get("target")),
            ("Status", status_label(route.get("status"))),
            ("Reached target", fmt_bool(route.get("completed"))),
            ("Hops with no reply", route.get("missing_hop_count")),
            ("Message", route.get("message") or "none"),
        ]
    )
    note = (
        '<div class="note">A hop with no reply means that router did not answer a TTL-expired ICMP '
        "request. It is not proof of packet loss for normal traffic. Judge loss from the end-to-end "
        "latency tests instead.</div>"
    )
    return f"<h2>Route trace (tracert)</h2>{body}{table}{note}"


def _wifi_section(data: dict[str, Any]) -> str:
    wifi = data.get("wifi")
    if not wifi:
        return ""
    if not wifi.get("available"):
        message = wifi.get("message") or "No wireless interface was found on this computer."
        return f'<h2>Wi-Fi</h2><div class="note">{_esc(message)}</div>'
    return "<h2>Wi-Fi</h2>" + _kv_list(
        [
            ("SSID", wifi.get("ssid")),
            ("BSSID", wifi.get("bssid")),
            ("State", wifi.get("state")),
            ("Signal", "unavailable" if wifi.get("signal_percent") is None else f"{wifi.get('signal_percent')}%"),
            ("Radio type", wifi.get("radio_type")),
            ("Band", wifi.get("band")),
            ("Channel", wifi.get("channel")),
            ("Receive link rate", wifi.get("receive_rate_mbps")),
            ("Transmit link rate", wifi.get("transmit_rate_mbps")),
        ]
    ) + (
        '<div class="note">Wi-Fi link rates are radio negotiation figures, not internet bandwidth. '
        "A high link rate does not mean a fast connection, and a low signal causes latency spikes "
        "and loss even when the internet itself is healthy.</div>"
    )


def _speed_section(data: dict[str, Any]) -> str:
    speed = data.get("speed_test")
    if not speed:
        return ""
    body = _kv_list(
        [
            ("Result", "completed" if speed.get("ok") else "not completed"),
            ("URL", speed.get("url")),
            ("Downloaded", fmt_bytes(speed.get("bytes_downloaded"))),
            ("Duration", fmt_number(speed.get("duration_s"), 2) + " s"),
            (
                "Throughput",
                "unavailable"
                if speed.get("megabits_per_second") is None
                else f"{float(speed.get('megabits_per_second')):.2f} Mbit/s",
            ),
            ("Stopped early", fmt_bool(speed.get("stopped_early"))),
            ("Error", speed.get("error")),
        ]
    )
    note = f'<div class="note">{_esc(speed.get("privacy_note"))}</div>' if speed.get("privacy_note") else ""
    return f"<h2>Optional download speed test</h2>{body}{note}"


def _changes_section(data: dict[str, Any]) -> str:
    changes = data.get("applied_changes") or []
    if not changes:
        return ""
    rows = []
    for change in changes:
        rows.append(
            [
                _cell(change.get("action_id")),
                _cell(change.get("title")),
                _cell("Yes" if change.get("applied") else "No"),
                _cell(change.get("before")),
                _cell(change.get("after")),
                _cell(change.get("timestamp")),
            ]
        )
    return "<h2>Configuration changes recorded by NetPulse</h2>" + _table(
        [("ID", False), ("Action", False), ("Applied", False), ("Before", False), ("After", False), ("When", False)],
        rows,
    )


def _diagnoses_section(data: dict[str, Any]) -> str:
    diagnoses = data.get("diagnoses") or []
    if not diagnoses:
        return "<h2>Diagnosis</h2><p>No finding was produced.</p>"
    blocks: list[str] = []
    for diagnosis in diagnoses:
        severity = _status_class(diagnosis.get("severity"))
        evidence = "".join(f"<li>{_esc(item)}</li>" for item in diagnosis.get("evidence") or [])
        parts = [
            f'<div class="finding {severity}">',
            f'<div class="title">{_esc(diagnosis.get("finding"))}</div>',
            f'<div class="tags">{escape(str(diagnosis.get("rule_id")))} &middot; '
            f'<span class="pill {severity}">{escape(severity_label(diagnosis.get("severity")))}</span> &middot; '
            f'Confidence: {escape(confidence_label(diagnosis.get("confidence")))} &middot; '
            f'{escape(str(diagnosis.get("category")))}</div>',
        ]
        if evidence:
            parts.append(f'<div class="label">Evidence</div><ul>{evidence}</ul>')
        if diagnosis.get("meaning"):
            parts.append(f'<div class="label">What this may mean</div><p>{_esc(diagnosis.get("meaning"))}</p>')
        if diagnosis.get("recommendation"):
            parts.append(
                f'<div class="label">Recommended next action</div><p>{_esc(diagnosis.get("recommendation"))}</p>'
            )
        if diagnosis.get("cannot_verify"):
            parts.append(
                f'<div class="label">What NetPulse cannot verify</div><p>{_esc(diagnosis.get("cannot_verify"))}</p>'
            )
        parts.append("</div>")
        blocks.append("".join(parts))
    return f'<h2>Diagnosis ({len(diagnoses)} findings)</h2>' + "".join(blocks)


def _warnings_section(data: dict[str, Any]) -> str:
    warnings = data.get("warnings") or []
    if not warnings:
        return ""
    items = "".join(f"<li>{_esc(w)}</li>" for w in warnings)
    return f"<h2>Warnings and limitations</h2><ul>{items}</ul>"


def render_html(report_data: dict[str, Any]) -> str:
    """Render ``report_data`` as a self-contained printable HTML document."""
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{escape(APP_DISPLAY_NAME)} diagnostic report</title>",
        f"<style>{_CSS}</style></head><body><div class='report'>",
        _header(report_data),
        _banner(report_data),
    ]
    if report_data.get("gateway_ping"):
        parts.append(_latency_section("Local gateway (PC to router)", report_data["gateway_ping"]))
    parts += [
        _internet_section(report_data),
        _tcp_section(report_data),
        _dns_section(report_data),
        _route_section(report_data),
        _wifi_section(report_data),
        _speed_section(report_data),
        _adapters_section(report_data),
        _host_section(report_data),
        _changes_section(report_data),
        _warnings_section(report_data),
        _diagnoses_section(report_data),
        f"<footer>Generated by {escape(APP_DISPLAY_NAME)} {escape(APP_VERSION)} &mdash; "
        f'<a href="{escape(APP_URL)}">{escape(APP_URL)}</a><br>'
        "NetPulse is an open-source diagnostic tool. It provides no guarantee of repair and "
        "never modifies Windows network settings without explicit confirmation.</footer>",
        "</div></body></html>",
    ]
    return "\n".join(part for part in parts if part)


__all__ = ["render_html"]
