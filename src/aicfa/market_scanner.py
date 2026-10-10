"""Centralized causal live-market scanner with a persistent rolling OHLCV window.

Each market/timeframe owns an independent bounded history. The CSV cache is
atomically replaced so a process restart can resume from the last saved candle.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Callable

import pandas as pd

from .features import build_features
from .market_data import MarketDataProvider, MarketKey, completed_ohlcv, merge_ohlcv, next_since_ms


FeatureBuilder = Callable[[pd.DataFrame], pd.DataFrame]
OHLCV_WINDOW_SIZES = {
    "1m": 500,
    "5m": 500,
    "15m": 500,
    "1h": 500,
    "4h": 500,
    "1d": 365,
    "1w": 200,
    "1M": 24,
}


def rolling_window_size(timeframe: str) -> int:
    """Return the configured maximum number of retained candles."""
    try:
        return OHLCV_WINDOW_SIZES[timeframe]
    except KeyError as exc:
        raise ValueError(f"No rolling OHLCV window configured for {timeframe}") from exc


@dataclass(frozen=True)
class ScanResult:
    key: MarketKey
    candles: pd.DataFrame
    features: pd.DataFrame
    latest: pd.Series


class CentralMarketScanner:
    """Stateful polling scanner with a persistent, bounded OHLCV cache."""

    def __init__(
        self,
        provider: MarketDataProvider,
        universe: list[MarketKey],
        *,
        fetch_limit: int = 1000,
        feature_builder: FeatureBuilder = build_features,
        cache_dir: str | Path | None = None,
    ) -> None:
        if fetch_limit <= 0:
            raise ValueError("fetch_limit must be positive")
        if not universe:
            raise ValueError("universe must not be empty")
        if len(set(universe)) != len(universe):
            raise ValueError("universe contains duplicate market keys")

        self.provider = provider
        self.universe = tuple(universe)
        self.fetch_limit = fetch_limit
        self.feature_builder = feature_builder
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._history: dict[MarketKey, pd.DataFrame] = {}
        self._loaded: set[MarketKey] = set()

    @staticmethod
    def _cache_filename(key: MarketKey) -> str:
        identity = "\\0".join((key.exchange, key.symbol, key.market_type, key.timeframe))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
        return f"{digest}.csv"

    def _cache_path(self, key: MarketKey) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / self._cache_filename(key)

    def _load_history(self, key: MarketKey) -> pd.DataFrame | None:
        if key in self._loaded:
            return self._history.get(key)
        self._loaded.add(key)
        path = self._cache_path(key)
        if path is None or not path.is_file():
            return self._history.get(key)
        loaded = pd.read_csv(path)
        if loaded.empty:
            return None
        merged = merge_ohlcv(None, loaded).tail(rolling_window_size(key.timeframe)).reset_index(drop=True)
        self._history[key] = merged
        return merged

    def _save_history(self, key: MarketKey, candles: pd.DataFrame) -> None:
        path = self._cache_path(key)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        candles.to_csv(temporary, index=False)
        os.replace(temporary, path)

    @property
    def history(self) -> dict[MarketKey, pd.DataFrame]:
        return {key: value.copy() for key, value in self._history.items()}

    def seed(self, key: MarketKey, candles: pd.DataFrame) -> None:
        if key not in self.universe:
            raise ValueError(f"Market key is not in scanner universe: {key}")
        self._loaded.add(key)
        merged = merge_ohlcv(self._history.get(key), candles)
        bounded = merged.tail(rolling_window_size(key.timeframe)).reset_index(drop=True)
        self._history[key] = bounded
        self._save_history(key, bounded)

    def scan_once(self, *, now_ms: int) -> list[ScanResult]:
        """Incrementally fetch candles, persist a rolling window, then build features."""
        results: list[ScanResult] = []

        for key in self.universe:
            current = self._load_history(key)
            window_size = rolling_window_size(key.timeframe)
            since_ms = next_since_ms(current, timeframe=key.timeframe)
            # Bootstrap only the required window; later requests continue from
            # the next candle instead of downloading the full history again.
            limit = min(self.fetch_limit, window_size) if current is None or current.empty else min(self.fetch_limit, 100)
            incoming = self.provider.fetch_ohlcv(
                symbol=key.symbol,
                market_type=key.market_type,
                timeframe=key.timeframe,
                since_ms=since_ms,
                limit=limit,
            )
            merged = merge_ohlcv(current, incoming)
            completed = completed_ohlcv(merged, timeframe=key.timeframe, now_ms=now_ms)
            bounded = completed.tail(window_size).reset_index(drop=True)
            if bounded.empty:
                continue

            self._history[key] = bounded
            self._save_history(key, bounded)
            features = self.feature_builder(bounded)
            if features.empty:
                continue

            results.append(
                ScanResult(
                    key=key,
                    candles=bounded.copy(),
                    features=features,
                    latest=features.iloc[-1].copy(),
                )
            )

        return results
