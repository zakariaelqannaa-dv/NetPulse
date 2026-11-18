"""Presentation-only helpers shared by the TXT and HTML report writers.

Nothing in this module performs I/O or touches the network; it only turns the
values produced by :meth:`app.core.models.DiagnosticReport.to_dict` into text.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from app.core.models import SEVERITY_LABELS, Severity, TestStatus

STATUS_LABELS: dict[str, str] = {
    TestStatus.PENDING.value: "Pending",
    TestStatus.RUNNING.value: "Running",
    TestStatus.OK.value: "Completed",
    TestStatus.WARNING.value: "Completed with warnings",
    TestStatus.CRITICAL.value: "Completed with critical findings",
    TestStatus.UNSUPPORTED.value: "Not supported on this system",
    TestStatus.NOT_MEASURABLE.value: "Could not be measured",
    TestStatus.ERROR.value: "Failed",
    TestStatus.SKIPPED.value: "Skipped",
    TestStatus.CANCELLED.value: "Cancelled",
}

#: Human wording for every rating so the report never shows a raw enum value.
SEVERITY_TEXT: dict[str, str] = {
    Severity.GOOD.value: "Good",
    Severity.INFO.value: "Informational",
    Severity.WARNING.value: "Warning",
    Severity.CRITICAL.value: "Critical",
    Severity.UNKNOWN.value: "Unknown",
}


def severity_label(value: Any) -> str:
    if isinstance(value, Severity):
        return SEVERITY_LABELS[value]
    return SEVERITY_TEXT.get(str(value), "Unknown")


def status_label(value: Any) -> str:
    if isinstance(value, TestStatus):
        return STATUS_LABELS[value.value]
    return STATUS_LABELS.get(str(value), str(value))


def confidence_label(value: Any) -> str:
    text = value.value if hasattr(value, "value") else str(value)
    return {"low": "Low", "medium": "Medium", "high": "High"}.get(text.lower(), text)


def fmt_ms(value: float | None) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):.1f} ms"


def fmt_ms_precise(value: float | None) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):.2f} ms"


def fmt_percent(value: float | None) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):.2f}%"


def fmt_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):.{digits}f}"


def fmt_plain(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value).strip()
    return text or "unavailable"


def fmt_bool(value: Any) -> str:
    if value is None:
        return "unavailable"
    return "Yes" if value else "No"


def fmt_timestamp(value: Any) -> str:
    """Render an ISO timestamp in the machine's local time zone."""
    if not value:
        return "unavailable"
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    if moment.tzinfo is None:
        moment = moment.astimezone()
    return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def human_duration_ms(value: Any) -> str:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError):
        return "unavailable"
    if milliseconds < 1000:
        return f"{milliseconds:.0f} ms"
    seconds = milliseconds / 1000.0
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes = int(seconds // 60)
    return f"{minutes} min {seconds - minutes * 60:.0f} s"


def fmt_bytes(value: Any) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "unavailable"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def sample_series_text(samples: Sequence[dict[str, Any]], limit: int = 120) -> str:
    """Compact ``1:12.3ms`` series so a text report stays readable."""
    parts: list[str] = []
    for sample in samples[:limit]:
        index = sample.get("index")
        rtt = sample.get("rtt_ms")
        if rtt is None:
            parts.append(f"{index}:lost")
        else:
            parts.append(f"{index}:{float(rtt):.1f}ms")
    if len(samples) > limit:
        parts.append(f"... (+{len(samples) - limit} more)")
    return ", ".join(parts) if parts else "no samples recorded"


__all__ = [
    "SEVERITY_TEXT",
    "STATUS_LABELS",
    "confidence_label",
    "fmt_bool",
    "fmt_bytes",
    "fmt_ms",
    "fmt_ms_precise",
    "fmt_number",
    "fmt_percent",
    "fmt_plain",
    "fmt_timestamp",
    "human_duration_ms",
    "sample_series_text",
    "severity_label",
    "status_label",
]
