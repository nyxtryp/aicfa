"""Provider-agnostic incremental WebSocket market transport.

The transport accepts an injected WebSocket connector so the analytical core
does not depend on a particular WebSocket library. The Binance implementation
uses public kline streams and accepts only closed candles as confirmed market
observations.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Callable, Protocol

import pandas as pd

from .data_reliability import LocalMarketStateStore
from .market_data import MarketKey, validate_ohlcv


class WebSocketConnection(Protocol):
    def send(self, message: str) -> None: ...
    def recv(self) -> str: ...
    def close(self) -> None: ...


class WebSocketConnector(Protocol):
    def __call__(self, url: str, *, timeout: float) -> WebSocketConnection: ...


class WebSocketTransportError(RuntimeError):
    """WebSocket transport failure with explicit retryability."""


@dataclass(frozen=True)
class WebSocketObservation:
    key: MarketKey
    data: pd.DataFrame
    observed_at_ms: int


_SPOT_WS_URL = "wss://stream.binance.com:9443/ws"
_FUTURES_WS_URL = "wss://fstream.binance.com/ws"


def _stream_name(key: MarketKey) -> str:
    symbol = key.symbol.replace("/", "").replace("-", "").lower()
    return f"{symbol}@kline_{key.timeframe}"


def _url_for(key: MarketKey) -> str:
    if key.market_type == "spot":
        return _SPOT_WS_URL
    if key.market_type == "futures":
        return _FUTURES_WS_URL
    raise ValueError("market_type must be spot or futures")


def parse_binance_kline_message(message: str, key: MarketKey) -> WebSocketObservation | None:
    """Parse one Binance kline event; ignore non-closed candles."""
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError) as exc:
        raise WebSocketTransportError("Invalid Binance WebSocket JSON") from exc

    kline = payload.get("k")
    if not isinstance(kline, dict):
        return None
    if kline.get("x") is not True:
        return None

    required = ("t", "o", "h", "l", "c", "v")
    if any(field not in kline for field in required):
        raise WebSocketTransportError("Incomplete Binance kline event")

    row = pd.DataFrame(
        [[kline["t"], kline["o"], kline["h"], kline["l"], kline["c"], kline["v"]]],
        columns=("timestamp", "open", "high", "low", "close", "volume"),
    )
    return WebSocketObservation(
        key=key,
        data=validate_ohlcv(row),
        observed_at_ms=int(kline["T"]),
    )


class BinanceWebSocketMarketDataTransport:
    """Reconnectable Binance kline transport for confirmed closed candles."""

    def __init__(
        self,
        *,
        keys: tuple[MarketKey, ...],
        connector: WebSocketConnector,
        timeout_seconds: float = 10.0,
        max_reconnects: int = 2,
        reconnect_backoff_seconds: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
        state_store: LocalMarketStateStore | None = None,
    ) -> None:
        if not keys:
            raise ValueError("keys must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_reconnects < 0:
            raise ValueError("max_reconnects must be non-negative")
        if reconnect_backoff_seconds < 0:
            raise ValueError("reconnect_backoff_seconds must be non-negative")
        self.keys = tuple(keys)
        self.timeout_seconds = float(timeout_seconds)
        self.max_reconnects = int(max_reconnects)
        self.reconnect_backoff_seconds = float(reconnect_backoff_seconds)
        self._connector = connector
        self._sleeper = sleeper
        self._state_store = state_store

    def _subscribe(self, connection: WebSocketConnection) -> None:
        params = [_stream_name(key) for key in self.keys]
        connection.send(json.dumps({"method": "SUBSCRIBE", "params": params, "id": 1}))

    def stream(self, *, max_observations: int | None = None):
        """Yield confirmed closed-candle observations, reconnecting when needed."""
        if max_observations is not None and max_observations <= 0:
            raise ValueError("max_observations must be positive")

        observations = 0
        reconnects = 0
        while max_observations is None or observations < max_observations:
            connection = None
            try:
                connection = self._connector(
                    _url_for(self.keys[0]), timeout=self.timeout_seconds
                )
                self._subscribe(connection)
                reconnects = 0
                while max_observations is None or observations < max_observations:
                    raw = connection.recv()
                    for key in self.keys:
                        observation = parse_binance_kline_message(raw, key)
                        if observation is None:
                            continue
                        if self._state_store is not None:
                            self._state_store.update(
                                key,
                                observation.data,
                                observed_at_ms=observation.observed_at_ms,
                            )
                        observations += 1
                        yield observation
                        break
            except (OSError, TimeoutError, ConnectionError, WebSocketTransportError) as exc:
                if reconnects >= self.max_reconnects:
                    raise WebSocketTransportError(
                        "Binance WebSocket reconnect budget exhausted"
                    ) from exc
                self._sleeper(
                    self.reconnect_backoff_seconds * (2**reconnects)
                )
                reconnects += 1
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except OSError:
                        pass
