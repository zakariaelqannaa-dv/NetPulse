"""Report rendering and export.

This module is the single entry point the GUI uses to turn a diagnosis into a
file. It handles format selection, redaction and file naming so the UI layer
contains no report logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from app.core.models import DiagnosticReport
from app.reporting.html_report import render_html
from app.reporting.json_report import render_json
from app.reporting.redaction import collect_sensitive_fields, redact_report_data
from app.reporting.txt_report import render_txt


class ReportFormat(str, Enum):
    JSON = "json"
    TXT = "txt"
    HTML = "html"


FORMAT_EXTENSIONS: dict[ReportFormat, str] = {
    ReportFormat.JSON: ".json",
    ReportFormat.TXT: ".txt",
    ReportFormat.HTML: ".html",
}

FORMAT_LABELS: dict[ReportFormat, str] = {
    ReportFormat.JSON: "JSON (full machine-readable data)",
    ReportFormat.TXT: "Text (easy to read and paste into an e-mail)",
    ReportFormat.HTML: "HTML (formatted, printable)",
}

#: Ready-made filter string for a Qt file dialog.
FILE_DIALOG_FILTER = ";;".join(
    f"{FORMAT_LABELS[fmt]} (*{FORMAT_EXTENSIONS[fmt]})" for fmt in ReportFormat
)


def report_to_dict(report: DiagnosticReport | dict[str, Any]) -> dict[str, Any]:
    """Accept either a report object or already-serialised report data."""
    if isinstance(report, DiagnosticReport):
        return report.to_dict()
    return report


def render_report(report_data: dict[str, Any], fmt: ReportFormat) -> str:
    """Render report data in the requested format."""
    if fmt == ReportFormat.JSON:
        return render_json(report_data)
    if fmt == ReportFormat.TXT:
        return render_txt(report_data)
    if fmt == ReportFormat.HTML:
        return render_html(report_data)
    raise ValueError(f"Unsupported report format: {fmt!r}")


def default_filename(
    report_data: dict[str, Any],
    fmt: ReportFormat,
    moment: datetime | None = None,
) -> str:
    """Build a stable, sortable file name such as ``NetPulse-report-2026-11-18_140322.txt``."""
    if moment is None:
        stamp = report_data.get("finished_at") or report_data.get("started_at")
        try:
            moment = datetime.fromisoformat(str(stamp)) if stamp else datetime.now()
        except ValueError:
            moment = datetime.now()
    return f"NetPulse-report-{moment.astimezone().strftime('%Y-%m-%d_%H%M%S')}{FORMAT_EXTENSIONS[fmt]}"


def export_report(
    report: DiagnosticReport | dict[str, Any],
    fmt: ReportFormat,
    path: str | Path,
    redacted_keys: Iterable[str] | None = None,
) -> Path:
    """Write a report file and return its final path.

    ``redacted_keys`` is a collection of :data:`app.reporting.redaction.PLACEHOLDERS`
    keys; when omitted the report is written unmodified.
    """
    report_data = report_to_dict(report)
    if redacted_keys is not None and list(redacted_keys):
        report_data = redact_report_data(report_data, redacted_keys)
    content = render_report(report_data, fmt)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


__all__ = [
    "FILE_DIALOG_FILTER",
    "FORMAT_EXTENSIONS",
    "FORMAT_LABELS",
    "ReportFormat",
    "collect_sensitive_fields",
    "default_filename",
    "export_report",
    "render_report",
    "report_to_dict",
]
