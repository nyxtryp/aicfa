"""CCXT source construction and capability-aware public venue selection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .ccxt_market_data import CcxtMarketDataProvider
from .market_source_registry import MarketCapability, MarketSourceRegistry, SourceDescriptor

# Keep this list broad enough for fallback coverage, but do not instantiate every
# CCXT integration on every process start. Availability is checked lazily.
DEFAULT_CCXT_EXCHANGES = (
    "binance",
    "bybit",
    "okx",
    "bitget",
    "gate",
    "kucoin",
    "mexc",
    "kraken",
    "coinbase",
    "bitfinex",
    "bingx",
    "htx",
    "bitmart",
    "coinex",
    "whitebit",
    "cryptocom",
    "bitrue",
    "bitstamp",
    "gemini",
    "upbit",
)


@dataclass(frozen=True)
class CcxtSource:
    name: str
    provider: CcxtMarketDataProvider
    descriptor: SourceDescriptor


def _capabilities(provider: CcxtMarketDataProvider) -> frozenset[MarketCapability]:
    has = getattr(provider._exchange, "has", {}) or {}
    capabilities = {MarketCapability.SYMBOLS}
    if has.get("fetchOHLCV"):
        capabilities.add(MarketCapability.OHLCV)
    if has.get("fetchTrades"):
        capabilities.add(MarketCapability.TRADES)
    if has.get("fetchOrderBook"):
        capabilities.add(MarketCapability.ORDER_BOOK)
    if has.get("fetchFundingRate") or has.get("fetchFundingRateHistory"):
        capabilities.add(MarketCapability.FUNDING)
    if has.get("fetchOpenInterest") or has.get("fetchOpenInterestHistory"):
        capabilities.add(MarketCapability.OPEN_INTEREST)
    if has.get("fetchLiquidations") or has.get("fetchMyLiquidations"):
        capabilities.add(MarketCapability.LIQUIDATIONS)
    if has.get("fetchMarkPrice") or has.get("fetchMarkPriceOHLCV"):
        capabilities.add(MarketCapability.MARK_PRICE)
    return frozenset(capabilities)


def build_ccxt_sources(
    exchange_ids: Iterable[str] = DEFAULT_CCXT_EXCHANGES,
    *,
    timeout_seconds: float = 10.0,
) -> tuple[CcxtSource, ...]:
    """Construct CCXT sources, skipping integrations unavailable in this install."""
    sources: list[CcxtSource] = []
    for priority, exchange_id in enumerate(exchange_ids, start=100):
        try:
            provider = CcxtMarketDataProvider(
                exchange_id,
                timeout_seconds=timeout_seconds,
            )
        except (AttributeError, TypeError, ValueError):
            continue
        descriptor = SourceDescriptor(
            name=exchange_id,
            priority=priority,
            capabilities=_capabilities(provider),
        )
        sources.append(CcxtSource(exchange_id, provider, descriptor))
    return tuple(sources)


def build_ccxt_registry(
    exchange_ids: Iterable[str] = DEFAULT_CCXT_EXCHANGES,
    *,
    timeout_seconds: float = 10.0,
) -> MarketSourceRegistry:
    """Build a capability-aware registry from the installed CCXT version."""
    return MarketSourceRegistry(
        source.descriptor
        for source in build_ccxt_sources(
            exchange_ids,
            timeout_seconds=timeout_seconds,
        )
    )
