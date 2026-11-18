"""Unit tests for app.network.wifi — netsh wlan output parsing.

The parser is a pure function, so these tests need neither Windows nor a
wireless adapter. Samples use English labels plus a few localised ones to
confirm the mapping works.
"""

from __future__ import annotations

from app.network.wifi import parse_wlan_interfaces


# --------------------------------------------------------------------------- #
# English netsh output
# --------------------------------------------------------------------------- #

ENGLISH_CONNECTED = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201
    GUID                   : 12345678-1234-1234-1234-123456789012
    Physical address       : 00-11-22-33-44-55
    State                  : connected
    SSID                   : MyHomeNetwork
    BSSID                  : aa:bb:cc:dd:ee:ff
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Auto
    Channel                : 36
    Receive rate (Mbps)    : 866.7
    Transmit rate (Mbps)   : 866.7
    Signal                 : 78%
    Profile                : MyHomeNetwork

    Hosted network status  : Not available
"""


ENGLISH_DISCONNECTED = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201
    GUID                   : 12345678-1234-1234-1234-123456789012
    Physical address       : 00-11-22-33-44-55
    State                  : disconnected
    SSID                   :
    BSSID                  :
    Network type           : Infrastructure
    Radio type             : 802.11ax
    Authentication         : WPA2-Personal
    Cipher                 : CCMP
    Connection mode        : Auto
    Channel                :
    Receive rate (Mbps)    :
    Transmit rate (Mbps)   :
    Signal                 :
    Profile                :

    Hosted network status  : Not available
"""


ENGLISH_NO_INTERFACE = """
There is no wireless interface on the system.
"""


def test_parse_wifi_english_connected() -> None:
    info = parse_wlan_interfaces(ENGLISH_CONNECTED)
    assert info.available is True
    assert info.ssid == "MyHomeNetwork"
    assert info.bssid == "aa:bb:cc:dd:ee:ff"
    assert info.state == "connected"
    assert info.signal_percent == 78
    assert info.radio_type == "802.11ax"
    assert info.channel == 36
    assert info.band == "5 GHz"  # channel 36 -> 5 GHz
    assert info.receive_rate_mbps == 866.7
    assert info.transmit_rate_mbps == 866.7


def test_parse_wifi_english_disconnected() -> None:
    info = parse_wlan_interfaces(ENGLISH_DISCONNECTED)
    assert info.available is True
    assert info.ssid is None
    assert info.signal_percent is None
    assert "not connected" in info.message.lower()


def test_parse_wifi_no_interface() -> None:
    info = parse_wlan_interfaces(ENGLISH_NO_INTERFACE)
    assert info.available is False


def test_parse_wifi_empty() -> None:
    info = parse_wlan_interfaces("")
    assert info.available is False
    assert "No output" in info.message


# --------------------------------------------------------------------------- #
# Localised labels
# --------------------------------------------------------------------------- #

GERMAN_CONNECTED = """
Es gibt 1 Schnittstelle im System:

    Name                   : WLAN
    Beschreibung           : Intel(R) Wi-Fi 6 AX201
    GUID                   : 12345678-1234-1234-1234-123456789012
    Physische Adresse      : 00-11-22-33-44-55
    Zustand                : verbunden
    SSID                   : FritzBox
    BSSID                  : aa:bb:cc:dd:ee:ff
    Netztyp                : Infrastruktur
    Funkstandard           : 802.11ax
    Authentifizierung      : WPA2-Personal
    Verschlüsselung        : CCMP
    Verbindungsmodus       : Auto
    Kanal                  : 1
    Empfangsrate (Mbps)    : 150.0
    Sende rate (Mbps)      : 150.0
    Signal                 : 92%
    Profil                 : FritzBox
"""


def test_parse_wifi_german_connected() -> None:
    info = parse_wlan_interfaces(GERMAN_CONNECTED)
    assert info.available is True
    assert info.ssid == "FritzBox"
    assert info.signal_percent == 92
    assert info.channel == 1
    assert info.band == "2.4 GHz"  # channel 1 -> 2.4 GHz


# --------------------------------------------------------------------------- #
# Value-shaped fallbacks for unknown labels
# --------------------------------------------------------------------------- #

VALUE_SHAPED = """
There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Generic Wi-Fi Adapter
    GUID                   : 12345678-1234-1234-1234-123456789012
    Physical address       : 00-11-22-33-44-55
    Zustand                : verbunden
    SSID                   : FallbackNet
    SomeUnknownLabel       : aa:bb:cc:dd:ee:ff
    AnotherUnknown         : 802.11ac
    YetAnother             : 2.4 GHz
    OneMore                : 6
    SignalUnknown          : 50%
    ReceiveUnknown         : 300 Mbps
    TransmitUnknown        : 300 Mbps
"""


def test_parse_wifi_value_shaped_fallbacks() -> None:
    info = parse_wlan_interfaces(VALUE_SHAPED)
    assert info.available is True
    assert info.ssid == "FallbackNet"
    assert info.bssid == "aa:bb:cc:dd:ee:ff"
    assert info.radio_type == "802.11ac"
    assert info.band == "2.4 GHz"
    assert info.channel == 6
    assert info.signal_percent == 50
    assert info.receive_rate_mbps == 300.0
    assert info.transmit_rate_mbps == 300.0


# --------------------------------------------------------------------------- #
# Band inference from channel
# --------------------------------------------------------------------------- #

def test_band_inference_2_4_ghz() -> None:
    info = parse_wlan_interfaces(ENGLISH_CONNECTED.replace("Channel                : 36", "Channel                : 11"))
    assert info.band == "2.4 GHz"


def test_band_inference_6_ghz() -> None:
    info = parse_wlan_interfaces(ENGLISH_CONNECTED.replace("Channel                : 36", "Channel                : 37"))
    assert info.band == "6 GHz"
