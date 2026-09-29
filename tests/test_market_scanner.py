import pandas as pd
import pytest

from aicfa.market_data import MarketKey
from aicfa.market_scanner import CentralMarketScanner


def candles(timestamps):
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [100.0 + i for i in range(len(timestamps))],
        "high": [101.0 + i for i in range(len(timestamps))],
        "low": [99.0 + i for i in range(len(timestamps))],
        "close": [100.5 + i for i in range(len(timestamps))],
        "volume": [10.0 + i for i in range(len(timestamps))],
    })


class FakeProvider:
    def __init__(self):
        self.calls = []

    def fetch_ohlcv(self, *, symbol, market_type, timeframe, since_ms, limit):
        self.calls.append((symbol, market_type, timeframe, since_ms, limit))
        return candles([0, 60000, 120000])


def build_test_features(frame):
    out = frame.copy()
    out["market_state_test"] = out["close"] * 2
    return out


def test_scanner_processes_each_market_key_once_and_only_completed_data():
    key = MarketKey("fake", "BTC/USDT", "spot", "1m")
    provider = FakeProvider()
    scanner = CentralMarketScanner(provider, [key], feature_builder=build_test_features)

    results = scanner.scan_once(now_ms=150000)

    assert len(results) == 1
    assert provider.calls == [("BTC/USDT", "spot", "1m", None, 1000)]
    assert results[0].candles["timestamp"].tolist() == [0, 60000]
    assert results[0].latest["market_state_test"] == 201.0


def test_scanner_is_incremental_on_second_cycle():
    key = MarketKey("fake", "BTC/USDT", "spot", "1m")
    provider = FakeProvider()
    scanner = CentralMarketScanner(provider, [key], feature_builder=build_test_features)

    scanner.scan_once(now_ms=150000)
    scanner.scan_once(now_ms=250000)

    assert provider.calls[1] == ("BTC/USDT", "spot", "1m", 120000, 1000)


def test_scanner_rejects_duplicate_universe_keys():
    key = MarketKey("fake", "BTC/USDT", "spot", "1m")
    with pytest.raises(ValueError):
        CentralMarketScanner(FakeProvider(), [key, key], feature_builder=build_test_features)
