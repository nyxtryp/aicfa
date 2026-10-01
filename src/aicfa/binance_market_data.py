"""Binance public market-data adapter for AICFA.

This adapter implements the provider-agnostic MarketDataProvider contract using
Binance's unauthenticated public REST market-data endpoints. It is deliberately
limited to OHLCV transport; WebSocket, derivatives side channels and retries
remain separate stages.
"""
from __future__ import annotations

import json
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from .market_data import BASE_TIMEFRAMES

_BINANCE_INTERVALS = set(BASE_TIMEFRAMES)
_SPOT_BASE_URL = "https://data-api.binance.vision/api/v3"
_FUTURES_BASE_URL = "https://fapi.binance.com/fapi/v1"
_OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
_TRADE_COLUMNS = ("timestamp", "price", "volume", "side")
_BOOK_COLUMNS = ("timestamp", "bid_price", "bid_size", "ask_price", "ask_size")

class BinanceTransportError(RuntimeError):
    """Provider transport failure classified as retryable or terminal."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class BinanceMarketDataProvider:
    """Public Binance REST OHLCV provider.

    Symbols may be supplied as BTC/USDT or BTCUSDT. No API key is
    required because only public market-data endpoints are used.
    """

    exchange = "binance"

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.25,
        opener: Callable[..., object] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be non-negative")
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        self._opener = opener
        self._sleeper = sleeper

    def resolve_symbol(self, asset: str, *, quote_asset: str = "USDT", market_type: str = "spot") -> str:
        """Resolve a user asset to a currently tradable Binance symbol.

        Explicit pairs are validated as-is. Bare base assets are resolved to
        a currently trading USDT pair. No asset universe is hardcoded.
        """
        normalized = asset.strip().upper().replace("/", "").replace("-", "").replace("_", "")
        if not normalized:
            raise ValueError("asset must not be empty")
        if "/" in asset or "-" in asset or "_" in asset:
            requested = normalized
            symbols = self._exchange_symbols(market_type)
            if requested not in symbols:
                raise ValueError(f"unsupported Binance symbol: {requested}")
            return requested

        symbols = self._exchange_symbols(market_type)
        if normalized in symbols:
            return normalized

        base = normalized
        quote = quote_asset.strip().upper()
        requested = f"{base}{quote}"
        if requested not in symbols:
            raise ValueError(f"no Binance {quote} market found for asset: {base}")
        return requested

    def _exchange_symbols(self, market_type: str) -> set[str]:
        endpoint = "https://api.binance.com/api/v3/exchangeInfo" if market_type == "spot" else "https://fapi.binance.com/fapi/v1/exchangeInfo"
        request = Request(endpoint, headers={"Accept": "application/json", "User-Agent": "AICFA/1.0"}, method="GET")
        with self._opener(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)
        if not isinstance(payload, dict) or not isinstance(payload.get("symbols"), list):
            raise ValueError("Binance exchangeInfo response must contain symbols")
        symbols = set()
        for item in payload["symbols"]:
            if not isinstance(item, dict):
                continue
            status = item.get("status") if market_type == "spot" else item.get("status") or item.get("contractStatus")
            if status not in {None, "TRADING"}:
                continue
            symbol = item.get("symbol")
            if isinstance(symbol, str) and symbol:
                symbols.add(symbol.upper())
        return symbols

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.replace("/", "").replace("-", "").strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if limit > 1000:
            raise ValueError("Binance adapter currently caps limit at 1000")
        return int(limit)

    @staticmethod
    def _endpoint(market_type: str) -> str:
        if market_type == "spot":
            return _SPOT_BASE_URL
        if market_type == "futures":
            return _FUTURES_BASE_URL
        raise ValueError("market_type must be spot or futures")

    def fetch_ohlcv(self, *, symbol: str, market_type: str, timeframe: str, since_ms: int | None, limit: int) -> pd.DataFrame:
        if timeframe not in _BINANCE_INTERVALS:
            raise ValueError(f"Unsupported Binance timeframe: {timeframe}")
        if timeframe == "1M":
            raise ValueError("1M requires provider-specific scanner semantics")
        if since_ms is not None and int(since_ms) < 0:
            raise ValueError("since_ms must be non-negative")

        params = {"symbol": self._normalize_symbol(symbol), "interval": timeframe, "limit": self._validate_limit(limit)}
        if since_ms is not None:
            params["startTime"] = int(since_ms)
        endpoint = self._endpoint(market_type).replace("/klines", "")
        request = Request(
            f"{endpoint}/klines?{urlencode(params)}",
            headers={"Accept": "application/json", "User-Agent": "AICFA/1.0"},
            method="GET",
        )
        payload = self._request_json(request)
        if not isinstance(payload, list):
            raise ValueError("Binance klines response must be a list")
        rows = []
        for row in payload:
            if not isinstance(row, list) or len(row) < 6:
                raise ValueError("Binance kline row must contain at least 6 fields")
            rows.append(row[:6])
        return pd.DataFrame(rows, columns=_OHLCV_COLUMNS)

    def _request_json(self, request: Request):
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    return json.load(response)
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt == attempts - 1:
                    raise BinanceTransportError(
                        f"Binance HTTP error {exc.code}", retryable=retryable
                    ) from exc
            except (URLError, TimeoutError, ConnectionError, OSError) as exc:
                if attempt == attempts - 1:
                    raise BinanceTransportError(
                        "Binance network/timeout error", retryable=True
                    ) from exc
            if self.retry_backoff_seconds:
                self._sleeper(self.retry_backoff_seconds * (2**attempt))
        raise AssertionError("unreachable")

    def _public_json(self, path: str, *, market_type: str, params: dict[str, object]):
        base = self._endpoint(market_type).rsplit("/", 1)[0]
        request = Request(
            f"{base}/{path}?{urlencode(params)}",
            headers={"Accept": "application/json", "User-Agent": "AICFA/1.0"},
            method="GET",
        )
        return self._request_json(request)

    def fetch_trades(self, *, symbol: str, market_type: str, limit: int) -> pd.DataFrame:
        if limit <= 0 or limit > 1000:
            raise ValueError("Binance trade limit must be between 1 and 1000")
        payload = self._public_json(
            "trades", market_type=market_type,
            params={"symbol": self._normalize_symbol(symbol), "limit": int(limit)},
        )
        if not isinstance(payload, list):
            raise ValueError("Binance trades response must be a list")
        rows = []
        for row in payload:
            if not isinstance(row, dict):
                raise ValueError("Binance trade row must be an object")
            required = ("price", "qty", "time", "isBuyerMaker")
            if any(key not in row for key in required):
                raise ValueError("Binance trade row is incomplete")
            side = -1 if bool(row["isBuyerMaker"]) else 1
            rows.append([row["time"], row["price"], row["qty"], side])
        return pd.DataFrame(rows, columns=_TRADE_COLUMNS).sort_values(
            "timestamp"
        ).reset_index(drop=True)

    def fetch_order_book(self, *, symbol: str, market_type: str, limit: int = 1) -> pd.DataFrame:
        if limit <= 0 or limit > 5000:
            raise ValueError("Binance order-book limit must be between 1 and 5000")
        payload = self._public_json(
            "depth", market_type=market_type,
            params={"symbol": self._normalize_symbol(symbol), "limit": int(limit)},
        )
        if not isinstance(payload, dict):
            raise ValueError("Binance order book response must be an object")
        bids = payload.get("bids")
        asks = payload.get("asks")
        if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
            raise ValueError("Binance order book must contain bids and asks")
        observed_at = int(time.time() * 1000)
        return pd.DataFrame(
            [[observed_at, bids[0][0], bids[0][1], asks[0][0], asks[0][1]]],
            columns=_BOOK_COLUMNS,
        )
