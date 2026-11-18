"""Unit tests for app.network.validation — input validation helpers."""

from __future__ import annotations

import pytest

from app.network.validation import (
    HOSTNAME_RE,
    is_valid_host,
    is_valid_hostname,
    is_valid_ip,
    is_valid_ipv4,
    is_valid_ipv6,
    validate_host,
    validate_http_url,
    validate_port,
)

# --------------------------------------------------------------------------- #
# IP validation
# --------------------------------------------------------------------------- #

def test_is_valid_ipv4() -> None:
    assert is_valid_ipv4("1.1.1.1")
    assert is_valid_ipv4("192.168.0.1")
    assert not is_valid_ipv4("256.1.1.1")
    assert not is_valid_ipv4("1.1.1")
    assert not is_valid_ipv4("not-an-ip")


def test_is_valid_ipv6() -> None:
    assert is_valid_ipv6("::1")
    assert is_valid_ipv6("2001:db8::1")
    assert not is_valid_ipv6("1.1.1.1")
    assert not is_valid_ipv6("not-an-ip")


def test_is_valid_ip() -> None:
    assert is_valid_ip("1.1.1.1")
    assert is_valid_ip("::1")
    assert not is_valid_ip("google.com")
    assert not is_valid_ip("")


# --------------------------------------------------------------------------- #
# Hostname validation
# --------------------------------------------------------------------------- #

def test_is_valid_hostname() -> None:
    assert is_valid_hostname("google.com")
    assert is_valid_hostname("example.com.")
    assert is_valid_hostname("a" * 63 + ".com")  # max label length
    assert not is_valid_hostname("")
    assert not is_valid_hostname("-bad.com")     # leading hyphen
    assert not is_valid_hostname("bad-.com")     # trailing hyphen
    assert not is_valid_hostname("a" * 64 + ".com")  # label too long


def test_hostname_regex() -> None:
    assert HOSTNAME_RE.match("example.com")
    assert not HOSTNAME_RE.match("")


# --------------------------------------------------------------------------- #
# is_valid_host
# --------------------------------------------------------------------------- #

def test_is_valid_host() -> None:
    assert is_valid_host("1.1.1.1")
    assert is_valid_host("::1")
    assert is_valid_host("google.com")
    assert not is_valid_host("")
    assert not is_valid_host("not a host")


# --------------------------------------------------------------------------- #
# validate_host
# --------------------------------------------------------------------------- #

def test_validate_host_accepts_valid() -> None:
    assert validate_host("1.1.1.1") == "1.1.1.1"
    assert validate_host("google.com") == "google.com"


def test_validate_host_rejects_invalid() -> None:
    with pytest.raises(ValueError):
        validate_host("")
    with pytest.raises(ValueError):
        validate_host("not a host")


# --------------------------------------------------------------------------- #
# validate_port
# --------------------------------------------------------------------------- #

def test_validate_port() -> None:
    assert validate_port(443) == 443
    assert validate_port("80") == 80
    assert validate_port(1) == 1
    assert validate_port(65535) == 65535


def test_validate_port_invalid() -> None:
    with pytest.raises(ValueError):
        validate_port(0)
    with pytest.raises(ValueError):
        validate_port(65536)
    with pytest.raises(ValueError):
        validate_port("not-a-number")


# --------------------------------------------------------------------------- #
# validate_http_url
# --------------------------------------------------------------------------- #

def test_validate_http_url() -> None:
    assert validate_http_url("https://example.com/file.bin") == "https://example.com/file.bin"
    assert validate_http_url("http://1.1.1.1/test") == "http://1.1.1.1/test"


def test_validate_http_url_invalid() -> None:
    with pytest.raises(ValueError):
        validate_http_url("")
    with pytest.raises(ValueError):
        validate_http_url("ftp://example.com")
    with pytest.raises(ValueError):
        validate_http_url("not-a-url")
