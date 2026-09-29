import io
import json

import pytest

from aicfa.binance_market_data import BinanceMarketDataProvider


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return io.BytesIO(json.dumps(self.payload).encode())

    def __exit__(self, *args):
        return False


def test_binance_adapter_maps_public_spot_klines_to_ohlcv():
    captured = {}
    payload = [[1700000000000, "100", "110", "90", "105", "12", 1700000059999, "0", 1, "0", "0", "0"]]

    def opener(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse(payload)

    provider = BinanceMarketDataProvider(opener=opener)
    out = provider.fetch_ohlcv(
        symbol="BTC/USDT", market_type="spot", timeframe="1m", since_ms=1700000000000, limit=100
    )

    assert captured["timeout"] == 10.0
    assert "symbol=BTCUSDT" in captured["url"]
    assert "interval=1m" in captured["url"]
    assert "startTime=1700000000000" in captured["url"]
    assert "limit=100" in captured["url"]
    assert out.columns.tolist() == ["timestamp", "open", "high", "low", "close", "volume"]
    assert out.iloc[0]["close"] == "105"


def test_binance_adapter_uses_futures_endpoint():
    payload = [[1700000000000, "100", "110", "90", "105", "12"]]

    def opener(request, timeout):
        assert request.full_url.startswith("https://fapi.binance.com/fapi/v1/klines?")
        return FakeResponse(payload)

    out = BinanceMarketDataProvider(opener=opener).fetch_ohlcv(
        symbol="BTCUSDT", market_type="futures", timeframe="5m", since_ms=None, limit=10
    )
    assert len(out) == 1


@pytest.mark.parametrize("limit", [0, -1, 1001])
def test_binance_adapter_rejects_invalid_limit(limit):
    with pytest.raises(ValueError):
        BinanceMarketDataProvider().fetch_ohlcv(
            symbol="BTCUSDT", market_type="spot", timeframe="1m", since_ms=None, limit=limit
        )


def test_binance_adapter_defers_monthly_completion_semantics():
    with pytest.raises(ValueError):
        BinanceMarketDataProvider().fetch_ohlcv(
            symbol="BTCUSDT", market_type="spot", timeframe="1M", since_ms=None, limit=10
        )
