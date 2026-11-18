"""Network adapter, IP configuration and default-gateway discovery.

Primary source: PowerShell CIM cmdlets, whose *property names* are always
English regardless of the Windows display language. Instead of serialising to
JSON (which silently collapses single-element arrays) NetPulse has the script
emit simple ``|`` delimited records that are parsed by pure functions, so the
parsing logic is fully unit testable.

Fallback source (PowerShell unavailable): ``psutil`` for adapters/addresses and
the IP Helper API (``GetIpForwardTable``) for the default gateway.
"""

from __future__ import annotations

import ctypes
import os
import re
import socket
import struct
from dataclasses import dataclass, field

from app.core.cancellation import CancellationToken
from app.core.models import AdapterInfo
from app.network.proc import powershell_available, run_powershell

# --------------------------------------------------------------------------- #
# PowerShell collection script (read-only)
# --------------------------------------------------------------------------- #

ADAPTER_SCRIPT = r"""
Get-NetAdapter -IncludeHidden:$false -ErrorAction SilentlyContinue |
  Where-Object { $_.Status -eq 'Up' } |
  ForEach-Object {
    "ADP|$($_.Name)|$($_.InterfaceDescription)|$($_.Status)|$($_.LinkSpeed)|$($_.MediaType)|$($_.PhysicalMediaType)|$($_.MacAddress)|$($_.ifIndex)"
  }
Get-NetIPAddress -ErrorAction SilentlyContinue |
  ForEach-Object {
    "IP|$($_.InterfaceIndex)|$($_.AddressFamily)|$($_.IPAddress)|$($_.PrefixLength)|$($_.AddressState)"
  }
Get-NetRoute -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Where-Object { $_.DestinationPrefix -eq '0.0.0.0/0' } |
  ForEach-Object { "GW|$($_.InterfaceIndex)|$($_.NextHop)" }
Get-NetRoute -AddressFamily IPv6 -ErrorAction SilentlyContinue |
  Where-Object { $_.DestinationPrefix -eq '::/0' } |
  ForEach-Object { "GW6|$($_.InterfaceIndex)|$($_.NextHop)" }
Get-DnsClientServerAddress -ErrorAction SilentlyContinue |
  ForEach-Object {
    "DNS|$($_.InterfaceIndex)|$($_.AddressFamily)|$($_.ServerAddresses -join ',')"
  }
Get-NetIPInterface -ErrorAction SilentlyContinue |
  ForEach-Object { "DHCP|$($_.InterfaceIndex)|$($_.Dhcp)|$($_.NlMtu)" }
"""

_SPEED_RE = re.compile(r"([\d]+(?:[.,]\d+)?)\s*([KMGT])?\s*(?:bit|b)?(?:/s|ps)?", re.IGNORECASE)
_UNITS = {"": 1.0, "K": 1e-3, "M": 1.0, "G": 1000.0, "T": 1e6}

WIFI_MEDIA_MARKERS = ("802.11", "wireless", "wi-fi", "wifi", "wlan")
ETHERNET_MEDIA_MARKERS = ("802.3", "ethernet")

#: Interface names that are almost always virtual rather than physical links.
_VIRTUAL_NAME_HINTS = (
    "vethernet",
    "hyper-v",
    "virtual",
    "vmware",
    "virtualbox",
    "loopback",
    "bluetooth",
    "tap-",
    "tun",
    "npcap",
    "wintun",
    "vpn",
    "zerotier",
    "tailscale",
)


def parse_link_speed(text: str) -> float | None:
    """Parse ``"1 Gbps"`` / ``"100 Mbps"`` / ``"866,7 Mbps"`` into Mbps."""
    if not text:
        return None
    match = _SPEED_RE.search(text.strip())
    if not match:
        return None
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:  # pragma: no cover - regex guarantees a number
        return None
    unit = (match.group(2) or "").upper()
    return round(value * _UNITS.get(unit, 1.0), 3)


def normalise_media_type(media_type: str, physical_media_type: str = "") -> str:
    blob = f"{media_type} {physical_media_type}".lower()
    if any(marker in blob for marker in WIFI_MEDIA_MARKERS):
        return "Wi-Fi"
    if any(marker in blob for marker in ETHERNET_MEDIA_MARKERS):
        return "Ethernet"
    return (media_type or physical_media_type or "Unknown").strip()


def is_wireless_media(media_type: str, physical_media_type: str = "") -> bool:
    blob = f"{media_type} {physical_media_type}".lower()
    return any(marker in blob for marker in WIFI_MEDIA_MARKERS)


def looks_virtual(name: str, description: str = "") -> bool:
    blob = f"{name} {description}".lower()
    return any(hint in blob for hint in _VIRTUAL_NAME_HINTS)


@dataclass
class AdapterSnapshot:
    """Everything the local-link test produced."""

    adapters: list[AdapterInfo] = field(default_factory=list)
    active_adapter: AdapterInfo | None = None
    message: str = ""
    source: str = "powershell"

    @property
    def active_name(self) -> str | None:
        return self.active_adapter.name if self.active_adapter else None


def _split_record(line: str) -> list[str]:
    return [part.strip() for part in line.split("|")]


def parse_adapter_dump(text: str) -> AdapterSnapshot:
    """Parse the ``ADP``/``IP``/``GW``/``DNS``/``DHCP`` record dump."""
    snapshot = AdapterSnapshot()
    by_index: dict[int, AdapterInfo] = {}
    order: list[AdapterInfo] = []

    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line or "|" not in line:
            continue
        parts = _split_record(line)
        kind = parts[0].upper()

        if kind == "ADP" and len(parts) >= 9:
            name, description, status, link_speed, media_type, phys, mac, raw_index = parts[1:9]
            index = _safe_int(raw_index)
            adapter = AdapterInfo(
                name=name,
                description=description,
                media_type=normalise_media_type(media_type, phys),
                status=status,
                link_speed_text=link_speed,
                link_speed_mbps=parse_link_speed(link_speed),
                mac_address=mac,
                if_index=index,
                is_wireless=is_wireless_media(media_type, phys),
                source="powershell",
            )
            if index is not None:
                by_index[index] = adapter
            order.append(adapter)

        elif kind == "IP" and len(parts) >= 6:
            index = _safe_int(parts[1])
            family = parts[2].lower()
            address = parts[3]
            prefix = _safe_int(parts[4])
            state = parts[5]
            adapter = by_index.get(index or -1)
            if adapter is None:
                continue
            if state and state.lower() not in ("preferred", "tentative", "deprecated"):
                continue
            if family in ("ipv4", "2"):
                if not adapter.ipv4:
                    adapter.ipv4 = []
                adapter.ipv4.append(f"{address}/{prefix}" if prefix is not None else address)
            elif family in ("ipv6", "23"):
                if address.lower().startswith("fe80"):
                    continue
                adapter.ipv6.append(f"{address}/{prefix}" if prefix is not None else address)

        elif kind in ("GW", "GW6") and len(parts) >= 3:
            index = _safe_int(parts[1])
            next_hop = parts[2]
            adapter = by_index.get(index or -1)
            if (
                adapter is not None
                and next_hop
                and next_hop not in ("0.0.0.0", "::")  # noqa: S104 - excluding unspecified addresses, not binding
                and kind == "GW"
                and adapter.gateway is None
            ):
                adapter.gateway = next_hop

        elif kind == "DNS" and len(parts) >= 4:
            index = _safe_int(parts[1])
            family = parts[2].lower()
            servers = [s for s in parts[3].split(",") if s]
            adapter = by_index.get(index or -1)
            if adapter is not None and family in ("ipv4", "2"):
                for server in servers:
                    if server not in adapter.dns_servers:
                        adapter.dns_servers.append(server)

        elif kind == "DHCP" and len(parts) >= 3:
            index = _safe_int(parts[1])
            dhcp = parts[2].lower()
            mtu = _safe_int(parts[3]) if len(parts) > 3 else None
            adapter = by_index.get(index or -1)
            if adapter is not None:
                if dhcp in ("enabled", "disabled"):
                    adapter.dhcp_enabled = dhcp == "enabled"
                adapter.mtu = mtu

    snapshot.adapters = order
    snapshot.active_adapter = pick_active_adapter(order)
    if not order:
        snapshot.message = "No active network adapter was reported by Windows."
    return snapshot


def _safe_int(value: str) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def pick_active_adapter(adapters: list[AdapterInfo]) -> AdapterInfo | None:
    """Choose the adapter that currently carries the default route."""
    if not adapters:
        return None
    with_gateway = [a for a in adapters if a.gateway and a.ipv4]
    physical = [a for a in with_gateway if not looks_virtual(a.name, a.description)]
    candidates = physical or with_gateway or [a for a in adapters if a.ipv4] or adapters
    return candidates[0]


# --------------------------------------------------------------------------- #
# IP Helper fallback: default gateway + interface list via psutil
# --------------------------------------------------------------------------- #


class _MIB_IPFORWARDROW(ctypes.Structure):
    _fields_ = [
        ("dwForwardDest", ctypes.c_ulong),
        ("dwForwardMask", ctypes.c_ulong),
        ("dwForwardPolicy", ctypes.c_ulong),
        ("dwForwardNextHop", ctypes.c_ulong),
        ("dwForwardIfIndex", ctypes.c_ulong),
        ("dwForwardType", ctypes.c_ulong),
        ("dwForwardProto", ctypes.c_ulong),
        ("dwForwardAge", ctypes.c_ulong),
        ("dwForwardNextHopAS", ctypes.c_ulong),
        ("dwForwardMetric1", ctypes.c_ulong),
        ("dwForwardMetric2", ctypes.c_ulong),
        ("dwForwardMetric3", ctypes.c_ulong),
        ("dwForwardMetric4", ctypes.c_ulong),
        ("dwForwardMetric5", ctypes.c_ulong),
    ]


def default_gateway_ipv4() -> str | None:
    """Return the IPv4 default gateway using the IP Helper API (locale free)."""
    if os.name != "nt":
        return None
    try:
        dll = ctypes.WinDLL("iphlpapi.dll")  # type: ignore[attr-defined]
    except OSError:  # pragma: no cover - non Windows
        return None
    try:
        size = ctypes.c_ulong(0)
        dll.GetIpForwardTable(None, ctypes.byref(size), True)
        if size.value <= 0:
            return None
        buffer = ctypes.create_string_buffer(size.value)
        code = dll.GetIpForwardTable(buffer, ctypes.byref(size), True)
        if code != 0:
            return None
        count = ctypes.c_ulong.from_buffer(buffer).value
        if count <= 0:
            return None
        base_address = ctypes.addressof(buffer) + ctypes.sizeof(ctypes.c_ulong)
        rows = ctypes.cast(base_address, ctypes.POINTER(_MIB_IPFORWARDROW))
        best: tuple[int, str] | None = None
        for index in range(count):
            row = rows[index]
            if row.dwForwardDest != 0 or row.dwForwardMask != 0:
                continue
            if row.dwForwardNextHop == 0:
                continue
            next_hop = socket.inet_ntoa(struct.pack("<L", row.dwForwardNextHop))
            metric = int(row.dwForwardMetric1)
            if best is None or metric < best[0]:
                best = (metric, next_hop)
        return best[1] if best else None
    except Exception:  # pragma: no cover - defensive
        return None


def collect_with_psutil() -> AdapterSnapshot:
    """Degraded adapter collection when PowerShell is unavailable."""
    snapshot = AdapterSnapshot(source="psutil")
    try:
        import psutil
    except ImportError:  # pragma: no cover - psutil is a hard dependency
        snapshot.message = "psutil is not installed; adapter details are unavailable."
        return snapshot

    try:
        addresses = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
    except Exception as exc:  # pragma: no cover - defensive
        snapshot.message = f"Adapter enumeration failed: {exc}"
        return snapshot

    gateway = default_gateway_ipv4()
    for name, addrs in addresses.items():
        stat = stats.get(name)
        if stat is not None and not stat.isup:
            continue
        adapter = AdapterInfo(
            name=name,
            status="Up" if (stat and stat.isup) else "Unknown",
            source="psutil",
        )
        adapter.is_wireless = any(marker in name.lower() for marker in WIFI_MEDIA_MARKERS)
        adapter.media_type = "Wi-Fi" if adapter.is_wireless else "Ethernet"
        if stat is not None and stat.speed:
            adapter.link_speed_mbps = float(stat.speed)
            adapter.link_speed_text = f"{stat.speed} Mbps"
        for addr in addrs:
            family = getattr(addr, "family", None)
            if family == socket.AF_INET:
                adapter.ipv4.append(addr.address)
            elif (
                family == socket.AF_INET6
                and not str(addr.address).lower().startswith("fe80")
            ):
                adapter.ipv6.append(addr.address)
            elif str(family) == "AddressFamily.AF_LINK" or family == getattr(psutil, "AF_LINK", None):
                adapter.mac_address = addr.address
        if adapter.ipv4:
            if gateway and adapter.gateway is None:
                adapter.gateway = gateway
            snapshot.adapters.append(adapter)

    snapshot.adapters.sort(
        key=lambda a: (a.gateway is None, looks_virtual(a.name, a.description))
    )
    snapshot.active_adapter = pick_active_adapter(snapshot.adapters)
    snapshot.message = (
        "PowerShell was unavailable, so NetPulse used a reduced fallback. "
        "DNS servers and DHCP state may be shown as unavailable."
    )
    return snapshot


def collect_adapters(
    token: CancellationToken | None = None, timeout: float = 20.0
) -> AdapterSnapshot:
    """Collect adapter information, degrading gracefully."""
    if powershell_available():
        result = run_powershell(ADAPTER_SCRIPT, timeout=timeout, token=token)
        if result.cancelled:
            snapshot = AdapterSnapshot()
            snapshot.message = "Adapter collection was cancelled."
            return snapshot
        if result.ok or result.stdout.strip():
            snapshot = parse_adapter_dump(result.stdout)
            if snapshot.adapters:
                return snapshot
            snapshot.message = (
                snapshot.message
                or "PowerShell returned no active adapters; using the fallback collector."
            )
        fallback = collect_with_psutil()
        if not fallback.message:
            fallback.message = result.error or "PowerShell adapter query failed."
        return fallback

    return collect_with_psutil()


__all__ = [
    "AdapterSnapshot",
    "collect_adapters",
    "collect_with_psutil",
    "default_gateway_ipv4",
    "is_wireless_media",
    "looks_virtual",
    "normalise_media_type",
    "parse_adapter_dump",
    "parse_link_speed",
    "pick_active_adapter",
]
