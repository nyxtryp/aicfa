"""Bybit public V5 market-data adapter for AICFA.

Only unauthenticated public endpoints are used. The adapter currently
implements symbol resolution and OHLCV transport so it can serve as the first
real fallback after Binance. Other Bybit capabilities are exposed by the
registry only when their transport adapters are implemented and tested.
"""
from __future__ import annotations

import json
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

_BYBIT_INTERVALS = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": "D",
    "1w": "W",
}
_BASE_URL = "https://api.bybit.com/v5/market"
_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class BybitTransportError(RuntimeError):
    """Bybit public transport failure."""

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class BybitMarketDataProvider:
    """Public Bybit V5 OHLCV provider for spot or linear markets."""

    exchange = "bybit"

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
        self.timeout_seconds = float(timeout_seconds)
        self.max_retries = int(max_retries)
        self.retry_backoff_seconds = float(retry_backoff_seconds)
        self._opener = opener
        self._sleeper = sleeper

    @staticmethod
    def _category(market_type: str) -> str:
        if market_type == "spot":
            return "spot"
        if market_type == "futures":
            return "linear"
        raise ValueError("market_type must be spot or futures")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = symbol.replace("/", "").replace("-", "").replace("_", "").strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if limit > 1000:
            raise ValueError("Bybit kline limit is capped at 1000")
        return int(limit)

    def _get(self, path: str, params: dict[str, object]) -> dict:
        request = Request(
            f"{_BASE_URL}/{path}?{urlencode(params)}",
            headers={"Accept": "application/json", "User-Agent": "AICFA/1.0"},
            method="GET",
        )
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                with self._opener(request, timeout=self.timeout_seconds) as response:
                    payload = json.load(response)
                break
            except HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt == attempts - 1:
                    raise BybitTransportError(
                        f"Bybit HTTP error {exc.code}", retryable=retryable
                    ) from exc
            except (URLError, TimeoutError, ConnectionError, OSError) as exc:
                if attempt == attempts - 1:
                    raise BybitTransportError(
                        "Bybit network/timeout error", retryable=True
                    ) from exc
            if self.retry_backoff_seconds:
                self._sleeper(self.retry_backoff_seconds * (2**attempt))

        if not isinstance(payload, dict):
            raise ValueError("Bybit response must be an object")
        if payload.get("retCode") != 0:
            raise BybitTransportError(
                f"Bybit API error {payload.get('retCode')}: {payload.get('retMsg')}",
                retryable=payload.get("retCode") in {10006},
            )
        return payload

    def resolve_symbol(
        self,
        asset: str,
        *,
        quote_asset: str = "USDT",
        market_type: str = "spot",
    ) -> str:
        normalized = asset.strip().upper().replace("/", "").replace("-", "").replace("_", "")
        if not normalized:
            raise ValueError("asset must not be empty")
        category = self._category(market_type)
        payload = self._get(
            "instruments-info",
            {"category": category, "limit": 1000},
        )
        items = payload.get("result", {}).get("list", [])
        symbols = {
            str(item.get("symbol", "")).upper()
            for item in items
            if isinstance(item, dict)
            and item.get("status") in {None, "Trading"}
        }
        if normalized in symbols:
            return normalized
        requested = f"{normalized}{quote_asset.strip().upper()}"
        if requested not in symbols:
            raise ValueError(f"no Bybit {quote_asset.upper()} market found for asset: {normalized}")
        return requested

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        market_type: str,
        timeframe: str,
        since_ms: int | None,
        limit: int,
    ) -> pd.DataFrame:
        if timeframe not in _BYBIT_INTERVALS:
            raise ValueError(f"Unsupported Bybit timeframe: {timeframe}")
        if since_ms is not None and int(since_ms) < 0:
            raise ValueError("since_ms must be non-negative")
        params: dict[str, object] = {
            "category": self._category(market_type),
            "symbol": self._normalize_symbol(symbol),
            "interval": _BYBIT_INTERVALS[timeframe],
            "limit": self._validate_limit(limit),
        }
        if since_ms is not None:
            params["start"] = int(since_ms)
        payload = self._get("kline", params)
        rows = payload.get("result", {}).get("list", [])
        if not isinstance(rows, list):
            raise ValueError("Bybit kline result must contain a list")
        normalized_rows = []
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                raise ValueError("Bybit kline row must contain at least 6 fields")
            normalized_rows.append(row[:6])
        return pd.DataFrame(normalized_rows, columns=_COLUMNS)
