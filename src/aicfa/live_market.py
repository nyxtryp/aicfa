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
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Sequence

import pandas as pd

from .data_requirements import TradingMode
from .market_data import MarketKey, merge_ohlcv, validate_ohlcv
from .websocket_market_data import BinanceWebSocketMarketDataTransport, WebSocketObservation


WINDOWS: dict[str, int] = {
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

    def seed(self, key: MarketKey, frame: pd.DataFrame) -> pd.DataFrame:
        return self.append(key, frame)


class LiveMarketDataCache:
    """Rolling local cache implementing the normal market-data provider contract."""

    def __init__(self, upstream: object, store: PersistentCandleStore) -> None:
        self.upstream = upstream
        self.store = store
        self._frames: dict[MarketKey, pd.DataFrame] = {}
        self._lock = threading.RLock()

    def register_market_symbols(self, asset, venue_symbols, *, market_type="spot"):
        register = getattr(self.upstream, "register_market_symbols", None)
        if register is not None:
            register(asset, venue_symbols, market_type=market_type)

    def resolve_symbol(self, asset, *, market_type="spot"):
        return str(self.upstream.resolve_symbol(asset, market_type=market_type))

    def seed(self, key: MarketKey, frame: pd.DataFrame) -> pd.DataFrame:
        with self._lock:
            stored = self.store.seed(key, frame)
            self._frames[key] = stored
            return stored.copy()

    def frame(self, key: MarketKey) -> pd.DataFrame | None:
        with self._lock:
            value = self._frames.get(key)
            return None if value is None else value.copy()

    def update(self, key: MarketKey, frame: pd.DataFrame) -> pd.DataFrame:
        with self._lock:
            updated = self.store.append(key, frame)
            self._frames[key] = updated
            return updated.copy()

    def fetch_ohlcv(self, *, symbol, market_type, timeframe, since_ms, limit):
        key = MarketKey("binance", symbol, market_type, timeframe)
        with self._lock:
            cached = self._frames.get(key)
            if cached is None:
                cached = self.store.load(key)
                if not cached.empty:
                    self._frames[key] = cached
            if cached is not None and not cached.empty:
                return cached.tail(limit).copy()
        return self.upstream.fetch_ohlcv(
            symbol=symbol, market_type=market_type, timeframe=timeframe,
            since_ms=since_ms, limit=limit,
        )

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
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="aicfa-live")
        self._threads: list[threading.Thread] = []

    @property
    def monitored_timeframes(self) -> tuple[str, ...]:
        return tuple(WINDOWS)

    def seed_history(self) -> None:
        """Restore local windows first; fetch only when a window is incomplete."""
        for market in self.universe.markets:
            self.cache.register_market_symbols(
                market.asset, market.venue_symbols, market_type=market.market_type
            )
            symbol = self.cache.resolve_symbol(market.asset, market_type=market.market_type)
            for timeframe in self.monitored_timeframes:
                key = MarketKey("binance", symbol, market.market_type, timeframe)
                existing = self.cache.store.load(key)
                target = WINDOWS[timeframe]
                if len(existing) < target:
                    incoming = self.cache.upstream.fetch_ohlcv(
                        symbol=symbol,
                        market_type=market.market_type,
                        timeframe=timeframe,
                        since_ms=None,
                        limit=target,
                    )
                    self.cache.seed(key, incoming)
                else:
                    self.cache.seed(key, existing.tail(target))

    def _handle(self, observation: WebSocketObservation) -> None:
        key = observation.key
        timestamp = int(observation.data["timestamp"].iloc[-1])
        last = self.checkpoint.get(key)
        if last is not None and timestamp <= last:
            return
        self.cache.update(key, observation.data)
        event = CandleEvent(key=key, timestamp_ms=timestamp, observed_at_ms=observation.observed_at_ms)
        self.on_candle(event)
        # Advance the durable checkpoint only after the candle was accepted by
        # the analysis pipeline. A failed analysis is replayed after restart.
        self.checkpoint.mark(key, timestamp)

    def _stream(self, keys: tuple[MarketKey, ...]) -> None:
        transport = BinanceWebSocketMarketDataTransport(
            keys=keys,
            state_store=None,
            timeout_seconds=10.0,
            max_reconnects=20,
            reconnect_backoff_seconds=1.0,
        )
        for observation in transport.stream():
            if self._stopped.is_set():
                return
            self._pool.submit(self._handle, observation)

    def start(self) -> None:
        self.seed_history()
        by_market_type: dict[str, list[MarketKey]] = {}
        for market in self.universe.markets:
            symbol = self.cache.resolve_symbol(market.asset, market_type=market.market_type)
            for timeframe in self.monitored_timeframes:
                by_market_type.setdefault(market.market_type, []).append(
                    MarketKey("binance", symbol, market.market_type, timeframe)
                )
        for market_type, keys in by_market_type.items():
            thread = threading.Thread(
                target=self._stream,
                args=(tuple(keys),),
                name=f"aicfa-ws-{market_type}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def stop(self) -> None:
        self._stopped.set()
        self._pool.shutdown(wait=False, cancel_futures=True)


__all__ = [
    "WINDOWS",
    "CandleEvent",
    "PersistentCandleStore",
    "LiveMarketDataCache",
    "CandleCheckpoint",
    "LiveMarketCoordinator",
]
