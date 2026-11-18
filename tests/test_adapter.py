"""Unit tests for app.network.adapter — adapter dump parsing.

The parsing functions are pure, so these tests need neither Windows nor
PowerShell.
"""

from __future__ import annotations

from app.network.adapter import (
    is_wireless_media,
    looks_virtual,
    normalise_media_type,
    parse_adapter_dump,
    parse_link_speed,
    pick_active_adapter,
)

# --------------------------------------------------------------------------- #
# parse_link_speed
# --------------------------------------------------------------------------- #

def test_parse_link_speed_various_units() -> None:
    assert parse_link_speed("1 Gbps") == 1000.0
    assert parse_link_speed("100 Mbps") == 100.0
    assert parse_link_speed("10 Mbps") == 10.0
    assert parse_link_speed("866,7 Mbps") == 866.7  # German decimal comma
    assert parse_link_speed("1.5 Gbps") == 1500.0


def test_parse_link_speed_edge_cases() -> None:
    assert parse_link_speed("") is None
    assert parse_link_speed("unknown") is None
    assert parse_link_speed("0 Mbps") == 0.0


# --------------------------------------------------------------------------- #
# normalise_media_type / is_wireless_media
# --------------------------------------------------------------------------- #

def test_normalise_media_type_wifi() -> None:
    assert normalise_media_type("802.11", "Native 802.11") == "Wi-Fi"
    assert normalise_media_type("Wi-Fi", "") == "Wi-Fi"
    assert normalise_media_type("Wireless", "") == "Wi-Fi"


def test_normalise_media_type_ethernet() -> None:
    assert normalise_media_type("802.3", "Ethernet") == "Ethernet"
    assert normalise_media_type("Ethernet", "") == "Ethernet"


def test_is_wireless_media() -> None:
    assert is_wireless_media("802.11", "") is True
    assert is_wireless_media("Ethernet", "") is False


# --------------------------------------------------------------------------- #
# looks_virtual
# --------------------------------------------------------------------------- #

def test_looks_virtual() -> None:
    assert looks_virtual("vEthernet (Default Switch)", "") is True
    assert looks_virtual("Hyper-V Virtual Adapter", "") is True
    assert looks_virtual("VMware Network Adapter", "") is True
    assert looks_virtual("Ethernet", "") is False
    assert looks_virtual("Wi-Fi", "") is False


# --------------------------------------------------------------------------- #
# parse_adapter_dump
# --------------------------------------------------------------------------- #

def _adapter_dump() -> str:
    return (
        "ADP|Ethernet|Ethernet Controller|Up|1 Gbps|802.3|Ethernet|00-11-22-33-44-55|12\n"
        "IP|12|IPv4|192.168.1.50|24|Preferred\n"
        "GW|12|192.168.1.1\n"
        "DNS|12|IPv4|1.1.1.1,8.8.8.8\n"
        "DHCP|12|Enabled|1500\n"
    )


def test_parse_adapter_dump_basic() -> None:
    snapshot = parse_adapter_dump(_adapter_dump())
    assert len(snapshot.adapters) == 1
    adapter = snapshot.adapters[0]
    assert adapter.name == "Ethernet"
    assert adapter.media_type == "Ethernet"
    assert adapter.status == "Up"
    assert adapter.link_speed_mbps == 1000.0
    assert adapter.link_speed_text == "1 Gbps"
    assert adapter.mac_address == "00-11-22-33-44-55"
    assert adapter.if_index == 12
    assert adapter.ipv4 == ["192.168.1.50/24"]
    assert adapter.gateway == "192.168.1.1"
    assert adapter.dns_servers == ["1.1.1.1", "8.8.8.8"]
    assert adapter.dhcp_enabled is True
    assert adapter.mtu == 1500
    assert adapter.is_wireless is False


def test_parse_adapter_dump_empty() -> None:
    snapshot = parse_adapter_dump("")
    assert snapshot.adapters == []
    assert snapshot.active_adapter is None
    assert "No active network adapter" in snapshot.message


def test_parse_adapter_dump_skips_non_preferred_ip() -> None:
    text = (
        "ADP|Wi-Fi|Wireless Adapter|Up|866,7 Mbps|802.11|Wireless|aa-bb-cc-dd-ee-ff|5\n"
        "IP|5|IPv4|169.254.1.2|16|Invalid\n"  # not preferred/tentative/deprecated -> skipped
        "GW|5|192.168.1.1\n"
    )
    snapshot = parse_adapter_dump(text)
    adapter = snapshot.adapters[0]
    assert adapter.ipv4 == []  # Invalid state filtered out


def test_parse_adapter_dump_filters_link_local_ipv6() -> None:
    text = (
        "ADP|Wi-Fi|Wireless Adapter|Up|866,7 Mbps|802.11|Wireless|aa-bb-cc-dd-ee-ff|5\n"
        "IP|5|IPv6|fe80::1|64|Preferred\n"  # link-local, filtered
        "IP|5|IPv6|2001:db8::1|64|Preferred\n"
        "GW|5|192.168.1.1\n"
    )
    snapshot = parse_adapter_dump(text)
    adapter = snapshot.adapters[0]
    assert "fe80::1" not in adapter.ipv6
    assert "2001:db8::1/64" in adapter.ipv6


# --------------------------------------------------------------------------- #
# pick_active_adapter
# --------------------------------------------------------------------------- #

def test_pick_active_adapter_prefers_gateway_and_ipv4() -> None:
    adapters = [
        # wireless with gateway and ipv4
        type(
            "A",
            (),
            {
                "name": "Wi-Fi",
                "description": "Wi-Fi",
                "gateway": "192.168.1.1",
                "ipv4": ["192.168.1.50"],
                "is_wireless": True,
            },
        )(),
        # ethernet with gateway and ipv4, non-virtual
        type(
            "A",
            (),
            {
                "name": "Ethernet",
                "description": "Ethernet",
                "gateway": "192.168.1.1",
                "ipv4": ["192.168.1.100"],
                "is_wireless": False,
            },
        )(),
    ]
    active = pick_active_adapter(adapters)
    assert active is not None
    assert active.name == "Wi-Fi"  # first physical adapter in the list


def test_pick_active_adapter_empty() -> None:
    assert pick_active_adapter([]) is None
