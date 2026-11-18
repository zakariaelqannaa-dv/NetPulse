"""Wi-Fi diagnostics based on ``netsh wlan show interfaces``.

``netsh`` prints *localised field labels*, so NetPulse maps a broad set of
localised labels to canonical fields and additionally falls back to
value-shaped heuristics (percentages, ``802.11xx`` radio types, ``GHz`` bands,
MAC addresses). Parsing is a pure function so it can be tested against English,
Chinese, German, French, Spanish and Russian samples.
"""

from __future__ import annotations

import re

from app.core.cancellation import CancellationToken
from app.core.models import WifiInfo
from app.network.proc import run_command

WLAN_ARGS = ["netsh", "wlan", "show", "interfaces"]

_PERCENT_RE = re.compile(r"^(\d{1,3})\s*%$")
_RADIO_TYPE_RE = re.compile(r"^802\.11([a-zA-Z]{1,3})$")
_BAND_RE = re.compile(r"^(\d(?:[.,]\d)?)\s*GHz$", re.IGNORECASE)
_MAC_RE = re.compile(r"^([0-9a-f]{2}[:\-]){5}[0-9a-f]{2}$", re.IGNORECASE)
_NUMBER_RE = re.compile(r"^(\d+(?:[.,]\d+)?)$")

#: canonical field -> normalised localised labels (lower case, punctuation removed)
_LABEL_ALIASES: dict[str, set[str]] = {
    "ssid": {"ssid"},
    "bssid": {"bssid"},
    "state": {
        "state",
        "status",
        "zustand",
        "estado",
        "etat",
        "état",
        "stato",
        "состояние",
        "状态",
        "狀態",
        "状態",
        "상태",
        "situacao",
        "situação",
        "staat",
    },
    "signal": {
        "signal",
        "signalstarke",
        "signalstärke",
        "senal",
        "señal",
        "segnale",
        "сигнал",
        "信号",
        "信號",
        "シグナル",
        "신호",
        "sinal",
        "ontvangstsignaal",
    },
    "channel": {
        "channel",
        "kanal",
        "canal",
        "канал",
        "信道",
        "チャネル",
        "채널",
        "kanaal",
    },
    "radio_type": {
        "radiotype",
        "funktyp",
        "tipoderadio",
        "typederadio",
        "tipodidiradio",
        "типрадио",
        "无线电类型",
        "無線電類型",
        "無線の種類",
        "무선종류",
        "radiotyp",
    },
    "receive_rate": {
        "receiverate",
        "receiveratembps",
        "empfangsrate",
        "empfangsratembps",
        "velocidadderecepcion",
        "velocidadderecepción",
        "tauxdereception",
        "tauxderéception",
        "velocitadiricezione",
        "скоростьприема",
        "接收速率",
        "受信速度",
        "수신속도",
        "taxaderecebimento",
        "ontvangstsnelheid",
    },
    "transmit_rate": {
        "transmitrate",
        "transmitratembps",
        "ubertragungsrate",
        "übertragungsrate",
        "ubertragungsratembps",
        "velocidaddetransmision",
        "velocidaddetransmisión",
        "tauxdetransmission",
        "velocitaditrasmissione",
        "скоростьпередачи",
        "传输速率",
        "傳輸速率",
        "送信速度",
        "송신속도",
        "taxadetransmissao",
        "zendsnelheid",
    },
    "band": {"band", "frequenzband", "banda", "диапазон", "频段", "頻段", "バンド", "대역", "faixa"},
}

_CONNECTED_STATES = {
    "connected",
    "verbunden",
    "connecte",
    "connecté",
    "conectado",
    "подключено",
    "已连接",
    "已連接",
    "接続されています",
    "연결됨",
    "connesso",
    "ligado",
}

_DISCONNECTED_STATES = {
    "disconnected",
    "getrennt",
    "deconnecte",
    "déconnecté",
    "desconectado",
    "отключено",
    "已断开连接",
    "已中斷連線",
    "接続されていません",
    "연결 끊김",
    "disconnesso",
    "desligado",
}

_PUNCT_RE = re.compile(r"[\s\-_.()（）:：\[\]/]+")

#: Localised "Name" label that starts a new interface section in netsh output.
_INTERFACE_NAME_LABELS = {
    "name",
    "nom",
    "nombre",
    "nome",
    "имя",
    "名称",
    "名稱",
    "名前",
    "이름",
    "naam",
}


def normalise_label(label: str) -> str:
    return _PUNCT_RE.sub("", (label or "").strip().lower())


def canonical_field(label: str) -> str | None:
    normalised = normalise_label(label)
    if not normalised:
        return None
    if normalised.startswith("bssid"):
        return "bssid"
    for field_name, aliases in _LABEL_ALIASES.items():
        if normalised in aliases:
            return field_name
    for field_name, aliases in _LABEL_ALIASES.items():
        for alias in aliases:
            if len(alias) >= 4 and alias in normalised:
                return field_name
    return None


def _parse_number(value: str) -> float | None:
    match = _NUMBER_RE.match(value.strip())
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except ValueError:  # pragma: no cover
        return None


def _split_line(line: str) -> tuple[str, str] | None:
    for separator in (":", "："):
        if separator in line:
            label, _, value = line.partition(separator)
            return label.strip(), value.strip()
    return None


def parse_wlan_interfaces(text: str) -> WifiInfo:
    """Parse ``netsh wlan show interfaces`` output into :class:`WifiInfo`."""
    info = WifiInfo()
    if not text or not text.strip():
        info.message = 'No output from "netsh wlan show interfaces".'
        return info

    blocks: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if current:
                blocks.append(current)
                current = {}
            continue
        split = _split_line(line)
        if split is None:
            continue
        label, value = split
        field_name = canonical_field(label)
        if field_name and value:
            current[field_name] = value
        elif value and normalise_label(label) in _INTERFACE_NAME_LABELS:
            if current:
                blocks.append(current)
                current = {}
            current["interface"] = value
        elif value and not field_name:
            # Value-shaped fallbacks for localised labels. A MAC address is only
            # treated as the BSSID inside the associated-network section (after
            # the SSID line); the adapter's own "Physical address" comes earlier.
            if _MAC_RE.match(value) and "bssid" not in current and "ssid" in current:
                current["bssid"] = value
            elif _PERCENT_RE.match(value) and "signal" not in current:
                current["signal"] = value
            elif _RADIO_TYPE_RE.match(value) and "radio_type" not in current:
                current["radio_type"] = value
            elif _BAND_RE.match(value) and "band" not in current:
                current["band"] = value
            elif _NUMBER_RE.match(value) and "channel" not in current and "radio_type" in current:
                current["channel"] = value
    if current:
        blocks.append(current)

    if not blocks:
        info.message = "No Wi-Fi interface data was reported by Windows."
        return info

    def score(block: dict[str, str]) -> tuple[int, int]:
        state = (block.get("state") or "").lower()
        connected = 1 if state in _CONNECTED_STATES else 0
        return (connected, len(block))

    block = max(blocks, key=score)
    state = block.get("state")
    info.state = state
    info.ssid = block.get("ssid")
    info.bssid = block.get("bssid")
    info.radio_type = block.get("radio_type")
    info.band = block.get("band")

    signal_raw = block.get("signal", "")
    percent_match = _PERCENT_RE.match(signal_raw.strip())
    if percent_match:
        try:
            info.signal_percent = int(percent_match.group(1))
        except ValueError:  # pragma: no cover
            info.signal_percent = None

    channel_value = _parse_number(block.get("channel", ""))
    if channel_value is not None:
        info.channel = int(channel_value)

    receive = _parse_number(block.get("receive_rate", ""))
    transmit = _parse_number(block.get("transmit_rate", ""))
    info.receive_rate_mbps = receive
    info.transmit_rate_mbps = transmit

    state_lower = (state or "").lower()
    if state_lower in _DISCONNECTED_STATES:
        info.available = True
        info.message = "A Wi-Fi interface exists but is not connected, so radio metrics are unavailable."
    elif not info.ssid and not info.signal_percent:
        info.available = False
        info.message = "A Wi-Fi adapter was found but no associated network was reported."
    else:
        info.available = True

    if info.available and not info.band and info.channel is not None:
        info.band = "2.4 GHz" if info.channel <= 14 else "5 GHz" if info.channel < 200 else "6 GHz"
    return info


def collect_wifi(token: CancellationToken | None = None, timeout: float = 10.0) -> WifiInfo:
    """Run ``netsh wlan show interfaces`` and parse the result."""
    result = run_command(WLAN_ARGS, timeout=timeout, token=token)
    if result.error and not result.stdout:
        info = WifiInfo()
        info.message = f"Wi-Fi data unavailable: {result.error}"
        return info
    info = parse_wlan_interfaces(result.stdout or result.combined)
    if result.cancelled:
        info.message = "Wi-Fi query was cancelled."
    return info


__all__ = ["canonical_field", "collect_wifi", "normalise_label", "parse_wlan_interfaces"]
