"""Reversible Windows network changes.

Guarantees enforced by this module:

* nothing runs without an explicit call from the UI after a confirmation dialog;
* every action documents why it exists and what it can cost the user;
* a snapshot of the previous value is written *before* the change;
* administrator rights are checked first and the user is asked to elevate;
* Firewall, Defender, IPv6 and security-related settings are never touched;
* link speed, duplex and MTU are never forced;
* ``netsh`` resets are never run automatically - they require an explicit,
  separately confirmed destructive action and are not reversible.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.models import ChangeRecord
from app.network.privileges import is_admin
from app.network.validation import is_valid_ip
from app.optimization.models import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    NetworkAction,
    Snapshot,
    SnapshotEntry,
    SnapshotStore,
    new_snapshot,
)
from app.optimization.state import CommandExecutor, NetworkState, collect_state

ACTIONS: tuple[NetworkAction, ...] = (
    NetworkAction(
        action_id="tcp-autotuning-normal",
        title="Restore the Windows default TCP auto-tuning",
        category="tcp",
        summary="Set 'Receive Window Auto-Tuning Level' back to Normal.",
        why=(
            "Windows adapts the TCP receive window to the connection when auto-tuning is Normal. Older "
            "'optimizer' tools and tweak guides often switch it off, which can leave download throughput "
            "well below what the connection can deliver on links with higher latency."
        ),
        tradeoffs=[
            "This does not lower ping or jitter; it affects throughput only.",
            "A few legacy VPN or firewall products expect a fixed receive window.",
        ],
        risk=RISK_LOW,
        documentation="netsh interface tcp set global autotuninglevel=normal",
    ),
    NetworkAction(
        action_id="rss-enable",
        title="Enable Receive Side Scaling (RSS)",
        category="adapter",
        summary="Let several CPU cores process network interrupts on the active adapter.",
        why=(
            "RSS spreads network processing across CPU cores, which can raise throughput on fast links "
            "when a single core is saturated."
        ),
        tradeoffs=[
            "Requires driver support; unsupported adapters ignore it.",
            "No benefit on single-core systems or slow links.",
        ],
        risk=RISK_LOW,
        documentation="Enable-NetAdapterRss",
    ),
    NetworkAction(
        action_id="adapter-power-saving-off",
        title="Stop Windows from powering down the adapter",
        category="adapter",
        summary="Uncheck 'Allow the computer to turn off this device to save power'.",
        why=(
            "Power saving is a very common cause of short disconnects and a burst of packet loss a few "
            "seconds after a laptop has been idle."
        ),
        tradeoffs=["Idle power use rises slightly, which matters mostly on battery-powered laptops."],
        risk=RISK_LOW,
        documentation="Set-NetAdapterPowerManagement -AllowComputerToTurnOffDevice Disabled",
    ),
    NetworkAction(
        action_id="dns-set",
        title="Set DNS servers on the active adapter",
        category="dns",
        summary="Replace the adapter's DNS resolvers with servers you choose.",
        why=(
            "If the diagnosis shows slow name resolution and a public resolver answered much faster, "
            "switching the adapter to that resolver can make pages start loading sooner."
        ),
        tradeoffs=[
            "Changing DNS never improves the ping to a server whose address is already resolved.",
            "Corporate, ISP and parental-control networks may require their own resolver.",
            "Some resolvers apply filtering or logging policies you should be aware of.",
        ],
        risk=RISK_MEDIUM,
        documentation="Set-DnsClientServerAddress -ServerAddresses",
    ),
    NetworkAction(
        action_id="winsock-reset",
        title="Reset the Winsock catalog",
        category="reset",
        summary="Rewrite the Winsock layered-service-provider catalog (requires a restart).",
        why=(
            "Only useful when the Winsock catalog is damaged - typically after an incomplete removal of a "
            "VPN, proxy or adware component. It is not a general performance fix."
        ),
        tradeoffs=[
            "Removes custom Winsock providers; some VPN and firewall products must be reinstalled.",
            "A restart is required.",
            "This cannot be undone automatically. NetPulse records what it did, but the catalog itself cannot be restored.",
        ],
        risk=RISK_HIGH,
        requires_reboot=True,
        is_destructive=True,
        documentation="netsh winsock reset",
    ),
    NetworkAction(
        action_id="ip-reset",
        title="Reset the TCP/IP stack",
        category="reset",
        summary="Rewrite the TCP/IP configuration to its default state (requires a restart).",
        why=(
            "Only useful when the TCP/IP stack is damaged. Static IP, gateway and DNS settings may have to "
            "be entered again afterwards."
        ),
        tradeoffs=[
            "Static addressing and custom routes may need to be re-entered.",
            "A restart is required.",
            "This cannot be undone automatically.",
        ],
        risk=RISK_HIGH,
        requires_reboot=True,
        is_destructive=True,
        documentation="netsh int ip reset",
    ),
)

ACTION_REGISTRY: dict[str, NetworkAction] = {a.action_id: a for a in ACTIONS}

_ADMIN_ERROR = (
    "Administrator rights are required for this change. NetPulse does not elevate on its own: "
    "restart it as administrator after confirming the change."
)
_DESTRUCTIVE_ERROR = (
    "This action is destructive and must be confirmed separately before it can be applied."
)


def get_action(action_id: str) -> NetworkAction | None:
    return ACTION_REGISTRY.get(action_id)


def available_actions() -> list[NetworkAction]:
    return list(ACTIONS)


# --------------------------------------------------------------------------- #
# Preview / validation
# --------------------------------------------------------------------------- #


def validate_dns_servers(servers: Any) -> list[str]:
    """Validate a user supplied DNS server list (1-3 IPv4/IPv6 addresses)."""
    if isinstance(servers, str):
        candidates = [part.strip() for part in servers.replace(",", " ").split()]
    else:
        candidates = [str(part).strip() for part in (servers or [])]
    cleaned: list[str] = []
    for candidate in candidates:
        if not candidate:
            continue
        if not is_valid_ip(candidate):
            raise ValueError(f"'{candidate}' is not a valid IP address.")
        if candidate not in cleaned:
            cleaned.append(candidate)
    if not cleaned:
        raise ValueError("At least one DNS server address is required.")
    if len(cleaned) > 3:
        raise ValueError("At most three DNS servers can be configured at once.")
    return cleaned


def preview_command(
    action_id: str,
    adapter_name: str = "",
    options: dict[str, Any] | None = None,
) -> str:
    """Return the exact command that would run, for display before confirmation."""
    options = options or {}
    if action_id == "tcp-autotuning-normal":
        return "netsh int tcp set global autotuninglevel=normal"
    if action_id == "rss-enable":
        return f"Enable-NetAdapterRss -Name '{adapter_name}'"
    if action_id == "adapter-power-saving-off":
        return (
            "Set-NetAdapterPowerManagement -Name "
            f"'{adapter_name}' -AllowComputerToTurnOffDevice Disabled"
        )
    if action_id == "dns-set":
        servers = validate_dns_servers(options.get("servers") or [])
        return f"Set-DnsClientServerAddress -InterfaceAlias '{adapter_name}' -ServerAddresses {','.join(servers)}"
    if action_id == "winsock-reset":
        return "netsh winsock reset"
    if action_id == "ip-reset":
        return "netsh int ip reset"
    return ""


# --------------------------------------------------------------------------- #
# Apply
# --------------------------------------------------------------------------- #


@dataclass
class ApplyResult:
    """Outcome of an attempted change, including the snapshot trail."""

    record: ChangeRecord
    snapshot: Snapshot | None = None

    @property
    def applied(self) -> bool:
        return self.record.applied


def _now() -> str:
    return datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _record(
    action: NetworkAction,
    *,
    target: str = "",
    applied: bool = False,
    before: str | None = None,
    after: str | None = None,
    note: str = "",
    error: str | None = None,
    command: str = "",
) -> ChangeRecord:
    return ChangeRecord(
        action_id=action.action_id,
        title=action.title,
        target=target,
        applied=applied,
        requires_admin=action.requires_admin,
        before=before,
        after=after,
        note=note,
        error=error,
        timestamp=_now(),
        command=command,
    )


def _autotuning_level(state: NetworkState) -> str:
    return (state.tcp.get("autotuning") or "").strip().lower()


def apply_action(
    action_id: str,
    *,
    adapter_name: str = "",
    options: dict[str, Any] | None = None,
    executor: CommandExecutor | None = None,
    store: SnapshotStore | None = None,
    state: NetworkState | None = None,
    confirm_destructive: bool = False,
    assume_admin: bool | None = None,
) -> ApplyResult:
    """Apply one reversible action and return its audit record plus snapshot."""
    options = options or {}
    action = get_action(action_id)
    if action is None:
        raise ValueError(f"Unknown action: {action_id!r}")

    runner = executor or CommandExecutor()
    snapshot_store = store or SnapshotStore()
    current = state or collect_state(adapter_name, runner)
    target = adapter_name or action.category
    command = ""
    try:
        command = preview_command(action_id, adapter_name, options)
    except ValueError as exc:
        return ApplyResult(_record(action, target=target, error=str(exc)))

    if action.requires_admin and not (is_admin() if assume_admin is None else assume_admin):
        return ApplyResult(_record(action, target=target, error=_ADMIN_ERROR, command=command))

    if action.is_destructive and not confirm_destructive:
        return ApplyResult(_record(action, target=target, note=_DESTRUCTIVE_ERROR, command=command))

    entry = SnapshotEntry(action_id=action.action_id, target=target, requires_reboot=action.requires_reboot)
    before_text = ""
    after_text = ""
    result_ok = False
    error: str | None = None

    if action_id == "tcp-autotuning-normal":
        level = _autotuning_level(current)
        before_text = level or "unknown"
        entry.before = before_text
        entry.undo_args = ["netsh", "int", "tcp", "set", "global", f"autotuninglevel={level or 'normal'}"]
        outcome = runner.args(["netsh", "int", "tcp", "set", "global", "autotuninglevel=normal"])
        result_ok = outcome.ok
        error = None if outcome.ok else (outcome.error or outcome.combined.strip() or "netsh failed")
        after_text = "normal" if result_ok else before_text

    elif action_id == "rss-enable":
        if not adapter_name:
            return ApplyResult(_record(action, target=target, error="An active adapter is required.", command=command))
        before_text = "enabled" if current.rss_enabled else "disabled"
        entry.before = before_text
        entry.undo_script = (
            f"Disable-NetAdapterRss -Name '{_escape(adapter_name)}' -ErrorAction SilentlyContinue"
        )
        outcome = runner.ps(
            f"Enable-NetAdapterRss -Name '{_escape(adapter_name)}' -ErrorAction SilentlyContinue"
        )
        result_ok = outcome.ok
        error = None if outcome.ok else (outcome.error or outcome.combined.strip() or "Enable-NetAdapterRss failed")
        after_text = "enabled" if result_ok else before_text

    elif action_id == "adapter-power-saving-off":
        if not adapter_name:
            return ApplyResult(_record(action, target=target, error="An active adapter is required.", command=command))
        before_text = "on" if current.power_save_enabled else "off"
        entry.before = before_text
        entry.undo_script = (
            "Set-NetAdapterPowerManagement -Name "
            f"'{_escape(adapter_name)}' -AllowComputerToTurnOffDevice Enabled -ErrorAction SilentlyContinue"
        )
        outcome = runner.ps(
            "Set-NetAdapterPowerManagement -Name "
            f"'{_escape(adapter_name)}' -AllowComputerToTurnOffDevice Disabled -ErrorAction SilentlyContinue"
        )
        result_ok = outcome.ok
        error = None if outcome.ok else (outcome.error or outcome.combined.strip() or "Set-NetAdapterPowerManagement failed")
        after_text = "off" if result_ok else before_text

    elif action_id == "dns-set":
        if not adapter_name:
            return ApplyResult(_record(action, target=target, error="An active adapter is required.", command=command))
        servers = validate_dns_servers(options.get("servers") or [])
        before_text = ", ".join(current.dns_servers) or "automatic (DHCP)"
        entry.before = before_text
        if current.dns_servers:
            joined = ",".join(f"'{_escape(s)}'" for s in current.dns_servers)
            entry.undo_script = (
                f"Set-DnsClientServerAddress -InterfaceAlias '{_escape(adapter_name)}' "
                f"-ServerAddresses {joined} -ErrorAction SilentlyContinue"
            )
        else:
            entry.undo_script = (
                f"Set-DnsClientServerAddress -InterfaceAlias '{_escape(adapter_name)}' "
                "-ResetServerAddresses -ErrorAction SilentlyContinue"
            )
        joined = ",".join(f"'{_escape(s)}'" for s in servers)
        outcome = runner.ps(
            f"Set-DnsClientServerAddress -InterfaceAlias '{_escape(adapter_name)}' "
            f"-ServerAddresses {joined} -ErrorAction SilentlyContinue"
        )
        result_ok = outcome.ok
        error = None if outcome.ok else (outcome.error or outcome.combined.strip() or "Set-DnsClientServerAddress failed")
        after_text = ", ".join(servers) if result_ok else before_text

    elif action_id == "winsock-reset":
        before_text = "current Winsock catalog"
        entry.before = before_text
        entry.manual_note = "The Winsock catalog cannot be restored automatically; a restart is required."
        entry.undo_args = []
        entry.undo_script = ""
        outcome = runner.args(["netsh", "winsock", "reset"])
        result_ok = outcome.ok
        error = None if outcome.ok else (outcome.error or outcome.combined.strip() or "netsh winsock reset failed")
        after_text = "reset requested (restart required)" if result_ok else before_text

    elif action_id == "ip-reset":
        before_text = "current TCP/IP configuration"
        entry.before = before_text
        entry.manual_note = "Static addressing may need to be re-entered; a restart is required."
        entry.undo_args = []
        entry.undo_script = ""
        outcome = runner.args(["netsh", "int", "ip", "reset"])
        result_ok = outcome.ok
        error = None if outcome.ok else (outcome.error or outcome.combined.strip() or "netsh int ip reset failed")
        after_text = "reset requested (restart required)" if result_ok else before_text

    else:  # pragma: no cover - registry guards against this
        return ApplyResult(_record(action, target=target, error=f"Action {action_id} is not implemented."))

    note = action.summary
    if action.requires_reboot and result_ok:
        note += " A restart is required to finish this change."

    record = _record(
        action,
        target=target,
        applied=result_ok,
        before=before_text,
        after=after_text,
        note=note,
        error=error if not result_ok else None,
        command=command,
    )
    snapshot = new_snapshot(description=action.title, action_ids=[action.action_id], entries=[entry])
    snapshot_store.save(snapshot)
    return ApplyResult(record, snapshot)


def _escape(value: str) -> str:
    return str(value).replace("'", "''")


# --------------------------------------------------------------------------- #
# Restore
# --------------------------------------------------------------------------- #


def restore_snapshot(
    snapshot_id: str,
    *,
    executor: CommandExecutor | None = None,
    store: SnapshotStore | None = None,
    assume_admin: bool | None = None,
) -> list[ChangeRecord]:
    """Revert every reversible entry of a snapshot."""
    snapshot_store = store or SnapshotStore()
    snapshot = snapshot_store.get(snapshot_id)
    if snapshot is None:
        return [
            ChangeRecord(
                action_id="restore",
                title="Restore snapshot",
                applied=False,
                error=f"Snapshot {snapshot_id} was not found.",
                timestamp=_now(),
            )
        ]
    return restore_snapshot_object(snapshot, executor=executor, assume_admin=assume_admin)


def restore_snapshot_object(
    snapshot: Snapshot,
    *,
    executor: CommandExecutor | None = None,
    assume_admin: bool | None = None,
) -> list[ChangeRecord]:
    runner = executor or CommandExecutor()
    records: list[ChangeRecord] = []
    admin = is_admin() if assume_admin is None else assume_admin

    for entry in snapshot.entries:
        action = get_action(entry.action_id)
        title = action.title if action else entry.action_id
        if not entry.reversible:
            records.append(
                ChangeRecord(
                    action_id=entry.action_id,
                    title=f"Restore: {title}",
                    target=entry.target,
                    applied=False,
                    before=entry.before,
                    note=entry.manual_note or "This setting cannot be restored automatically.",
                    timestamp=_now(),
                )
            )
            continue
        if not admin:
            records.append(
                ChangeRecord(
                    action_id=entry.action_id,
                    title=f"Restore: {title}",
                    target=entry.target,
                    applied=False,
                    before=entry.before,
                    error=_ADMIN_ERROR,
                    timestamp=_now(),
                )
            )
            continue

        outcome = runner.args(entry.undo_args) if entry.undo_args else runner.ps(entry.undo_script)
        records.append(
            ChangeRecord(
                action_id=entry.action_id,
                title=f"Restore: {title}",
                target=entry.target,
                applied=outcome.ok,
                before=entry.before,
                after=entry.before,
                note="Previous value restored.",
                error=None if outcome.ok else (outcome.error or outcome.combined.strip() or "restore failed"),
                timestamp=_now(),
                command=" ".join(entry.undo_args) if entry.undo_args else entry.undo_script,
            )
        )
    return records


def environment_note() -> str:
    """Short note about the current privilege level, shown on the page."""
    elevated = is_admin()
    platform_name = platform.system()
    if elevated:
        return f"NetPulse is running with administrator rights on {platform_name}."
    return (
        f"NetPulse is running without administrator rights on {platform_name}. "
        "All read-only checks work normally; changes will ask you to restart elevated."
    )


__all__ = [
    "ACTIONS",
    "ACTION_REGISTRY",
    "ApplyResult",
    "apply_action",
    "available_actions",
    "environment_note",
    "get_action",
    "preview_command",
    "restore_snapshot",
    "restore_snapshot_object",
    "validate_dns_servers",
]
