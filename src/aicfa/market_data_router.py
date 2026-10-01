"""Request-scoped market-data routing and short-lived shared snapshots."""
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
    data_profile: str

@dataclass(frozen=True)
class _Snapshot:
    created_at: float
    results: dict[str, MarketFetchResult]

class FallbackMarketDataProvider:
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
            since_ms=since_ms, limit=limit).frame

    def fetch_ohlcv_with_source(self, *, symbol: str, market_type: str,
                                timeframe: str, since_ms: int | None,
                                limit: int) -> MarketFetchResult:
        attempts: list[ProviderAttempt] = []
        for provider in self._providers:
            try:
                frame = provider.fetch_ohlcv(
                    symbol=symbol, market_type=market_type, timeframe=timeframe,
                    since_ms=since_ms, limit=limit)
                if frame is None or frame.empty:
                    raise ValueError("provider returned no OHLCV rows")
                return MarketFetchResult(provider=provider_name(provider),
                    symbol=symbol, frame=frame, attempts=tuple(attempts))
            except Exception as exc:
                attempts.append(ProviderAttempt(provider_name(provider), str(exc)))
        raise RuntimeError(format_attempts("all market data providers failed", attempts))

    def fetch_ohlcv_snapshot(self, *, symbol: str, market_type: str,
                             timeframes: Sequence[str], since_ms: int | None,
                             limit: int | None = None,
                             limits: dict[str, int] | None = None) -> dict[str, MarketFetchResult]:
        normalized = tuple(timeframes)
        if not normalized:
            raise ValueError("at least one timeframe is required")
        if limits is not None and limit is not None:
            raise ValueError("provide either limit or limits, not both")
        if limits is not None and set(limits) != set(normalized):
            raise ValueError("limits must contain exactly the requested timeframes")
        if limit is None and limits is None:
            raise ValueError("either limit or limits is required")
        return {tf: self.fetch_ohlcv_with_source(
            symbol=symbol, market_type=market_type, timeframe=tf,
            since_ms=since_ms, limit=(limits[tf] if limits is not None else limit)) for tf in normalized}

class SharedSnapshotMarketDataProvider:
    """One shared temporary snapshot containing all requested timeframes."""
    def __init__(self, provider: FallbackMarketDataProvider, *,
                 ttl_seconds: float = 60.0, clock=time.monotonic) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self._provider = provider
        self._ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._snapshots: dict[SnapshotKey, _Snapshot] = {}

    def resolve_symbol(self, asset: str, *, market_type: str = "spot") -> str:
        return self._provider.resolve_symbol(asset, market_type=market_type)

    def fetch_ohlcv_snapshot(self, *, symbol: str, market_type: str,
                             timeframes: Sequence[str], since_ms: int | None,
                             limit: int | None = None,
                             limits: dict[str, int] | None = None,
                             data_profile: str = "ohlcv") -> dict[str, MarketFetchResult]:
        normalized = tuple(timeframes)
        if not normalized:
            raise ValueError("at least one timeframe is required")
        if limits is not None and limit is not None:
            raise ValueError("provide either limit or limits, not both")
        if limits is not None and set(limits) != set(normalized):
            raise ValueError("limits must contain exactly the requested timeframes")
        if limit is None and limits is None:
            raise ValueError("either limit or limits is required")
        limit_key = (
            "limit=" + str(limit)
            if limits is None
            else "limits=" + ",".join(f"{tf}:{limits[tf]}" for tf in normalized)
        )
        key = SnapshotKey(
            source=self._source_key(), market_type=market_type, symbol=symbol,
            data_profile=data_profile + ":" + ",".join(normalized) + ":" + limit_key)
        now = self._clock()
        with self._lock:
            cached = self._snapshots.get(key)
            if cached is not None and now - cached.created_at < self._ttl_seconds:
                return clone_snapshot(cached)
            fetched = self._provider.fetch_ohlcv_snapshot(
                symbol=symbol, market_type=market_type, timeframes=normalized,
                since_ms=since_ms, limit=limit, limits=limits)
            snapshot = _Snapshot(now, {tf: clone_result(result) for tf, result in fetched.items()})
            self._discard_expired(now)
            self._snapshots[key] = snapshot
            return clone_snapshot(snapshot)

    def _source_key(self) -> str:
        return "fallback:" + ",".join(provider_name(p) for p in self._provider.providers)

    def _discard_expired(self, now: float) -> None:
        for key, snapshot in list(self._snapshots.items()):
            if now - snapshot.created_at >= self._ttl_seconds:
                del self._snapshots[key]

    def clear(self) -> None:
        with self._lock:
            self._snapshots.clear()

def clone_result(result: MarketFetchResult) -> MarketFetchResult:
    return MarketFetchResult(result.provider, result.symbol, result.frame.copy(deep=True), result.attempts)

def clone_snapshot(snapshot: _Snapshot) -> dict[str, MarketFetchResult]:
    return {tf: clone_result(result) for tf, result in snapshot.results.items()}

def provider_name(provider: object) -> str:
    name = getattr(provider, "exchange", None)
    return str(name) if name else provider.__class__.__name__.lower()

def format_attempts(prefix: str, attempts: Sequence[ProviderAttempt]) -> str:
    if not attempts:
        return prefix
    return f"{prefix}: " + "; ".join(f"{x.provider}: {x.error}" for x in attempts)
