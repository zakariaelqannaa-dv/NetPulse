"""Optional, explicitly consented download speed test.

NetPulse deliberately does **not** download files from arbitrary speed-test
servers. The user must provide a URL to a test file they trust (for example a
file hosted on their own server), enable the feature and confirm consent in
Settings. The test is never run automatically.

Privacy: the only network traffic generated is a plain HTTP GET to the URL the
user entered; the same URL may appear in the exported report unless it is
redacted. No measurement is uploaded anywhere.
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from collections.abc import Callable

from app import APP_VERSION
from app.core.cancellation import CancellationToken
from app.core.models import SpeedTestResult
from app.network.validation import validate_http_url

PRIVACY_NOTE = (
    "This optional test performs a direct HTTP(S) GET to a URL you provide. "
    "The URL and the measured speed stay on this machine and are only written to a "
    "report if you export one. NetPulse never runs a speed test automatically and "
    "never uploads results."
)

DEFAULT_MAX_SECONDS = 10.0
DEFAULT_MAX_BYTES = 100 * 1024 * 1024
_CHUNK = 64 * 1024

ProgressCallback = Callable[[int], None]


def measure_download(
    url: str,
    max_seconds: float = DEFAULT_MAX_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    token: CancellationToken | None = None,
    progress: ProgressCallback | None = None,
) -> SpeedTestResult:
    """Download from ``url`` for at most ``max_seconds`` and report Mbit/s."""
    result = SpeedTestResult(url=url, privacy_note=PRIVACY_NOTE)
    try:
        url = validate_http_url(url)
    except ValueError as exc:
        result.error = str(exc)
        return result

    request = urllib.request.Request(url, headers={"User-Agent": f"NetPulse/{APP_VERSION}"})  # noqa: S310 - user supplied URL
    started = time.monotonic()
    downloaded = 0
    try:
        with urllib.request.urlopen(request, timeout=10.0) as response:  # noqa: S310 - user supplied URL
            while True:
                if token is not None and token.is_cancelled():
                    result.stopped_early = True
                    break
                if time.monotonic() - started >= max_seconds:
                    result.stopped_early = True
                    break
                if downloaded >= max_bytes:
                    result.stopped_early = True
                    break
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                downloaded += len(chunk)
                if progress is not None:
                    progress(downloaded)
    except urllib.error.URLError as exc:
        result.error = f"Download failed: {exc}"
        return result
    except OSError as exc:  # pragma: no cover - defensive
        result.error = f"Download failed: {exc}"
        return result

    duration = time.monotonic() - started
    result.bytes_downloaded = downloaded
    result.duration_s = duration
    if downloaded <= 0 or duration <= 0:
        result.error = "No data was transferred."
        return result
    result.megabits_per_second = (downloaded * 8) / (duration * 1_000_000)
    result.ok = True
    return result


__all__ = ["DEFAULT_MAX_BYTES", "DEFAULT_MAX_SECONDS", "PRIVACY_NOTE", "measure_download"]
