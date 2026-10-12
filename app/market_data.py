"""Binance USDⓈ-M candle configuration, parsing, and live stream ingestion."""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import threading
import urllib.error
import email.utils
from pathlib import Path
from collections import deque
import logging
import time
import urllib.parse
import urllib.request
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
RECONCILIATION_INTERVAL_SECONDS = 3600
WS_ROTATION_INTERVAL_SECONDS = 23 * 60 * 60
WS_ROTATION_RETRY_SECONDS = 60
WS_ROTATION_CONFIRM_SECONDS = 1
REST_KLINES_URL = "https://fapi.binance.com/fapi/v1/klines"
REST_MIN_INTERVAL_SECONDS = 0.25
REST_FALLBACK_DELAY_MS = 2_500
REST_MAX_RATE_LIMIT_RETRIES = 5
REST_MAX_BACKOFF_SECONDS = 60.0
_rest_request_lock = threading.Lock()
_rest_next_request_at = 0.0


def _retry_after_seconds(error: urllib.error.HTTPError) -> float | None:
    raw = error.headers.get("Retry-After") if error.headers else None
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        try:
            return max(0.0, email.utils.parsedate_to_datetime(raw).timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return None


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



class SQLiteCandleStore:
    """Durable closed-candle store using SQLite WAL and a 500-row per-series cap."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured = path or os.environ.get("AICFA_DATA_DIR", "/srv/frostdeploy/aicfa/shared/data")
        configured_path = Path(configured)
        self.path = configured_path if configured_path.suffix == ".db" else configured_path / "candles.sqlite3"
        self._connection: sqlite3.Connection | None = None
        self._thread_lock = threading.RLock()

    def initialize(self) -> None:
        with self._thread_lock:
            if self._connection is not None:
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.path), timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS candles (
                    symbol TEXT NOT NULL, timeframe TEXT NOT NULL,
                    open_time_ms INTEGER NOT NULL, close_time_ms INTEGER NOT NULL,
                    open TEXT NOT NULL, high TEXT NOT NULL, low TEXT NOT NULL,
                    close TEXT NOT NULL, volume TEXT NOT NULL,
                    PRIMARY KEY (symbol, timeframe, open_time_ms)
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_candles_series_time ON candles(symbol, timeframe, open_time_ms DESC)")
            connection.commit()
            self._connection = connection

    def _db(self) -> sqlite3.Connection:
        if self._connection is None:
            self.initialize()
        assert self._connection is not None
        return self._connection

    @staticmethod
    def _values(candle: ClosedCandle) -> tuple[Any, ...]:
        return (candle.symbol, candle.timeframe, candle.open_time_ms, candle.close_time_ms,
                str(candle.open), str(candle.high), str(candle.low), str(candle.close), str(candle.volume))

    def upsert_many(self, candles: list[ClosedCandle] | tuple[ClosedCandle, ...]) -> None:
        if not candles:
            return
        with self._thread_lock:
            db = self._db()
            db.executemany("""
                INSERT INTO candles (symbol, timeframe, open_time_ms, close_time_ms, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, timeframe, open_time_ms) DO UPDATE SET
                    close_time_ms=excluded.close_time_ms, open=excluded.open, high=excluded.high,
                    low=excluded.low, close=excluded.close, volume=excluded.volume
            """, (self._values(candle) for candle in candles))
            for symbol, timeframe in {(c.symbol, c.timeframe) for c in candles}:
                db.execute("""
                    DELETE FROM candles WHERE symbol=? AND timeframe=? AND open_time_ms NOT IN (
                        SELECT open_time_ms FROM candles WHERE symbol=? AND timeframe=?
                        ORDER BY open_time_ms DESC LIMIT ?
                    )
                """, (symbol, timeframe, symbol, timeframe, CANDLES_PER_SERIES))
            db.commit()

    def load_window(self, symbol: str, timeframe: str) -> tuple[ClosedCandle, ...]:
        with self._thread_lock:
            rows = self._db().execute("""
                SELECT symbol, timeframe, open_time_ms, close_time_ms, open, high, low, close, volume
                FROM candles WHERE symbol=? AND timeframe=? ORDER BY open_time_ms DESC LIMIT ?
            """, (symbol, timeframe, CANDLES_PER_SERIES)).fetchall()
        return tuple(ClosedCandle(
            symbol=r["symbol"], timeframe=r["timeframe"], open_time_ms=r["open_time_ms"],
            close_time_ms=r["close_time_ms"], open=Decimal(r["open"]), high=Decimal(r["high"]),
            low=Decimal(r["low"]), close=Decimal(r["close"]), volume=Decimal(r["volume"])
        ) for r in reversed(rows))

    def count(self) -> int:
        with self._thread_lock:
            return int(self._db().execute("SELECT COUNT(*) FROM candles").fetchone()[0])

    def close(self) -> None:
        with self._thread_lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


class MarketDataManager:
    """Two reconnecting Binance connections with a rolling closed-candle window.

    SQLite/WAL is the durable source of closed candles; memory holds the latest
    500 candles per configured symbol/timeframe for fast analysis.
    """

    def __init__(self) -> None:
        self.candles: dict[tuple[str, str], deque[ClosedCandle]] = {}
        self.latest: dict[tuple[str, str], ClosedCandle] = {}
        self.groups: dict[str, dict[str, Any]] = {
            "tradfi": self._new_group(len(TRADFI_SYMBOLS) * len(TIMEFRAMES)),
            "crypto": self._new_group(len(CRYPTO_SYMBOLS) * len(TIMEFRAMES)),
        }
        self._tasks: list[asyncio.Task[None]] = []
        self._fallback_tasks: list[asyncio.Task[None]] = []
        self._history_task: asyncio.Task[None] | None = None
        self._reconciliation_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._lock = asyncio.Lock()
        self.store = SQLiteCandleStore()
        self.history_status: dict[str, Any] = {
            "status": "not_started",
            "series_loaded": 0,
            "candles_loaded": 0,
            "errors": [],
        }
        self.reconciliation_status: dict[str, Any] = {
            "status": "waiting",
            "interval_seconds": RECONCILIATION_INTERVAL_SECONDS,
            "last_attempt_ms": None,
            "last_success_ms": None,
            "series_checked": 0,
            "candles_checked": 0,
            "errors": [],
        }

    @staticmethod
    def _new_group(expected: int) -> dict[str, Any]:
        return {
            "status": "stopped",
            "expected_streams": expected,
            "messages": 0,
            "closed_candles": 0,
            "invalid_messages": 0,
            "reconnects": 0,
            "rotations": 0,
            "fallback_polls": 0,
            "fallback_errors": 0,
            "last_message_ms": None,
            "last_closed_candle_ms": None,
            "last_error": None,
        }

    async def start(self) -> None:
        if self._tasks:
            return
        self._stopping = False
        # Fail startup if durable storage cannot be initialized; restore saved
        # windows before REST synchronization begins.
        self.store.initialize()
        restored_series = 0
        restored_candles = 0
        for symbol in ALL_SYMBOLS:
            for timeframe in TIMEFRAMES:
                series = self.store.load_window(symbol, timeframe)
                if series:
                    key = (symbol, timeframe)
                    self.candles[key] = deque(series, maxlen=CANDLES_PER_SERIES)
                    self.latest[key] = series[-1]
                    restored_series += 1
                    restored_candles += len(series)
        logger.info("Restored %s candle series / %s candles from SQLite", restored_series, restored_candles)
        # Do not block ASGI startup/health checks on 250 REST requests.
        self._history_task = asyncio.create_task(
            self.load_history(), name="aicfa-rest-history"
        )
        self._tasks = [
            asyncio.create_task(self._run_group("tradfi", TRADFI_SYMBOLS), name="aicfa-ws-tradfi"),
            asyncio.create_task(self._run_group("crypto", CRYPTO_SYMBOLS), name="aicfa-ws-crypto"),
        ]
        self._fallback_tasks = [
            asyncio.create_task(self._rest_fallback_loop("tradfi", TRADFI_SYMBOLS), name="aicfa-rest-fallback-tradfi"),
            asyncio.create_task(self._rest_fallback_loop("crypto", CRYPTO_SYMBOLS), name="aicfa-rest-fallback-crypto"),
        ]
        self._reconciliation_task = asyncio.create_task(
            self._reconciliation_loop(), name="aicfa-rest-reconciliation"
        )

    async def stop(self) -> None:
        self._stopping = True
        tasks, self._tasks = self._tasks, []
        if self._history_task is not None:
            self._history_task.cancel()
            await asyncio.gather(self._history_task, return_exceptions=True)
            self._history_task = None
        if self._reconciliation_task is not None:
            self._reconciliation_task.cancel()
            await asyncio.gather(self._reconciliation_task, return_exceptions=True)
            self._reconciliation_task = None
        fallback_tasks, self._fallback_tasks = self._fallback_tasks, []
        for task in fallback_tasks:
            task.cancel()
        if fallback_tasks:
            await asyncio.gather(*fallback_tasks, return_exceptions=True)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for state in self.groups.values():
            state["status"] = "stopped"
        self.store.close()

    @staticmethod
    def _fetch_rest_klines(symbol: str, timeframe: str) -> list[Any]:
        """Fetch klines with process-wide pacing and bounded rate-limit retries."""
        global _rest_next_request_at
        query = urllib.parse.urlencode({
            "symbol": symbol,
            "interval": timeframe,
            "limit": CANDLES_PER_SERIES + 1,
        })
        request = urllib.request.Request(
            f"{REST_KLINES_URL}?{query}",
            headers={"User-Agent": "AICFA/0.1"},
        )
        # Share one lock across history, gap recovery, and hourly reconciliation.
        with _rest_request_lock:
            retries = 0
            while True:
                delay = _rest_next_request_at - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                try:
                    # Pace every attempt, including responses that raise HTTPError.
                    _rest_next_request_at = time.monotonic() + REST_MIN_INTERVAL_SECONDS
                    with urllib.request.urlopen(request, timeout=20) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    if not isinstance(payload, list):
                        raise ValueError("Binance klines response is not a list")
                    return payload
                except urllib.error.HTTPError as exc:
                    if exc.code not in (418, 429) or retries >= REST_MAX_RATE_LIMIT_RETRIES:
                        raise
                    exponential = min(2.0 ** retries, REST_MAX_BACKOFF_SECONDS)
                    server_delay = _retry_after_seconds(exc)
                    wait_seconds = max(exponential, server_delay or 0.0)
                    retries += 1
                    logger.warning(
                        "Binance REST rate limit for %s %s (HTTP %s); retry %s/%s in %.1fs",
                        symbol, timeframe, exc.code, retries,
                        REST_MAX_RATE_LIMIT_RETRIES, wait_seconds,
                    )
                    time.sleep(wait_seconds)
                    # The server delay was honored; do not add a second pacing wait.
                    _rest_next_request_at = time.monotonic()
    @staticmethod
    def _parse_rest_candle(symbol: str, timeframe: str, row: Any) -> ClosedCandle | None:
        if not isinstance(row, list) or len(row) < 7:
            raise ValueError("invalid REST kline row")
        try:
            open_time_ms = int(row[0])
            close_time_ms = int(row[6])
        except (TypeError, ValueError, IndexError) as exc:
            raise ValueError("invalid REST kline timestamp") from exc
        if close_time_ms >= int(time.time() * 1000):
            return None
        candle = ClosedCandle(
            symbol=symbol,
            timeframe=timeframe,
            open_time_ms=open_time_ms,
            close_time_ms=close_time_ms,
            open=_decimal(row[1], "open"),
            high=_decimal(row[2], "high"),
            low=_decimal(row[3], "low"),
            close=_decimal(row[4], "close"),
            volume=_decimal(row[5], "volume"),
        )
        if candle.high < max(candle.open, candle.close, candle.low):
            raise ValueError("REST kline high is below another candle price")
        if candle.low > min(candle.open, candle.close, candle.high):
            raise ValueError("REST kline low is above another candle price")
        if candle.volume < 0:
            raise ValueError("REST kline volume must not be negative")
        return candle

    async def load_history(self) -> None:
        """Warm each of the 250 series with its latest 500 closed REST candles.

        Ask Binance for 501 rows because the last row may still be forming.
        Filtering that row leaves enough data for the full 500-candle window.
        """
        self.history_status = {
            "status": "loading",
            "series_loaded": 0,
            "candles_loaded": 0,
            "errors": [],
        }
        semaphore = asyncio.Semaphore(6)

        async def load_series(symbol: str, timeframe: str) -> None:
            async with semaphore:
                try:
                    rows = await asyncio.to_thread(self._fetch_rest_klines, symbol, timeframe)
                    candles = []
                    for row in rows:
                        candle = self._parse_rest_candle(symbol, timeframe, row)
                        if candle is not None:
                            candles.append(candle)
                    candles.sort(key=lambda item: item.open_time_ms)
                    key = (symbol, timeframe)
                    async with self._lock:
                        # Merge REST history with candles that arrived live while
                        # warm-up was running; retain unique timestamps and the
                        # newest 500 closed candles without discarding live data.
                        merged = {
                            item.open_time_ms: item
                            for item in self.candles.get(
                                key, deque(maxlen=CANDLES_PER_SERIES)
                            )
                        }
                        for item in candles:
                            merged.setdefault(item.open_time_ms, item)
                        series = deque(
                            sorted(merged.values(), key=lambda item: item.open_time_ms)[-CANDLES_PER_SERIES:],
                            maxlen=CANDLES_PER_SERIES,
                        )
                        self.candles[key] = series
                        if series:
                            self.latest[key] = series[-1]
                        self.store.upsert_many(tuple(series))
                        self.history_status["series_loaded"] += 1
                        self.history_status["candles_loaded"] += len(series)
                except Exception as exc:
                    self.history_status["errors"].append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "error": type(exc).__name__,
                        "detail": str(exc)[:240],
                    })
                    logger.warning(
                        "REST history failed for %s %s (%s)",
                        symbol, timeframe, type(exc).__name__,
                    )

        await asyncio.gather(*(
            load_series(symbol, timeframe)
            for symbol in ALL_SYMBOLS
            for timeframe in TIMEFRAMES
        ))
        self.history_status["status"] = (
            "complete"
            if self.history_status["series_loaded"] == EXPECTED_STREAM_COUNT
            and self.history_status["candles_loaded"] == EXPECTED_STREAM_COUNT * CANDLES_PER_SERIES
            and not self.history_status["errors"]
            else "partial"
        )

    @staticmethod
    def _timeframe_ms(timeframe: str) -> int:
        """Return the fixed duration of a supported Binance kline interval."""
        durations = {"1m": 60_000, "5m": 300_000, "15m": 900_000,
                     "1h": 3_600_000, "4h": 14_400_000}
        try:
            return durations[timeframe]
        except KeyError as exc:
            raise ValueError(f"unsupported timeframe: {timeframe}") from exc

    async def _recover_series_gap(self, symbol: str, timeframe: str) -> None:
        """Reconcile a series from REST after a detected live-candle time gap."""
        rows = await asyncio.to_thread(self._fetch_rest_klines, symbol, timeframe)
        restored: list[ClosedCandle] = []
        for row in rows:
            candle = self._parse_rest_candle(symbol, timeframe, row)
            if candle is not None:
                restored.append(candle)
        restored.sort(key=lambda item: item.open_time_ms)
        if not restored:
            raise ValueError("REST gap recovery returned no closed candles")

        key = (symbol, timeframe)
        async with self._lock:
            merged = {item.open_time_ms: item for item in self.candles.get(
                key, deque(maxlen=CANDLES_PER_SERIES)
            )}
            # REST is authoritative for candles missed while the WebSocket was disconnected.
            for item in restored:
                merged[item.open_time_ms] = item
            series = deque(
                sorted(merged.values(), key=lambda item: item.open_time_ms)[-CANDLES_PER_SERIES:],
                maxlen=CANDLES_PER_SERIES,
            )
            self.store.upsert_many(tuple(series))
            self.candles[key] = series
            if series:
                self.latest[key] = series[-1]

    async def _reconcile_series(self, symbol: str, timeframe: str) -> int:
        """Compare the latest closed REST candles with memory/SQLite and repair differences."""
        rows = await asyncio.to_thread(self._fetch_rest_klines, symbol, timeframe)
        restored: list[ClosedCandle] = []
        for row in rows:
            candle = self._parse_rest_candle(symbol, timeframe, row)
            if candle is not None:
                restored.append(candle)
        restored.sort(key=lambda item: item.open_time_ms)
        if not restored:
            raise ValueError("REST reconciliation returned no closed candles")

        key = (symbol, timeframe)
        async with self._lock:
            merged = {
                item.open_time_ms: item
                for item in self.candles.get(key, deque(maxlen=CANDLES_PER_SERIES))
            }
            # REST is authoritative for matching timestamps; keep newer live candles
            # if the REST response is momentarily behind the stream.
            for item in restored:
                merged[item.open_time_ms] = item
            series = deque(
                sorted(merged.values(), key=lambda item: item.open_time_ms)[-CANDLES_PER_SERIES:],
                maxlen=CANDLES_PER_SERIES,
            )
            self.store.upsert_many(tuple(series))
            self.candles[key] = series
            if series:
                self.latest[key] = series[-1]
        return len(restored)

    async def reconcile_all_series(self) -> None:
        """Reconcile all 250 configured series with REST, limiting concurrency."""
        self.reconciliation_status.update({
            "status": "running",
            "series_checked": 0,
            "candles_checked": 0,
            "errors": [],
        })
        semaphore = asyncio.Semaphore(6)

        async def reconcile_one(symbol: str, timeframe: str) -> None:
            async with semaphore:
                try:
                    count = await self._reconcile_series(symbol, timeframe)
                    self.reconciliation_status["series_checked"] += 1
                    self.reconciliation_status["candles_checked"] += count
                except Exception as exc:
                    self.reconciliation_status["errors"].append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "error": type(exc).__name__,
                        "detail": str(exc)[:240],
                    })
                    logger.warning(
                        "REST reconciliation failed for %s %s (%s)",
                        symbol, timeframe, type(exc).__name__,
                    )

        await asyncio.gather(*(
            reconcile_one(symbol, timeframe)
            for symbol in ALL_SYMBOLS
            for timeframe in TIMEFRAMES
        ))
        finished_ms = int(time.time() * 1000)
        self.reconciliation_status["last_attempt_ms"] = finished_ms
        if not self.reconciliation_status["errors"] and self.reconciliation_status["series_checked"] == EXPECTED_STREAM_COUNT:
            self.reconciliation_status["status"] = "complete"
            self.reconciliation_status["last_success_ms"] = finished_ms
        else:
            self.reconciliation_status["status"] = "partial"

    async def _rest_fallback_loop(self, name: str, symbols: tuple[str, ...]) -> None:
        """Poll only series whose next candle has closed while this WS group is down.

        All REST calls still pass through the shared process-wide request pacer.
        Polling is disabled while the WebSocket is healthy; failed series retry
        after five seconds, and successful series are scheduled for their next close.
        """
        try:
            if self._history_task is not None:
                await self._history_task
            keys = [(symbol, timeframe) for symbol in symbols for timeframe in TIMEFRAMES]
            next_due_ms: dict[tuple[str, str], int] = {}
            while not self._stopping:
                if self.groups[name]["status"] in ("connected", "rotating"):
                    await asyncio.sleep(0.5)
                    continue
                now_ms = int(time.time() * 1000)
                due_keys: list[tuple[str, str]] = []
                for key in keys:
                    if key not in next_due_ms:
                        latest = self.latest.get(key)
                        next_due_ms[key] = max(now_ms, latest.close_time_ms + REST_FALLBACK_DELAY_MS) if latest else now_ms
                    if next_due_ms[key] <= now_ms:
                        due_keys.append(key)
                if not due_keys:
                    wait_ms = min(next_due_ms.values()) - now_ms
                    await asyncio.sleep(min(0.5, max(0.05, wait_ms / 1000)))
                    continue
                key = min(due_keys, key=lambda item: next_due_ms[item])
                try:
                    await self._reconcile_series(*key)
                    self.groups[name]["fallback_polls"] += 1
                    latest = self.latest.get(key)
                    interval_ms = self._timeframe_ms(key[1])
                    next_due_ms[key] = (
                        latest.close_time_ms + interval_ms + REST_FALLBACK_DELAY_MS
                        if latest else now_ms + interval_ms + REST_FALLBACK_DELAY_MS
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.groups[name]["fallback_errors"] += 1
                    self.groups[name]["last_error"] = f"rest_fallback:{type(exc).__name__}"
                    next_due_ms[key] = int(time.time() * 1000) + 5000
                    logger.warning("REST fallback failed for %s %s (%s)", key[0], key[1], type(exc).__name__)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("REST fallback loop stopped for %s (%s)", name, type(exc).__name__)

    async def _reconciliation_loop(self) -> None:
        """Run the first REST reconciliation one hour after startup, then hourly.

        Startup history already fills the 250 series. Running a second full REST
        pass immediately after history needlessly doubles startup traffic and can
        trigger Binance 429 responses; live closed candles continue to arrive by
        WebSocket while the hourly reconciliation timer is waiting. An unexpected
        failure in one cycle is recorded but must not permanently disable later
        hourly reconciliation attempts.
        """
        try:
            if self._history_task is not None:
                await self._history_task
            while not self._stopping:
                await asyncio.sleep(RECONCILIATION_INTERVAL_SECONDS)
                if self._stopping:
                    return
                try:
                    await self.reconcile_all_series()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.reconciliation_status["status"] = "failed"
                    self.reconciliation_status["last_attempt_ms"] = int(time.time() * 1000)
                    logger.exception(
                        "Unexpected REST reconciliation failure (%s); next hourly attempt remains scheduled",
                        type(exc).__name__,
                    )
        except asyncio.CancelledError:
            raise

    async def _consume_socket(self, name: str, socket: Any) -> None:
        """Consume one socket; overlapping old/new sockets are deduplicated by candle timestamp."""
        state = self.groups[name]
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
            previous = self.latest.get((candle.symbol, candle.timeframe))
            interval_ms = self._timeframe_ms(candle.timeframe)
            if previous is not None and candle.open_time_ms > previous.open_time_ms + interval_ms:
                try:
                    await self._recover_series_gap(candle.symbol, candle.timeframe)
                    logger.warning("Recovered candle gap via REST for %s %s",
                                   candle.symbol, candle.timeframe)
                except Exception as exc:
                    state["last_error"] = f"gap_recovery:{type(exc).__name__}"
                    logger.warning("REST gap recovery failed for %s %s (%s)",
                                   candle.symbol, candle.timeframe, type(exc).__name__)
                    continue
            async with self._lock:
                if not self.add_closed_candle(candle):
                    continue
            state["closed_candles"] += 1
            state["last_closed_candle_ms"] = candle.close_time_ms

    async def _run_group_connection(self, name: str, url: str) -> None:
        """Keep a group live, rotating its socket make-before-break every 23 hours."""
        state = self.groups[name]
        active_context = websockets.connect(
            url, ping_interval=20, ping_timeout=20, close_timeout=10, max_queue=4096
        )
        active_socket = await active_context.__aenter__()
        consumer = asyncio.create_task(self._consume_socket(name, active_socket))
        rotation_deadline = asyncio.get_running_loop().time() + WS_ROTATION_INTERVAL_SECONDS
        try:
            state["status"] = "connected"
            state["last_error"] = None
            while not self._stopping:
                remaining = max(0.0, rotation_deadline - asyncio.get_running_loop().time())
                done, _ = await asyncio.wait({consumer}, timeout=remaining)
                if done:
                    # Propagate an exception or reconnect if the iterator ended unexpectedly.
                    consumer.result()
                    raise ConnectionError("Binance WebSocket stream ended")

                state["status"] = "rotating"
                replacement_context = websockets.connect(
                    url, ping_interval=20, ping_timeout=20, close_timeout=10, max_queue=4096
                )
                try:
                    replacement_socket = await replacement_context.__aenter__()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    # Keep the existing connection alive and retry the rotation shortly.
                    state["status"] = "connected"
                    state["last_error"] = f"rotation_connect:{type(exc).__name__}"
                    logger.warning("Binance %s rotation connection failed (%s); keeping old socket",
                                   name, type(exc).__name__)
                    rotation_deadline = asyncio.get_running_loop().time() + WS_ROTATION_RETRY_SECONDS
                    continue

                replacement_consumer = asyncio.create_task(
                    self._consume_socket(name, replacement_socket)
                )
                # The handshake succeeded and the new consumer must remain alive briefly
                # before the old connection is retired. Duplicate candles are rejected.
                try:
                    await asyncio.sleep(WS_ROTATION_CONFIRM_SECONDS)
                except BaseException:
                    replacement_consumer.cancel()
                    await asyncio.gather(replacement_consumer, return_exceptions=True)
                    await replacement_context.__aexit__(None, None, None)
                    raise
                if replacement_consumer.done():
                    try:
                        replacement_consumer.result()
                        replacement_error = "stream_ended"
                    except Exception as exc:
                        replacement_error = type(exc).__name__
                    replacement_consumer.cancel()
                    await asyncio.gather(replacement_consumer, return_exceptions=True)
                    await replacement_context.__aexit__(None, None, None)
                    state["status"] = "connected"
                    state["last_error"] = f"rotation_unhealthy:{replacement_error}"
                    logger.warning("Binance %s replacement was not healthy; keeping old socket",
                                   name)
                    rotation_deadline = asyncio.get_running_loop().time() + WS_ROTATION_RETRY_SECONDS
                    continue

                old_context, old_consumer = active_context, consumer
                active_context, consumer = replacement_context, replacement_consumer
                old_consumer.cancel()
                await asyncio.gather(old_consumer, return_exceptions=True)
                await old_context.__aexit__(None, None, None)
                state["status"] = "connected"
                state["last_error"] = None
                state["rotations"] += 1
                logger.info("Binance %s WebSocket rotated successfully; new socket confirmed before old socket closed",
                            name)
                rotation_deadline = asyncio.get_running_loop().time() + WS_ROTATION_INTERVAL_SECONDS
        finally:
            if not consumer.done():
                consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)
            await active_context.__aexit__(None, None, None)

    async def _run_group(self, name: str, symbols: tuple[str, ...]) -> None:
        state = self.groups[name]
        url = combined_stream_url(symbols, TIMEFRAMES)
        backoff = 1
        while not self._stopping:
            try:
                state["status"] = "connecting"
                await self._run_group_connection(name, url)
                if self._stopping:
                    break
                raise ConnectionError("Binance WebSocket connection stopped unexpectedly")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
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
        # Persist before publishing to the in-memory window.
        if self.store._connection is not None:
            self.store.upsert_many((candle,))
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

    def _freshness_status(self, now_ms: int | None = None) -> dict[str, Any]:
        """Summarize missing/stale candle series without treating higher timeframes as late."""
        checked_at_ms = int(time.time() * 1000) if now_ms is None else now_ms
        stale_after_grace_ms = 120_000
        missing: list[dict[str, str]] = []
        stale: list[dict[str, Any]] = []
        max_age_ms = 0
        series_with_data = 0
        for symbol in ALL_SYMBOLS:
            for timeframe in TIMEFRAMES:
                candle = self.latest.get((symbol, timeframe))
                if candle is None:
                    missing.append({"symbol": symbol, "timeframe": timeframe})
                    continue
                series_with_data += 1
                age_ms = max(0, checked_at_ms - candle.close_time_ms)
                max_age_ms = max(max_age_ms, age_ms)
                allowed_age_ms = self._timeframe_ms(timeframe) + stale_after_grace_ms
                if age_ms > allowed_age_ms:
                    stale.append({
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "age_ms": age_ms,
                        "allowed_age_ms": allowed_age_ms,
                    })
        return {
            "checked_at_ms": checked_at_ms,
            "series_with_data": series_with_data,
            "missing_series": len(missing),
            "stale_series": len(stale),
            "max_age_ms": max_age_ms,
            "missing_details": missing[:25],
            "stale_details": stale[:25],
            "grace_ms": stale_after_grace_ms,
        }

    def status(self) -> dict[str, Any]:
        return {
            "status": "connected" if all(g["status"] == "connected" for g in self.groups.values()) else "degraded",
            "instruments": len(ALL_SYMBOLS),
            "timeframes": list(TIMEFRAMES),
            "expected_streams": EXPECTED_STREAM_COUNT,
            "latest_series": len(self.latest),
            "stored_candles": sum(len(series) for series in self.candles.values()),
            "window_size": CANDLES_PER_SERIES,
            "freshness": self._freshness_status(),
            "persistence": {"backend": "sqlite", "journal_mode": "WAL", "database_path": str(self.store.path), "stored_candles": self.store.count() if self.store._connection is not None else 0},
            "history": dict(self.history_status),
            "reconciliation": dict(self.reconciliation_status),
            "groups": {name: dict(state) for name, state in self.groups.items()},
        }
