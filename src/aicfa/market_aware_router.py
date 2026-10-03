"""Market-aware fallback routing with venue-specific symbol resolution."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .market_data import MarketDataProvider


@dataclass(frozen=True)
class ResolvedMarket:
    asset: str
    market_type: str
    provider: str
    symbol: str


@dataclass(frozen=True)
class MarketResolutionAttempt:
    provider: str
    error: str


class MarketAwareFallbackProvider:
    """Resolve an asset once, then keep its venue-specific symbol for all reads."""

    def __init__(self, providers: Sequence[MarketDataProvider]) -> None:
        if not providers:
            raise ValueError("at least one market data provider is required")
        self._providers = tuple(providers)
        self._resolved: dict[tuple[str, str], ResolvedMarket] = {}
        self._by_symbol: dict[tuple[str, str], ResolvedMarket] = {}
        self._market_symbols: dict[tuple[str, str], dict[str, str]] = {}

    @property
    def providers(self) -> tuple[MarketDataProvider, ...]:
        return self._providers

    def register_market_symbols(
        self,
        asset: str,
        venue_symbols: Sequence[tuple[str, str]],
        *,
        market_type: str = "spot",
    ) -> None:
        """Register verified venue-native symbols for one configured market."""
        key = (asset.strip().upper(), market_type)
        normalized = {
            str(venue).strip().lower(): str(symbol).strip()
            for venue, symbol in venue_symbols
            if str(venue).strip() and str(symbol).strip()
        }
        if not normalized:
            return
        self._market_symbols[key] = normalized
        self._resolved.pop(key, None)
        for cache_key in tuple(self._by_symbol):
            if cache_key[1] == market_type:
                self._by_symbol.pop(cache_key, None)
        # Make every explicitly mapped native symbol immediately routable.
        # Fetch still tries all mapped venues in configured order.
        first_provider = next(iter(normalized), None)
        for provider_id, native_symbol in normalized.items():
            self._by_symbol[(native_symbol.upper(), market_type)] = ResolvedMarket(
                asset=key[0],
                market_type=market_type,
                provider=provider_id,
                symbol=native_symbol,
            )
        if first_provider is not None:
            self._resolved[key] = ResolvedMarket(
                asset=key[0],
                market_type=market_type,
                provider=first_provider,
                symbol=normalized[first_provider],
            )

    def resolve_market(self, asset: str, *, market_type: str = "spot") -> ResolvedMarket:
        key = (asset.strip().upper(), market_type)
        cached = self._resolved.get(key)
        if cached is not None:
            return cached

        mapped = self._market_symbols.get(key, {})
        attempts: list[MarketResolutionAttempt] = []
        for provider in self._providers:
            provider_id = provider_name(provider).strip().lower()

            # Explicit venue mappings are authoritative. Never replace a
            # verified native symbol with a generic resolver result from an
            # unmapped venue.
            if mapped:
                if provider_id not in mapped:
                    continue
                resolved = ResolvedMarket(
                    asset=key[0],
                    market_type=market_type,
                    provider=provider_name(provider),
                    symbol=mapped[provider_id],
                )
                self._resolved[key] = resolved
                self._by_symbol[(resolved.symbol.upper(), market_type)] = resolved
                return resolved

            resolver = getattr(provider, "resolve_symbol", None)
            if resolver is None:
                attempts.append(MarketResolutionAttempt(
                    provider_name(provider), "symbol resolver unavailable"
                ))
                continue
            try:
                symbol = str(resolver(asset, market_type=market_type))
                resolved = ResolvedMarket(
                    asset=key[0],
                    market_type=market_type,
                    provider=provider_name(provider),
                    symbol=symbol,
                )
                self._resolved[key] = resolved
                self._by_symbol[(symbol.upper(), market_type)] = resolved
                return resolved
            except Exception as exc:
                attempts.append(MarketResolutionAttempt(
                    provider_name(provider), str(exc)
                ))
        details = "; ".join(f"{x.provider}: {x.error}" for x in attempts)
        raise ValueError(f"unable to resolve market {asset}: {details}")

    def resolve_symbol(self, asset: str, *, market_type: str = "spot") -> str:
        """Resolve an asset through the fallback chain and return its venue-native symbol."""
        return self.resolve_market(asset, market_type=market_type).symbol

    def clear_resolution_cache(self) -> None:
        self._resolved.clear()
        self._by_symbol.clear()

    def fetch_ohlcv(self, *, symbol: str, market_type: str, timeframe: str, since_ms: int | None, limit: int):
        return self.fetch_ohlcv_with_source(
            symbol=symbol, market_type=market_type, timeframe=timeframe,
            since_ms=since_ms, limit=limit,
        ).frame

    def fetch_ohlcv_with_source(self, *, symbol: str, market_type: str, timeframe: str, since_ms: int | None, limit: int):
        from .market_data_router import MarketFetchResult, ProviderAttempt
        resolved = self._by_symbol.get((symbol.upper(), market_type))
        if resolved is None:
            raise ValueError("symbol was not resolved through MarketAwareFallbackProvider")
        attempts: list[ProviderAttempt] = []
        mapped = self._market_symbols.get((resolved.asset, market_type), {})

        if mapped:
            # Explicit mappings may fall back only between mapped venues.
            providers = tuple(
                provider
                for provider in self._providers
                if provider_name(provider).strip().lower() in mapped
            )
        else:
            start = self._providers.index(next(
                p for p in self._providers if provider_name(p) == resolved.provider
            ))
            providers = self._providers[start:]

        for provider in providers:
            resolver = getattr(provider, "resolve_symbol", None)
            if resolver is None:
                attempts.append(ProviderAttempt(provider_name(provider), "symbol resolver unavailable"))
                continue
            try:
                venue_symbol = (
                    mapped.get(provider_name(provider).strip().lower())
                    or (
                        resolved.symbol
                        if provider_name(provider) == resolved.provider
                        else str(resolver(resolved.asset, market_type=market_type))
                    )
                )
                frame = provider.fetch_ohlcv(
                    symbol=venue_symbol, market_type=market_type, timeframe=timeframe,
                    since_ms=since_ms, limit=limit,
                )
                if frame is None or frame.empty:
                    raise ValueError("provider returned no OHLCV rows")
                current = ResolvedMarket(
                    asset=resolved.asset, market_type=market_type,
                    provider=provider_name(provider), symbol=venue_symbol,
                )
                self._resolved[(resolved.asset, market_type)] = current
                self._by_symbol[(venue_symbol.upper(), market_type)] = current
                return MarketFetchResult(
                    provider=provider_name(provider), symbol=venue_symbol,
                    frame=frame, attempts=tuple(attempts),
                )
            except Exception as exc:
                attempts.append(ProviderAttempt(provider_name(provider), str(exc)))
        raise RuntimeError(
            "all market data providers failed: "
            + "; ".join(f"{x.provider}: {x.error}" for x in attempts)
        )


def provider_name(provider: object) -> str:
    name = getattr(provider, "exchange", None)
    return str(name) if name else provider.__class__.__name__.lower()
