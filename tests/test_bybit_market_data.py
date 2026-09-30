import json
from io import BytesIO

import pytest

from aicfa.bybit_market_data import BybitMarketDataProvider, BybitTransportError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode()

    def __iter__(self):
        return iter(())


def opener_factory(payload):
    def opener(request, timeout):
        return JsonResponse(payload)
    return opener


class JsonResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(())

    def __getattr__(self, name):
        if name == "read":
            return lambda: json.dumps(self.payload).encode()
        raise AttributeError(name)


def test_bybit_resolves_bare_asset_to_usdt(monkeypatch):
    provider = BybitMarketDataProvider(opener=lambda request, timeout: JsonResponse({
        "retCode": 0,
        "retMsg": "OK",
        "result": {"list": [{"symbol": "PEPEUSDT", "status": "Trading"}]},
    }))
    assert provider.resolve_symbol("PEPE") == "PEPEUSDT"


def test_bybit_resolves_explicit_pair():
    provider = BybitMarketDataProvider(opener=lambda request, timeout: JsonResponse({
        "retCode": 0,
        "retMsg": "OK",
        "result": {"list": [{"symbol": "BTCUSDT", "status": "Trading"}]},
    }))
    assert provider.resolve_symbol("BTC/USDT") == "BTCUSDT"


def test_bybit_rejects_unknown_asset():
    provider = BybitMarketDataProvider(opener=lambda request, timeout: JsonResponse({
        "retCode": 0,
        "retMsg": "OK",
        "result": {"list": [{"symbol": "BTCUSDT", "status": "Trading"}]},
    }))
    with pytest.raises(ValueError, match="no Bybit"):
        provider.resolve_symbol("NOTREAL")


def test_bybit_maps_kline_to_common_ohlcv_contract():
    provider = BybitMarketDataProvider(opener=lambda request, timeout: JsonResponse({
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "list": [["1700000000000", "100", "105", "99", "103", "123.4", "0"]]
        },
    }))
    frame = provider.fetch_ohlcv(
        symbol="BTCUSDT",
        market_type="spot",
        timeframe="5m",
        since_ms=None,
        limit=1,
    )
    assert frame.columns.tolist() == ["timestamp", "open", "high", "low", "close", "volume"]
    assert frame.iloc[0].tolist() == ["1700000000000", "100", "105", "99", "103", "123.4"]


def test_bybit_rejects_unsupported_timeframe():
    provider = BybitMarketDataProvider()
    with pytest.raises(ValueError, match="Unsupported Bybit timeframe"):
        provider.fetch_ohlcv(
            symbol="BTCUSDT",
            market_type="spot",
            timeframe="1M",
            since_ms=None,
            limit=1,
        )


def test_bybit_api_rate_limit_is_retryable():
    provider = BybitMarketDataProvider(opener=lambda request, timeout: JsonResponse({
        "retCode": 10006,
        "retMsg": "Too many visits!",
        "result": {},
    }))
    with pytest.raises(BybitTransportError) as exc:
        provider.fetch_ohlcv(
            symbol="BTCUSDT",
            market_type="spot",
            timeframe="1m",
            since_ms=None,
            limit=1,
        )
    assert exc.value.retryable is True


def test_bybit_symbol_resolution_follows_instruments_cursor():
    calls = []

    def opener(request, timeout):
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(request.full_url).query)
        calls.append(query.get("cursor", [None])[0])
        cursor = query.get("cursor", [None])[0]
        if cursor is None:
            payload = {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "list": [{"symbol": "FIRSTUSDT", "status": "Trading"}],
                    "nextPageCursor": "cursor-2",
                },
            }
        else:
            payload = {
                "retCode": 0,
                "retMsg": "OK",
                "result": {
                    "list": [{"symbol": "SECONDUSDT", "status": "Trading"}],
                    "nextPageCursor": "",
                },
            }
        return JsonResponse(payload)

    provider = BybitMarketDataProvider(opener=opener)
    assert provider.resolve_symbol("SECOND") == "SECONDUSDT"
    assert calls == [None, "cursor-2"]


def test_bybit_symbol_resolution_stops_when_cursor_repeats():
    calls = []

    def opener(request, timeout):
        from urllib.parse import parse_qs, urlparse

        query = parse_qs(urlparse(request.full_url).query)
        cursor = query.get("cursor", [None])[0]
        calls.append(cursor)
        return JsonResponse({
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [{"symbol": "FIRSTUSDT", "status": "Trading"}],
                "nextPageCursor": "same-cursor",
            },
        })

    provider = BybitMarketDataProvider(opener=opener)
    with pytest.raises(ValueError, match="no Bybit"):
        provider.resolve_symbol("SECOND")
    assert calls == [None, "same-cursor"]
