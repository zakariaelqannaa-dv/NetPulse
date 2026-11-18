"""The Dashboard: overall status, live latency, per-section cards and findings."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    AdapterInfo,
    DiagnosticReport,
    DnsTestResult,
    PingResult,
    RouteTrace,
    Severity,
    SpeedTestResult,
    TcpProbeResult,
    TestStatus,
    WifiInfo,
)
from app.core.settings import AppSettings
from app.ui import theme as theme_module
from app.ui.widgets import (
    Card,
    FindingCard,
    LatencyBars,
    MetricTile,
    StatusBadge,
    body,
    current_theme,
    fmt_ms,
    fmt_percent,
    kv_grid,
    muted,
    section_label,
)

_STATUS_TO_SEVERITY = {
    TestStatus.OK: Severity.GOOD,
    TestStatus.WARNING: Severity.WARNING,
    TestStatus.CRITICAL: Severity.CRITICAL,
    TestStatus.UNSUPPORTED: Severity.UNKNOWN,
    TestStatus.NOT_MEASURABLE: Severity.UNKNOWN,
    TestStatus.ERROR: Severity.UNKNOWN,
    TestStatus.SKIPPED: Severity.UNKNOWN,
    TestStatus.CANCELLED: Severity.UNKNOWN,
    TestStatus.PENDING: Severity.UNKNOWN,
    TestStatus.RUNNING: Severity.UNKNOWN,
}


def ping_severity(ping: PingResult | None) -> Severity:
    if ping is None:
        return Severity.UNKNOWN
    return _STATUS_TO_SEVERITY.get(ping.status, Severity.UNKNOWN)


def _clear(layout: Any) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        else:
            child = item.layout()
            if child is not None:
                _clear(child)


def _make_table(headers: Sequence[str], selectable: bool = True) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.verticalHeader().setVisible(False)
    table.setShowGrid(False)
    table.setAlternatingRowColors(True)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    if not selectable:
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setHighlightSections(False)
    return table


def _fit_table_height(table: QTableWidget, row_height: int = 24, minimum: int = 40) -> None:
    rows = max(table.rowCount(), 1)
    header = table.horizontalHeader().height()
    table.setFixedHeight(min(maximum_table_height(), max(minimum, header + rows * row_height + 6)))


def maximum_table_height() -> int:
    return 260


def _cell(text: str, alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(int(alignment | Qt.AlignmentFlag.AlignVCenter))
    return item


class DashboardPage(QWidget):
    """Main status view."""

    run_requested = Signal()
    stop_requested = Signal()
    export_requested = Signal()

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._report: DiagnosticReport | None = None
        self._internet_results: list[PingResult] = []
        self._tcp_probes: list[TcpProbeResult] = []
        self._speed_test: SpeedTestResult | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        inner = QWidget()
        scroll.setWidget(inner)
        root.addWidget(scroll)

        layout = QVBoxLayout(inner)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        layout.addWidget(self._build_toolbar())
        layout.addWidget(self._build_banner())
        layout.addWidget(self._build_hero())

        cards = QGridLayout()
        cards.setHorizontalSpacing(12)
        cards.setVerticalSpacing(12)
        cards.setColumnStretch(0, 1)
        cards.setColumnStretch(1, 1)
        self.gateway_card = Card("Local gateway (PC to router)", "Latency to your own router.")
        self.internet_card = Card("Internet targets", "Latency beyond your router.")
        self.dns_card = Card("DNS resolution", "Time needed to turn a name into an address.")
        self.wifi_card = Card("Wi-Fi / Ethernet", "Physical link of the active adapter.")
        self.route_card = Card("Route trace", "Path your traffic takes to a public address.")
        self.adapter_card = Card("Adapters", "Every adapter Windows reports as connected.")
        cards.addWidget(self.gateway_card, 0, 0)
        cards.addWidget(self.internet_card, 0, 1)
        cards.addWidget(self.dns_card, 1, 0)
        cards.addWidget(self.wifi_card, 1, 1)
        cards.addWidget(self.route_card, 2, 0, 1, 2)
        cards.addWidget(self.adapter_card, 3, 0, 1, 2)
        layout.addLayout(cards)

        self.findings_card = Card("Diagnosis", "Rule-based findings with evidence and confidence.")
        layout.addWidget(self.findings_card)
        layout.addStretch(1)

        self.reset()

    # ------------------------------------------------------------------ #
    # Construction
    # ------------------------------------------------------------------ #

    def _build_toolbar(self) -> QWidget:
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        heading = QLabel("Connection diagnosis")
        heading.setProperty("role", "title")
        subtitle = QLabel(
            "NetPulse measures your link, router, internet path and DNS. It explains what it found "
            "and never claims to repair your ISP, cabling or router."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(heading)
        title_box.addWidget(subtitle)
        row.addLayout(title_box, 1)

        self.start_button = QPushButton("Start diagnosis")
        self.start_button.setProperty("accent", "true")
        self.start_button.clicked.connect(self.run_requested.emit)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setProperty("danger", "true")
        self.stop_button.clicked.connect(self.stop_requested.emit)
        self.stop_button.setEnabled(False)
        self.export_button = QPushButton("Export report")
        self.export_button.clicked.connect(self.export_requested.emit)
        self.export_button.setEnabled(False)
        row.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.stop_button, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.export_button, 0, Qt.AlignmentFlag.AlignTop)
        return holder

    def _build_banner(self) -> QWidget:
        card = Card()
        card.setObjectName("statusBanner")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.banner_badge = StatusBadge(Severity.UNKNOWN)
        self.banner_headline = QLabel("No diagnosis has been run yet.")
        self.banner_headline.setProperty("role", "headline")
        self.banner_headline.setWordWrap(True)
        row.addWidget(self.banner_badge, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.banner_headline, 1)
        card.add_layout(row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_label = muted("Idle.")
        self.progress_label.setVisible(False)
        card.add(self.progress_bar)
        card.add(self.progress_label)
        self.banner_card = card
        return card

    def _build_hero(self) -> QWidget:
        holder = QWidget(self)
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        card = Card("Measured latency", "Average round trip time to your router and to the internet.")
        top = QHBoxLayout()
        top.setSpacing(16)

        hero_box = QVBoxLayout()
        hero_box.setSpacing(0)
        hero_row = QHBoxLayout()
        hero_row.setSpacing(6)
        self.hero_value = QLabel("--")
        self.hero_value.setProperty("role", "hero")
        self.hero_unit = QLabel("ms")
        self.hero_unit.setProperty("role", "heroUnit")
        hero_row.addWidget(self.hero_value)
        hero_row.addWidget(self.hero_unit, 0, Qt.AlignmentFlag.AlignBottom)
        hero_row.addStretch(1)
        hero_box.addLayout(hero_row)
        self.hero_caption = muted("Not measured yet.")
        hero_box.addWidget(self.hero_caption)
        top.addLayout(hero_box, 2)

        tiles = QGridLayout()
        tiles.setHorizontalSpacing(10)
        tiles.setVerticalSpacing(10)
        self.tile_gateway = MetricTile("Gateway", "--", "ms")
        self.tile_jitter = MetricTile("Jitter", "--", "ms")
        self.tile_loss = MetricTile("Packet loss", "--", "%")
        self.tile_dns = MetricTile("DNS lookup", "--", "ms")
        tiles.addWidget(self.tile_gateway, 0, 0)
        tiles.addWidget(self.tile_jitter, 0, 1)
        tiles.addWidget(self.tile_loss, 1, 0)
        tiles.addWidget(self.tile_dns, 1, 1)
        top.addLayout(tiles, 3)
        card.add_layout(top)

        self.bars = LatencyBars()
        self.bars.setToolTip("Each bar is one probe. A bar at the baseline marks a lost probe.")
        card.add(self.bars)
        self.bars_caption = muted(
            "Bars show every individual probe to the selected internet target. "
            "Dashed lines mark the warning and critical thresholds."
        )
        card.add(self.bars_caption)
        self.speed_label = muted("")
        self.speed_label.setVisible(False)
        card.add(self.speed_label)

        layout.addWidget(card)
        return holder

    # ------------------------------------------------------------------ #
    # Run state
    # ------------------------------------------------------------------ #

    def set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.export_button.setEnabled(bool(self._report) and not running)
        if running:
            self.progress_bar.setValue(0)
            self.progress_label.setVisible(True)
            self.progress_label.setText("Starting...")

    def set_progress(self, percent: int, task: str) -> None:
        self.progress_bar.setValue(max(0, min(100, percent)))
        if task == "finished":
            self.progress_label.setText("Finished.")
        else:
            self.progress_label.setText(f"Running: {task}" if task else "Running...")

    def reset(self) -> None:
        """Clear every result so a new run starts from an empty dashboard."""
        self._report = None
        self._internet_results = []
        self._tcp_probes = []
        self._speed_test = None
        self.banner_badge.set_severity(Severity.UNKNOWN)
        self.banner_headline.setText("No diagnosis has been run yet.")
        self.progress_bar.setValue(0)
        self.progress_label.setVisible(False)
        self.export_button.setEnabled(False)
        self._set_hero(None, "Not measured yet.")
        self.speed_label.setVisible(False)
        self.bars.clear()
        self._render_gateway(None)
        self._render_internet()
        self._render_dns(None)
        self._render_wifi(None)
        self._render_route(None)
        self._render_adapters(None, None, [])
        _clear(self.findings_card.body)
        self.findings_card.add(muted("Run a diagnosis to see findings here."))

    # ------------------------------------------------------------------ #
    # Live updates
    # ------------------------------------------------------------------ #

    def apply_section(self, name: str, payload: Any) -> None:
        if name == "adapters":
            snapshot = payload
            self._render_adapters(
                getattr(snapshot, "active_adapter", None),
                getattr(snapshot, "active_name", None),
                list(getattr(snapshot, "adapters", []) or []),
            )
            self._render_wifi(LINK_PLACEHOLDER if _is_wireless(getattr(snapshot, "active_adapter", None)) else None)
        elif name == "wifi":
            self._render_wifi(payload)
        elif name == "gateway":
            self._render_gateway(payload)
            self._update_hero_from([payload], self._internet_results)
        elif name == "internet":
            self._add_internet_result(payload)
            self._update_hero_from([self._report.gateway_ping] if self._report else [], self._internet_results)
            self._render_internet()
        elif name == "tcp":
            self._tcp_probes = list(payload or [])
            self._render_internet()
        elif name == "dns":
            self._render_dns(payload)
        elif name == "route":
            self._render_route(payload)
        elif name == "speed":
            self._render_speed(payload)

    def _add_internet_result(self, ping: PingResult | None) -> None:
        if ping is None:
            return
        self._internet_results = [p for p in self._internet_results if p.target != ping.target]
        self._internet_results.append(ping)

    def _render_speed(self, speed: SpeedTestResult | None) -> None:
        self._speed_test = speed
        if speed is None:
            self.speed_label.setVisible(False)
            return
        if speed.ok and speed.megabits_per_second is not None:
            text = (
                f"Speed test: {speed.megabits_per_second:.1f} Mbps down "
                f"({speed.bytes_downloaded / 1_048_576:.1f} MiB in {speed.duration_s:.1f}s)."
            )
            if speed.stopped_early:
                text += " Stopped after the configured time limit."
        else:
            text = f"Speed test did not complete: {speed.error or 'no measurement'}"
        if speed.privacy_note:
            text += f" {speed.privacy_note}"
        self.speed_label.setText(text)
        self.speed_label.setVisible(True)

    def _update_hero_from(self, gateway: list[Any], internet: list[Any]) -> None:
        best = None
        for ping in internet:
            if ping is not None and ping.stats.received > 0 and ping.kind != "gateway":
                if best is None or (ping.stats.mean_ms or 1e9) < (best.stats.mean_ms or 1e9):
                    best = ping
        if best is None:
            self._set_hero(gateway[0] if gateway else None, "Measured to your router only.")
            return
        self._set_hero(best, f"Best internet target: {best.target}")

    def _set_hero(self, ping: PingResult | None, caption: str) -> None:
        if ping is None or ping.stats.received == 0:
            self.hero_value.setText("--")
            self.hero_caption.setText(caption)
            self.bars.clear()
            self.tile_gateway.set_value("--", None, "ms")
            self.tile_jitter.set_value("--", None, "ms")
            self.tile_loss.set_value("--", None, "%")
            return
        stats = ping.stats
        self.hero_value.setText(f"{stats.mean_ms:.1f}" if stats.mean_ms is not None else "--")
        severity = ping_severity(ping)
        color = theme_module.severity_color(current_theme(), severity.value)
        self.hero_value.setStyleSheet(f"font-size: 44px; font-weight: 600; color: {color};")
        self.hero_caption.setText(f"{caption}  |  {fmt_ms(stats.min_ms)} - {fmt_ms(stats.max_ms)} range")
        thresholds = self._settings.thresholds
        self.bars.set_samples(
            [sample.to_dict() for sample in ping.samples],
            thresholds.get("latency_warn_ms", 80.0),
            thresholds.get("latency_critical_ms", 150.0),
        )

    # ------------------------------------------------------------------ #
    # Sections
    # ------------------------------------------------------------------ #

    def _render_gateway(self, ping: PingResult | None) -> None:
        _clear(self.gateway_card.body)
        if ping is None:
            self.gateway_card.add(muted("Not measured yet."))
            self.tile_gateway.set_value("--", None, "ms")
            return
        stats = ping.stats
        self.tile_gateway.set_value(
            f"{stats.mean_ms:.1f}" if stats.mean_ms is not None else "--",
            ping_severity(ping),
            "ms",
        )
        header = QHBoxLayout()
        header.addWidget(StatusBadge(ping_severity(ping)))
        header.addWidget(muted(f"{ping.target}", wrap=False))
        header.addStretch(1)
        self.gateway_card.add_layout(header)
        self.gateway_card.add(
            kv_grid(
                [
                    ("Address", ping.resolved_ip or ping.target),
                    ("Mean RTT", fmt_ms(stats.mean_ms)),
                    ("Jitter", fmt_ms(stats.jitter_ms)),
                    ("Packet loss", fmt_percent(stats.loss_percent)),
                    ("Probes", f"{stats.received} of {stats.sent} answered"),
                ]
            )
        )
        if ping.message:
            self.gateway_card.add(muted(ping.message))

    def _render_internet(self) -> None:
        results = self._internet_results
        _clear(self.internet_card.body)
        if not results:
            self.internet_card.add(muted("Not measured yet."))
            self.tile_jitter.set_value("--", None, "ms")
            self.tile_loss.set_value("--", None, "%")
            return
        table = _make_table(["Target", "Mean", "Jitter", "Loss", "Rating"])
        table.setRowCount(len(results))
        for row, ping in enumerate(results):
            stats = ping.stats
            table.setItem(row, 0, _cell(ping.resolved_ip or ping.target))
            table.setItem(row, 1, _cell(fmt_ms(stats.mean_ms, 1), Qt.AlignmentFlag.AlignRight))
            table.setItem(row, 2, _cell(fmt_ms(stats.jitter_ms, 1), Qt.AlignmentFlag.AlignRight))
            table.setItem(row, 3, _cell(fmt_percent(stats.loss_percent), Qt.AlignmentFlag.AlignRight))
            table.setItem(row, 4, _cell(str(_STATUS_TO_SEVERITY.get(ping.status, Severity.UNKNOWN).value)))
        _fit_table_height(table)
        self.internet_card.add(table)

        best = min(
            (p for p in results if p.stats.received > 0),
            key=lambda p: p.stats.mean_ms or 1e9,
            default=None,
        )
        if best is not None:
            self.tile_jitter.set_value(
                f"{best.stats.jitter_ms:.1f}" if best.stats.jitter_ms is not None else "--",
                ping_severity(best),
                "ms",
            )
        worst_loss = max(results, key=lambda p: p.stats.loss_percent)
        loss_severity = (
            Severity.GOOD
            if worst_loss.stats.loss_percent <= self._settings.thresholds.get("loss_warn_percent", 1.0)
            else Severity.WARNING
            if worst_loss.stats.loss_percent <= self._settings.thresholds.get("loss_critical_percent", 5.0)
            else Severity.CRITICAL
        )
        self.tile_loss.set_value(f"{worst_loss.stats.loss_percent:.2f}", loss_severity, "%")

        blocked = [p for p in results if p.icmp_may_be_blocked]
        if blocked:
            self.internet_card.add(
                muted(
                    "ICMP echo appears to be filtered for at least one target. The TCP results "
                    "below are more reliable than these latency figures."
                )
            )

        if self._tcp_probes:
            self.internet_card.add(section_label("TCP connect test"))
            tcp_table = _make_table(["Endpoint", "Connect time", "Result"], selectable=False)
            tcp_table.setRowCount(len(self._tcp_probes))
            for row, probe in enumerate(self._tcp_probes):
                endpoint = f"{probe.resolved_ip or probe.host}:{probe.port}"
                tcp_table.setItem(row, 0, _cell(endpoint))
                tcp_table.setItem(
                    row,
                    1,
                    _cell(fmt_ms(probe.connect_ms, 1), Qt.AlignmentFlag.AlignRight),
                )
                tcp_table.setItem(
                    row,
                    2,
                    _cell("connected" if probe.connected else (probe.error or "no connection")),
                )
            _fit_table_height(tcp_table, minimum=50)
            self.internet_card.add(tcp_table)

    def _render_dns(self, dns: DnsTestResult | None) -> None:
        _clear(self.dns_card.body)
        if dns is None:
            self.dns_card.add(muted("Not measured yet."))
            self.tile_dns.set_value("--", None, "ms")
            return
        severity = _STATUS_TO_SEVERITY.get(dns.status, Severity.UNKNOWN)
        self.tile_dns.set_value(
            f"{dns.average_ms:.1f}" if dns.average_ms is not None else "--",
            severity,
            "ms",
        )
        header = QHBoxLayout()
        header.addWidget(StatusBadge(severity))
        header.addStretch(1)
        self.dns_card.add_layout(header)
        if dns.message:
            self.dns_card.add(muted(dns.message))
        if not dns.queries:
            self.dns_card.add(muted("No DNS query was performed."))
            return
        table = _make_table(["Hostname", "Resolver", "Time", "Result"])
        table.setRowCount(len(dns.queries))
        for row, query in enumerate(dns.queries):
            table.setItem(row, 0, _cell(query.hostname))
            table.setItem(row, 1, _cell(query.server + (" (public)" if query.is_public_resolver else "")))
            table.setItem(row, 2, _cell(fmt_ms(query.duration_ms, 0), Qt.AlignmentFlag.AlignRight))
            table.setItem(row, 3, _cell("resolved" if query.ok else "failed"))
        _fit_table_height(table)
        self.dns_card.add(table)

    def _render_wifi(self, wifi: WifiInfo | None) -> None:
        _clear(self.wifi_card.body)
        if wifi is None:
            self.wifi_card.add(muted("No wireless adapter is active."))
            return
        if not wifi.available:
            self.wifi_card.add(body(wifi.message or "No wireless interface was found on this computer."))
            return
        signal_text = "Not available" if wifi.signal_percent is None else f"{wifi.signal_percent}%"
        rows: list[tuple[str, Any]] = [
            ("SSID", wifi.ssid),
            ("State", wifi.state),
            ("Signal", signal_text),
            ("Band / channel", _band_channel(wifi)),
            ("Radio type", wifi.radio_type),
        ]
        self.wifi_card.add(kv_grid(rows))
        if wifi.signal_percent is not None:
            warn = self._settings.thresholds.get("wifi_signal_warn_percent", 55)
            self.wifi_card.add(
                muted(
                    "A signal below about "
                    f"{int(warn)}% is where latency spikes and packet loss usually start."
                )
            )

    def _render_route(self, route: RouteTrace | None) -> None:
        _clear(self.route_card.body)
        if route is None:
            self.route_card.add(muted("Not measured yet."))
            return
        severity = _STATUS_TO_SEVERITY.get(route.status, Severity.UNKNOWN)
        header = QHBoxLayout()
        header.addWidget(StatusBadge(severity))
        header.addWidget(muted(f"target {route.target}", wrap=False))
        header.addStretch(1)
        self.route_card.add_layout(header)
        if route.message:
            self.route_card.add(muted(route.message))
        if not route.hops:
            self.route_card.add(muted("No hop was reported."))
            return
        table = _make_table(["#", "Address", "Probe 1", "Probe 2", "Probe 3", "Average"], selectable=False)
        table.setRowCount(len(route.hops))
        for row, hop in enumerate(route.hops):
            rtts = list(hop.rtts) + [None, None, None]
            table.setItem(row, 0, _cell(str(hop.hop), Qt.AlignmentFlag.AlignRight))
            table.setItem(row, 1, _cell(hop.address or hop.hostname or "*"))
            for column in range(3):
                value = rtts[column]
                table.setItem(
                    row,
                    2 + column,
                    _cell("*" if value is None else f"{value:.1f}", Qt.AlignmentFlag.AlignRight),
                )
            table.setItem(
                row,
                5,
                _cell(fmt_ms(hop.average_ms, 1) if hop.has_reply else "*", Qt.AlignmentFlag.AlignRight),
            )
        _fit_table_height(table, minimum=60)
        self.route_card.add(table)
        self.route_card.add(
            muted(
                "A '*' hop means that router did not answer an ICMP request. It is not proof of "
                "packet loss for normal traffic."
            )
        )

    def _render_adapters(
        self,
        active: AdapterInfo | None,
        active_name: str | None,
        adapters: Sequence[AdapterInfo],
    ) -> None:
        _clear(self.adapter_card.body)
        if not adapters:
            self.adapter_card.add(muted("No adapter with an active link was detected."))
            return
        if active is not None:
            self.adapter_card.add(
                kv_grid(
                    [
                        ("Active adapter", active.name),
                        ("Description", active.description),
                        ("Type", active.media_type),
                        ("Link speed", active.link_speed_text or _speed_text(active.link_speed_mbps)),
                        ("Local IPv4", ", ".join(active.ipv4) or None),
                        ("Local IPv6", ", ".join(active.ipv6) or None),
                        ("Default gateway", active.gateway),
                        ("DNS servers", ", ".join(active.dns_servers) or None),
                        ("DHCP enabled", active.dhcp_enabled),
                        ("MTU", active.mtu),
                    ]
                )
            )
        others = [a for a in adapters if active is None or a.name != active.name]
        if others:
            self.adapter_card.add(section_label("Other connected adapters"))
            table = _make_table(["Adapter", "Type", "Link speed", "IPv4"], selectable=False)
            table.setRowCount(len(others))
            for row, adapter in enumerate(others):
                table.setItem(row, 0, _cell(adapter.name))
                table.setItem(row, 1, _cell(adapter.media_type))
                table.setItem(row, 2, _cell(adapter.link_speed_text or _speed_text(adapter.link_speed_mbps)))
                table.setItem(row, 3, _cell(", ".join(adapter.ipv4) or None))
            _fit_table_height(table, minimum=50)
            self.adapter_card.add(table)
        if active_name is None and adapters:
            self.adapter_card.add(muted("No adapter has a default gateway, so no router could be identified."))

    # ------------------------------------------------------------------ #

    def show_report(self, report: DiagnosticReport) -> None:
        """Render a completed report."""
        self._report = report
        self._internet_results = list(report.internet_pings)
        self._tcp_probes = list(report.tcp_probes)
        if report.gateway_ping is not None:
            self._render_gateway(report.gateway_ping)
        self._render_internet()
        self._render_dns(report.dns)
        if report.wifi is not None:
            self._render_wifi(report.wifi)
        self._render_route(report.route)
        self._render_adapters(report.active_adapter, report.active_adapter_name, report.adapters)
        self._render_speed(report.speed_test)
        self._update_hero_from(
            [report.gateway_ping] if report.gateway_ping else [],
            list(report.internet_pings),
        )

        self.banner_badge.set_severity(report.overall_status)
        headline = report.headline or "Diagnosis finished."
        if report.cancelled:
            headline = "Stopped early: " + headline
        self.banner_headline.setText(headline)
        self.progress_label.setVisible(True)
        self.progress_label.setText(f"Finished in {report.duration_ms / 1000.0:.1f} s.")
        self.export_button.setEnabled(True)

        _clear(self.findings_card.body)
        if not report.diagnoses:
            self.findings_card.add(muted("No finding was produced."))
        else:
            for diagnosis in report.diagnoses:
                self.findings_card.add(FindingCard(diagnosis))
        if report.warnings:
            self.findings_card.add(section_label("Warnings and limitations"))
            for warning in report.warnings:
                self.findings_card.add(muted(f"- {warning}"))

    @property
    def report(self) -> DiagnosticReport | None:
        return self._report


def _speed_text(mbps: float | None) -> str | None:
    return None if mbps is None else f"{mbps:.0f} Mbps"


def _band_channel(wifi: WifiInfo) -> str | None:
    parts = [part for part in (wifi.band, f"channel {wifi.channel}" if wifi.channel else None) if part]
    return " / ".join(parts) or None


def _is_wireless(adapter: AdapterInfo | None) -> bool:
    return bool(adapter and adapter.is_wireless)


class _LinkPlaceholder:
    """Placeholder used until the Wi-Fi collector reports its own result."""

    available = False
    message = "Checking the wireless interface..."


LINK_PLACEHOLDER = _LinkPlaceholder()


__all__ = ["DashboardPage", "ping_severity"]
