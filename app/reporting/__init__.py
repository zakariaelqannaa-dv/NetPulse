"""Report generation: JSON, plain text and printable HTML with redaction."""

from __future__ import annotations

from app.reporting.exporter import (
    FILE_DIALOG_FILTER,
    FORMAT_EXTENSIONS,
    FORMAT_LABELS,
    ReportFormat,
    default_filename,
    export_report,
    render_report,
    report_to_dict,
)
from app.reporting.redaction import (
    FIELD_DESCRIPTIONS,
    FIELD_LABELS,
    PLACEHOLDERS,
    SensitiveField,
    collect_sensitive_fields,
    default_selection,
    redact_report_data,
)

__all__ = [
    "FIELD_DESCRIPTIONS",
    "FIELD_LABELS",
    "FILE_DIALOG_FILTER",
    "FORMAT_EXTENSIONS",
    "FORMAT_LABELS",
    "PLACEHOLDERS",
    "ReportFormat",
    "SensitiveField",
    "collect_sensitive_fields",
    "default_filename",
    "default_selection",
    "export_report",
    "redact_report_data",
    "render_report",
    "report_to_dict",
]
