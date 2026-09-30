"""Request-scoped market-data fallback router.

The router tries providers in deterministic priority order. It does not retain
market data between requests and does not silently merge incompatible sources.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

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


class FallbackMarketDataProvider:
    """Try public providers in priority order for one request."""

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

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        market_type: str,
        timeframe: str,
        since_ms: int | None,
        limit: int,
    ) -> pd.DataFrame:
        result = self.fetch_ohlcv_with_source(
            symbol=symbol,
            market_type=market_type,
            timeframe=timeframe,
            since_ms=since_ms,
            limit=limit,
        )
        return result.frame

    def fetch_ohlcv_with_source(
        self,
        *,
        symbol: str,
        market_type: str,
        timeframe: str,
        since_ms: int | None,
        limit: int,
    ) -> MarketFetchResult:
        attempts: list[ProviderAttempt] = []
        for provider in self._providers:
            try:
                frame = provider.fetch_ohlcv(
                    symbol=symbol,
                    market_type=market_type,
                    timeframe=timeframe,
                    since_ms=since_ms,
                    limit=limit,
                )
                if frame is None or frame.empty:
                    raise ValueError("provider returned no OHLCV rows")
                return MarketFetchResult(
                    provider=provider_name(provider),
                    symbol=symbol,
                    frame=frame,
                    attempts=tuple(attempts),
                )
            except Exception as exc:
                attempts.append(ProviderAttempt(provider_name(provider), str(exc)))
        raise RuntimeError(format_attempts("all market data providers failed", attempts))


def provider_name(provider: object) -> str:
    name = getattr(provider, "exchange", None)
    return str(name) if name else provider.__class__.__name__.lower()


def format_attempts(prefix: str, attempts: Sequence[ProviderAttempt]) -> str:
    if not attempts:
        return prefix
    detail = "; ".join(f"{item.provider}: {item.error}" for item in attempts)
    return f"{prefix}: {detail}"
