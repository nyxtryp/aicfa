from __future__ import annotations

import pandas as pd

from aicfa.ccxt_market_data import CcxtMarketDataProvider


class FakeExchange:
    def __init__(self):
        self.timeout = None
        self.markets = {}

    def load_markets(self):
        self.markets = {
            "BTC/USDT": {
                "symbol": "BTC/USDT", "base": "BTC", "quote": "USDT",
                "spot": True, "contract": False, "swap": False, "future": False,
            },
            "TON/USDT": {
                "symbol": "TON/USDT", "base": "TON", "quote": "USDT",
                "spot": True, "contract": False, "swap": False, "future": False,
            },
            "TON/USDT:USDT": {
                "symbol": "TON/USDT:USDT", "base": "TON", "quote": "USDT",
                "spot": False, "contract": True, "swap": True, "future": False,
            },
            "1000PEPE/USDT:USDT": {
                "symbol": "1000PEPE/USDT:USDT", "base": "1000PEPE", "quote": "USDT",
                "spot": False, "contract": True, "swap": True, "future": False,
            },
            "1000BONK/USDT:USDT": {
                "symbol": "1000BONK/USDT:USDT", "base": "1000BONK", "quote": "USDT",
                "spot": False, "contract": True, "swap": True, "future": False,
            },
        }
        return self.markets

    def fetch_ohlcv(self, symbol, *, timeframe, since, limit):
        return [[1_000, 1, 2, 0.5, 1.5, 10]]

    def fetch_trades(self, symbol, *, limit):
        return [{"timestamp": 1_000, "price": 1.5, "amount": 2, "side": "buy"}]

    def fetch_order_book(self, symbol, *, limit):
        return {
            "timestamp": 1_000,
            "bids": [[1.4, 3]],
            "asks": [[1.6, 4]],
        }


def factory(_exchange_id):
    return FakeExchange()


def test_ccxt_adapter_resolves_spot_and_futures_and_reuses_loaded_markets():
    provider = CcxtMarketDataProvider("fake", exchange_factory=factory)

    assert provider.resolve_symbol("BTC/USDT", market_type="spot") == "BTC/USDT"
    assert provider.resolve_symbol("TON/USDT", market_type="futures") == "TON/USDT:USDT"
    assert provider.resolve_symbol("PEPE/USDT", market_type="futures") == "1000PEPE/USDT:USDT"
    assert provider.resolve_symbol("BONK/USDT", market_type="futures") == "1000BONK/USDT:USDT"


def test_ccxt_adapter_normalizes_public_market_data():
    provider = CcxtMarketDataProvider("fake", exchange_factory=factory)

    candles = provider.fetch_ohlcv(
        symbol="BTC/USDT",
        market_type="spot",
        timeframe="5m",
        since_ms=None,
        limit=10,
    )
    trades = provider.fetch_trades(
        symbol="BTC/USDT", market_type="spot", limit=10
    )
    book = provider.fetch_order_book(
        symbol="BTC/USDT", market_type="spot", limit=5
    )

    assert list(candles.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert candles.iloc[0]["close"] == 1.5
    assert list(trades.columns) == ["timestamp", "price", "volume", "side"]
    assert trades.iloc[0]["side"] == 1
    assert list(book.columns) == [
        "timestamp", "bid_price", "bid_size", "ask_price", "ask_size"
    ]
    assert book.iloc[0]["ask_price"] == 1.6
