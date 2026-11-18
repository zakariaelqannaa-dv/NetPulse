"""User settings with validation and local persistence.

Settings are stored as JSON in the per-user NetPulse data directory. Nothing is
uploaded and the file contains no credentials.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.core.paths import ensure_app_data_dir, settings_path
from app.core.stats import DEFAULT_THRESHOLDS
from app.network.validation import is_valid_host, validate_http_url

THEMES = ("dark", "light")

DEFAULT_INTERNET_TARGETS = ["1.1.1.1", "8.8.8.8"]
DEFAULT_TCP_PROBES = ["1.1.1.1:443", "8.8.8.8:53"]
DEFAULT_DNS_HOSTNAMES = ["google.com", "cloudflare.com"]
DEFAULT_PUBLIC_DNS = ["1.1.1.1", "8.8.8.8"]


@dataclass
class AppSettings:
    """All tunable parameters of a NetPulse diagnosis."""

    theme: str = "dark"

    # Latency probes
    ping_count: int = 30
    ping_interval_ms: int = 1000
    ping_timeout_ms: int = 1000
    gateway_count: int = 30
    max_workers: int = 4
    internet_targets: list[str] = field(default_factory=lambda: list(DEFAULT_INTERNET_TARGETS))
    enable_tcp_probes: bool = True
    tcp_probes: list[str] = field(default_factory=lambda: list(DEFAULT_TCP_PROBES))
    tcp_timeout_ms: int = 3000

    # DNS
    dns_hostnames: list[str] = field(default_factory=lambda: list(DEFAULT_DNS_HOSTNAMES))
    enable_public_dns_comparison: bool = False
    public_dns_servers: list[str] = field(default_factory=lambda: list(DEFAULT_PUBLIC_DNS))
    dns_timeout_ms: int = 3000

    # Route
    enable_route_trace: bool = True
    route_target: str = "1.1.1.1"
    route_max_hops: int = 20
    route_probe_timeout_ms: int = 1000

    # Optional speed test (never automatic)
    speed_test_enabled: bool = False
    speed_test_url: str = ""
    speed_test_consent: bool = False
    speed_test_max_seconds: int = 10

    # History / export
    history_enabled: bool = True
    history_limit: int = 50
    redacted_fields: list[str] = field(default_factory=list)

    # Rating thresholds (ms / percent)
    thresholds: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_THRESHOLDS))

    # ------------------------------------------------------------------ #

    def normalized(self) -> AppSettings:
        """Return a copy with every value clamped/validated."""
        settings = AppSettings(**{k: v for k, v in asdict(self).items()})
        settings.theme = self.theme if self.theme in THEMES else "dark"
        settings.ping_count = _clamp(self.ping_count, 1, 500, 30)
        settings.gateway_count = _clamp(self.gateway_count, 1, 500, 30)
        settings.ping_interval_ms = _clamp(self.ping_interval_ms, 50, 10000, 1000)
        settings.ping_timeout_ms = _clamp(self.ping_timeout_ms, 100, 10000, 1000)
        settings.max_workers = _clamp(self.max_workers, 1, 8, 4)
        settings.tcp_timeout_ms = _clamp(self.tcp_timeout_ms, 200, 15000, 3000)
        settings.dns_timeout_ms = _clamp(self.dns_timeout_ms, 200, 15000, 3000)
        settings.route_max_hops = _clamp(self.route_max_hops, 1, 64, 20)
        settings.route_probe_timeout_ms = _clamp(self.route_probe_timeout_ms, 100, 5000, 1000)
        settings.history_limit = _clamp(self.history_limit, 1, 500, 50)
        settings.speed_test_max_seconds = _clamp(self.speed_test_max_seconds, 3, 60, 10)

        settings.internet_targets = _clean_hosts(self.internet_targets, DEFAULT_INTERNET_TARGETS, minimum=2)
        settings.dns_hostnames = _clean_hostnames(self.dns_hostnames, DEFAULT_DNS_HOSTNAMES)
        settings.public_dns_servers = _clean_ips(self.public_dns_servers, DEFAULT_PUBLIC_DNS)
        settings.tcp_probes = _clean_probes(self.tcp_probes, DEFAULT_TCP_PROBES)
        settings.route_target = (
            self.route_target if is_valid_host(self.route_target or "") else "1.1.1.1"
        )
        if self.speed_test_url:
            try:
                settings.speed_test_url = validate_http_url(self.speed_test_url)
            except ValueError:
                settings.speed_test_url = ""
        if not settings.speed_test_url:
            settings.speed_test_enabled = False
            settings.speed_test_consent = False
        if not settings.speed_test_consent:
            settings.speed_test_enabled = False

        merged = dict(DEFAULT_THRESHOLDS)
        for key, value in (self.thresholds or {}).items():
            if key in merged:
                try:
                    merged[key] = float(value)
                except (TypeError, ValueError):
                    continue
        settings.thresholds = merged
        settings.redacted_fields = [str(f) for f in (self.redacted_fields or [])]
        return settings

    # ------------------------------------------------------------------ #

    def to_dict(self) -> dict[str, Any]:
        return asdict(self.normalized())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppSettings:
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        try:
            return cls(**filtered).normalized()
        except TypeError:
            return cls().normalized()

    def load(self, path: Path | None = None) -> AppSettings:
        target = path or settings_path()
        try:
            raw = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return self.normalized()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return self.normalized()
        loaded = AppSettings.from_dict(data if isinstance(data, dict) else {})
        self.__dict__.update(loaded.__dict__)
        return loaded

    def save(self, path: Path | None = None) -> Path:
        target = path or settings_path()
        if path is None:
            ensure_app_data_dir()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target


def _clamp(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(minimum, min(number, maximum))


def _clean_hosts(values: list[str], fallback: list[str], minimum: int = 1) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        candidate = str(value).strip()
        if candidate and is_valid_host(candidate) and candidate not in cleaned:
            cleaned.append(candidate)
    if len(cleaned) < minimum:
        for value in fallback:
            if value not in cleaned:
                cleaned.append(value)
    return cleaned


def _clean_hostnames(values: list[str], fallback: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        candidate = str(value).strip()
        if not candidate:
            continue
        if is_valid_host(candidate) and candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned or list(fallback)


def _clean_ips(values: list[str], fallback: list[str]) -> list[str]:
    from app.network.validation import is_valid_ip

    cleaned: list[str] = []
    for value in values or []:
        candidate = str(value).strip()
        if is_valid_ip(candidate) and candidate not in cleaned:
            cleaned.append(candidate)
    return cleaned or list(fallback)


def _clean_probes(values: list[str], fallback: list[str]) -> list[str]:
    from app.network.validation import validate_port

    cleaned: list[str] = []
    for value in values or []:
        candidate = str(value).strip()
        if ":" not in candidate:
            continue
        host, _, port = candidate.rpartition(":")
        try:
            validate_port(port)
        except ValueError:
            continue
        if is_valid_host(host):
            entry = f"{host}:{port}"
            if entry not in cleaned:
                cleaned.append(entry)
    return cleaned or list(fallback)


def parse_probe(entry: str) -> tuple[str, int]:
    host, _, port = entry.rpartition(":")
    return host, int(port)


__all__ = [
    "AppSettings",
    "DEFAULT_DNS_HOSTNAMES",
    "DEFAULT_INTERNET_TARGETS",
    "DEFAULT_PUBLIC_DNS",
    "DEFAULT_TCP_PROBES",
    "THEMES",
    "parse_probe",
]
