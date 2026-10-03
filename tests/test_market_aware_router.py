from aicfa.market_aware_router import MarketAwareFallbackProvider


class Provider:
    def __init__(self, name, symbol):
        self.exchange = name
        self.symbol = symbol
        self.calls = []

    def resolve_symbol(self, asset, *, market_type="spot"):
        if self.symbol is None:
            raise ValueError("not listed")
        return self.symbol

    def fetch_ohlcv(self, *, symbol, market_type, timeframe, since_ms, limit):
        self.calls.append(symbol)
        if self.exchange == "first":
            raise RuntimeError("temporary outage")
        import pandas as pd
        return pd.DataFrame({
            "timestamp": [1000], "open": [1], "high": [2],
            "low": [1], "close": [1.5], "volume": [10],
        })


def test_router_falls_back_using_the_second_venues_own_symbol():
    first = Provider("first", "TON/USDT")
    second = Provider("second", "TON/USDT:USDT")
    router = MarketAwareFallbackProvider([first, second])
    router.resolve_symbol("TON/USDT", market_type="spot")
    result = router.fetch_ohlcv_with_source(
        symbol="TON/USDT", market_type="spot", timeframe="5m",
        since_ms=None, limit=10,
    )
    assert result.provider == "second"
    assert result.symbol == "TON/USDT:USDT"
    assert first.calls == ["TON/USDT"]
    assert second.calls == ["TON/USDT:USDT"]
