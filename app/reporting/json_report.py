"""Machine-readable JSON report writer.

The JSON report is the full, lossless representation of a diagnosis. It is the
input for the TXT and HTML writers as well, so those two formats never lose a
field that the JSON format carries.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.models import to_jsonable

#: Bumped whenever the layout of the exported JSON changes.
REPORT_FORMAT_VERSION = 1


def build_payload(report_data: dict[str, Any]) -> dict[str, Any]:
    """Wrap the raw report data with format metadata."""
    payload = to_jsonable(report_data)
    payload.setdefault("redacted_fields", [])
    return {
        "report_format": "netpulse-diagnostic-report",
        "report_format_version": REPORT_FORMAT_VERSION,
        "report": payload,
    }


def render_json(report_data: dict[str, Any], indent: int = 2) -> str:
    """Return the report serialised as pretty-printed UTF-8 JSON."""
    return json.dumps(build_payload(report_data), indent=indent, ensure_ascii=False) + "\n"


__all__ = ["REPORT_FORMAT_VERSION", "build_payload", "render_json"]
