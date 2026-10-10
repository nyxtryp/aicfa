"""Live candle cache and event-driven market monitor for AICFA.

The monitor owns transport, local rolling OHLCV windows and recovery
checkpoints. It deliberately does not implement trading logic: closed-candle
events are handed to the existing AutonomousScanEngine.
"""
from __future__ import annotations

from dataclasses import dataclass
import csv
import json
import os
from pathlib import Path
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Sequence

import pandas as pd

from .data_requirements import TradingMode
from .market_data import MarketKey, merge_ohlcv, timeframe_ms, validate_ohlcv
from .websocket_market_data import BinanceWebSocketMarketDataTransport, WebSocketObservation


LIVE_CANDLE_MODE_TRIGGERS: dict[str, tuple[TradingMode, ...]] = {
    "1m": (TradingMode.SCALPING,),
    "5m": (TradingMode.SCALPING,),
    "15m": (TradingMode.INTRADAY,),
    "1h": (TradingMode.SWING,),
    "4h": (TradingMode.POSITION,),
}


BINANCE_WS_MAX_STREAMS = 200
BINANCE_WS_ROTATE_SECONDS = 23 * 60 * 60


def chunk_market_keys(keys: Sequence[MarketKey], *, max_streams: int = BINANCE_WS_MAX_STREAMS) -> tuple[tuple[MarketKey, ...], ...]:
    """Split unique market keys into Binance-safe connection-sized groups."""
    if max_streams <= 0:
        raise ValueError("max_streams must be positive")
    # Repeated setups can reference the same symbol/timeframe. Subscribe once;
    # the durable candle checkpoint handles duplicate events across sockets.
    values = tuple(dict.fromkeys(keys))
    return tuple(values[offset:offset + max_streams] for offset in range(0, len(values), max_streams))


WINDOWS: dict[str, int] = {
    "1m": 500,
    "5m": 500,
    "15m": 500,
    "1h": 500,
    "4h": 500,
    "1d": 365,
    "1w": 200,
}


@dataclass(frozen=True)
class CandleEvent:
    key: MarketKey
    timestamp_ms: int
    observed_at_ms: int
    high: float | None = None
    low: float | None = None
    close: float | None = None


class PersistentCandleStore:
    """Atomic rolling-window storage under AICFA_DATA_DIR/raw."""

    def __init__(self, root: str | Path, *, windows: dict[str, int] | None = None) -> None:
        self.root = Path(root)
        self.windows = dict(windows or WINDOWS)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, key: MarketKey) -> Path:
        symbol = key.symbol.replace("/", "_").replace(":", "_")
        return self.root / symbol / f"{key.timeframe}.csv"

    def load(self, key: MarketKey) -> pd.DataFrame:
        path = self._path(key)
        if not path.exists():
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        try:
            return validate_ohlcv(pd.read_csv(path))
        except (OSError, ValueError, pd.errors.ParserError):
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    def append(self, key: MarketKey, frame: pd.DataFrame) -> pd.DataFrame:
        with self._lock:
            merged = merge_ohlcv(self.load(key), frame)
            limit = self.windows.get(key.timeframe, 500)
            merged = merged.tail(limit).reset_index(drop=True)
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".csv.tmp")
            merged.to_csv(temp, index=False)
            temp.replace(path)
            return merged.copy()

    def replace(self, key: MarketKey, frame: pd.DataFrame) -> pd.DataFrame:
        """Atomically replace one rolling window with a verified candle batch."""
        with self._lock:
            merged = validate_ohlcv(frame).tail(self.windows.get(key.timeframe, 500)).reset_index(drop=True)
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(".csv.tmp")
            merged.to_csv(temp, index=False)
            temp.replace(path)
            return merged.copy()

    def seed(self, key: MarketKey, frame: pd.DataFrame) -> pd.DataFrame:
        return self.append(key, frame)


class LiveMarketDataCache:
    """Rolling local cache implementing the normal market-data provider contract."""

    def __init__(self, upstream: object, store: PersistentCandleStore) -> None:
        self.upstream = upstream
        self.store = store
        self._frames: dict[MarketKey, pd.DataFrame] = {}
        self._versions: dict[MarketKey, int] = {}
        self._lock = threading.RLock()

    def _versioned_copy(self, key: MarketKey, frame: pd.DataFrame) -> pd.DataFrame:
        result = frame.copy()
        result.attrs["aicfa_cache_version"] = self._versions.get(key, 0)
        return result

    def register_market_symbols(self, asset, venue_symbols, *, market_type="futures"):
        register = getattr(self.upstream, "register_market_symbols", None)
        if register is not None:
            register(asset, venue_symbols, market_type=market_type)

    def resolve_symbol(self, asset, *, market_type="futures"):
        return str(self.upstream.resolve_symbol(asset, market_type=market_type))

    def seed(self, key: MarketKey, frame: pd.DataFrame) -> pd.DataFrame:
        with self._lock:
            stored = self.store.seed(key, frame)
            self._frames[key] = stored
            self._versions[key] = self._versions.get(key, 0) + 1
            return self._versioned_copy(key, stored)

    def frame(self, key: MarketKey) -> pd.DataFrame | None:
        with self._lock:
            value = self._frames.get(key)
            return None if value is None else self._versioned_copy(key, value)

    def update(self, key: MarketKey, frame: pd.DataFrame) -> pd.DataFrame:
        with self._lock:
            updated = self.store.append(key, frame)
            self._frames[key] = updated
            self._versions[key] = self._versions.get(key, 0) + 1
            return self._versioned_copy(key, updated)

    @staticmethod
    def _candle_is_closed(timestamp_ms: int, timeframe: str, now_ms: int | None = None) -> bool:
        durations = {
            "1m": 60_000,
            "5m": 300_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
            "1d": 86_400_000,
            "1w": 604_800_000,
        }
        duration = durations.get(str(timeframe))
        if duration is None:
            return True
        current_ms = int(time.time() * 1000) if now_ms is None else int(now_ms)
        return int(timestamp_ms) + duration <= current_ms

    @classmethod
    def _closed_only(cls, frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        if frame.empty or "timestamp" not in frame.columns:
            return frame.copy()
        now_ms = int(time.time() * 1000)
        mask = frame["timestamp"].map(
            lambda value: cls._candle_is_closed(int(value), timeframe, now_ms)
        )
        return frame.loc[mask].reset_index(drop=True)

    def fetch_ohlcv(self, *, symbol, market_type, timeframe, since_ms, limit):
        key = MarketKey("binance", symbol, market_type, timeframe)
        cached = pd.DataFrame()
        needs_refresh = True
        with self._lock:
            cached = self._frames.get(key)
            if cached is None:
                cached = self.store.load(key)
                if not cached.empty:
                    self._frames[key] = cached
            closed = self._closed_only(cached, timeframe) if cached is not None else pd.DataFrame()
            if not closed.empty and len(closed) >= int(limit):
                # A full cache is not necessarily a current cache. If the WS
                # stream disconnected, the old implementation returned these
                # rows forever and the scanner kept analyzing stale candles.
                now_ms = int(time.time() * 1000)
                if timeframe == "1w":
                    now = pd.Timestamp(now_ms, unit="ms", tz="UTC")
                    current_week_open = now.normalize() - pd.Timedelta(days=now.weekday())
                    expected_latest_open = int(
                        (current_week_open - pd.Timedelta(days=7)).timestamp() * 1000
                    )
                else:
                    duration_ms = timeframe_ms(timeframe)
                    expected_latest_open = (now_ms // duration_ms) * duration_ms - duration_ms
                latest_cached_open = int(closed["timestamp"].iloc[-1])
                if latest_cached_open >= expected_latest_open:
                    # Never hand the analysis pipeline an open candle. Attach
                    # the cache generation so feature caching need not hash
                    # every OHLCV row on each lower-timeframe event.
                    return self._versioned_copy(key, closed.tail(limit))
            needs_refresh = True

        # Refresh whenever the cache does not contain enough *closed* candles.
        # This also repairs a cache seeded with an open final candle.
        refresh_limit = max(int(limit) + 1, int(limit))
        incoming = self.upstream.fetch_ohlcv(
            symbol=symbol, market_type=market_type, timeframe=timeframe,
            since_ms=since_ms, limit=refresh_limit,
        )
        merged = merge_ohlcv(cached if cached is not None else pd.DataFrame(), incoming)
        closed = self._closed_only(merged, timeframe)
        if not merged.empty:
            with self._lock:
                merged = merged.tail(
                    self.store.windows.get(timeframe, max(int(limit), 500))
                ).reset_index(drop=True)
                self._frames[key] = merged
                self._versions[key] = self._versions.get(key, 0) + 1
                self.store.append(key, incoming)
                closed = self._closed_only(merged, timeframe)
                return self._versioned_copy(key, closed.tail(limit))
        return closed.tail(limit).copy()

    def fetch_trades(self, *, symbol, market_type, limit):
        return self.upstream.fetch_trades(symbol=symbol, market_type=market_type, limit=limit)

    def fetch_order_book(self, *, symbol, market_type, limit=1):
        return self.upstream.fetch_order_book(symbol=symbol, market_type=market_type, limit=limit)

    def fetch_order_book_history(self, *, symbol, market_type, snapshots, interval_seconds):
        return self.upstream.fetch_order_book_history(
            symbol=symbol, market_type=market_type,
            snapshots=snapshots, interval_seconds=interval_seconds,
        )


class CandleCheckpoint:
    """Durable last-processed closed-candle timestamp per market/timeframe."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._values: dict[str, int] = {}
        self._load()

    @staticmethod
    def _key(key: MarketKey) -> str:
        return "|".join((key.exchange, key.symbol, key.market_type, key.timeframe))

    def _load(self) -> None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            values = payload.get("last_processed", {}) if isinstance(payload, dict) else {}
            self._values = {str(k): int(v) for k, v in values.items()}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self._values = {}

    def get(self, key: MarketKey) -> int | None:
        with self._lock:
            return self._values.get(self._key(key))

    def mark(self, key: MarketKey, timestamp_ms: int) -> None:
        with self._lock:
            current = self._values.get(self._key(key))
            if current is not None and timestamp_ms <= current:
                return
            self._values[self._key(key)] = int(timestamp_ms)
            temp = self.path.with_suffix(".json.tmp")
            temp.write_text(
                json.dumps({"version": 1, "last_processed": self._values}, separators=(",", ":")),
                encoding="utf-8",
            )
            temp.replace(self.path)


class LiveMarketCoordinator:
    """Seed 100+ configured markets once, then react to closed-candle events."""

    def __init__(
        self,
        universe,
        *,
        provider: object,
        data_dir: str | Path,
        on_candle: Callable[[CandleEvent], None],
        max_workers: int = 4,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        self.universe = universe
        self.cache = LiveMarketDataCache(
            provider,
            PersistentCandleStore(Path(data_dir) / "raw"),
        )
        self.checkpoint = CandleCheckpoint(Path(data_dir) / "journal" / "candle_checkpoints.json")
        self.on_candle = on_candle
        self.max_workers = max_workers
        self._stopped = threading.Event()
        # The fallback rotation is permitted only when the live candle feed
        # has gone quiet. Seed the clock at startup so a failed initial
        # connection eventually activates the safety net.
        self._last_observation_received_at_ms = int(time.time() * 1000)
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="aicfa-live")
        self._threads: list[threading.Thread] = []
        self._seed_thread: threading.Thread | None = None
        self._seed_done = threading.Event()
        self._dispatch_lock = threading.RLock()
        self._scheduled_keys: set[MarketKey] = set()
        self._pending_observations: dict[MarketKey, list[WebSocketObservation]] = {}
        self._resolved_market_keys: tuple[tuple[int, MarketKey], ...] = ()

    @property
    def monitored_timeframes(self) -> tuple[str, ...]:
        return tuple(WINDOWS)

    def seed_history(self) -> None:
        """Restore only local rolling windows; never duplicate the startup REST scan."""
        failures: list[str] = []
        for market in self.universe.markets:
            try:
                self.cache.register_market_symbols(
                    market.asset, market.venue_symbols, market_type="futures"
                )
                symbol = self.cache.resolve_symbol(market.asset, market_type="futures")
            except Exception as exc:
                failures.append(f"{market.asset}:symbol:{type(exc).__name__}:{exc}")
                continue
            for timeframe in self.monitored_timeframes:
                try:
                    key = MarketKey("binance", symbol, "futures", timeframe)
                    existing = self.cache.store.load(key)
                    if existing.empty:
                        continue
                    self.cache.seed(key, existing.tail(WINDOWS[timeframe]))
                except Exception as exc:
                    failures.append(f"{market.asset}:{timeframe}:{type(exc).__name__}:{exc}")
        if failures:
            print(
                "AICFA local history restore skipped failed market/timeframe(s): "
                + " | ".join(failures[:20]),
                flush=True,
            )
        self._seed_done.set()

    def wait_seed(self, timeout: float | None = None) -> bool:
        """Wait until the initial REST/local history pass has completed."""
        return self._seed_done.wait(timeout)

    def _dispatch(self, observation: WebSocketObservation) -> None:
        key = observation.key
        try:
            current = observation
            while not self._stopped.is_set():
                self._handle(current)
                with self._dispatch_lock:
                    pending = self._pending_observations.get(key)
                    if not pending:
                        self._pending_observations.pop(key, None)
                        self._scheduled_keys.discard(key)
                        return
                    # Preserve every closed candle in arrival order. Replacing
                    # this queue with only the newest observation loses events
                    # whenever analysis takes longer than the exchange cadence.
                    current = pending.pop(0)
                    if not pending:
                        self._pending_observations.pop(key, None)
                        # Keep the key scheduled until the just-popped event has
                        # finished; a new event arriving during _handle must queue.
                        self._pending_observations[key] = []
        except Exception:
            # Keep the failed event at the head of the queue. The durable
            # checkpoint has not advanced, so retrying is idempotent and
            # prevents a transient analysis/persistence error from losing it.
            with self._dispatch_lock:
                pending = self._pending_observations.setdefault(key, [])
                pending.insert(0, current)
                self._scheduled_keys.discard(key)
            raise

    def _retry_pending_key(self, key: MarketKey) -> None:
        if self._stopped.is_set():
            return
        with self._dispatch_lock:
            pending = self._pending_observations.get(key)
            if key in self._scheduled_keys or not pending:
                return
            current = pending.pop(0)
            if not pending:
                self._pending_observations[key] = []
            self._scheduled_keys.add(key)
        future = self._pool.submit(self._dispatch, current)

        def report_retry_failure(done) -> None:
            try:
                done.result()
            except Exception as exc:
                print(
                    f"AICFA live candle retry failed: {key.symbol} {key.timeframe}: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                if not self._stopped.is_set():
                    timer = threading.Timer(1.0, self._retry_pending_key, args=(key,))
                    timer.daemon = True
                    timer.start()

        future.add_done_callback(report_retry_failure)

    @property
    def last_observation_received_at_ms(self) -> int:
        return self._last_observation_received_at_ms

    def websocket_is_stale(self, *, max_age_seconds: float = 180.0, now_ms: int | None = None) -> bool:
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        current = int(time.time() * 1000) if now_ms is None else int(now_ms)
        return current - self._last_observation_received_at_ms > int(max_age_seconds * 1000)

    def _submit_observation(self, observation: WebSocketObservation) -> None:
        key = observation.key
        self._last_observation_received_at_ms = int(time.time() * 1000)
        with self._dispatch_lock:
            pending = self._pending_observations.get(key)
            if key in self._scheduled_keys:
                # Per-key FIFO preserves all confirmed candles when analysis is
                # slower than the feed. The dispatcher serializes this key while
                # other symbols/timeframes continue on the worker pool.
                self._pending_observations.setdefault(key, []).append(observation)
                return
            if pending:
                # A failed event may be waiting for its scheduled retry. If a
                # new candle arrives first, resume the oldest queued event,
                # never jump ahead of it.
                pending.append(observation)
                observation = pending.pop(0)
                if not pending:
                    self._pending_observations[key] = []
            self._scheduled_keys.add(key)
        future = self._pool.submit(self._dispatch, observation)
        def _report_failure(done) -> None:
            try:
                done.result()
            except Exception as exc:
                print(
                    f"AICFA live candle dispatch error: {key.symbol} {key.timeframe}: "
                    f"{type(exc).__name__}: {exc}; retrying in 1s",
                    flush=True,
                )
                if not self._stopped.is_set():
                    timer = threading.Timer(1.0, self._retry_pending_key, args=(key,))
                    timer.daemon = True
                    timer.start()
        future.add_done_callback(_report_failure)

    def _handle(self, observation: WebSocketObservation) -> None:
        key = observation.key
        timestamp = int(observation.data["timestamp"].iloc[-1])
        last = self.checkpoint.get(key)
        if last is not None and timestamp <= last:
            return
        self.cache.update(key, observation.data)
        candle = observation.data.iloc[-1]
        event = CandleEvent(
            key=key,
            timestamp_ms=timestamp,
            observed_at_ms=observation.observed_at_ms,
            high=float(candle["high"]),
            low=float(candle["low"]),
            close=float(candle["close"]),
        )
        self.on_candle(event)
        # Advance the durable checkpoint only after the candle was accepted by
        # the analysis pipeline. A failed analysis is replayed after restart.
        self.checkpoint.mark(key, timestamp)

    @staticmethod
    def _latest_closed_open(timeframe: str, now_ms: int) -> int:
        if timeframe == "1w":
            now = pd.Timestamp(now_ms, unit="ms", tz="UTC")
            current_week_open = now.normalize() - pd.Timedelta(days=now.weekday())
            return int((current_week_open - pd.Timedelta(days=7)).timestamp() * 1000)
        duration_ms = timeframe_ms(timeframe)
        return (int(now_ms) // duration_ms) * duration_ms - duration_ms

    def _recover_missed_candles(self, keys: tuple[MarketKey, ...]) -> bool:
        """Fetch actual closed candles after each durable checkpoint, in order.

        Return False on any incomplete gap; the caller must not resume WebSocket
        delivery until REST recovery succeeds, or the next candle could advance
        the checkpoint past missing history.
        """
        now_ms = int(time.time() * 1000)
        for key in keys:
            if self._stopped.is_set():
                return False
            last = self.checkpoint.get(key)
            if last is None:
                # On first startup the REST history seed supplies context; do
                # not replay hundreds of historical candles as live events.
                continue
            duration_ms = timeframe_ms(key.timeframe)
            latest_closed_open = self._latest_closed_open(key.timeframe, now_ms)
            if last >= latest_closed_open:
                continue
            cursor = last + duration_ms
            pages = 0
            while cursor <= latest_closed_open and not self._stopped.is_set():
                try:
                    frame = self.cache.upstream.fetch_ohlcv(
                        symbol=key.symbol,
                        market_type=key.market_type,
                        timeframe=key.timeframe,
                        since_ms=cursor,
                        limit=500,
                    )
                    frame = validate_ohlcv(frame)
                    frame = LiveMarketDataCache._closed_only(frame, key.timeframe)
                    frame = frame.loc[frame["timestamp"] >= cursor].sort_values("timestamp")
                except Exception as exc:
                    print(
                        f"AICFA candle recovery failed: {key.symbol} {key.timeframe}: "
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )
                    return False
                if frame.empty:
                    return False
                newest_timestamp = cursor - duration_ms
                for _, row in frame.iterrows():
                    timestamp = int(row["timestamp"])
                    if timestamp > latest_closed_open:
                        break
                    observation = WebSocketObservation(
                        key=key,
                        data=pd.DataFrame([row]).reset_index(drop=True),
                        observed_at_ms=timestamp + duration_ms - 1,
                    )
                    self._submit_observation(observation)
                    newest_timestamp = max(newest_timestamp, timestamp)
                next_cursor = newest_timestamp + duration_ms
                if next_cursor <= cursor:
                    return False
                cursor = next_cursor
                pages += 1
        return True

    def _stream(self, keys: tuple[MarketKey, ...]) -> None:
        # The exchange may close a stream session after a fixed lifetime. The
        # transport deliberately surfaces disconnects and 23-hour rotations;
        # repair the candle gap from REST before opening the next WebSocket.
        while not self._stopped.is_set():
            transport = BinanceWebSocketMarketDataTransport(
                keys=keys,
                state_store=None,
                timeout_seconds=10.0,
                # Surface disconnects and planned rotation so REST repairs the
                # candle gap before a new session starts.
                max_reconnects=0,
                reconnect_backoff_seconds=1.0,
                connection_max_age_seconds=BINANCE_WS_ROTATE_SECONDS,
            )
            try:
                for observation in transport.stream():
                    if self._stopped.is_set():
                        return
                    self._submit_observation(observation)
            except Exception as exc:
                print(
                    f"AICFA WebSocket stream interrupted: {type(exc).__name__}: {exc}",
                    flush=True,
                )
                # Do not reconnect to live candles while a historical gap is
                # still unresolved: otherwise the next event could advance the
                # durable checkpoint beyond missing candles.
                while not self._stopped.is_set():
                    if self._recover_missed_candles(keys):
                        break
                    if self._stopped.wait(2.0):
                        return
                if self._stopped.is_set() or self._stopped.wait(2.0):
                    return

    def start(self) -> None:
        # Do not block live transport on the initial REST seed. With a large
        # configured universe this is hundreds of HTTP requests; blocking here
        # leaves the terminal frozen and prevents the price/candle streams from
        # starting at all. WebSocket events may safely arrive first because the
        # cache provider refreshes missing/short windows on demand.
        self._seed_thread = threading.Thread(
            target=self.seed_history,
            name="aicfa-history-seed",
            daemon=True,
        )
        self._seed_thread.start()

        # Symbol resolution used to happen serially here. One unmapped/slow
        # market could therefore block startup for minutes, before the control
        # endpoint and initial scanner were even started. Resolve the configured
        # universe in bounded parallelism and keep failed markets out of the WS
        # transport; the canonical scanner can still resolve/fallback that market
        # when a manual or initial scan explicitly reaches it.
        def resolve_market(item: tuple[int, object]):
            index, market = item
            self.cache.register_market_symbols(
                market.asset, market.venue_symbols, market_type="futures"
            )
            resolver = getattr(self.cache.upstream, "resolve_market", None)
            if resolver is None:
                symbol = self.cache.resolve_symbol(market.asset, market_type="futures")
                provider_name = "binance"
            else:
                resolved_market = resolver(market.asset, market_type="futures")
                symbol = str(resolved_market.symbol)
                provider_name = str(getattr(resolved_market, "provider", "unknown")).strip().lower()
            return index, "futures", symbol, provider_name

        resolved: list[tuple[int, str, str, str]] = []
        with ThreadPoolExecutor(max_workers=min(12, max(1, len(self.universe.markets)))) as pool:
            futures = [
                pool.submit(resolve_market, (index, market))
                for index, market in enumerate(self.universe.markets)
            ]
            for future in futures:
                try:
                    resolved.append(future.result())
                except Exception as exc:
                    print(
                        f"AICFA live symbol resolution skipped market: "
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )

        by_market_type: dict[str, list[MarketKey]] = {}
        resolved_pairs: list[tuple[int, MarketKey]] = []
        rest_polled: list[tuple[int, str, str, str]] = []
        for index, market_type, symbol, provider_name in resolved:
            # Keep the canonical key/provider mapping for every successfully
            # resolved market. Binance markets use WebSocket; other venues use
            # candle-close-aligned REST polling, not a competing scan rotation.
            resolved_pairs.append((index, MarketKey("binance", symbol, market_type, "5m")))
            if provider_name == "binance":
                for timeframe in self.monitored_timeframes:
                    key = MarketKey("binance", symbol, market_type, timeframe)
                    by_market_type.setdefault(market_type, []).append(key)
            else:
                rest_polled.append((index, market_type, symbol, provider_name))

        self._resolved_market_keys = tuple(resolved_pairs)
        self._rest_polled_markets = tuple(rest_polled)

        for market_type, keys in by_market_type.items():
            for chunk_index, chunk in enumerate(chunk_market_keys(keys), start=1):
                thread = threading.Thread(
                    target=self._stream,
                    args=(chunk,),
                    name=f"aicfa-ws-{market_type}-{chunk_index}",
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()

        if self._rest_polled_markets:
            thread = threading.Thread(
                target=self._poll_non_binance_closed_candles,
                name="aicfa-rest-candle-events",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def _poll_non_binance_closed_candles(self) -> None:
        """Emit candle-close events for mapped venues without Binance WS support.

        REST requests are scheduled only at the close cadence of each timeframe.
        This is a candle-event fallback, not a per-symbol analysis rotation.
        """
        # Poll context timeframes too: daily/weekly closes refresh SMC zones even
        # though only the five trigger timeframes launch a trading profile.
        trigger_timeframes = tuple(self.monitored_timeframes)
        last_polled_bucket: dict[tuple[str, str], int] = {}
        while not self._stopped.is_set():
            now_ms = int(time.time() * 1000)
            due = []
            for timeframe in trigger_timeframes:
                duration = timeframe_ms(timeframe)
                # Only attempt polling during the short window after a candle close.
                if now_ms % duration < 8_000:
                    due.append(timeframe)
            if due:
                for _index, market_type, symbol, provider_name in self._rest_polled_markets:
                    for timeframe in due:
                        if self._stopped.is_set():
                            return
                        duration = timeframe_ms(timeframe)
                        bucket = now_ms // duration
                        poll_key = (symbol, timeframe)
                        if last_polled_bucket.get(poll_key) == bucket:
                            continue
                        key = MarketKey("binance", symbol, market_type, timeframe)
                        try:
                            frame = self.cache.upstream.fetch_ohlcv(
                                symbol=symbol,
                                market_type=market_type,
                                timeframe=timeframe,
                                since_ms=None,
                                limit=3,
                            )
                            closed = self.cache._closed_only(frame, timeframe)
                            if not closed.empty:
                                last_timestamp = int(closed["timestamp"].iloc[-1])
                                checkpoint = self.checkpoint.get(key)
                                if checkpoint is None or last_timestamp > checkpoint:
                                    observation = WebSocketObservation(
                                        key=key,
                                        data=closed.tail(1).reset_index(drop=True),
                                        observed_at_ms=now_ms,
                                    )
                                    self._submit_observation(observation)
                            # Empty/no-new-candle is a successful poll. On an
                            # exception leave the bucket unmarked so it retries
                            # within this close window rather than missing a candle.
                            last_polled_bucket[poll_key] = bucket
                        except Exception as exc:
                            print(
                                f"AICFA REST candle fallback failed: {symbol} {timeframe} "
                                f"venue={provider_name}: {type(exc).__name__}: {exc}",
                                flush=True,
                            )
            # Alignment is checked every second; API calls occur only after a
            # timeframe boundary and only for non-Binance markets.
            if self._stopped.wait(1.0):
                return

    def stop(self) -> None:
        self._stopped.set()
        self._pool.shutdown(wait=False, cancel_futures=True)



class BinancePriceMonitor:
    """Lightweight ticker stream used only for active SL/TP lifecycle checks."""

    def __init__(self, keys: Sequence[MarketKey], *, on_price: Callable[[MarketKey, float, int], None]) -> None:
        if not keys:
            raise ValueError("price monitor requires at least one market key")
        self.keys = tuple(keys)
        self.on_price = on_price
        self._stopped = threading.Event()
        self._threads: list[threading.Thread] = []

    @staticmethod
    def _stream_name(key: MarketKey) -> str:
        symbol = key.symbol.split(":", 1)[0].replace("/", "").replace("-", "").replace("_", "").lower()
        return f"{symbol}@miniTicker"

    @staticmethod
    def _url(key: MarketKey) -> str:
        return (
            "wss://stream.binance.com:9443/ws"
            if key.market_type == "spot"
            else "wss://fstream.binance.com/ws"
        )

    def _run(self, keys: tuple[MarketKey, ...]) -> None:
        import json
        from .websocket_market_data import default_websocket_connector
        while not self._stopped.is_set():
            connection = None
            try:
                connection = default_websocket_connector(self._url(keys[0]), timeout=10.0)
                connected_at = time.monotonic()
                connection.send(json.dumps({
                    "method": "SUBSCRIBE",
                    "params": [self._stream_name(key) for key in keys],
                    "id": 2,
                }))
                while not self._stopped.is_set():
                    if time.monotonic() - connected_at >= BINANCE_WS_ROTATE_SECONDS:
                        # Tickers are current-state observations; rotate proactively.
                        break
                    payload = json.loads(connection.recv())
                    if isinstance(payload, dict) and payload.get("code") is not None:
                        raise RuntimeError(
                            f"Binance price-stream subscription error: {payload.get('code')}: {payload.get('msg', '')}"
                        )
                    if isinstance(payload, dict) and "data" in payload:
                        payload = payload["data"]
                    if not isinstance(payload, dict) or payload.get("e") != "24hrMiniTicker":
                        continue
                    symbol = str(payload.get("s", "")).upper()
                    try:
                        price = float(payload["c"])
                        event_ms = int(payload.get("E", 0))
                    except (KeyError, TypeError, ValueError):
                        continue
                    for key in keys:
                        expected = key.symbol.split(":", 1)[0].replace("/", "").replace("-", "").replace("_", "").upper()
                        if expected == symbol:
                            self.on_price(key, price, event_ms)
                            break
            except Exception:
                if self._stopped.wait(2.0):
                    return
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except OSError:
                        pass

    def start(self) -> None:
        by_market_type: dict[str, list[MarketKey]] = {}
        for key in self.keys:
            by_market_type.setdefault(key.market_type, []).append(key)
        for market_type, keys in by_market_type.items():
            for chunk_index, chunk in enumerate(chunk_market_keys(keys), start=1):
                thread = threading.Thread(
                    target=self._run,
                    args=(chunk,),
                    name=f"aicfa-price-{market_type}-{chunk_index}",
                    daemon=True,
                )
                self._threads.append(thread)
                thread.start()

    def stop(self) -> None:
        self._stopped.set()


__all__ = [
    "WINDOWS",
    "BINANCE_WS_MAX_STREAMS",
    "BINANCE_WS_ROTATE_SECONDS",
    "chunk_market_keys",
    "CandleEvent",
    "PersistentCandleStore",
    "LiveMarketDataCache",
    "CandleCheckpoint",
    "LiveMarketCoordinator",
    "BinancePriceMonitor",
]
