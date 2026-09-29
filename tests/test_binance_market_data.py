import io
import json
from urllib.error import HTTPError, URLError

import pytest

from aicfa.binance_market_data import BinanceMarketDataProvider, BinanceTransportError


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


def test_binance_adapter_retries_transient_network_failure():
    calls = []
    sleeps = []
    payload = [[1700000000000, "100", "110", "90", "105", "12"]]

    def opener(request, timeout):
        calls.append(timeout)
        if len(calls) < 3:
            raise URLError("temporary network failure")
        return FakeResponse(payload)

    provider = BinanceMarketDataProvider(
        max_retries=2,
        retry_backoff_seconds=0.5,
        opener=opener,
        sleeper=sleeps.append,
    )
    out = provider.fetch_ohlcv(
        symbol="BTCUSDT", market_type="spot", timeframe="1m", since_ms=None, limit=1
    )

    assert len(out) == 1
    assert len(calls) == 3
    assert sleeps == [0.5, 1.0]


def test_binance_adapter_retries_rate_limit_and_server_errors():
    calls = []

    def opener(request, timeout):
        calls.append(len(calls))
        if len(calls) == 1:
            raise HTTPError(request.full_url, 429, "rate limited", {}, None)
        if len(calls) == 2:
            raise HTTPError(request.full_url, 503, "unavailable", {}, None)
        return FakeResponse([[1700000000000, "100", "110", "90", "105", "12"]])

    provider = BinanceMarketDataProvider(
        max_retries=2, retry_backoff_seconds=0, opener=opener
    )
    out = provider.fetch_ohlcv(
        symbol="BTCUSDT", market_type="spot", timeframe="1m", since_ms=None, limit=1
    )

    assert len(out) == 1
    assert len(calls) == 3


def test_binance_adapter_does_not_retry_nonrecoverable_http_error():
    calls = []

    def opener(request, timeout):
        calls.append(1)
        raise HTTPError(request.full_url, 400, "bad request", {}, None)

    provider = BinanceMarketDataProvider(
        max_retries=2, retry_backoff_seconds=0, opener=opener
    )

    with pytest.raises(BinanceTransportError) as exc_info:
        provider.fetch_ohlcv(
            symbol="BTCUSDT", market_type="spot", timeframe="1m", since_ms=None, limit=1
        )

    assert exc_info.value.retryable is False
    assert len(calls) == 1


def test_binance_adapter_exhausted_transient_error_is_explicitly_retryable():
    calls = []

    def opener(request, timeout):
        calls.append(1)
        raise URLError("still unavailable")

    provider = BinanceMarketDataProvider(
        max_retries=2, retry_backoff_seconds=0, opener=opener
    )

    with pytest.raises(BinanceTransportError) as exc_info:
        provider.fetch_ohlcv(
            symbol="BTCUSDT", market_type="spot", timeframe="1m", since_ms=None, limit=1
        )

    assert exc_info.value.retryable is True
    assert len(calls) == 3


@pytest.mark.parametrize(
    ("max_retries", "backoff"),
    [(-1, 0), (0, -0.1)],
)
def test_binance_adapter_rejects_invalid_recovery_configuration(max_retries, backoff):
    with pytest.raises(ValueError):
        BinanceMarketDataProvider(
            max_retries=max_retries, retry_backoff_seconds=backoff
        )
