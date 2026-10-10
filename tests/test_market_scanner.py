import pandas as pd
import pytest

from aicfa.market_data import MarketKey
from aicfa.market_scanner import CentralMarketScanner, rolling_window_size


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
        if since_ms is None:
            return candles([0, 60000, 120000])
        return candles([since_ms, since_ms + 60000])


def build_test_features(frame):
    out = frame.copy()
    out["market_state_test"] = out["close"] * 2
    return out


def test_rolling_window_policy_matches_requested_timeframes():
    assert rolling_window_size("1m") == 500
    assert rolling_window_size("5m") == 500
    assert rolling_window_size("15m") == 500
    assert rolling_window_size("1h") == 500
    assert rolling_window_size("4h") == 500
    assert rolling_window_size("1d") == 365
    assert rolling_window_size("1w") == 200


def test_scanner_processes_each_market_key_once_and_only_completed_data():
    key = MarketKey("fake", "BTC/USDT", "spot", "1m")
    provider = FakeProvider()
    scanner = CentralMarketScanner(provider, [key], feature_builder=build_test_features)

    results = scanner.scan_once(now_ms=150000)

    assert len(results) == 1
    assert provider.calls == [("BTC/USDT", "spot", "1m", None, 500)]
    assert results[0].candles["timestamp"].tolist() == [0, 60000]
    assert results[0].latest["market_state_test"] == 203.0


def test_scanner_is_incremental_on_second_cycle():
    key = MarketKey("fake", "BTC/USDT", "spot", "1m")
    provider = FakeProvider()
    scanner = CentralMarketScanner(provider, [key], feature_builder=build_test_features)

    scanner.scan_once(now_ms=150000)
    scanner.scan_once(now_ms=250000)

    assert provider.calls[1] == ("BTC/USDT", "spot", "1m", 120000, 100)


def test_scanner_persists_and_restores_history_between_instances(tmp_path):
    key = MarketKey("fake", "BTC/USDT", "spot", "1m")
    first_provider = FakeProvider()
    first = CentralMarketScanner(
        first_provider, [key], feature_builder=build_test_features, cache_dir=tmp_path,
    )
    first.scan_once(now_ms=150000)

    second_provider = FakeProvider()
    second = CentralMarketScanner(
        second_provider, [key], feature_builder=build_test_features, cache_dir=tmp_path,
    )
    second.scan_once(now_ms=250000)

    assert second_provider.calls[0][3] == 120000
    assert second.history[key]["timestamp"].tolist() == [0, 60000, 120000, 180000]


def test_seed_enforces_sliding_window_and_persists(tmp_path):
    key = MarketKey("fake", "BTC/USDT", "spot", "1m")
    scanner = CentralMarketScanner(
        FakeProvider(), [key], feature_builder=build_test_features, cache_dir=tmp_path,
    )
    stamps = [i * 60000 for i in range(510)]
    scanner.seed(key, candles(stamps))
    assert len(scanner.history[key]) == 500
    assert scanner.history[key]["timestamp"].iloc[0] == 10 * 60000
    restored = CentralMarketScanner(
        FakeProvider(), [key], feature_builder=build_test_features, cache_dir=tmp_path,
    )
    assert restored._load_history(key)["timestamp"].tolist() == stamps[-500:]


def test_scanner_rejects_duplicate_universe_keys():
    key = MarketKey("fake", "BTC/USDT", "spot", "1m")
    with pytest.raises(ValueError):
        CentralMarketScanner(FakeProvider(), [key, key], feature_builder=build_test_features)
