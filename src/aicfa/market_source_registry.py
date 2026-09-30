"""Capability registry for request-scoped multi-source market data.

This module contains only source selection policy. Provider adapters remain
responsible for transport and normalization. No market history is persisted.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable


class MarketCapability(str, Enum):
    SYMBOLS = "symbols"
    OHLCV = "ohlcv"
    TRADES = "trades"
    ORDER_BOOK = "order_book"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    LIQUIDATIONS = "liquidations"
    MARK_PRICE = "mark_price"


@dataclass(frozen=True)
class SourceDescriptor:
    name: str
    priority: int
    capabilities: frozenset[MarketCapability]
    public: bool = True

    def supports(self, required: Iterable[MarketCapability]) -> bool:
        return set(required).issubset(self.capabilities)


@dataclass(frozen=True)
class SourceSelection:
    source: SourceDescriptor
    missing: frozenset[MarketCapability] = frozenset()


class MarketSourceRegistry:
    """Ordered source registry with deterministic capability-aware fallback."""

    def __init__(self, sources: Iterable[SourceDescriptor]) -> None:
        ordered = sorted(sources, key=lambda source: (source.priority, source.name))
        names = [source.name for source in ordered]
        if len(names) != len(set(names)):
            raise ValueError("source names must be unique")
        self._sources = tuple(ordered)

    @property
    def sources(self) -> tuple[SourceDescriptor, ...]:
        return self._sources

    def candidates(
        self,
        *,
        required: Iterable[MarketCapability],
    ) -> tuple[SourceSelection, ...]:
        required_set = frozenset(required)
        return tuple(
            SourceSelection(source=source)
            for source in self._sources
            if source.public and source.supports(required_set)
        )

    def fallback_chain(self, *, required: Iterable[MarketCapability]) -> tuple[SourceDescriptor, ...]:
        return tuple(selection.source for selection in self.candidates(required=required))

    def best(self, *, required: Iterable[MarketCapability]) -> SourceDescriptor | None:
        chain = self.fallback_chain(required=required)
        return chain[0] if chain else None


DEFAULT_PUBLIC_SOURCES = (
    SourceDescriptor(
        "binance",
        10,
        frozenset({
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
            MarketCapability.TRADES,
            MarketCapability.ORDER_BOOK,
            MarketCapability.FUNDING,
            MarketCapability.OPEN_INTEREST,
            MarketCapability.LIQUIDATIONS,
            MarketCapability.MARK_PRICE,
        }),
    ),
    SourceDescriptor(
        "bybit",
        20,
        frozenset({
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
        }),
    ),
    SourceDescriptor(
        "bitget",
        30,
        frozenset({
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
            MarketCapability.TRADES,
            MarketCapability.ORDER_BOOK,
            MarketCapability.FUNDING,
            MarketCapability.OPEN_INTEREST,
            MarketCapability.LIQUIDATIONS,
            MarketCapability.MARK_PRICE,
        }),
    ),
    SourceDescriptor(
        "kraken",
        40,
        frozenset({
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
            MarketCapability.TRADES,
            MarketCapability.ORDER_BOOK,
        }),
    ),
    SourceDescriptor(
        "kucoin",
        50,
        frozenset({
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
            MarketCapability.TRADES,
            MarketCapability.ORDER_BOOK,
            MarketCapability.FUNDING,
            MarketCapability.OPEN_INTEREST,
        }),
    ),
    SourceDescriptor(
        "gate",
        60,
        frozenset({
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
            MarketCapability.TRADES,
            MarketCapability.ORDER_BOOK,
            MarketCapability.FUNDING,
            MarketCapability.OPEN_INTEREST,
            MarketCapability.LIQUIDATIONS,
            MarketCapability.MARK_PRICE,
        }),
    ),
    SourceDescriptor(
        "mexc",
        70,
        frozenset({
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
            MarketCapability.TRADES,
            MarketCapability.ORDER_BOOK,
            MarketCapability.FUNDING,
            MarketCapability.OPEN_INTEREST,
            MarketCapability.LIQUIDATIONS,
            MarketCapability.MARK_PRICE,
        }),
    ),
    SourceDescriptor(
        "coinlore",
        80,
        frozenset({
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
        }),
    ),
    SourceDescriptor(
        "coingecko",
        90,
        frozenset({
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
        }),
    ),
)


def default_market_source_registry() -> MarketSourceRegistry:
    return MarketSourceRegistry(DEFAULT_PUBLIC_SOURCES)
