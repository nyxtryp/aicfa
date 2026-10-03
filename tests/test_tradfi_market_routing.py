from __future__ import annotations

import json
from pathlib import Path

from aicfa.market_aware_router import MarketAwareFallbackProvider


class _Provider:
    def __init__(self, exchange: str, resolved: str, fetched: str) -> None:
        self.exchange = exchange
        self.resolved = resolved
        self.fetched = fetched

    def resolve_symbol(self, asset: str, *, market_type: str = "spot") -> str:
        return self.resolved

    def fetch_ohlcv(self, **kwargs):
        assert kwargs["symbol"] == self.fetched
        import pandas as pd
        return pd.DataFrame({"close": [1.0]})


def test_verified_venue_mapping_selects_native_symbol_before_generic_resolution() -> None:
    bybit = _Provider("bybit", "WRONG/USDT:USDT", "XAU/USDT:USDT")
    okx = _Provider("okx", "WRONG/USDT:USDT", "XAU/USDT:USDT")
    router = MarketAwareFallbackProvider([bybit, okx])

    router.register_market_symbols(
        "XAU/USDT",
        (("bybit", "XAU/USDT:USDT"), ("okx", "XAU/USDT:USDT")),
        market_type="futures",
    )

    assert router.resolve_symbol("XAU/USDT", market_type="futures") == "XAU/USDT:USDT"
    result = router.fetch_ohlcv(
        symbol="XAU/USDT:USDT",
        market_type="futures",
        timeframe="1h",
        since_ms=None,
        limit=10,
    )
    assert float(result.iloc[-1]["close"]) == 1.0


def test_production_universe_keeps_117_crypto_and_adds_29_final_tradfi() -> None:
    path = Path(__file__).parents[1] / "config" / "market_universe.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    markets = payload["markets"]

    crypto = [item for item in markets if item.get("asset_class", "crypto") == "crypto"]
    tradfi = [item for item in markets if item.get("asset_class") == "tradfi"]

    assert len(crypto) == 117
    assert len(tradfi) == 29
    assert all(item["market_type"] == "futures" for item in tradfi)
    assert all(item["instrument_type"] == "perpetual" for item in tradfi)
    assert all(item["venue_symbols"] for item in tradfi)
    assert all(
        "EUR/USDT:USDT" not in item["venue_symbols"].values()
        and "GBP/USDT:USDT" not in item["venue_symbols"].values()
        for item in tradfi
    )


def test_explicit_mapping_never_falls_back_to_unmapped_generic_venue() -> None:
    binance = _Provider("binance", "XAGUSDT", "XAGUSDT")
    bybit = _Provider("bybit", "WRONG", "XAG/USDT:USDT")
    router = MarketAwareFallbackProvider([binance, bybit])

    router.register_market_symbols(
        "XAG/USDT",
        (("bybit", "XAG/USDT:USDT"),),
        market_type="futures",
    )

    assert router.resolve_symbol("XAG/USDT", market_type="futures") == "XAG/USDT:USDT"
    result = router.fetch_ohlcv(
        symbol="XAG/USDT:USDT",
        market_type="futures",
        timeframe="1h",
        since_ms=None,
        limit=10,
    )
    assert float(result.iloc[-1]["close"]) == 1.0


def test_explicit_mapping_can_fallback_between_mapped_venues_only() -> None:
    bybit = _Provider("bybit", "WRONG", "BAD")
    okx = _Provider("okx", "WRONG", "XAG/USDT:USDT")
    router = MarketAwareFallbackProvider([bybit, okx])

    router.register_market_symbols(
        "XAG/USDT",
        (("bybit", "XAG/USDT:USDT"), ("okx", "XAG/USDT:USDT")),
        market_type="futures",
    )

    result = router.fetch_ohlcv(
        symbol="XAG/USDT:USDT",
        market_type="futures",
        timeframe="1h",
        since_ms=None,
        limit=10,
    )
    assert float(result.iloc[-1]["close"]) == 1.0
