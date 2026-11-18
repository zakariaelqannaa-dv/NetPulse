"""Unit tests for app.network.ping_parse — ping output parsing."""

from __future__ import annotations

from app.network.ping_parse import (
    expand_rtts,
    parse_ping_output,
    parse_rtt_token,
)


# --------------------------------------------------------------------------- #
# parse_rtt_token
# --------------------------------------------------------------------------- #

def test_parse_rtt_token_plain_ms() -> None:
    assert parse_rtt_token("time=13ms") == 13.0


def test_parse_rtt_token_less_than() -> None:
    # Windows prints "<1ms" for sub-millisecond replies -> 0.5 ms
    assert parse_rtt_token("time<1ms") == 0.5
    assert parse_rtt_token("<1ms") == 0.5


def test_parse_rtt_token_decimal_comma() -> None:
    assert parse_rtt_token("time=12,5ms") == 12.5


def test_parse_rtt_token_no_match() -> None:
    assert parse_rtt_token("Request timed out.") is None
    assert parse_rtt_token("") is None


# --------------------------------------------------------------------------- #
# parse_ping_output
# --------------------------------------------------------------------------- #

def test_parse_ping_output_all_lost() -> None:
    text = (
        "Request timed out.\n"
        "Request timed out.\n"
        "Request timed out.\n"
        "Request timed out.\n"
        "\n"
        "Packets: Sent = 4, Received = 0, Lost = 4 (100% loss),\n"
    )
    parsed = parse_ping_output(text)
    assert parsed.rtts == []
    assert parsed.timeouts == 4
    assert parsed.sent == 4
    assert parsed.received == 0
    assert "timed out" in parsed.message


def test_parse_ping_output_mixed() -> None:
    text = (
        "Reply from 1.1.1.1: bytes=32 time=12ms TTL=56\n"
        "Request timed out.\n"
        "Reply from 1.1.1.1: bytes=32 time=15ms TTL=56\n"
        "\n"
        "Packets: Sent = 3, Received = 2, Lost = 1 (33% loss),\n"
    )
    parsed = parse_ping_output(text)
    assert parsed.rtts == [12.0, 15.0]
    assert parsed.timeouts == 1
    assert parsed.sent == 3
    assert parsed.received == 2


def test_parse_ping_output_empty() -> None:
    parsed = parse_ping_output("")
    assert parsed.rtts == []
    assert parsed.message == "No output from ping"


def test_parse_ping_output_unreachable() -> None:
    text = (
        "Reply from 10.0.0.1: Destination host unreachable.\n"
        "Reply from 10.0.0.1: Destination host unreachable.\n"
    )
    parsed = parse_ping_output(text)
    assert parsed.unreachable == 2


# --------------------------------------------------------------------------- #
# expand_rtts
# --------------------------------------------------------------------------- #

def test_expand_rtts_pads_lost() -> None:
    from app.network.ping_parse import PingParseResult

    parsed = PingParseResult(rtts=[1.0, 2.0], timeouts=2, unreachable=1)
    series = expand_rtts(parsed, expected=5)
    assert series == [1.0, 2.0, None, None, None]


def test_expand_rtts_truncates_to_expected() -> None:
    from app.network.ping_parse import PingParseResult

    parsed = PingParseResult(rtts=[1.0, 2.0, 3.0], timeouts=0, unreachable=0)
    series = expand_rtts(parsed, expected=2)
    assert series == [1.0, 2.0]
