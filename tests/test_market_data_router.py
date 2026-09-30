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


def test_shared_snapshot_reuses_fresh_result():
    provider = FakeProvider("binance", frame=frame())
    shared = SharedSnapshotMarketDataProvider(
        FallbackMarketDataProvider([provider]), ttl_seconds=60,
    )
    kwargs = dict(symbol="BTCUSDT", market_type="spot", timeframe="1m",
                  since_ms=100, limit=1)
    first = shared.fetch_ohlcv_with_source(**kwargs)
    second = shared.fetch_ohlcv_with_source(**kwargs)
    assert provider.calls == 1
    assert first.frame.equals(second.frame)


def test_shared_snapshot_separates_market_and_profile():
    provider = FakeProvider("binance", frame=frame())
    shared = SharedSnapshotMarketDataProvider(
        FallbackMarketDataProvider([provider]), ttl_seconds=60,
    )
    kwargs = dict(symbol="BTCUSDT", timeframe="1m", since_ms=100, limit=1)
    shared.fetch_ohlcv_with_source(**kwargs, market_type="spot", data_profile="ohlcv")
    shared.fetch_ohlcv_with_source(**kwargs, market_type="linear", data_profile="ohlcv")
    shared.fetch_ohlcv_with_source(**kwargs, market_type="spot", data_profile="ohlcv+trades")
    assert provider.calls == 3


def test_shared_snapshot_expires():
    provider = FakeProvider("binance", frame=frame())
    now = [100.0]
    shared = SharedSnapshotMarketDataProvider(
        FallbackMarketDataProvider([provider]), ttl_seconds=60,
        clock=lambda: now[0],
    )
    kwargs = dict(symbol="BTCUSDT", market_type="spot", timeframe="1m",
                  since_ms=100, limit=1)
    shared.fetch_ohlcv_with_source(**kwargs)
    now[0] = 159.9
    shared.fetch_ohlcv_with_source(**kwargs)
    assert provider.calls == 1
    now[0] = 160.0
    shared.fetch_ohlcv_with_source(**kwargs)
    assert provider.calls == 2


def test_shared_snapshot_returns_isolated_frame():
    provider = FakeProvider("binance", frame=frame())
    shared = SharedSnapshotMarketDataProvider(
        FallbackMarketDataProvider([provider]), ttl_seconds=60,
    )
    kwargs = dict(symbol="BTCUSDT", market_type="spot", timeframe="1m",
                  since_ms=100, limit=1)
    first = shared.fetch_ohlcv_with_source(**kwargs)
    first.frame.loc[0, "close"] = -1
    second = shared.fetch_ohlcv_with_source(**kwargs)
    assert second.frame.loc[0, "close"] == 100.5
