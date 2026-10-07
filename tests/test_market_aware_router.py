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


class SlowResolverProvider(Provider):
    def __init__(self, name, symbol, delay):
        super().__init__(name, symbol)
        self.delay = delay

    def resolve_symbol(self, asset, *, market_type="spot"):
        import time
        time.sleep(self.delay)
        return super().resolve_symbol(asset, market_type=market_type)


def test_router_bypasses_slow_resolver_and_uses_next_venue():
    slow = SlowResolverProvider("slow", "SLOW/USDT", 10.0)
    second = Provider("second", "TON/USDT:USDT")
    router = MarketAwareFallbackProvider([slow, second])
    import time
    started = time.monotonic()
    resolved = router.resolve_market("TON/USDT", market_type="futures")
    elapsed = time.monotonic() - started
    assert resolved.provider == "second"
    assert resolved.symbol == "TON/USDT:USDT"
    assert elapsed < 4.5


def test_router_missing_market_does_not_serialize_all_venues():
    providers = [SlowResolverProvider(f"slow-{index}", None, 10.0) for index in range(7)]
    router = MarketAwareFallbackProvider(providers)
    import time
    started = time.monotonic()
    try:
        router.resolve_market("MISSING/USDT", market_type="futures")
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected unresolved market")
    elapsed = time.monotonic() - started
    assert "resolver timed out after 3.0s" in message
    assert elapsed < 7.5

class AuxiliaryProvider(Provider):
    def fetch_trades(self, *, symbol, market_type, limit):
        self.calls.append(("trades", symbol))
        import pandas as pd
        return pd.DataFrame({"timestamp": [1000], "price": [1.5], "amount": [2.0]})

    def fetch_order_book(self, *, symbol, market_type, limit):
        self.calls.append(("order_book", symbol))
        import pandas as pd
        return pd.DataFrame({"timestamp": [1000], "bid": [1.4], "ask": [1.6]})

    def fetch_order_book_history(self, *, symbol, market_type, snapshots, interval_seconds):
        self.calls.append(("history", symbol))
        import pandas as pd
        return pd.DataFrame({"timestamp": [1000], "bid": [1.4], "ask": [1.6]})


def test_router_routes_auxiliary_feeds_with_venue_native_symbol():
    first = AuxiliaryProvider("first", "TON/USDT")
    second = AuxiliaryProvider("second", "TON/USDT:USDT")
    router = MarketAwareFallbackProvider([first, second])
    router.resolve_symbol("TON/USDT", market_type="futures")

    trades = router.fetch_trades_with_source(
        symbol="TON/USDT", market_type="futures", limit=10
    )
    book = router.fetch_order_book_with_source(
        symbol="TON/USDT", market_type="futures", limit=1
    )
    history = router.fetch_order_book_history_with_source(
        symbol="TON/USDT", market_type="futures", snapshots=1, interval_seconds=1.0
    )

    assert trades.symbol == "TON/USDT"
    assert book.symbol == "TON/USDT"
    assert history.symbol == "TON/USDT"


def test_router_preserves_reverse_symbol_cache_for_previous_markets():
    first = Provider("first", "BTC/USDT")
    second = Provider("second", "ETH/USDT")
    router = MarketAwareFallbackProvider([first, second])
    router.register_market_symbols(
        "BTC/USDT", (("first", "BTC/USDT"),), market_type="futures"
    )
    router.resolve_symbol("BTC/USDT", market_type="futures")
    router.register_market_symbols(
        "ETH/USDT", (("second", "ETH/USDT"),), market_type="futures"
    )
    router.resolve_symbol("ETH/USDT", market_type="futures")

    result = router.fetch_ohlcv_with_source(
        symbol="BTC/USDT", market_type="futures", timeframe="5m",
        since_ms=None, limit=10,
    )
    assert result.provider == "first"
    assert first.calls == ["BTC/USDT"]
