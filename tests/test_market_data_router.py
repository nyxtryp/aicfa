import pandas as pd
import pytest

from aicfa.market_data_router import FallbackMarketDataProvider


class FakeProvider:
    def __init__(self, name, *, symbol=None, frame=None, error=None):
        self.exchange = name
        self.symbol = symbol
        self.frame = frame
        self.error = error

    def resolve_symbol(self, asset, *, market_type):
        if self.error:
            raise RuntimeError(self.error)
        return self.symbol or asset.upper()

    def fetch_ohlcv(self, **kwargs):
        if self.error:
            raise RuntimeError(self.error)
        return self.frame


def frame():
    return pd.DataFrame({
        "timestamp": [1000],
        "open": [100.0],
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
        symbol="BTCUSDT",
        market_type="spot",
        timeframe="1m",
        since_ms=None,
        limit=1,
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
            symbol="BTCUSDT",
            market_type="spot",
            timeframe="1m",
            since_ms=None,
            limit=1,
        )
