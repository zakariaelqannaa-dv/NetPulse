"""Report redaction.

NetPulse shows the user exactly which potentially identifying values are
included in a report and lets them redact any of them before exporting.

Redaction is two-layered:

1. a *structural* pass replaces the values of known fields (adapter names,
   addresses, gateway, DNS servers, SSID, computer name, ...);
2. a *text* pass replaces the original values that also appear inside generated
   sentences (for example diagnosis evidence), skipping short generic words so
   the report stays readable.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

PLACEHOLDERS: dict[str, str] = {
    "computer_name": "[redacted-computer-name]",
    "local_ipv4": "[redacted-ipv4]",
    "local_ipv6": "[redacted-ipv6]",
    "gateway": "[redacted-gateway]",
    "dns_servers": "[redacted-dns]",
    "mac_addresses": "[redacted-mac]",
    "adapter_names": "[redacted-adapter]",
    "adapter_descriptions": "[redacted-adapter-model]",
    "wifi_ssid": "[redacted-ssid]",
    "wifi_bssid": "[redacted-bssid]",
    "public_ip": "[redacted-public-ip]",
    "route_hop_addresses": "[redacted-hop]",
    "speed_test_url": "[redacted-url]",
}

FIELD_LABELS: dict[str, str] = {
    "computer_name": "Computer name",
    "local_ipv4": "Local IPv4 address(es)",
    "local_ipv6": "Local IPv6 address(es)",
    "gateway": "Default gateway",
    "dns_servers": "DNS server addresses",
    "mac_addresses": "Adapter MAC address(es)",
    "adapter_names": "Adapter name(s)",
    "adapter_descriptions": "Adapter model/description",
    "wifi_ssid": "Wi-Fi network name (SSID)",
    "wifi_bssid": "Wi-Fi access point MAC (BSSID)",
    "public_ip": "Public IP address (if discovered)",
    "route_hop_addresses": "Route trace hop addresses",
    "speed_test_url": "Speed test URL",
}

FIELD_DESCRIPTIONS: dict[str, str] = {
    "computer_name": "The Windows computer name of this PC.",
    "local_ipv4": "Private IPv4 addresses of the active adapter.",
    "local_ipv6": (
        "Global IPv6 addresses of the active adapter "
        "(link-local addresses are already excluded)."
    ),
    "gateway": "The address of your router on the local network.",
    "dns_servers": "The DNS resolvers configured on the adapter.",
    "mac_addresses": "Hardware addresses of the network adapters.",
    "adapter_names": "Windows names of the network adapters.",
    "adapter_descriptions": "Adapter model strings, which can identify your hardware.",
    "wifi_ssid": "The Wi-Fi network you were connected to.",
    "wifi_bssid": "The hardware address of the Wi-Fi access point.",
    "public_ip": "NetPulse does not look up your public IP; this entry is listed for completeness.",
    "route_hop_addresses": (
        "Router addresses along the traced path, which can identify your ISP "
        "and region."
    ),
    "speed_test_url": "The download URL you entered for the optional speed test.",
}

#: Values shorter than this, or generic network words, are never text-replaced,
#: so the report stays readable.
_TEXT_MIN_LENGTH = 4
_GENERIC_VALUES = {
    "ethernet",
    "wi-fi",
    "wifi",
    "wlan",
    "lan",
    "wan",
    "local area connection",
    "local area connection* 1",
    "system",
    "loopback",
    "unknown",
    "unavailable",
    "none",
}


@dataclass
class SensitiveField:
    """One redactable field together with the values found in the report."""

    key: str
    label: str
    description: str
    values: list[str] = field(default_factory=list)

    @property
    def placeholder(self) -> str:
        return PLACEHOLDERS.get(self.key, "[redacted]")

    @property
    def has_values(self) -> bool:
        return bool(self.values)

    def display_values(self) -> str:
        if not self.values:
            return "not present in this report"
        shown = self.values[:4]
        text = ", ".join(shown)
        if len(self.values) > len(shown):
            text += f" (+{len(self.values) - len(shown)} more)"
        return text


def _add(target: dict[str, list[str]], key: str, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if not text or text.startswith("["):
        return
    bucket = target.setdefault(key, [])
    if text not in bucket:
        bucket.append(text)


def collect_sensitive_fields(report_data: dict[str, Any]) -> list[SensitiveField]:
    """Return every redactable field present in an exported report."""
    found: dict[str, list[str]] = {}

    host = report_data.get("host") or {}
    _add(found, "computer_name", host.get("computer_name"))

    active = report_data.get("active_adapter") or {}
    _add(found, "adapter_names", report_data.get("active_adapter_name"))
    for adapter in report_data.get("adapters") or []:
        _add(found, "adapter_names", adapter.get("name"))
        _add(found, "adapter_descriptions", adapter.get("description"))
        _add(found, "mac_addresses", adapter.get("mac_address"))
        _add(found, "gateway", adapter.get("gateway"))
        for address in adapter.get("ipv4") or []:
            _add(found, "local_ipv4", address)
            _add(found, "local_ipv4", str(address).split("/")[0])
        for address in adapter.get("ipv6") or []:
            _add(found, "local_ipv6", address)
        for server in adapter.get("dns_servers") or []:
            _add(found, "dns_servers", server)

    if not active and report_data.get("adapters"):
        active = (report_data.get("adapters") or [{}])[0]

    wifi = report_data.get("wifi") or {}
    _add(found, "wifi_ssid", wifi.get("ssid"))
    _add(found, "wifi_bssid", wifi.get("bssid"))

    route = report_data.get("route") or {}
    for hop in route.get("hops") or []:
        address = hop.get("address")
        if address and address != route.get("resolved_ip"):
            _add(found, "route_hop_addresses", address)

    speed = report_data.get("speed_test") or {}
    _add(found, "speed_test_url", speed.get("url"))

    fields: list[SensitiveField] = []
    for key in PLACEHOLDERS:
        fields.append(
            SensitiveField(
                key=key,
                label=FIELD_LABELS.get(key, key),
                description=FIELD_DESCRIPTIONS.get(key, ""),
                values=found.get(key, []),
            )
        )
    return fields


def _positional_placeholder(key: str, index: int) -> str:
    if key == "adapter_names":
        return f"[adapter-{index + 1}]"
    return PLACEHOLDERS.get(key, "[redacted]")


def redact_report_data(
    report_data: dict[str, Any],
    selected_keys: Iterable[str],
    collected: list[SensitiveField] | None = None,
) -> dict[str, Any]:
    """Return a deep-copied report with the selected fields redacted."""
    selected = set(selected_keys)
    fields = collected if collected is not None else collect_sensitive_fields(report_data)
    originals: dict[str, str] = {}
    for item in fields:
        if item.key in selected:
            for value in item.values:
                originals.setdefault(value, item.placeholder)

    redacted = copy.deepcopy(report_data)

    # ---- structural pass -------------------------------------------------- #
    if "computer_name" in selected:
        host = redacted.setdefault("host", {})
        if host.get("computer_name"):
            host["computer_name"] = PLACEHOLDERS["computer_name"]

    adapters = redacted.get("adapters") or []
    for index, adapter in enumerate(adapters):
        if "adapter_names" in selected and adapter.get("name"):
            adapter["name"] = _positional_placeholder("adapter_names", index)
        if "adapter_descriptions" in selected and adapter.get("description"):
            adapter["description"] = PLACEHOLDERS["adapter_descriptions"]
        if "mac_addresses" in selected and adapter.get("mac_address"):
            adapter["mac_address"] = PLACEHOLDERS["mac_addresses"]
        if "gateway" in selected and adapter.get("gateway"):
            adapter["gateway"] = PLACEHOLDERS["gateway"]
        if "local_ipv4" in selected and adapter.get("ipv4"):
            adapter["ipv4"] = [PLACEHOLDERS["local_ipv4"] for _ in adapter["ipv4"]]
        if "local_ipv6" in selected and adapter.get("ipv6"):
            adapter["ipv6"] = [PLACEHOLDERS["local_ipv6"] for _ in adapter["ipv6"]]
        if "dns_servers" in selected and adapter.get("dns_servers"):
            adapter["dns_servers"] = [PLACEHOLDERS["dns_servers"] for _ in adapter["dns_servers"]]

    if "adapter_names" in selected and redacted.get("active_adapter_name"):
        redacted["active_adapter_name"] = _positional_placeholder("adapter_names", 0)

    wifi = redacted.get("wifi") or {}
    if "wifi_ssid" in selected and wifi.get("ssid"):
        wifi["ssid"] = PLACEHOLDERS["wifi_ssid"]
    if "wifi_bssid" in selected and wifi.get("bssid"):
        wifi["bssid"] = PLACEHOLDERS["wifi_bssid"]

    route = redacted.get("route") or {}
    if "route_hop_addresses" in selected:
        for hop in route.get("hops") or []:
            if hop.get("address"):
                hop["address"] = PLACEHOLDERS["route_hop_addresses"]

    speed = redacted.get("speed_test") or {}
    if "speed_test_url" in selected and speed.get("url"):
        speed["url"] = PLACEHOLDERS["speed_test_url"]

    # ---- text pass (diagnosis sentences, warnings, messages) -------------- #
    text_map = {
        value: placeholder
        for value, placeholder in originals.items()
        if _worth_text_replacing(value)
    }
    if text_map:
        redacted = _replace_in_strings(redacted, text_map)

    redacted["redacted_fields"] = sorted(selected)
    return redacted


def _worth_text_replacing(value: str) -> bool:
    """Decide whether a redacted value should also be scrubbed from sentences.

    Short values and generic network words are left in place so the report stays
    readable, but any distinctive value (an SSID, adapter name, computer name,
    address, ...) is replaced wherever it appears — including inside the
    generated diagnosis evidence.
    """
    if len(value) < _TEXT_MIN_LENGTH:
        return False
    return value.lower() not in _GENERIC_VALUES


def _replace_in_strings(node: Any, replacements: dict[str, str]) -> Any:
    if isinstance(node, str):
        result = node
        for value in sorted(replacements, key=len, reverse=True):
            if value in result:
                result = result.replace(value, replacements[value])
        return result
    if isinstance(node, list):
        return [_replace_in_strings(item, replacements) for item in node]
    if isinstance(node, dict):
        return {key: _replace_in_strings(value, replacements) for key, value in node.items()}
    return node


def default_selection(fields: list[SensitiveField]) -> set[str]:
    """Fields pre-selected in the export dialog (those actually present)."""
    return {f.key for f in fields if f.has_values}


__all__ = [
    "FIELD_DESCRIPTIONS",
    "FIELD_LABELS",
    "PLACEHOLDERS",
    "SensitiveField",
    "collect_sensitive_fields",
    "default_selection",
    "redact_report_data",
]
