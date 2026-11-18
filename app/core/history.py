"""Local diagnostic history.

History is stored as a single JSON file in the per-user data directory. It never
leaves the machine, contains no credentials, and can be deleted at any time from
the History page (Clear History).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.models import DiagnosticReport, Severity, to_jsonable
from app.core.paths import ensure_app_data_dir, history_path

HISTORY_VERSION = 1


@dataclass
class HistoryEntry:
    """A compact summary plus the full report data of one diagnosis run."""

    entry_id: str
    timestamp: str
    overall_status: str
    headline: str
    adapter_name: str | None = None
    gateway_mean_ms: float | None = None
    gateway_loss_percent: float | None = None
    internet_mean_ms: float | None = None
    internet_jitter_ms: float | None = None
    internet_loss_percent: float | None = None
    dns_average_ms: float | None = None
    diagnosis_count: int = 0
    report: dict[str, Any] = field(default_factory=dict)

    @property
    def timestamp_display(self) -> str:
        try:
            moment = datetime.fromisoformat(self.timestamp)
        except ValueError:
            return self.timestamp
        return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "overall_status": self.overall_status,
            "headline": self.headline,
            "adapter_name": self.adapter_name,
            "gateway_mean_ms": self.gateway_mean_ms,
            "gateway_loss_percent": self.gateway_loss_percent,
            "internet_mean_ms": self.internet_mean_ms,
            "internet_jitter_ms": self.internet_jitter_ms,
            "internet_loss_percent": self.internet_loss_percent,
            "dns_average_ms": self.dns_average_ms,
            "diagnosis_count": self.diagnosis_count,
            "report": self.report,
        }

    @classmethod
    def from_report(cls, report: DiagnosticReport) -> HistoryEntry:
        gateway = report.gateway_ping
        internet = report.internet_pings[0] if report.internet_pings else None
        dns = report.dns
        moment = report.finished_at or report.started_at or datetime.now().astimezone()
        return cls(
            entry_id=uuid.uuid4().hex[:12],
            timestamp=moment.isoformat(),
            overall_status=report.overall_status.value,
            headline=report.headline,
            adapter_name=report.active_adapter_name,
            gateway_mean_ms=gateway.stats.mean_ms if gateway else None,
            gateway_loss_percent=gateway.stats.loss_percent if gateway else None,
            internet_mean_ms=internet.stats.mean_ms if internet else None,
            internet_jitter_ms=internet.stats.jitter_ms if internet else None,
            internet_loss_percent=internet.stats.loss_percent if internet else None,
            dns_average_ms=dns.average_ms if dns else None,
            diagnosis_count=len(report.diagnoses),
            report=to_jsonable(report.to_dict()),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HistoryEntry:
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


class HistoryStore:
    """Read/write access to the local history file."""

    def __init__(self, path: Path | None = None, limit: int = 50) -> None:
        self.path = path or history_path()
        self.limit = max(1, int(limit))
        self._entries: list[HistoryEntry] = []
        self._loaded = False

    # ------------------------------------------------------------------ #

    def load(self) -> list[HistoryEntry]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            self._entries = []
            self._loaded = True
            return self._entries
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self._entries = []
            self._loaded = True
            return self._entries
        entries = payload.get("entries") if isinstance(payload, dict) else payload
        result: list[HistoryEntry] = []
        for item in entries or []:
            if isinstance(item, dict):
                result.append(HistoryEntry.from_dict(item))
        self._entries = result
        self._loaded = True
        return self._entries

    def entries(self) -> list[HistoryEntry]:
        if not self._loaded:
            self.load()
        return list(self._entries)

    def add(self, report: DiagnosticReport) -> HistoryEntry:
        entry = HistoryEntry.from_report(report)
        if not self._loaded:
            self.load()
        self._entries.insert(0, entry)
        del self._entries[self.limit :]
        self.save()
        return entry

    def delete(self, entry_id: str) -> bool:
        if not self._loaded:
            self.load()
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.entry_id != entry_id]
        changed = len(self._entries) != before
        if changed:
            self.save()
        return changed

    def clear(self) -> None:
        self._entries = []
        self._loaded = True
        try:
            self.path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - defensive
            self.save()

    def save(self) -> Path:
        ensure_app_data_dir()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": HISTORY_VERSION,
            "entries": [e.to_dict() for e in self._entries],
        }
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return self.path

    def get(self, entry_id: str) -> HistoryEntry | None:
        if not self._loaded:
            self.load()
        for entry in self._entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    def worst_status(self) -> str:
        order = {
            Severity.UNKNOWN.value: 0,
            Severity.GOOD.value: 1,
            Severity.INFO.value: 2,
            Severity.WARNING.value: 3,
            Severity.CRITICAL.value: 4,
        }
        worst = Severity.UNKNOWN.value
        for entry in self.entries():
            if order.get(entry.overall_status, 0) > order.get(worst, 0):
                worst = entry.overall_status
        return worst


__all__ = ["HISTORY_VERSION", "HistoryEntry", "HistoryStore"]
