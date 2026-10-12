"""Binance USDⓈ-M candle configuration, parsing, and live stream ingestion."""
from __future__ import annotations

import asyncio
import json
from collections import deque
import logging
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger("aicfa.market_data")

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
CANDLES_PER_SERIES = 500


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
    """Return a validated candle only for a configured, finalized kline event."""
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


class MarketDataManager:
    """Two reconnecting Binance connections with a rolling closed-candle window.

    The 500-candle windows are currently in memory. REST warm-up, durable
    persistence, and SMC processing remain separate follow-up tasks.
    """

    def __init__(self) -> None:
        self.candles: dict[tuple[str, str], deque[ClosedCandle]] = {}
        self.latest: dict[tuple[str, str], ClosedCandle] = {}
        self.groups: dict[str, dict[str, Any]] = {
            "tradfi": self._new_group(len(TRADFI_SYMBOLS) * len(TIMEFRAMES)),
            "crypto": self._new_group(len(CRYPTO_SYMBOLS) * len(TIMEFRAMES)),
        }
        self._tasks: list[asyncio.Task[None]] = []
        self._stopping = False
        self._lock = asyncio.Lock()

    @staticmethod
    def _new_group(expected: int) -> dict[str, Any]:
        return {
            "status": "stopped",
            "expected_streams": expected,
            "messages": 0,
            "closed_candles": 0,
            "invalid_messages": 0,
            "reconnects": 0,
            "last_message_ms": None,
            "last_closed_candle_ms": None,
            "last_error": None,
        }

    async def start(self) -> None:
        if self._tasks:
            return
        self._stopping = False
        self._tasks = [
            asyncio.create_task(self._run_group("tradfi", TRADFI_SYMBOLS), name="aicfa-ws-tradfi"),
            asyncio.create_task(self._run_group("crypto", CRYPTO_SYMBOLS), name="aicfa-ws-crypto"),
        ]

    async def stop(self) -> None:
        self._stopping = True
        tasks, self._tasks = self._tasks, []
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for state in self.groups.values():
            state["status"] = "stopped"

    async def _run_group(self, name: str, symbols: tuple[str, ...]) -> None:
        state = self.groups[name]
        url = combined_stream_url(symbols, TIMEFRAMES)
        backoff = 1
        while not self._stopping:
            try:
                state["status"] = "connecting"
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=10,
                    max_queue=4096,
                ) as socket:
                    state["status"] = "connected"
                    state["last_error"] = None
                    backoff = 1
                    async for raw in socket:
                        state["messages"] += 1
                        state["last_message_ms"] = int(time.time() * 1000)
                        try:
                            message = json.loads(raw)
                            if not isinstance(message, Mapping):
                                continue
                            candle = parse_closed_kline(message)
                        except (json.JSONDecodeError, ValueError, TypeError) as exc:
                            state["invalid_messages"] += 1
                            logger.warning("Invalid Binance message (%s): %s", name, exc)
                            continue
                        if candle is None:
                            continue
                        async with self._lock:
                            if not self.add_closed_candle(candle):
                                continue
                        state["closed_candles"] += 1
                        state["last_closed_candle_ms"] = candle.close_time_ms
            except asyncio.CancelledError:
                raise
            except (OSError, ConnectionClosed, asyncio.TimeoutError, Exception) as exc:
                if self._stopping:
                    break
                state["status"] = "reconnecting"
                state["last_error"] = type(exc).__name__
                state["reconnects"] += 1
                logger.warning("Binance %s stream disconnected (%s); retrying", name, type(exc).__name__)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)
        state["status"] = "stopped"

    def add_closed_candle(self, candle: ClosedCandle) -> bool:
        """Append a newer closed candle and evict the oldest beyond 500."""
        key = (candle.symbol, candle.timeframe)
        if key[0] not in SYMBOL_SET or key[1] not in TIMEFRAME_SET:
            return False
        previous = self.latest.get(key)
        if previous is not None and candle.open_time_ms <= previous.open_time_ms:
            return False
        series = self.candles.setdefault(
            key, deque(maxlen=CANDLES_PER_SERIES)
        )
        series.append(candle)
        self.latest[key] = candle
        return True

    def candle_window(self, symbol: str, timeframe: str) -> tuple[ClosedCandle, ...]:
        """Return a stable snapshot of the stored closed-candle window."""
        series = self.candles.get((symbol.upper(), timeframe))
        return tuple(series) if series is not None else ()

    def status(self) -> dict[str, Any]:
        return {
            "status": "connected" if all(g["status"] == "connected" for g in self.groups.values()) else "degraded",
            "instruments": len(ALL_SYMBOLS),
            "timeframes": list(TIMEFRAMES),
            "expected_streams": EXPECTED_STREAM_COUNT,
            "latest_series": len(self.latest),
            "stored_candles": sum(len(series) for series in self.candles.values()),
            "window_size": CANDLES_PER_SERIES,
            "groups": {name: dict(state) for name, state in self.groups.items()},
        }
