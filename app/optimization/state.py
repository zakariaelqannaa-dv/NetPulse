"""Read-only collection of Windows network settings.

Everything in this module only *reads*: it queries Windows, parses the answer
and turns it into :class:`~app.optimization.models.NetworkCheck` objects. No
setting is ever modified here.

PowerShell CIM cmdlets are used where possible because their property names are
always English, which keeps parsing correct on non-English Windows installs.
A locale-independent token scan is used as a fallback for ``netsh`` output.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.core.cancellation import CancellationToken
from app.core.models import Severity
from app.network.proc import CommandResult, run_command, run_powershell
from app.optimization.models import NetworkCheck

# --------------------------------------------------------------------------- #
# Command execution
# --------------------------------------------------------------------------- #


@dataclass
class CommandExecutor:
    """Thin, injectable wrapper so the whole module can be unit tested.

    Tests substitute an executor that records commands and returns canned
    output instead of touching the real machine.
    """

    token: CancellationToken | None = None
    timeout: float = 25.0

    def args(self, argv: Sequence[str]) -> CommandResult:
        return run_command(argv, timeout=self.timeout, token=self.token)

    def ps(self, script: str) -> CommandResult:
        return run_powershell(script, timeout=self.timeout, token=self.token)


# --------------------------------------------------------------------------- #
# Pure parsers (unit tested directly)
# --------------------------------------------------------------------------- #


def parse_key_value_output(text: str) -> dict[str, str]:
    """Parse ``key|value`` lines emitted by the PowerShell probes."""
    result: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        key, _, value = line.partition("|")
        key = key.strip().lower()
        value = value.strip()
        if key:
            result[key] = value
    return result


#: Value vocabularies used to recognise ``netsh`` rows regardless of language.
_AUTOTUNING_TOKENS = {"normal", "disabled", "restricted", "highlyrestricted", "experimental"}
_TIMESTAMP_TOKENS = {"enabled", "disabled"}


def parse_netsh_tcp_global(text: str) -> dict[str, str]:
    """Extract auto-tuning level from ``netsh int tcp show global``.

    The label text is localised, but the *values* (``normal``, ``disabled``,
    ``restricted``, ``highlyrestricted``, ``experimental``) are stable across
    languages, so the scan is done on values rather than labels.
    """
    values: dict[str, str] = {}
    for raw_line in (text or "").splitlines():
        if ":" not in raw_line:
            continue
        _, _, value = raw_line.rpartition(":")
        token = value.strip().lower()
        if token in _AUTOTUNING_TOKENS and "autotuning" not in values:
            values["autotuning"] = token
    return values


def _truthy(text: str) -> bool | None:
    token = (text or "").strip().lower()
    if token in {"true", "1", "yes", "enabled"}:
        return True
    if token in {"false", "0", "no", "disabled"}:
        return False
    return None


def _clean_servers(text: str) -> list[str]:
    servers: list[str] = []
    for item in (text or "").replace(",", " ").split():
        candidate = item.strip()
        if candidate and candidate not in servers:
            servers.append(candidate)
    return servers


# --------------------------------------------------------------------------- #
# Windows probes
# --------------------------------------------------------------------------- #

_TCP_SCRIPT = (
    "$t = Get-NetTCPSetting -SettingName Internet -ErrorAction SilentlyContinue;"
    "if ($null -eq $t) { $t = Get-NetTCPSetting -ErrorAction SilentlyContinue | "
    "Sort-Object -Property SettingName | Select-Object -First 1 };"
    "if ($t) {"
    "  'autotuning|' + [string]$t.AutoTuningLevelLocal;"
    "  'ecn|' + [string]$t.EcnCapability;"
    "  'congestion|' + [string]$t.CongestionProvider;"
    "  'minrto|' + [string]$t.MinRto"
    "}"
)

_RSS_SCRIPT = (
    "$r = Get-NetAdapterRss -Name __ADAPTER__ -ErrorAction SilentlyContinue;"
    "if ($r) { 'rss|' + [string]$r.Enabled }"
)

_POWER_SCRIPT = (
    "$p = Get-NetAdapterPowerManagement -Name __ADAPTER__ -ErrorAction SilentlyContinue;"
    "if ($p) { 'powersave|' + [string]$p.AllowComputerToTurnOffDevice }"
)

_DNS_SCRIPT = (
    "Get-DnsClientServerAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | "
    "ForEach-Object { 'dns|' + $_.InterfaceAlias + '|' + ([string]::Join(',', $_.ServerAddresses)) }"
)

_PROXY_SCRIPT = (
    "$k = Get-ItemProperty -Path "
    "'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Internet Settings' "
    "-ErrorAction SilentlyContinue;"
    "'proxyenable|' + [string]$k.ProxyEnable;"
    "'proxyserver|' + [string]$k.ProxyServer;"
    "'autoconfigurl|' + [string]$k.AutoConfigURL"
)

_IPV6_SCRIPT = (
    "$c = Get-NetAdapterBinding -ComponentID ms_tcpip6 -ErrorAction SilentlyContinue | "
    "Where-Object { $_.Enabled -eq $true };"
    "if ($c) { 'ipv6|enabled' } else { 'ipv6|disabled' }"
)


def _ps_quote(value: str) -> str:
    """Inline a value into a PowerShell single-quoted literal."""
    return "'" + str(value).replace("'", "''") + "'"


@dataclass
class NetworkState:
    """Everything readable about the current network configuration."""

    adapter_name: str = ""
    tcp: dict[str, str] = field(default_factory=dict)
    rss_enabled: bool | None = None
    power_save_enabled: bool | None = None
    dns_servers: list[str] = field(default_factory=list)
    dns_by_interface: dict[str, list[str]] = field(default_factory=dict)
    proxy_enabled: bool | None = None
    proxy_server: str = ""
    auto_config_url: str = ""
    ipv6_enabled: bool | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "adapter_name": self.adapter_name,
            "tcp": dict(self.tcp),
            "rss_enabled": self.rss_enabled,
            "power_save_enabled": self.power_save_enabled,
            "dns_servers": list(self.dns_servers),
            "proxy_enabled": self.proxy_enabled,
            "proxy_server": self.proxy_server,
            "auto_config_url": self.auto_config_url,
            "ipv6_enabled": self.ipv6_enabled,
            "errors": list(self.errors),
        }


def collect_state(
    adapter_name: str = "",
    executor: CommandExecutor | None = None,
) -> NetworkState:
    """Read the current Windows network settings (never modifies anything)."""
    runner = executor or CommandExecutor()
    state = NetworkState(adapter_name=adapter_name)

    result = runner.ps(_TCP_SCRIPT)
    if result.ok and result.stdout.strip():
        state.tcp = parse_key_value_output(result.stdout)
    else:
        fallback = runner.args(["netsh", "int", "tcp", "show", "global"])
        if fallback.ok:
            state.tcp.update(parse_netsh_tcp_global(fallback.stdout))
        else:
            state.errors.append("TCP global parameters could not be read.")

    if adapter_name:
        rss = runner.ps(_RSS_SCRIPT.replace("__ADAPTER__", _ps_quote(adapter_name)))
        if rss.ok and rss.stdout.strip():
            parsed = parse_key_value_output(rss.stdout)
            state.rss_enabled = _truthy(parsed.get("rss", ""))
        else:
            state.errors.append("Receive Side Scaling state could not be read for this adapter.")

        power = runner.ps(_POWER_SCRIPT.replace("__ADAPTER__", _ps_quote(adapter_name)))
        if power.ok and power.stdout.strip():
            parsed = parse_key_value_output(power.stdout)
            state.power_save_enabled = _truthy(parsed.get("powersave", ""))
        else:
            state.errors.append("Adapter power management could not be read for this adapter.")

    dns = runner.ps(_DNS_SCRIPT)
    if dns.ok:
        for line in dns.stdout.splitlines():
            parts = line.strip().split("|")
            if len(parts) == 3 and parts[0].strip().lower() == "dns":
                interface, servers = parts[1].strip(), _clean_servers(parts[2])
                if interface:
                    state.dns_by_interface[interface] = servers
    if adapter_name and adapter_name in state.dns_by_interface:
        state.dns_servers = list(state.dns_by_interface[adapter_name])
    elif state.dns_by_interface:
        state.dns_servers = next(iter(state.dns_by_interface.values()))

    proxy = runner.ps(_PROXY_SCRIPT)
    if proxy.ok:
        parsed = parse_key_value_output(proxy.stdout)
        state.proxy_enabled = _truthy(parsed.get("proxyenable", ""))
        state.proxy_server = "" if parsed.get("proxyserver", "") in {"", "None"} else parsed["proxyserver"]
        state.auto_config_url = (
            "" if parsed.get("autoconfigurl", "") in {"", "None"} else parsed["autoconfigurl"]
        )

    ipv6 = runner.ps(_IPV6_SCRIPT)
    if ipv6.ok and ipv6.stdout.strip():
        state.ipv6_enabled = parse_key_value_output(ipv6.stdout).get("ipv6", "") == "enabled"
        if state.ipv6_enabled is False:
            # Binding state alone is not proof; report it as unknown rather than a fault.
            state.ipv6_enabled = None

    return state


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #

_AUTOTUNING_LABELS = {
    "normal": "Normal (Windows default)",
    "disabled": "Disabled",
    "restricted": "Restricted",
    "highlyrestricted": "Highly restricted",
    "experimental": "Experimental",
}


def build_checks(state: NetworkState, link_speed_mbps: float | None = None, is_wireless: bool = False) -> list[NetworkCheck]:
    """Turn a :class:`NetworkState` into explained, user-facing checks."""
    checks: list[NetworkCheck] = []

    level = (state.tcp.get("autotuning") or "").strip().lower()
    if level:
        is_default = level == "normal"
        checks.append(
            NetworkCheck(
                check_id="tcp-autotuning",
                title="Receive Window Auto-Tuning",
                category="tcp",
                current_value=_AUTOTUNING_LABELS.get(level, level.title()),
                status=Severity.GOOD if is_default else Severity.WARNING,
                is_default=is_default,
                explanation=(
                    "Windows adjusts the TCP receive window to match the connection when auto-tuning is "
                    "Normal. 'Optimizer' tools and old tweak guides often disable it, which can cap download "
                    "throughput on links with higher latency."
                ),
                finding=(
                    ""
                    if is_default
                    else f"Receive Window Auto-Tuning is set to '{_AUTOTUNING_LABELS.get(level, level)}' instead of the Windows default 'Normal'."
                ),
                recommendation=(
                    ""
                    if is_default
                    else "Restore the Windows default unless a specific application documents a reason to keep it changed."
                ),
                action_id=None if is_default else "tcp-autotuning-normal",
            )
        )
    else:
        checks.append(
            NetworkCheck(
                check_id="tcp-autotuning",
                title="Receive Window Auto-Tuning",
                category="tcp",
                current_value="unavailable",
                status=Severity.UNKNOWN,
                explanation="NetPulse could not read the TCP auto-tuning level on this system.",
                recommendation="No action: this value is only informational.",
            )
        )

    ecn = (state.tcp.get("ecn") or "").strip().lower()
    if ecn:
        checks.append(
            NetworkCheck(
                check_id="tcp-ecn",
                title="Explicit Congestion Notification (ECN)",
                category="tcp",
                current_value=ecn.title(),
                status=Severity.INFO,
                is_default=ecn == "disabled",
                explanation=(
                    "ECN is an optional TCP feature that can reduce retransmissions, but it depends on every "
                    "device on the path supporting it. Windows keeps it disabled by default."
                ),
                recommendation="No change recommended: leave this at the Windows default.",
            )
        )

    congestion = (state.tcp.get("congestion") or "").strip()
    if congestion:
        checks.append(
            NetworkCheck(
                check_id="tcp-congestion",
                title="Congestion control provider",
                category="tcp",
                current_value=congestion,
                status=Severity.INFO,
                explanation=(
                    "The default provider (CTCP) is tuned for broadband. Third-party providers can behave "
                    "unexpectedly on some links."
                ),
                recommendation="No change recommended unless a vendor explicitly requires a different provider.",
            )
        )

    if state.rss_enabled is None:
        checks.append(
            NetworkCheck(
                check_id="rss",
                title="Receive Side Scaling (RSS)",
                category="adapter",
                current_value="unavailable",
                status=Severity.UNKNOWN,
                explanation="RSS spreads network processing across CPU cores. It could not be read for this adapter.",
                recommendation="No action: this value is only informational.",
            )
        )
    else:
        checks.append(
            NetworkCheck(
                check_id="rss",
                title="Receive Side Scaling (RSS)",
                category="adapter",
                current_value="Enabled" if state.rss_enabled else "Disabled",
                status=Severity.GOOD if state.rss_enabled else Severity.INFO,
                is_default=state.rss_enabled,
                explanation=(
                    "RSS lets several CPU cores handle network interrupts. Enabling it can help throughput on "
                    "fast links, but it changes nothing on a slow or single-core connection."
                ),
                finding="" if state.rss_enabled else "RSS is disabled on the active adapter.",
                recommendation=(
                    ""
                    if state.rss_enabled
                    else "Optional: enabling RSS is reversible and usually beneficial on gigabit links."
                ),
                action_id=None if state.rss_enabled else "rss-enable",
            )
        )

    if state.power_save_enabled is None:
        checks.append(
            NetworkCheck(
                check_id="adapter-power-saving",
                title="Adapter power saving",
                category="adapter",
                current_value="unavailable",
                status=Severity.UNKNOWN,
                explanation="NetPulse could not read whether Windows may power down this adapter.",
                recommendation="No action: this value is only informational.",
            )
        )
    else:
        checks.append(
            NetworkCheck(
                check_id="adapter-power-saving",
                title="Adapter power saving",
                category="adapter",
                current_value="Windows may turn the device off" if state.power_save_enabled else "Always on",
                status=Severity.WARNING if state.power_save_enabled else Severity.GOOD,
                is_default=not state.power_save_enabled,
                explanation=(
                    "On laptops Windows may power down an idle network adapter. This is a common cause of "
                    "short disconnects or a few seconds of packet loss after the machine has been idle."
                ),
                finding=(
                    "Windows is allowed to turn off this network adapter to save power."
                    if state.power_save_enabled
                    else ""
                ),
                recommendation=(
                    "If you see short dropouts after being idle, turning this off is a safe, reversible change."
                    if state.power_save_enabled
                    else ""
                ),
                action_id="adapter-power-saving-off" if state.power_save_enabled else None,
            )
        )

    if state.dns_servers:
        checks.append(
            NetworkCheck(
                check_id="dns-servers",
                title="Configured DNS servers",
                category="dns",
                current_value=", ".join(state.dns_servers),
                status=Severity.INFO,
                explanation=(
                    "These are the resolvers Windows uses to turn names into IP addresses. Changing DNS can "
                    "affect how quickly a page starts loading, but never the ping to an address that is "
                    "already resolved."
                ),
                recommendation="Only consider changing DNS if the report shows slow lookups and a public resolver was measurably faster.",
            )
        )

    if state.proxy_enabled is None:
        checks.append(
            NetworkCheck(
                check_id="proxy",
                title="Proxy configuration",
                category="proxy",
                current_value="unavailable",
                status=Severity.UNKNOWN,
                explanation="NetPulse could not read the per-user proxy settings.",
                recommendation="No action: this value is only informational.",
            )
        )
    else:
        detail = state.proxy_server or state.auto_config_url
        checks.append(
            NetworkCheck(
                check_id="proxy",
                title="Proxy configuration",
                category="proxy",
                current_value=("Enabled" + (f" ({detail})" if detail else "")) if state.proxy_enabled else "Direct connection",
                status=Severity.WARNING if state.proxy_enabled else Severity.GOOD,
                is_default=not state.proxy_enabled,
                explanation=(
                    "A proxy server left behind by a VPN, adware or a corporate configuration can silently "
                    "break or slow down internet access for normal apps."
                ),
                finding="A proxy server is configured for this user account." if state.proxy_enabled else "",
                recommendation=(
                    "If you did not configure this proxy on purpose, review it in Windows Settings. "
                    "NetPulse does not change proxy settings for you."
                    if state.proxy_enabled
                    else ""
                ),
            )
        )

    if link_speed_mbps is not None and not is_wireless:
        slow = link_speed_mbps <= 100
        checks.append(
            NetworkCheck(
                check_id="link-speed",
                title="Ethernet negotiated speed",
                category="link",
                current_value=f"{link_speed_mbps:.0f} Mbps",
                status=Severity.WARNING if slow else Severity.GOOD,
                explanation=(
                    "This is the speed the adapter and the router negotiated. Latency is not affected by it, "
                    "but the maximum throughput is."
                ),
                finding=(
                    f"The link negotiated at {link_speed_mbps:.0f} Mbps, which usually means a marginal cable or "
                    "an older router/switch port."
                    if slow
                    else ""
                ),
                recommendation=(
                    "Try a known-good Cat5e/Cat6 cable and another router port. NetPulse never forces a link "
                    "speed or duplex mode, because forcing a speed a cable cannot support causes disconnects."
                    if slow
                    else ""
                ),
            )
        )

    if state.ipv6_enabled is True:
        checks.append(
            NetworkCheck(
                check_id="ipv6",
                title="IPv6",
                category="link",
                current_value="Enabled",
                status=Severity.INFO,
                is_default=True,
                explanation=(
                    "IPv6 is a standard part of Windows networking. Disabling it 'because it is unused' is a "
                    "common tip but it can break modern services and Microsoft support does not recommend it."
                ),
                recommendation="No change recommended: leave IPv6 enabled.",
            )
        )

    for error in state.errors:
        checks.append(
            NetworkCheck(
                check_id=f"error-{abs(hash(error)) % 100000}",
                title="A setting could not be read",
                category="system",
                current_value="unavailable",
                status=Severity.UNKNOWN,
                explanation=error,
                recommendation="This is usually harmless; some adapters do not expose every property.",
            )
        )

    return checks


__all__ = [
    "CommandExecutor",
    "NetworkState",
    "build_checks",
    "collect_state",
    "parse_key_value_output",
    "parse_netsh_tcp_global",
]
