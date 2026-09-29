"""Binance public market-data adapter for AICFA.

This adapter implements the provider-agnostic MarketDataProvider contract using
Binance's unauthenticated public REST market-data endpoints. It is deliberately
limited to OHLCV transport; WebSocket, derivatives side channels and retries
remain separate stages.
"""
from __future__ import annotations

import json
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from .market_data import BASE_TIMEFRAMES

_BINANCE_INTERVALS = set(BASE_TIMEFRAMES)
_SPOT_BASE_URL = "https://data-api.binance.vision/api/v3/klines"
_FUTURES_BASE_URL = "https://fapi.binance.com/fapi/v1/klines"
_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")

class BinanceMarketDataProvider:
    """Public Binance REST OHLCV provider.

    Symbols may be supplied as BTC/USDT or BTCUSDT. No API key is
    required because only public market-data endpoints are used.
    """

    exchange = "binance"

    def __init__(self, *, timeout_seconds: float = 10.0, opener: Callable[..., object] = urlopen) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = float(timeout_seconds)
        self._opener = opener

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

        request = Request(
            f"{self._endpoint(market_type)}?{urlencode(params)}",
            headers={"Accept": "application/json", "User-Agent": "AICFA/1.0"},
            method="GET",
        )
        with self._opener(request, timeout=self.timeout_seconds) as response:
            payload = json.load(response)

        if not isinstance(payload, list):
            raise ValueError("Binance klines response must be a list")

        rows = []
        for row in payload:
            if not isinstance(row, list) or len(row) < 6:
                raise ValueError("Binance kline row must contain at least 6 fields")
            rows.append(row[:6])

        return pd.DataFrame(rows, columns=_COLUMNS)
