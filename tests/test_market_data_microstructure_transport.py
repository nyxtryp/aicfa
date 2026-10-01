import pandas as pd

from aicfa.market_data_router import FallbackMarketDataProvider


class FakeProvider:
    def __init__(self, name, *, trades=None, book=None, book_history=None, error=None):
        self.exchange = name
        self.trades = trades
        self.book = book
        self.book_history = book_history if book_history is not None else book
        self.error = error

    def fetch_trades(self, **kwargs):
        if self.error:
            raise RuntimeError(self.error)
        return self.trades

    def fetch_order_book(self, **kwargs):
        if self.error:
            raise RuntimeError(self.error)
        return self.book

    def fetch_order_book_history(self, **kwargs):
        if self.error:
            raise RuntimeError(self.error)
        return self.book_history


def _trades():
    return pd.DataFrame(
        {
            "timestamp": [1000, 1001],
            "price": [100.0, 101.0],
            "volume": [2.0, 3.0],
            "side": [1, -1],
        }
    )


def _book():
    return pd.DataFrame(
        {
            "timestamp": [1001],
            "bid_price": [100.0],
            "bid_size": [5.0],
            "ask_price": [100.1],
            "ask_size": [4.0],
        }
    )


def test_router_falls_back_for_trades():
    router = FallbackMarketDataProvider(
        [FakeProvider("binance", error="offline"), FakeProvider("bybit", trades=_trades())]
    )
    result = router.fetch_trades_with_source(
        symbol="BTCUSDT", market_type="spot", limit=2
    )
    assert result.provider == "bybit"
    assert result.attempts[0].provider == "binance"
    assert result.frame["side"].tolist() == [1, -1]


def test_router_falls_back_for_order_book():
    router = FallbackMarketDataProvider(
        [FakeProvider("binance", error="timeout"), FakeProvider("bybit", book=_book())]
    )
    result = router.fetch_order_book_with_source(
        symbol="BTCUSDT", market_type="spot", limit=1
    )
    assert result.provider == "bybit"
    assert result.frame.iloc[0]["bid_price"] == 100.0


def test_router_rejects_provider_without_trade_capability():
    router = FallbackMarketDataProvider([object()])
    try:
        router.fetch_trades(symbol="BTCUSDT", market_type="spot", limit=1)
    except RuntimeError as exc:
        assert "fetch_trades" in str(exc)
    else:
        raise AssertionError("expected missing trade capability to fail")


def test_router_rejects_empty_order_book_result():
    router = FallbackMarketDataProvider([FakeProvider("binance", book=pd.DataFrame())])
    try:
        router.fetch_order_book(symbol="BTCUSDT", market_type="spot", limit=1)
    except RuntimeError as exc:
        assert "order_book" in str(exc)
    else:
        raise AssertionError("expected empty order book to fail")


def test_router_falls_back_for_order_book_history():
    history = pd.DataFrame(
        {
            "timestamp": [1000, 1100],
            "bid_price": [100.0, 100.0],
            "bid_size": [5.0, 6.0],
            "ask_price": [100.1, 100.1],
            "ask_size": [4.0, 3.0],
        }
    )
    router = FallbackMarketDataProvider(
        [
            FakeProvider("binance", error="timeout"),
            FakeProvider("bybit", book_history=history),
        ]
    )
    result = router.fetch_order_book_history_with_source(
        symbol="BTCUSDT",
        market_type="spot",
        snapshots=2,
        interval_seconds=0,
    )
    assert result.provider == "bybit"
    assert result.frame["bid_size"].tolist() == [5.0, 6.0]
