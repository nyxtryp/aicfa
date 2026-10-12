"""Binance USDⓈ-M candle configuration and closed-kline parsing.

This module deliberately does not connect to the network yet. It provides the
validated instrument/timeframe configuration and deterministic parser used by
the scanner's data-ingestion stage.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping


TRADFI_SYMBOLS: tuple[str, ...] = (
    "XAUUSDT", "CLUSDT", "SKHYNIXUSDT", "SOXLUSDT", "XAGUSDT",
    "SNDKUSDT", "BZUSDT", "KORUUSDT", "SPCXUSDT", "MUUSDT",
    "SKHYUSDT", "SAMSUNGUSDT", "SOXSUSDT", "MSTRUSDT", "CRCLUSDT",
    "QQQUSDT", "SNXXUSDT", "EWYUSDT", "NATGASUSDT", "NVDAUSDT",
    "SPYUSDT",
)

CRYPTO_SYMBOLS: tuple[str, ...] = (
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT",
    "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT",
    "DOTUSDT", "BCHUSDT", "LTCUSDT", "XLMUSDT", "HYPEUSDT",
    "SUIUSDT", "AAVEUSDT", "ZECUSDT", "TAOUSDT", "ENAUSDT",
    "ONDOUSDT", "NEARUSDT", "UNIUSDT", "1000PEPEUSDT",
    "1000BONKUSDT", "WLDUSDT", "INJUSDT", "ARBUSDT", "APTUSDT",
)

TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h")
ALL_SYMBOLS: tuple[str, ...] = TRADFI_SYMBOLS + CRYPTO_SYMBOLS
SYMBOL_SET = frozenset(ALL_SYMBOLS)
TIMEFRAME_SET = frozenset(TIMEFRAMES)
EXPECTED_STREAM_COUNT = len(ALL_SYMBOLS) * len(TIMEFRAMES)


@dataclass(frozen=True, slots=True)
class ClosedCandle:
    """A finalized Binance kline; timestamps are Unix milliseconds (UTC)."""

    symbol: str
    timeframe: str
    open_time_ms: int
    close_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def combined_stream_url(symbols: tuple[str, ...], timeframes: tuple[str, ...]) -> str:
    """Build a Binance combined-stream URL for a non-empty subscription set."""
    if not symbols or not timeframes:
        raise ValueError("symbols and timeframes must not be empty")
    streams = [
        f"{symbol.lower()}@kline_{timeframe}"
        for symbol in symbols
        for timeframe in timeframes
    ]
    return "wss://fstream.binance.com/market/stream?streams=" + "/".join(streams)


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid kline field: {field}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite kline field: {field}")
    return result


def parse_closed_kline(message: Mapping[str, Any]) -> ClosedCandle | None:
    """Parse a raw or combined Binance kline event.

    Returns None for non-kline events, unclosed candles, or symbols/timeframes
    outside the configured watchlist. Malformed kline payloads raise ValueError.
    """
    event: Any = message.get("data", message)
    if not isinstance(event, Mapping) or event.get("e") != "kline":
        return None

    kline = event.get("k")
    if not isinstance(kline, Mapping):
        raise ValueError("kline event is missing its k payload")
    if kline.get("x") is not True:
        return None

    symbol = str(kline.get("s", "")).upper()
    timeframe = str(kline.get("i", ""))
    if symbol not in SYMBOL_SET or timeframe not in TIMEFRAME_SET:
        return None

    try:
        open_time_ms = int(kline["t"])
        close_time_ms = int(kline["T"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid kline timestamp") from exc
    if open_time_ms < 0 or close_time_ms < open_time_ms:
        raise ValueError("invalid kline time range")

    candle = ClosedCandle(
        symbol=symbol,
        timeframe=timeframe,
        open_time_ms=open_time_ms,
        close_time_ms=close_time_ms,
        open=_decimal(kline.get("o"), "open"),
        high=_decimal(kline.get("h"), "high"),
        low=_decimal(kline.get("l"), "low"),
        close=_decimal(kline.get("c"), "close"),
        volume=_decimal(kline.get("v"), "volume"),
    )
    if candle.high < max(candle.open, candle.close, candle.low):
        raise ValueError("kline high is below another candle price")
    if candle.low > min(candle.open, candle.close, candle.high):
        raise ValueError("kline low is above another candle price")
    if candle.volume < 0:
        raise ValueError("kline volume must not be negative")
    return candle
