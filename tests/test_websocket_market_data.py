import json

import pandas as pd
import pytest
from websocket import WebSocketTimeoutException

from aicfa.data_reliability import DataFreshness, LocalMarketStateStore
from aicfa.market_data import MarketKey
from aicfa.websocket_market_data import (
    BinanceWebSocketMarketDataTransport,
    WebSocketTransportError,
    parse_binance_kline_message,
)


def _message(*, closed=True, symbol="BTCUSDT", interval="1m"):
    return json.dumps(
        {
            "e": "kline",
            "s": symbol,
            "k": {
                "t": 1700000000000,
                "T": 1700000059999,
                "s": symbol,
                "i": interval,
                "o": "100",
                "h": "110",
                "l": "90",
                "c": "105",
                "v": "12",
                "x": closed,
            },
        }
    )


def test_parse_binance_websocket_accepts_only_closed_kline():
    key = MarketKey("binance", "BTC/USDT", "spot", "1m")

    assert parse_binance_kline_message(_message(closed=False), key) is None
    observation = parse_binance_kline_message(_message(), key)

    assert observation is not None
    assert observation.key == key
    assert observation.data.iloc[0]["close"] == 105
    assert observation.observed_at_ms == 1700000059999


def test_parse_binance_websocket_rejects_invalid_payload():
    key = MarketKey("binance", "BTC/USDT", "spot", "1m")

    with pytest.raises(WebSocketTransportError):
        parse_binance_kline_message("{bad", key)

    with pytest.raises(WebSocketTransportError):
        parse_binance_kline_message(json.dumps({"k": {"x": True}}), key)


class FakeSocket:
    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []
        self.closed = False

    def send(self, message):
        self.sent.append(json.loads(message))

    def recv(self):
        if not self.messages:
            raise ConnectionError("socket disconnected")
        return self.messages.pop(0)

    def close(self):
        self.closed = True


def test_transport_subscribes_reconnects_and_updates_local_state():
    key = MarketKey("binance", "BTC/USDT", "spot", "1m")
    sockets = [FakeSocket([_message()]), FakeSocket([_message()])]
    sleeps = []

    def connector(url, *, timeout):
        assert url == "wss://stream.binance.com:9443/ws"
        return sockets.pop(0)

    store = LocalMarketStateStore(max_age_ms=120_000)
    transport = BinanceWebSocketMarketDataTransport(
        keys=(key,),
        connector=connector,
        max_reconnects=1,
        reconnect_backoff_seconds=0.5,
        sleeper=sleeps.append,
        state_store=store,
    )

    observations = list(transport.stream(max_observations=2))

    assert len(observations) == 2
    assert len(sleeps) == 1
    assert sleeps == [0.5]
    assert store.freshness(key, now_ms=1700000060000).status is DataFreshness.FRESH
    assert sockets == []


class TimeoutThenMessageSocket(FakeSocket):
    def __init__(self, message):
        super().__init__([message])
        self.timed_out = False

    def recv(self):
        if not self.timed_out:
            self.timed_out = True
            raise WebSocketTimeoutException("read timed out")
        return super().recv()


def test_transport_ignores_read_timeout_and_keeps_connection():
    key = MarketKey("binance", "BTC/USDT", "spot", "1m")
    socket = TimeoutThenMessageSocket(_message())
    connections = []

    def connector(url, *, timeout):
        connections.append((url, timeout))
        return socket

    transport = BinanceWebSocketMarketDataTransport(
        keys=(key,),
        connector=connector,
        timeout_seconds=1,
        max_reconnects=0,
    )

    observation = next(transport.stream(max_observations=1))

    assert observation.key == key
    assert len(connections) == 1
    assert socket.closed is True


class AlwaysTimeoutSocket(FakeSocket):
    def recv(self):
        raise WebSocketTimeoutException("read timed out")


def test_transport_bounds_continuous_read_timeouts():
    key = MarketKey("binance", "BTC/USDT", "spot", "1m")
    socket = AlwaysTimeoutSocket([])
    now = iter((0.0, 3.0))

    def connector(url, *, timeout):
        return socket

    transport = BinanceWebSocketMarketDataTransport(
        keys=(key,),
        connector=connector,
        timeout_seconds=1,
        max_reconnects=0,
        idle_timeout_seconds=2,
        clock=lambda: next(now),
    )

    with pytest.raises(WebSocketTransportError):
        next(transport.stream(max_observations=1))

    assert socket.closed is True


def test_transport_resubscribes_after_reconnect():
    key = MarketKey("binance", "BTC/USDT", "futures", "5m")
    sockets = [FakeSocket([]), FakeSocket([_message(interval="5m")])]

    def connector(url, *, timeout):
        assert url == "wss://fstream.binance.com/ws"
        return sockets.pop(0)

    transport = BinanceWebSocketMarketDataTransport(
        keys=(key,),
        connector=connector,
        max_reconnects=1,
        reconnect_backoff_seconds=0,
        sleeper=lambda _: None,
    )

    observation = next(transport.stream(max_observations=1))
    assert observation.key == key


def test_transport_exhausts_reconnect_budget_without_fabricating_data():
    key = MarketKey("binance", "BTC/USDT", "spot", "1m")

    def connector(url, *, timeout):
        raise ConnectionError("down")

    transport = BinanceWebSocketMarketDataTransport(
        keys=(key,),
        connector=connector,
        max_reconnects=1,
        reconnect_backoff_seconds=0,
        sleeper=lambda _: None,
    )

    with pytest.raises(WebSocketTransportError):
        next(transport.stream(max_observations=1))
