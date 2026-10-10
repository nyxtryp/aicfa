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

try:
    from websocket import WebSocketTimeoutException
except ImportError:  # pragma: no cover - runtime dependency is pinned in requirements
    class WebSocketTimeoutException(TimeoutError):
        pass

from .data_reliability import LocalMarketStateStore
from .market_data import MarketKey, timeframe_ms, validate_ohlcv


class WebSocketConnection(Protocol):
    def send(self, message: str) -> None: ...
    def recv(self) -> str: ...
    def close(self) -> None: ...


class WebSocketConnector(Protocol):
    def __call__(self, url: str, *, timeout: float) -> WebSocketConnection: ...


class WebSocketTransportError(RuntimeError):
    """WebSocket transport failure with explicit retryability."""


def default_websocket_connector(url: str, *, timeout: float) -> WebSocketConnection:
    """Create a real WebSocket connection using the runtime client."""
    try:
        import websocket
    except ImportError as exc:
        raise WebSocketTransportError(
            "websocket-client is required for live Binance WebSocket transport"
        ) from exc
    return websocket.create_connection(url, timeout=timeout)


@dataclass(frozen=True)
class WebSocketObservation:
    key: MarketKey
    data: pd.DataFrame
    observed_at_ms: int


_SPOT_WS_URL = "wss://stream.binance.com:9443/ws"
_FUTURES_WS_URL = "wss://fstream.binance.com/ws"


def _binance_symbol(symbol: str) -> str:
    """Convert a CCXT unified symbol to Binance's native stream ID.

    CCXT futures symbols commonly look like BTC/USDT:USDT; Binance's native
    stream ID is BTCUSDT. Keep the original unified symbol on MarketKey for
    REST routing and persistence, but strip the settlement suffix for WS.
    """
    return symbol.split(":", 1)[0].replace("/", "").replace("-", "").replace("_", "").upper()


def _stream_name(key: MarketKey) -> str:
    symbol = _binance_symbol(key.symbol).lower()
    return f"{symbol}@kline_{key.timeframe}"


def _url_for(key: MarketKey) -> str:
    if key.market_type == "spot":
        return _SPOT_WS_URL
    if key.market_type == "futures":
        return _FUTURES_WS_URL
    raise ValueError("market_type must be spot or futures")


def parse_binance_kline_message(
    message: str, key: MarketKey
) -> WebSocketObservation | None:
    """Parse one Binance kline event; ignore valid events for other streams."""
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError) as exc:
        raise WebSocketTransportError("Invalid Binance WebSocket JSON") from exc

    if not isinstance(payload, dict):
        raise WebSocketTransportError("Invalid Binance WebSocket payload")

    kline = payload.get("k")
    if kline is None:
        return None
    if not isinstance(kline, dict):
        raise WebSocketTransportError("Invalid Binance kline payload")

    identity_fields = ("s", "i", "x")
    if any(field not in kline for field in identity_fields):
        raise WebSocketTransportError("Incomplete Binance kline identity")

    expected_symbol = _binance_symbol(key.symbol)
    if str(kline["s"]).upper() != expected_symbol:
        return None
    if str(kline["i"]).lower() != key.timeframe.lower():
        return None
    if kline["x"] is not True:
        return None

    required = ("t", "T", "o", "h", "l", "c", "v")
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
        connector: WebSocketConnector = default_websocket_connector,
        timeout_seconds: float = 10.0,
        max_reconnects: int = 2,
        reconnect_backoff_seconds: float = 0.25,
        sleeper: Callable[[float], None] = time.sleep,
        state_store: LocalMarketStateStore | None = None,
        idle_timeout_seconds: float | None = None,
        observation_timeout_seconds: float | None = None,
        connection_max_age_seconds: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not keys:
            raise ValueError("keys must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_reconnects < 0:
            raise ValueError("max_reconnects must be non-negative")
        if reconnect_backoff_seconds < 0:
            raise ValueError("reconnect_backoff_seconds must be non-negative")
        if idle_timeout_seconds is not None and idle_timeout_seconds <= 0:
            raise ValueError("idle_timeout_seconds must be positive")
        if (
            observation_timeout_seconds is not None
            and observation_timeout_seconds <= 0
        ):
            raise ValueError("observation_timeout_seconds must be positive")
        if connection_max_age_seconds is not None and connection_max_age_seconds <= 0:
            raise ValueError("connection_max_age_seconds must be positive")
        self.keys = tuple(keys)
        self.timeout_seconds = float(timeout_seconds)
        self.max_reconnects = int(max_reconnects)
        self.reconnect_backoff_seconds = float(reconnect_backoff_seconds)
        self._connector = connector
        self._sleeper = sleeper
        self._state_store = state_store
        self._clock = clock
        self._connection_max_age_seconds = (
            None if connection_max_age_seconds is None else float(connection_max_age_seconds)
        )
        if len({key.market_type for key in self.keys}) != 1:
            raise ValueError("all keys on one WebSocket connection must use the same market_type")
        if idle_timeout_seconds is None:
            fixed_durations = [
                timeframe_ms(key.timeframe) / 1000.0
                for key in self.keys
                if key.timeframe != "1M"
            ]
            self._idle_timeout_seconds = (
                2.0 * max(fixed_durations) if fixed_durations else None
            )
        else:
            self._idle_timeout_seconds = float(idle_timeout_seconds)
        if observation_timeout_seconds is None:
            fixed_durations = [
                timeframe_ms(key.timeframe) / 1000.0
                for key in self.keys
                if key.timeframe != "1M"
            ]
            self._observation_timeout_seconds = (
                2.0 * max(fixed_durations) if fixed_durations else None
            )
        else:
            self._observation_timeout_seconds = float(observation_timeout_seconds)

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
                started_at = self._clock()
                idle_deadline = (
                    started_at + self._idle_timeout_seconds
                    if self._idle_timeout_seconds is not None
                    else None
                )
                observation_deadline = (
                    started_at + self._observation_timeout_seconds
                    if self._observation_timeout_seconds is not None
                    else None
                )
                while max_observations is None or observations < max_observations:
                    if (
                        self._connection_max_age_seconds is not None
                        and self._clock() - started_at >= self._connection_max_age_seconds
                    ):
                        # Let the supervisor recover candles over REST before it
                        # opens a fresh socket. This avoids treating planned rotation
                        # as an invisible, lossless reconnect.
                        raise ConnectionError("Binance WebSocket planned rotation deadline reached")
                    try:
                        raw = connection.recv()
                    except (TimeoutError, WebSocketTimeoutException) as exc:
                        # A read timeout does not mean the WebSocket is dead. The
                        # transport accepts only closed candles, so it can legitimately
                        # wait across a socket timeout for the next candle close.
                        # But continuous timeouts must remain bounded.
                        now = self._clock()
                        if (
                            observation_deadline is not None
                            and now >= observation_deadline
                        ):
                            raise ConnectionError(
                                "Binance WebSocket observation timeout exceeded"
                            ) from exc
                        if idle_deadline is not None and now >= idle_deadline:
                            raise ConnectionError(
                                "Binance WebSocket idle timeout exceeded"
                            ) from exc
                        continue

                    # Binance returns subscription errors as ordinary JSON
                    # messages. Previously those were silently ignored, leaving
                    # a bad 900-stream socket alive forever and producing no
                    # candle events, so autonomous scanning looked frozen.
                    try:
                        envelope = json.loads(raw)
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise WebSocketTransportError(
                            "Invalid Binance WebSocket JSON"
                        ) from exc
                    if isinstance(envelope, dict) and envelope.get("code") is not None:
                        raise WebSocketTransportError(
                            f"Binance WebSocket subscription error: "
                            f"{envelope.get('code')}: {envelope.get('msg', '')}"
                        )

                    # Reset the reconnect budget only after real valid traffic,
                    # not merely after a TCP/WebSocket handshake. Otherwise a
                    # server that accepts and immediately drops the socket can
                    # reconnect forever without ever triggering REST recovery.
                    reconnects = 0

                    # Any successfully received stream message proves that the
                    # connection is active. Open kline updates are deliberately
                    # ignored as market observations, but they still reset the
                    # transport-level idle watchdog.
                    if idle_deadline is not None:
                        received_at = self._clock()
                        idle_deadline = received_at + self._idle_timeout_seconds

                    kline = envelope.get("k") if isinstance(envelope, dict) else None
                    if not isinstance(kline, dict):
                        # SUBSCRIBE acknowledgements and other control frames
                        # are valid transport traffic, not market observations.
                        continue
                    identity = (
                        str(kline.get("s", "")).upper(),
                        str(kline.get("i", "")).lower(),
                    )
                    for key in self.keys:
                        expected = (
                            _binance_symbol(key.symbol),
                            key.timeframe.lower(),
                        )
                        if identity != expected:
                            continue
                        observation = parse_binance_kline_message(raw, key)
                        if observation is None:
                            break
                        if self._state_store is not None:
                            self._state_store.update(
                                key,
                                observation.data,
                                observed_at_ms=observation.observed_at_ms,
                            )
                        observations += 1
                        if observation_deadline is not None:
                            observation_deadline = (
                                self._clock() + self._observation_timeout_seconds
                            )
                        yield observation
                        break
            except (OSError, TimeoutError, ConnectionError, WebSocketTransportError) as exc:
                if reconnects >= self.max_reconnects:
                    raise WebSocketTransportError(
                        "Binance WebSocket reconnect budget exhausted"
                    ) from exc
                self._sleeper(
                    min(self.reconnect_backoff_seconds * (2**reconnects), 10.0)
                )
                reconnects += 1
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except OSError:
                        pass
