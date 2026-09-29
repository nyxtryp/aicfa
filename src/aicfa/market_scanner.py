"""Centralized causal live-market scanner foundation.

The scanner computes each configured asset/timeframe once per scan cycle.
Users are intentionally not part of this layer; fan-out/notifications belong
to a later subscription layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from .features import build_features
from .market_data import MarketDataProvider, MarketKey, completed_ohlcv, merge_ohlcv, next_since_ms


FeatureBuilder = Callable[[pd.DataFrame], pd.DataFrame]


@dataclass(frozen=True)
class ScanResult:
    key: MarketKey
    candles: pd.DataFrame
    features: pd.DataFrame
    latest: pd.Series


class CentralMarketScanner:
    """Stateful polling scanner with provider-independent data access."""

    def __init__(
        self,
        provider: MarketDataProvider,
        universe: list[MarketKey],
        *,
        fetch_limit: int = 1000,
        feature_builder: FeatureBuilder = build_features,
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
        self._history: dict[MarketKey, pd.DataFrame] = {}

    @property
    def history(self) -> dict[MarketKey, pd.DataFrame]:
        return {key: value.copy() for key, value in self._history.items()}

    def seed(self, key: MarketKey, candles: pd.DataFrame) -> None:
        if key not in self.universe:
            raise ValueError(f"Market key is not in scanner universe: {key}")
        self._history[key] = merge_ohlcv(self._history.get(key), candles)

    def scan_once(self, *, now_ms: int) -> list[ScanResult]:
        """Fetch, merge, filter completed candles and build current features."""
        results: list[ScanResult] = []

        for key in self.universe:
            current = self._history.get(key)
            since_ms = next_since_ms(current, timeframe=key.timeframe)
            incoming = self.provider.fetch_ohlcv(
                symbol=key.symbol,
                market_type=key.market_type,
                timeframe=key.timeframe,
                since_ms=since_ms,
                limit=self.fetch_limit,
            )
            merged = merge_ohlcv(current, incoming)
            completed = completed_ohlcv(
                merged,
                timeframe=key.timeframe,
                now_ms=now_ms,
            )
            if completed.empty:
                continue

            self._history[key] = completed
            features = self.feature_builder(completed)
            if features.empty:
                continue

            results.append(
                ScanResult(
                    key=key,
                    candles=completed.copy(),
                    features=features,
                    latest=features.iloc[-1].copy(),
                )
            )

        return results
