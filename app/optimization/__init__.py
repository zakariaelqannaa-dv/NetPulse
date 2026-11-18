"""Safe Windows network configuration: read-only checks plus reversible changes.

The design follows the NetPulse safety rules:

* every check is read first and explained, including its trade-offs;
* nothing is changed without explicit user confirmation;
* a snapshot is written before any change and can be reverted;
* NETPULSE never disables the Firewall, Defender, IPv6 or any security feature;
* link speed, duplex and MTU are never forced;
* ``netsh`` resets are never run automatically.
"""

from __future__ import annotations

from app.optimization.actions import (
    ACTION_REGISTRY,
    ACTIONS,
    ApplyResult,
    apply_action,
    available_actions,
    environment_note,
    get_action,
    preview_command,
    restore_snapshot,
    restore_snapshot_object,
    validate_dns_servers,
)
from app.optimization.models import (
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    NetworkAction,
    NetworkCheck,
    Snapshot,
    SnapshotEntry,
    SnapshotStore,
    new_snapshot,
)
from app.optimization.state import (
    CommandExecutor,
    NetworkState,
    build_checks,
    collect_state,
    parse_key_value_output,
    parse_netsh_tcp_global,
)

__all__ = [
    "ACTIONS",
    "ACTION_REGISTRY",
    "RISK_HIGH",
    "RISK_LOW",
    "RISK_MEDIUM",
    "ApplyResult",
    "CommandExecutor",
    "NetworkAction",
    "NetworkCheck",
    "NetworkState",
    "Snapshot",
    "SnapshotEntry",
    "SnapshotStore",
    "apply_action",
    "available_actions",
    "build_checks",
    "collect_state",
    "environment_note",
    "get_action",
    "new_snapshot",
    "parse_key_value_output",
    "parse_netsh_tcp_global",
    "preview_command",
    "restore_snapshot",
    "restore_snapshot_object",
    "validate_dns_servers",
]
