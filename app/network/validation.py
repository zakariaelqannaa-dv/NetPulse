"""Validation helpers for anything that reaches a subprocess or the network.

NetPulse never passes unvalidated user input to a shell. Targets are validated
here and subprocesses are always started with an argument list (``shell=False``),
so a validated value can never be interpreted as a shell token.
"""

from __future__ import annotations

import ipaddress
import re

#: A conservative hostname pattern: RFC 1123 labels, optional trailing dot.
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?!-)[A-Za-z0-9_-]{1,63}(?<!-)(?:\.(?!-)[A-Za-z0-9_-]{1,63}(?<!-))*\.?$"
)

#: Characters that are never allowed in a value handed to PowerShell.
PS_UNSAFE_RE = re.compile(r"[`$'\"\r\n;|&<>(){}@#,=+*?\[\]\\\s]")


class ValidationError(ValueError):
    """Raised when user supplied input fails validation."""


def is_valid_ipv4(value: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv4Address)
    except ValueError:
        return False


def is_valid_ipv6(value: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(value), ipaddress.IPv6Address)
    except ValueError:
        return False


def is_valid_ip(value: str) -> bool:
    return is_valid_ipv4(value) or is_valid_ipv6(value)


def is_valid_hostname(value: str) -> bool:
    if not value or len(value) > 253:
        return False
    return bool(HOSTNAME_RE.match(value))


def is_valid_host(value: str) -> bool:
    """True for a valid IP address or a valid hostname."""
    return is_valid_ip(value) or is_valid_hostname(value)


def validate_host(value: str, *, field_name: str = "target") -> str:
    candidate = (value or "").strip()
    if not candidate:
        raise ValidationError(f"{field_name} must not be empty")
    if not is_valid_host(candidate):
        raise ValidationError(f"{field_name} is not a valid hostname or IP address: {value!r}")
    return candidate


def validate_port(value: int | str, *, field_name: str = "port") -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a number") from exc
    if not 1 <= port <= 65535:
        raise ValidationError(f"{field_name} must be between 1 and 65535")
    return port


def validate_http_url(value: str, *, field_name: str = "url") -> str:
    from urllib.parse import urlparse

    candidate = (value or "").strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValidationError(f"{field_name} must start with http:// or https://")
    if not parsed.netloc or not is_valid_host(parsed.hostname or ""):
        raise ValidationError(f"{field_name} is not a valid URL: {value!r}")
    return candidate


def is_shell_safe_token(value: str) -> bool:
    """True when ``value`` contains no shell/PowerShell metacharacters."""
    return bool(value) and not PS_UNSAFE_RE.search(value)


def quote_powershell_literal(value: str, *, field_name: str = "value") -> str:
    """Return a single quoted PowerShell literal, or raise.

    Only shell-safe tokens are accepted; this is defence in depth on top of the
    strict hosts/URL validation performed by the callers.
    """
    if not is_shell_safe_token(value):
        raise ValidationError(f"{field_name} contains characters that are not allowed: {value!r}")
    return "'" + value + "'"


def validate_hosts(values: list[str], *, field_name: str = "targets") -> list[str]:
    cleaned: list[str] = []
    for raw in values:
        candidate = (raw or "").strip()
        if not candidate:
            continue
        cleaned.append(validate_host(candidate, field_name=field_name))
    if not cleaned:
        raise ValidationError(f"{field_name} must contain at least one valid entry")
    return cleaned
