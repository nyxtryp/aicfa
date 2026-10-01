import pandas as pd
import pytest

from aicfa.market_data_router import FallbackMarketDataProvider, SharedSnapshotMarketDataProvider


class FakeProvider:
    def __init__(self, name, *, symbol=None, frame=None, error=None):
        self.exchange = name
        self.symbol = symbol
        self.frame = frame
        self.error = error
        self.calls = 0

    def resolve_symbol(self, asset, *, market_type):
        if self.error:
            raise RuntimeError(self.error)
        return self.symbol or asset.upper()

    def fetch_ohlcv(self, **kwargs):
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        return self.frame


def frame(value=100.0):
    return pd.DataFrame({
        "timestamp": [1000],
        "open": [value],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [10.0],
    })


def test_router_uses_first_provider_that_resolves_symbol():
    router = FallbackMarketDataProvider([
        FakeProvider("first", error="offline"),
        FakeProvider("second", symbol="BTCUSDT"),
    ])
    assert router.resolve_symbol("btc") == "BTCUSDT"


def test_router_falls_back_when_primary_ohlcv_fails():
    router = FallbackMarketDataProvider([
        FakeProvider("first", error="429"),
        FakeProvider("second", frame=frame()),
    ])
    result = router.fetch_ohlcv_with_source(
        symbol="BTCUSDT", market_type="spot", timeframe="1m",
        since_ms=None, limit=1,
    )
    assert result.provider == "second"
    assert len(result.attempts) == 1
    assert result.attempts[0].provider == "first"


def test_router_rejects_empty_provider_list():
    with pytest.raises(ValueError):
        FallbackMarketDataProvider([])


def test_router_reports_all_failures():
    router = FallbackMarketDataProvider([
        FakeProvider("first", error="offline"),
        FakeProvider("second", error="timeout"),
    ])
    with pytest.raises(RuntimeError, match="first: offline"):
        router.fetch_ohlcv(
            symbol="BTCUSDT", market_type="spot", timeframe="1m",
            since_ms=None, limit=1,
        )


def test_shared_snapshot_reuses_all_timeframes():
    provider = FakeProvider("binance", frame=frame())
    shared = SharedSnapshotMarketDataProvider(FallbackMarketDataProvider([provider]), ttl_seconds=60)
    timeframes = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")
    first = shared.fetch_ohlcv_snapshot(
        symbol="BTCUSDT", market_type="spot", timeframes=timeframes, since_ms=100, limit=1,
    )
    second = shared.fetch_ohlcv_snapshot(
        symbol="BTCUSDT", market_type="spot", timeframes=timeframes, since_ms=100, limit=1,
    )
    assert provider.calls == 7
    assert tuple(first) == timeframes
    assert tuple(second) == timeframes
    assert all(first[tf].frame.equals(second[tf].frame) for tf in timeframes)


def test_shared_snapshot_separates_market_and_profile():
    provider = FakeProvider("binance", frame=frame())
    shared = SharedSnapshotMarketDataProvider(FallbackMarketDataProvider([provider]), ttl_seconds=60)
    timeframes = ("1m", "5m")
    shared.fetch_ohlcv_snapshot(
        symbol="BTCUSDT", market_type="spot", timeframes=timeframes,
        since_ms=100, limit=1, data_profile="ohlcv",
    )
    shared.fetch_ohlcv_snapshot(
        symbol="BTCUSDT", market_type="linear", timeframes=timeframes,
        since_ms=100, limit=1, data_profile="ohlcv",
    )
    shared.fetch_ohlcv_snapshot(
        symbol="BTCUSDT", market_type="spot", timeframes=timeframes,
        since_ms=100, limit=1, data_profile="ohlcv+trades",
    )
    assert provider.calls == 6


def test_shared_snapshot_expires_as_one_snapshot():
    provider = FakeProvider("binance", frame=frame())
    now = [100.0]
    shared = SharedSnapshotMarketDataProvider(
        FallbackMarketDataProvider([provider]), ttl_seconds=60, clock=lambda: now[0],
    )
    kwargs = dict(
        symbol="BTCUSDT", market_type="spot",
        timeframes=("1m", "5m", "15m"), since_ms=100, limit=1,
    )
    shared.fetch_ohlcv_snapshot(**kwargs)
    now[0] = 159.9
    shared.fetch_ohlcv_snapshot(**kwargs)
    assert provider.calls == 3
    now[0] = 160.0
    shared.fetch_ohlcv_snapshot(**kwargs)
    assert provider.calls == 6


def test_shared_snapshot_returns_isolated_frames():
    provider = FakeProvider("binance", frame=frame())
    shared = SharedSnapshotMarketDataProvider(FallbackMarketDataProvider([provider]), ttl_seconds=60)
    kwargs = dict(
        symbol="BTCUSDT", market_type="spot", timeframes=("1m", "5m"), since_ms=100, limit=1,
    )
    first = shared.fetch_ohlcv_snapshot(**kwargs)
    first["1m"].frame.loc[0, "close"] = -1
    second = shared.fetch_ohlcv_snapshot(**kwargs)
    assert second["1m"].frame.loc[0, "close"] == 100.5


def test_shared_snapshot_accepts_per_timeframe_limits():
    provider = FakeProvider("binance", frame=frame())
    shared = SharedSnapshotMarketDataProvider(FallbackMarketDataProvider([provider]), ttl_seconds=60)
    timeframes = ("1m", "1h", "1d")
    limits = {"1m": 60, "1h": 30, "1d": 10}
    shared.fetch_ohlcv_snapshot(
        symbol="BTCUSDT", market_type="spot", timeframes=timeframes,
        since_ms=None, limits=limits,
    )
    assert provider.calls == 3

def test_shared_snapshot_rejects_partial_per_timeframe_limits():
    provider = FakeProvider("binance", frame=frame())
    shared = SharedSnapshotMarketDataProvider(FallbackMarketDataProvider([provider]), ttl_seconds=60)
    with pytest.raises(ValueError, match="exactly the requested timeframes"):
        shared.fetch_ohlcv_snapshot(
            symbol="BTCUSDT", market_type="spot", timeframes=("1m", "1h"),
            since_ms=None, limits={"1m": 60},
        )
