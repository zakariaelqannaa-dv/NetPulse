"""Application settings.

Everything here is stored in a single local JSON file. NetPulse has no account,
no server and no telemetry, so these values never leave the machine.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.paths import app_data_dir
from app.core.settings import THEMES, AppSettings
from app.ui.widgets import muted

_THEME_LABELS = {"dark": "Dark", "light": "Light"}

# key, label, minimum, maximum, decimals, step
_THRESHOLDS: tuple[tuple[str, str, float, float, int, float], ...] = (
    ("latency_warn_ms", "Internet latency warning (ms)", 1.0, 5000.0, 1, 5.0),
    ("latency_critical_ms", "Internet latency critical (ms)", 1.0, 5000.0, 1, 5.0),
    ("jitter_warn_ms", "Jitter warning (ms)", 1.0, 2000.0, 1, 5.0),
    ("jitter_critical_ms", "Jitter critical (ms)", 1.0, 2000.0, 1, 5.0),
    ("loss_warn_percent", "Packet loss warning (%)", 0.0, 100.0, 2, 0.5),
    ("loss_critical_percent", "Packet loss critical (%)", 0.0, 100.0, 2, 0.5),
    ("gateway_latency_warn_ms", "Router latency warning (ms)", 1.0, 1000.0, 1, 1.0),
    ("gateway_latency_critical_ms", "Router latency critical (ms)", 1.0, 1000.0, 1, 1.0),
    ("gateway_loss_warn_percent", "Router loss warning (%)", 0.0, 100.0, 2, 0.5),
    ("gateway_loss_critical_percent", "Router loss critical (%)", 0.0, 100.0, 2, 0.5),
    ("dns_warn_ms", "DNS warning (ms)", 1.0, 5000.0, 0, 10.0),
    ("dns_critical_ms", "DNS critical (ms)", 1.0, 5000.0, 0, 10.0),
    ("wifi_signal_warn_percent", "Wi-Fi signal warning (%)", 0.0, 100.0, 0, 5.0),
    ("wifi_signal_critical_percent", "Wi-Fi signal critical (%)", 0.0, 100.0, 0, 5.0),
    ("ethernet_slow_link_mbps", "Slow Ethernet link warning (Mbps)", 1.0, 100000.0, 0, 100.0),
)


class SettingsPage(QWidget):
    """Edit the diagnosis parameters, thresholds and optional features."""

    settings_saved = Signal(object)

    def __init__(self, settings: AppSettings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self._threshold_boxes: dict[str, QDoubleSpinBox] = {}

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
        layout.addWidget(self._build_appearance())
        layout.addWidget(self._build_latency())
        layout.addWidget(self._build_dns_route())
        layout.addWidget(self._build_speed_test())
        layout.addWidget(self._build_thresholds())
        layout.addWidget(self._build_history())
        layout.addWidget(
            muted(f"Settings are stored at {app_data_dir() / 'settings.json'}")
        )
        layout.addStretch(1)

        self.load_from_settings(self._settings)

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
        heading = QLabel("Settings")
        heading.setProperty("role", "title")
        subtitle = QLabel(
            "These parameters control how long NetPulse measures and how strict its ratings are. "
            "Defaults follow the guidance in the documentation."
        )
        subtitle.setProperty("role", "subtitle")
        subtitle.setWordWrap(True)
        title_box.addWidget(heading)
        title_box.addWidget(subtitle)
        row.addLayout(title_box, 1)

        self.save_button = QPushButton("Save settings")
        self.save_button.setProperty("accent", "true")
        self.save_button.clicked.connect(self.save)
        self.reset_button = QPushButton("Restore defaults")
        self.reset_button.clicked.connect(self.restore_defaults)
        row.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.reset_button, 0, Qt.AlignmentFlag.AlignTop)
        return holder

    def _build_appearance(self) -> QGroupBox:
        box = QGroupBox("Appearance")
        form = QFormLayout(box)
        self.theme_combo = QComboBox()
        for theme in THEMES:
            self.theme_combo.addItem(_THEME_LABELS.get(theme, theme.title()), theme)
        form.addRow("Theme", self.theme_combo)
        return box

    def _build_latency(self) -> QGroupBox:
        box = QGroupBox("Latency measurement")
        form = QFormLayout(box)

        self.ping_count = _spin(1, 500, 1)
        self.gateway_count = _spin(1, 500, 1)
        self.ping_interval = _spin(50, 10000, 50)
        self.ping_timeout = _spin(100, 10000, 100)
        self.max_workers = _spin(1, 8, 1)
        self.internet_targets = QLineEdit()
        self.internet_targets.setPlaceholderText("1.1.1.1, 8.8.8.8")
        self.enable_tcp = QCheckBox("Run TCP handshake probes as well as ICMP")
        self.tcp_probes = QLineEdit()
        self.tcp_probes.setPlaceholderText("1.1.1.1:443, 8.8.8.8:53")
        self.tcp_timeout = _spin(200, 15000, 100)

        form.addRow("Probes per internet target", self.ping_count)
        form.addRow("Probes to the router", self.gateway_count)
        form.addRow("Interval between probes (ms)", self.ping_interval)
        form.addRow("Probe timeout (ms)", self.ping_timeout)
        form.addRow("Parallel workers", self.max_workers)
        form.addRow("Internet targets", self.internet_targets)
        form.addRow("", self.enable_tcp)
        form.addRow("TCP endpoints (host:port)", self.tcp_probes)
        form.addRow("TCP connect timeout (ms)", self.tcp_timeout)
        return box

    def _build_dns_route(self) -> QGroupBox:
        box = QGroupBox("DNS and route trace")
        form = QFormLayout(box)

        self.dns_hostnames = QLineEdit()
        self.dns_hostnames.setPlaceholderText("google.com, cloudflare.com")
        self.dns_timeout = _spin(200, 15000, 100)
        self.enable_public_dns = QCheckBox("Also query public resolvers for comparison")
        self.public_dns = QLineEdit()
        self.public_dns.setPlaceholderText("1.1.1.1, 8.8.8.8")
        self.enable_route = QCheckBox("Trace the route to a public address")
        self.route_target = QLineEdit()
        self.route_max_hops = _spin(1, 64, 1)
        self.route_timeout = _spin(100, 5000, 100)

        form.addRow("Hostnames to resolve", self.dns_hostnames)
        form.addRow("DNS timeout (ms)", self.dns_timeout)
        form.addRow("", self.enable_public_dns)
        form.addRow("Public resolvers", self.public_dns)
        form.addRow("", self.enable_route)
        form.addRow("Route trace target", self.route_target)
        form.addRow("Maximum hops", self.route_max_hops)
        form.addRow("Per-hop timeout (ms)", self.route_timeout)
        return box

    def _build_speed_test(self) -> QGroupBox:
        box = QGroupBox("Optional speed test")
        form = QFormLayout(box)
        note = muted(
            "Off by default. A speed test downloads real data from a URL you choose, so it can consume "
            "a significant amount of your data allowance. NetPulse never runs it unless you enable it, "
            "enter a URL and tick the consent box below."
        )
        note.setWordWrap(True)
        form.addRow(note)

        self.speed_enabled = QCheckBox("Enable the optional speed test")
        self.speed_url = QLineEdit()
        self.speed_url.setPlaceholderText("https://example.com/testfile.bin")
        self.speed_consent = QCheckBox(
            "I understand the speed test downloads data from the URL above and I consent to it"
        )
        self.speed_seconds = _spin(3, 60, 1)

        form.addRow("", self.speed_enabled)
        form.addRow("Download URL", self.speed_url)
        form.addRow("", self.speed_consent)
        form.addRow("Maximum duration (seconds)", self.speed_seconds)
        return box

    def _build_thresholds(self) -> QGroupBox:
        box = QGroupBox("Rating thresholds")
        form = QFormLayout(box)
        form.addRow(
            muted("Values at or above a warning level are reported as warnings, at or above the critical level as critical.")
        )
        for key, label, minimum, maximum, decimals, step in _THRESHOLDS:
            spin = QDoubleSpinBox()
            spin.setDecimals(decimals)
            spin.setRange(minimum, maximum)
            spin.setSingleStep(step)
            self._threshold_boxes[key] = spin
            form.addRow(label, spin)
        return box

    def _build_history(self) -> QGroupBox:
        box = QGroupBox("History")
        form = QFormLayout(box)
        self.history_enabled = QCheckBox("Keep a local history of diagnoses")
        self.history_limit = _spin(1, 500, 1)
        form.addRow("", self.history_enabled)
        form.addRow("Stored entries", self.history_limit)
        return box

    # ------------------------------------------------------------------ #
    # Load / save
    # ------------------------------------------------------------------ #

    def load_from_settings(self, settings: AppSettings) -> None:
        current = settings.normalized()
        self.theme_combo.setCurrentIndex(max(0, self.theme_combo.findData(current.theme)))
        self.ping_count.setValue(current.ping_count)
        self.gateway_count.setValue(current.gateway_count)
        self.ping_interval.setValue(current.ping_interval_ms)
        self.ping_timeout.setValue(current.ping_timeout_ms)
        self.max_workers.setValue(current.max_workers)
        self.internet_targets.setText(", ".join(current.internet_targets))
        self.enable_tcp.setChecked(current.enable_tcp_probes)
        self.tcp_probes.setText(", ".join(current.tcp_probes))
        self.tcp_timeout.setValue(current.tcp_timeout_ms)

        self.dns_hostnames.setText(", ".join(current.dns_hostnames))
        self.dns_timeout.setValue(current.dns_timeout_ms)
        self.enable_public_dns.setChecked(current.enable_public_dns_comparison)
        self.public_dns.setText(", ".join(current.public_dns_servers))
        self.enable_route.setChecked(current.enable_route_trace)
        self.route_target.setText(current.route_target)
        self.route_max_hops.setValue(current.route_max_hops)
        self.route_timeout.setValue(current.route_probe_timeout_ms)

        self.speed_enabled.setChecked(current.speed_test_enabled)
        self.speed_url.setText(current.speed_test_url)
        self.speed_consent.setChecked(current.speed_test_consent)
        self.speed_seconds.setValue(current.speed_test_max_seconds)

        for key, spin in self._threshold_boxes.items():
            spin.setValue(float(current.thresholds.get(key, spin.value())))

        self.history_enabled.setChecked(current.history_enabled)
        self.history_limit.setValue(current.history_limit)

    def collect_settings(self) -> AppSettings:
        """Build an :class:`AppSettings` from the current form values."""
        data = self._settings.to_dict()
        data["theme"] = self.theme_combo.currentData()
        data["ping_count"] = self.ping_count.value()
        data["gateway_count"] = self.gateway_count.value()
        data["ping_interval_ms"] = self.ping_interval.value()
        data["ping_timeout_ms"] = self.ping_timeout.value()
        data["max_workers"] = self.max_workers.value()
        data["internet_targets"] = _split(self.internet_targets.text())
        data["enable_tcp_probes"] = self.enable_tcp.isChecked()
        data["tcp_probes"] = _split(self.tcp_probes.text())
        data["tcp_timeout_ms"] = self.tcp_timeout.value()

        data["dns_hostnames"] = _split(self.dns_hostnames.text())
        data["dns_timeout_ms"] = self.dns_timeout.value()
        data["enable_public_dns_comparison"] = self.enable_public_dns.isChecked()
        data["public_dns_servers"] = _split(self.public_dns.text())
        data["enable_route_trace"] = self.enable_route.isChecked()
        data["route_target"] = self.route_target.text().strip()
        data["route_max_hops"] = self.route_max_hops.value()
        data["route_probe_timeout_ms"] = self.route_timeout.value()

        data["speed_test_enabled"] = self.speed_enabled.isChecked()
        data["speed_test_url"] = self.speed_url.text().strip()
        data["speed_test_consent"] = self.speed_consent.isChecked()
        data["speed_test_max_seconds"] = self.speed_seconds.value()

        data["thresholds"] = {
            key: spin.value() for key, spin in self._threshold_boxes.items()
        }

        data["history_enabled"] = self.history_enabled.isChecked()
        data["history_limit"] = self.history_limit.value()
        return AppSettings.from_dict(data)

    def save(self) -> None:
        updated = self.collect_settings()
        try:
            updated.save()
        except OSError as exc:
            QMessageBox.critical(self, "Settings not saved", f"The settings file could not be written:\n{exc}")
            return
        self._settings.__dict__.update(updated.__dict__)
        self.load_from_settings(self._settings)
        self.settings_saved.emit(self._settings)
        QMessageBox.information(self, "Settings saved", "Your settings were saved locally.")

    def restore_defaults(self) -> None:
        self.load_from_settings(AppSettings())


def _spin(minimum: int, maximum: int, step: int) -> QSpinBox:
    box = QSpinBox()
    box.setRange(minimum, maximum)
    box.setSingleStep(step)
    return box


def _split(text: str) -> list[str]:
    return [part.strip() for part in (text or "").replace(";", ",").split(",") if part.strip()]


__all__ = ["SettingsPage"]
