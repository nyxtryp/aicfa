"""Market-aware fallback routing with venue-specific symbol resolution."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Sequence

from .market_data import MarketDataProvider

MARKET_RESOLUTION_TIMEOUT_SECONDS = 3.0
MARKET_RESOLUTION_MAX_CONCURRENT_PROVIDERS = 6


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
        previous = self._market_symbols.get(key, {})
        self._market_symbols[key] = normalized
        self._resolved.pop(key, None)
        for native_symbol in previous.values():
            cache_key = (str(native_symbol).upper(), market_type)
            cached = self._by_symbol.get(cache_key)
            if cached is not None and cached.asset == key[0]:
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
            # A previous market registration must never invalidate the
            # symbol index of another already-resolved market. Rehydrate the
            # reverse lookup defensively if an older cache entry is missing.
            self._by_symbol[(cached.symbol.upper(), market_type)] = cached
            return cached

        mapped = self._market_symbols.get(key, {})
        attempts: list[MarketResolutionAttempt] = []

        # Explicit venue mappings are authoritative. Never replace a verified
        # native symbol with a generic resolver result from an unmapped venue.
        if mapped:
            for provider in self._providers:
                provider_id = provider_name(provider).strip().lower()
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

        # Generic discovery must not serialize slow or unsupported venues.
        # Probe the first priority venue alone, then bounded batches of six.
        providers = list(self._providers)
        batches: list[list[tuple[int, MarketDataProvider]]] = []
        if providers:
            batches.append([(0, providers[0])])
            for start_index in range(1, len(providers), MARKET_RESOLUTION_MAX_CONCURRENT_PROVIDERS):
                batch = providers[start_index:start_index + MARKET_RESOLUTION_MAX_CONCURRENT_PROVIDERS]
                batches.append(list(enumerate(batch, start=start_index)))

        for batch in batches:
            executor = ThreadPoolExecutor(max_workers=len(batch))
            futures = {
                executor.submit(self._resolve_provider, provider, asset, market_type): (index, provider)
                for index, provider in batch
            }
            done, pending = wait(futures, timeout=MARKET_RESOLUTION_TIMEOUT_SECONDS)

            successful: list[tuple[int, str, MarketDataProvider]] = []
            for future in done:
                index, provider = futures[future]
                try:
                    successful.append((index, str(future.result()), provider))
                except Exception as exc:
                    attempts.append(MarketResolutionAttempt(provider_name(provider), str(exc)))

            for future in pending:
                index, provider = futures[future]
                attempts.append(MarketResolutionAttempt(
                    provider_name(provider),
                    f"resolver timed out after {MARKET_RESOLUTION_TIMEOUT_SECONDS:.1f}s",
                ))

            executor.shutdown(wait=False, cancel_futures=True)

            if successful:
                _, symbol, provider = min(successful, key=lambda item: item[0])
                resolved = ResolvedMarket(
                    asset=key[0],
                    market_type=market_type,
                    provider=provider_name(provider),
                    symbol=symbol,
                )
                self._resolved[key] = resolved
                self._by_symbol[(symbol.upper(), market_type)] = resolved
                return resolved

        details = "; ".join(f"{x.provider}: {x.error}" for x in attempts)
        raise ValueError(f"unable to resolve market {asset}: {details}")

    @staticmethod
    def _resolve_provider(provider: MarketDataProvider, asset: str, market_type: str) -> str:
        resolver = getattr(provider, "resolve_symbol", None)
        if resolver is None:
            raise ValueError("symbol resolver unavailable")
        return str(resolver(asset, market_type=market_type))

    def resolve_symbol(self, asset: str, *, market_type: str = "spot") -> str:
        """Resolve an asset through the fallback chain and return its venue-native symbol."""
        return self.resolve_market(asset, market_type=market_type).symbol

    def clear_resolution_cache(self) -> None:
        self._resolved.clear()
        self._by_symbol.clear()

    def _resolved_provider_candidates(self, symbol: str, market_type: str):
        resolved = self._by_symbol.get((symbol.upper(), market_type))
        if resolved is None:
            raise ValueError("symbol was not resolved through MarketAwareFallbackProvider")
        mapped = self._market_symbols.get((resolved.asset, market_type), {})
        if mapped:
            return tuple(
                (provider, mapped.get(provider_name(provider).strip().lower()))
                for provider in self._providers
                if provider_name(provider).strip().lower() in mapped
            )
        start = self._providers.index(next(
            p for p in self._providers if provider_name(p) == resolved.provider
        ))
        return tuple(
            (provider, resolved.symbol if index == start else None)
            for index, provider in enumerate(self._providers[start:], start=start)
        )

    def _fetch_aux_recent_with_source(self, method_name: str, *, symbol: str,
                                      market_type: str, limit: int):
        from .market_data_router import MarketFetchResult, ProviderAttempt
        attempts: list[ProviderAttempt] = []
        resolved = self._by_symbol.get((symbol.upper(), market_type))
        if resolved is None:
            raise ValueError("symbol was not resolved through MarketAwareFallbackProvider")
        for provider, mapped_symbol in self._resolved_provider_candidates(symbol, market_type):
            try:
                method = getattr(provider, method_name, None)
                if method is None:
                    raise ValueError(f"provider does not support {method_name}")
                venue_symbol = mapped_symbol
                if venue_symbol is None:
                    resolver = getattr(provider, "resolve_symbol", None)
                    if resolver is None:
                        raise ValueError("symbol resolver unavailable")
                    venue_symbol = str(resolver(resolved.asset, market_type=market_type))
                frame = method(symbol=venue_symbol, market_type=market_type, limit=limit)
                if frame is None or frame.empty:
                    raise ValueError(f"provider returned no {method_name.removeprefix('fetch_')} rows")
                return MarketFetchResult(provider=provider_name(provider), symbol=venue_symbol,
                                         frame=frame, attempts=tuple(attempts))
            except Exception as exc:
                attempts.append(ProviderAttempt(provider_name(provider), str(exc)))
        raise RuntimeError("all market data providers failed: " +
                           "; ".join(f"{x.provider}: {x.error}" for x in attempts))

    def fetch_trades_with_source(self, *, symbol: str, market_type: str, limit: int):
        return self._fetch_aux_recent_with_source("fetch_trades", symbol=symbol,
                                                  market_type=market_type, limit=limit)

    def fetch_trades(self, *, symbol: str, market_type: str, limit: int):
        return self.fetch_trades_with_source(symbol=symbol, market_type=market_type, limit=limit).frame

    def fetch_order_book_with_source(self, *, symbol: str, market_type: str, limit: int = 1):
        return self._fetch_aux_recent_with_source("fetch_order_book", symbol=symbol,
                                                  market_type=market_type, limit=limit)

    def fetch_order_book(self, *, symbol: str, market_type: str, limit: int = 1):
        return self.fetch_order_book_with_source(symbol=symbol, market_type=market_type, limit=limit).frame

    def fetch_order_book_history_with_source(self, *, symbol: str, market_type: str,
                                             snapshots: int, interval_seconds: float):
        from .market_data_router import MarketFetchResult, ProviderAttempt
        attempts: list[ProviderAttempt] = []
        resolved = self._by_symbol.get((symbol.upper(), market_type))
        if resolved is None:
            raise ValueError("symbol was not resolved through MarketAwareFallbackProvider")
        for provider, mapped_symbol in self._resolved_provider_candidates(symbol, market_type):
            try:
                method = getattr(provider, "fetch_order_book_history", None)
                if method is None:
                    raise ValueError("provider does not support fetch_order_book_history")
                venue_symbol = mapped_symbol
                if venue_symbol is None:
                    resolver = getattr(provider, "resolve_symbol", None)
                    if resolver is None:
                        raise ValueError("symbol resolver unavailable")
                    venue_symbol = str(resolver(resolved.asset, market_type=market_type))
                frame = method(symbol=venue_symbol, market_type=market_type,
                               snapshots=snapshots, interval_seconds=interval_seconds)
                if frame is None or frame.empty:
                    raise ValueError("provider returned no order-book history rows")
                return MarketFetchResult(provider=provider_name(provider), symbol=venue_symbol,
                                         frame=frame, attempts=tuple(attempts))
            except Exception as exc:
                attempts.append(ProviderAttempt(provider_name(provider), str(exc)))
        raise RuntimeError("all order-book history providers failed: " +
                           "; ".join(f"{x.provider}: {x.error}" for x in attempts))

    def fetch_order_book_history(self, *, symbol: str, market_type: str,
                                 snapshots: int, interval_seconds: float):
        return self.fetch_order_book_history_with_source(symbol=symbol, market_type=market_type,
                                                         snapshots=snapshots,
                                                         interval_seconds=interval_seconds).frame

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
                if exc.__class__.__name__ == "MarketExecutionTimeout":
                    raise
                attempts.append(ProviderAttempt(provider_name(provider), str(exc)))
        raise RuntimeError(
            "all market data providers failed: "
            + "; ".join(f"{x.provider}: {x.error}" for x in attempts)
        )


def provider_name(provider: object) -> str:
    name = getattr(provider, "exchange", None)
    return str(name) if name else provider.__class__.__name__.lower()
