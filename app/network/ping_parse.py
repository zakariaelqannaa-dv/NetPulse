"""Robust parsing of ``ping`` console output, including non-English Windows.

Windows localises the ``ping.exe`` text ("Request timed out.", "Zeitüberschreitung",
"请求超时", ...). NetPulse prefers the native ICMP API (see
:mod:`app.network.icmp`), but this parser is used as a fallback and is unit
tested against English, Chinese, German, French, Spanish and Russian samples.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: "time=13ms", "time<1ms" and their localised equivalents.
_RTT_PATTERNS = [
    re.compile(r"(?:time|时间|時間|tiempo|temps|zeit|время|tempo|timp|čas|aika|tijd|czas)\s*([=<])\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE),
    re.compile(r"([=<])\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE),
]

#: Localised "request timed out" / "destination unreachable" markers.
_TIMEOUT_RE = re.compile(
    r"(?:timed?\s*out|timeout|d[eé]lai|zeit(?:ü|u)berschreitung|tiempo\s+de\s+espera|"
    r"tiempo\s+agotado|превышен|超时|超時|시간\s*초과|verzoek\s+time-out|przekroczono|"
    r"a(?:ş|s)[ıi]ld[ıi]\s+s[üu]re|време\s+за\s+изчакване|forbindelsen\s+blev\s+afbrudt)",
    re.IGNORECASE,
)

_UNREACHABLE_RE = re.compile(
    r"(?:unreachable|injoignable|nicht\s+erreichbar|inalcanzable|недоступен|无法访问|"
    r"無法連線|도달할\s+수\s+없|onbereikbaar|nieosiągalny|ulaşılamıyor)",
    re.IGNORECASE,
)

#: "Packets: Sent = 4, Received = 3, Lost = 1 (25% loss)" plus localised forms.
_SUMMARY_RE = re.compile(
    r"(?:sent|enviados|envoy[eé]s|gesendet|отправлено|已发送|傳送|보냄|verzonden)\D{0,4}(\d+)",
    re.IGNORECASE,
)
_SUMMARY_RECEIVED_RE = re.compile(
    r"(?:received|recibidos|re[cç]us|empfangen|получено|已接收|接收|받음|ontvangen)\D{0,4}(\d+)",
    re.IGNORECASE,
)


@dataclass
class PingParseResult:
    """Result of parsing one ``ping`` invocation."""

    rtts: list[float] = field(default_factory=list)
    timeouts: int = 0
    unreachable: int = 0
    sent: int | None = None
    received: int | None = None
    message: str = ""

    @property
    def total_probes(self) -> int:
        return len(self.rtts) + self.timeouts + self.unreachable


def parse_rtt_token(line: str) -> float | None:
    """Return the RTT in milliseconds found in ``line`` (``None`` if absent)."""
    for pattern in _RTT_PATTERNS:
        match = pattern.search(line)
        if not match:
            continue
        comparator, raw = match.group(1), match.group(2).replace(",", ".")
        try:
            value = float(raw)
        except ValueError:  # pragma: no cover - regex guarantees a number
            continue
        if comparator == "<":
            # Windows prints "<1ms" for sub-millisecond replies. 0.5 ms keeps
            # the value honest without inventing a 0 ms measurement.
            return 0.5 if value <= 1 else value
        return value
    return None


def parse_ping_output(text: str) -> PingParseResult:
    """Parse the full output of a ``ping`` run."""
    result = PingParseResult()
    if not text:
        result.message = "No output from ping"
        return result

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if _TIMEOUT_RE.search(line):
            result.timeouts += 1
            continue
        if _UNREACHABLE_RE.search(line):
            result.unreachable += 1
            continue
        rtt = parse_rtt_token(line)
        if rtt is not None:
            result.rtts.append(rtt)

    sent_match = _SUMMARY_RE.search(text)
    received_match = _SUMMARY_RECEIVED_RE.search(text)
    if sent_match:
        try:
            result.sent = int(sent_match.group(1))
        except ValueError:  # pragma: no cover
            result.sent = None
    if received_match:
        try:
            result.received = int(received_match.group(1))
        except ValueError:  # pragma: no cover
            result.received = None

    if not result.rtts and result.timeouts:
        result.message = "All probes timed out (ICMP may be filtered)"
    elif not result.rtts and not result.timeouts:
        result.message = "No probe results could be parsed"
    return result


def expand_rtts(parsed: PingParseResult, expected: int | None = None) -> list[float | None]:
    """Return a per-probe RTT series with ``None`` for lost probes."""
    series: list[float | None] = list(parsed.rtts)
    series.extend([None] * (parsed.timeouts + parsed.unreachable))
    if expected is not None:
        if len(series) > expected:
            series = series[:expected]
        elif len(series) < expected:
            series.extend([None] * (expected - len(series)))
    return series
