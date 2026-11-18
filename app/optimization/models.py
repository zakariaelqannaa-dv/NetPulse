"""Data models for the "Windows Network Settings" page.

The page is deliberately *read-first*: every check is collected and explained
before anything can be changed, every change is described with its trade-offs,
requires an explicit confirmation from the user, is recorded in a snapshot and
can be reverted from that snapshot.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.core.models import Severity
from app.core.paths import snapshots_dir

SNAPSHOT_VERSION = 1

#: Risk vocabulary shown next to an action before the user confirms it.
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"


@dataclass
class NetworkCheck:
    """One read-only observation about the current Windows network settings."""

    check_id: str
    title: str
    category: str
    current_value: str = ""
    status: Severity = Severity.INFO
    is_default: bool | None = None
    explanation: str = ""
    finding: str = ""
    recommendation: str = ""
    action_id: str | None = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "title": self.title,
            "category": self.category,
            "current_value": self.current_value,
            "status": self.status.value,
            "is_default": self.is_default,
            "explanation": self.explanation,
            "finding": self.finding,
            "recommendation": self.recommendation,
            "action_id": self.action_id,
            "detail": self.detail,
        }


@dataclass
class NetworkAction:
    """A reversible change NetPulse can apply, with its trade-offs spelled out."""

    action_id: str
    title: str
    category: str
    summary: str
    why: str
    tradeoffs: list[str] = field(default_factory=list)
    risk: str = RISK_LOW
    requires_admin: bool = True
    requires_reboot: bool = False
    is_destructive: bool = False
    documentation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "title": self.title,
            "category": self.category,
            "summary": self.summary,
            "why": self.why,
            "tradeoffs": list(self.tradeoffs),
            "risk": self.risk,
            "requires_admin": self.requires_admin,
            "requires_reboot": self.requires_reboot,
            "is_destructive": self.is_destructive,
            "documentation": self.documentation,
        }


@dataclass
class SnapshotEntry:
    """The previous value of one setting plus how to put it back."""

    action_id: str
    target: str = ""
    before: str = ""
    undo_args: list[str] = field(default_factory=list)
    undo_script: str = ""
    requires_reboot: bool = False
    manual_note: str = ""

    @property
    def reversible(self) -> bool:
        return bool(self.undo_args or self.undo_script)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id": self.action_id,
            "target": self.target,
            "before": self.before,
            "undo_args": list(self.undo_args),
            "undo_script": self.undo_script,
            "requires_reboot": self.requires_reboot,
            "manual_note": self.manual_note,
            "reversible": self.reversible,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SnapshotEntry:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass
class Snapshot:
    """A restore point created immediately before NetPulse changes anything."""

    snapshot_id: str
    created_at: str
    description: str
    action_ids: list[str] = field(default_factory=list)
    entries: list[SnapshotEntry] = field(default_factory=list)
    note: str = ""

    @property
    def created_display(self) -> str:
        try:
            moment = datetime.fromisoformat(self.created_at)
        except ValueError:
            return self.created_at
        return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": SNAPSHOT_VERSION,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "description": self.description,
            "action_ids": list(self.action_ids),
            "note": self.note,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snapshot:
        return cls(
            snapshot_id=str(data.get("snapshot_id") or uuid.uuid4().hex[:12]),
            created_at=str(data.get("created_at") or datetime.now(UTC).isoformat()),
            description=str(data.get("description") or ""),
            action_ids=[str(a) for a in (data.get("action_ids") or [])],
            entries=[SnapshotEntry.from_dict(e) for e in (data.get("entries") or [])],
            note=str(data.get("note") or ""),
        )


class SnapshotStore:
    """Persists snapshots as JSON files in the per-user data directory."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or snapshots_dir()

    def _path(self, snapshot_id: str) -> Path:
        return self.directory / f"{snapshot_id}.json"

    def save(self, snapshot: Snapshot) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(snapshot.snapshot_id)
        target.write_text(
            json.dumps(snapshot.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target

    def list(self) -> list[Snapshot]:
        if not self.directory.is_dir():
            return []
        snapshots: list[Snapshot] = []
        for path in self.directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict) and payload.get("snapshot_id"):
                snapshots.append(Snapshot.from_dict(payload))
        snapshots.sort(key=lambda s: s.created_at, reverse=True)
        return snapshots

    def latest(self) -> Snapshot | None:
        items = self.list()
        return items[0] if items else None

    def get(self, snapshot_id: str) -> Snapshot | None:
        path = self._path(snapshot_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(payload, dict) and payload.get("snapshot_id"):
            return Snapshot.from_dict(payload)
        return None

    def delete(self, snapshot_id: str) -> bool:
        path = self._path(snapshot_id)
        try:
            path.unlink()
        except OSError:
            return False
        return True


def new_snapshot(description: str, action_ids: list[str], entries: list[SnapshotEntry]) -> Snapshot:
    return Snapshot(
        snapshot_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(UTC).isoformat(),
        description=description,
        action_ids=list(action_ids),
        entries=list(entries),
    )


__all__ = [
    "RISK_HIGH",
    "RISK_LOW",
    "RISK_MEDIUM",
    "SNAPSHOT_VERSION",
    "NetworkAction",
    "NetworkCheck",
    "Snapshot",
    "SnapshotEntry",
    "SnapshotStore",
    "new_snapshot",
]
