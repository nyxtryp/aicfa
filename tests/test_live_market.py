import pandas as pd

from aicfa.live_market import CandleCheckpoint, PersistentCandleStore, LiveMarketDataCache, WINDOWS
from aicfa.market_data import MarketKey


def _frame(start=0, count=3):
    return pd.DataFrame({
        "timestamp": [start + i * 300000 for i in range(count)],
        "open": [100 + i for i in range(count)],
        "high": [101 + i for i in range(count)],
        "low": [99 + i for i in range(count)],
        "close": [100.5 + i for i in range(count)],
        "volume": [10.0] * count,
    })


class Provider:
    def __init__(self):
        self.calls = []

    def resolve_symbol(self, asset, *, market_type="spot"):
        return asset

    def fetch_ohlcv(self, *, symbol, market_type, timeframe, since_ms, limit):
        self.calls.append((symbol, market_type, timeframe, limit))
        return _frame(count=limit)

    def fetch_trades(self, **kwargs):
        raise AssertionError

    def fetch_order_book(self, **kwargs):
        raise AssertionError

    def fetch_order_book_history(self, **kwargs):
        raise AssertionError


def test_rolling_store_keeps_configured_window(tmp_path):
    store = PersistentCandleStore(tmp_path / "raw")
    key = MarketKey("binance", "BTC/USDT", "spot", "5m")
    frame = _frame(count=WINDOWS["5m"] + 10)
    stored = store.append(key, frame)

    assert len(stored) == 500
    assert len(store.load(key)) == 500
    assert stored["timestamp"].is_monotonic_increasing


def test_checkpoint_survives_restart(tmp_path):
    path = tmp_path / "journal" / "checkpoints.json"
    key = MarketKey("binance", "BTC/USDT", "spot", "5m")
    first = CandleCheckpoint(path)
    assert first.get(key) is None
    first.mark(key, 12345)

    second = CandleCheckpoint(path)
    assert second.get(key) == 12345
    second.mark(key, 12000)
    assert second.get(key) == 12345


def test_cache_prefers_local_window_after_seed(tmp_path):
    provider = Provider()
    store = PersistentCandleStore(tmp_path / "raw")
    cache = LiveMarketDataCache(provider, store)
    key = MarketKey("binance", "BTC/USDT", "spot", "5m")

    cache.seed(key, _frame(count=20))
    result = cache.fetch_ohlcv(
        symbol="BTC/USDT",
        market_type="spot",
        timeframe="5m",
        since_ms=None,
        limit=10,
    )

    assert len(result) == 10
    assert provider.calls == []
