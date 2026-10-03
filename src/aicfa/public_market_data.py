"""Production multi-source public market-data provider chain for AICFA."""
from __future__ import annotations

from .binance_market_data import BinanceMarketDataProvider
from .bybit_market_data import BybitMarketDataProvider
from .ccxt_sources import DEFAULT_CCXT_EXCHANGES, build_ccxt_sources
from .market_aware_router import MarketAwareFallbackProvider

def build_public_market_data_provider(*, timeout_seconds: float = 10.0) -> MarketAwareFallbackProvider:
    """Build native-first, CCXT-backed venue fallback routing."""
    providers = [
        BinanceMarketDataProvider(timeout_seconds=timeout_seconds),
        BybitMarketDataProvider(timeout_seconds=timeout_seconds),
    ]
    for source in build_ccxt_sources(
        (exchange_id for exchange_id in DEFAULT_CCXT_EXCHANGES if exchange_id not in {"binance", "bybit"}),
        timeout_seconds=timeout_seconds,
    ):
        providers.append(source.provider)
    return MarketAwareFallbackProvider(providers)

__all__ = ["build_public_market_data_provider"]
