"""Request-scoped market-data routing and short-lived shared snapshots.

Market data is never persisted as history. The snapshot cache only shares a
fresh request result for a maximum of TTL seconds, then discards it.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Sequence

import pandas as pd

from .market_data import MarketDataProvider


@dataclass(frozen=True)
class ProviderAttempt:
    provider: str
    error: str


@dataclass(frozen=True)
class MarketFetchResult:
    provider: str
    symbol: str
    frame: pd.DataFrame
    attempts: tuple[ProviderAttempt, ...] = ()


@dataclass(frozen=True)
class SnapshotKey:
    source: str
    market_type: str
    symbol: str
    timeframe: str
    data_profile: str


@dataclass(frozen=True)
class _Snapshot:
    created_at: float
    result: MarketFetchResult


class FallbackMarketDataProvider:
    """Try public providers in deterministic priority order for one request."""

    def __init__(self, providers: Sequence[MarketDataProvider]) -> None:
        if not providers:
            raise ValueError("at least one market data provider is required")
        self._providers = tuple(providers)

    @property
    def providers(self) -> tuple[MarketDataProvider, ...]:
        return self._providers

    def resolve_symbol(self, asset: str, *, market_type: str = "spot") -> str:
        attempts: list[ProviderAttempt] = []
        for provider in self._providers:
            resolver = getattr(provider, "resolve_symbol", None)
            if resolver is None:
                attempts.append(ProviderAttempt(provider_name(provider), "symbol resolver unavailable"))
                continue
            try:
                return str(resolver(asset, market_type=market_type))
            except Exception as exc:
                attempts.append(ProviderAttempt(provider_name(provider), str(exc)))
        raise ValueError(format_attempts("unable to resolve asset", attempts))

    def fetch_ohlcv(self, *, symbol: str, market_type: str, timeframe: str,
                    since_ms: int | None, limit: int) -> pd.DataFrame:
        return self.fetch_ohlcv_with_source(
            symbol=symbol, market_type=market_type, timeframe=timeframe,
            since_ms=since_ms, limit=limit,
        ).frame

    def fetch_ohlcv_with_source(self, *, symbol: str, market_type: str,
                                timeframe: str, since_ms: int | None,
                                limit: int) -> MarketFetchResult:
        attempts: list[ProviderAttempt] = []
        for provider in self._providers:
            try:
                frame = provider.fetch_ohlcv(
                    symbol=symbol, market_type=market_type, timeframe=timeframe,
                    since_ms=since_ms, limit=limit,
                )
                if frame is None or frame.empty:
                    raise ValueError("provider returned no OHLCV rows")
                return MarketFetchResult(
                    provider=provider_name(provider), symbol=symbol, frame=frame,
                    attempts=tuple(attempts),
                )
            except Exception as exc:
                attempts.append(ProviderAttempt(provider_name(provider), str(exc)))
        raise RuntimeError(format_attempts("all market data providers failed", attempts))


class SharedSnapshotMarketDataProvider:
    """Share identical fresh OHLCV snapshots for up to ttl_seconds.

    The cache is process-local and temporary. It is not a history store:
    expired entries are discarded and no candle history is accumulated.
    A lock covers cache misses so identical concurrent requests do not
    stampede the exchanges.
    """

    def __init__(self, provider: FallbackMarketDataProvider, *,
                 ttl_seconds: float = 60.0, clock=time.monotonic) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._provider = provider
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshots: dict[SnapshotKey, _Snapshot] = {}

    @property
    def ttl_seconds(self) -> float:
        return self._ttl_seconds

    def fetch_ohlcv(self, *, symbol: str, market_type: str, timeframe: str,
                    since_ms: int | None, limit: int,
                    data_profile: str = "ohlcv") -> pd.DataFrame:
        return self.fetch_ohlcv_with_source(
            symbol=symbol, market_type=market_type, timeframe=timeframe,
            since_ms=since_ms, limit=limit, data_profile=data_profile,
        ).frame

    def fetch_ohlcv_with_source(self, *, symbol: str, market_type: str,
                                timeframe: str, since_ms: int | None,
                                limit: int,
                                data_profile: str = "ohlcv") -> MarketFetchResult:
        key = SnapshotKey(
            source=self._source_key(), market_type=market_type, symbol=symbol,
            timeframe=timeframe, data_profile=data_profile,
        )
        now = self._clock()
        with self._lock:
            cached = self._snapshots.get(key)
            if cached is not None and now - cached.created_at < self._ttl_seconds:
                return clone_result(cached.result)

            result = self._provider.fetch_ohlcv_with_source(
                symbol=symbol, market_type=market_type, timeframe=timeframe,
                since_ms=since_ms, limit=limit,
            )
            self._discard_expired(now)
            self._snapshots[key] = _Snapshot(now, clone_result(result))
            return clone_result(result)

    def clear(self) -> None:
        with self._lock:
            self._snapshots.clear()

    def _source_key(self) -> str:
        return "fallback:" + ",".join(
            provider_name(p) for p in self._provider.providers
        )

    def _discard_expired(self, now: float) -> None:
        for key, snapshot in list(self._snapshots.items()):
            if now - snapshot.created_at >= self._ttl_seconds:
                del self._snapshots[key]


def clone_result(result: MarketFetchResult) -> MarketFetchResult:
    return MarketFetchResult(
        provider=result.provider, symbol=result.symbol,
        frame=result.frame.copy(deep=True), attempts=result.attempts,
    )


def provider_name(provider: object) -> str:
    name = getattr(provider, "exchange", None)
    return str(name) if name else provider.__class__.__name__.lower()


def format_attempts(prefix: str, attempts: Sequence[ProviderAttempt]) -> str:
    if not attempts:
        return prefix
    detail = "; ".join(f"{item.provider}: {item.error}" for item in attempts)
    return f"{prefix}: {detail}"
