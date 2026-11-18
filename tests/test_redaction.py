"""Unit tests for app.reporting.redaction — sensitive field redaction.

Pure logic; no network or Windows required.
"""

from __future__ import annotations

from app.reporting.redaction import (
    PLACEHOLDERS,
    collect_sensitive_fields,
    default_selection,
    redact_report_data,
)


def _base_report() -> dict:
    return {
        "host": {"computer_name": "DESKTOP-ABC123"},
        "active_adapter_name": "Ethernet",
        "adapters": [
            {
                "name": "Ethernet",
                "description": "Intel Ethernet Controller",
                "mac_address": "00-11-22-33-44-55",
                "gateway": "192.168.1.1",
                "ipv4": ["192.168.1.50/24"],
                "ipv6": [],
                "dns_servers": ["1.1.1.1", "8.8.8.8"],
            }
        ],
        "wifi": {"ssid": "MyHomeNetwork", "bssid": "aa:bb:cc:dd:ee:ff"},
        "route": {"resolved_ip": "1.1.1.1", "hops": [{"address": "192.168.1.1"}, {"address": "10.0.0.1"}]},
        "speed_test": {"url": "https://example.com/test.bin"},
        "diagnoses": [
            {"rule_id": "GW-002", "finding": "Loss to gateway 192.168.1.1", "evidence": ["gateway 192.168.1.1 loss 5%"]}
        ],
    }


def test_collect_sensitive_fields_finds_all() -> None:
    fields = collect_sensitive_fields(_base_report())
    keys = {f.key for f in fields}
    assert keys == set(PLACEHOLDERS)
    by_key = {f.key: f for f in fields}
    assert "DESKTOP-ABC123" in by_key["computer_name"].values
    assert "Ethernet" in by_key["adapter_names"].values
    assert "192.168.1.1" in by_key["gateway"].values
    assert "192.168.1.50" in by_key["local_ipv4"].values
    assert "MyHomeNetwork" in by_key["wifi_ssid"].values
    assert "https://example.com/test.bin" in by_key["speed_test_url"].values


def test_redact_structural_pass() -> None:
    report = _base_report()
    redacted = redact_report_data(report, {"computer_name", "gateway", "wifi_ssid"})

    assert redacted["host"]["computer_name"] == PLACEHOLDERS["computer_name"]
    assert redacted["adapters"][0]["gateway"] == PLACEHOLDERS["gateway"]
    assert redacted["wifi"]["ssid"] == PLACEHOLDERS["wifi_ssid"]
    # Non-selected fields untouched
    assert redacted["adapters"][0]["ipv4"] == ["192.168.1.50/24"]
    assert redacted["speed_test"]["url"] == "https://example.com/test.bin"


def test_redact_text_pass_scrubs_evidence() -> None:
    report = _base_report()
    redacted = redact_report_data(report, {"gateway"})
    evidence = redacted["diagnoses"][0]["evidence"][0]
    assert "192.168.1.1" not in evidence
    assert "[redacted-gateway]" in evidence


def test_redact_adapter_names_positional() -> None:
    report = _base_report()
    redacted = redact_report_data(report, {"adapter_names"})
    assert redacted["active_adapter_name"] == "[adapter-1]"
    assert redacted["adapters"][0]["name"] == "[adapter-1]"


def test_default_selection_only_fields_with_values() -> None:
    report = _base_report()
    fields = collect_sensitive_fields(report)
    selected = default_selection(fields)
    # All fields with values in _base_report should be selected (local_ipv6 and public_ip are empty)
    expected = set(PLACEHOLDERS) - {"local_ipv6", "public_ip"}
    assert selected == expected


def test_placeholder_values() -> None:
    assert PLACEHOLDERS["computer_name"] == "[redacted-computer-name]"
    assert PLACEHOLDERS["wifi_ssid"] == "[redacted-ssid]"
    assert PLACEHOLDERS["speed_test_url"] == "[redacted-url]"
