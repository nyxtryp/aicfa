"""Bybit public V5 market-data adapter for AICFA.

Only unauthenticated public endpoints are used. The adapter currently
implements symbol resolution and OHLCV transport so it can serve as the first
real fallback after Binance. Other Bybit capabilities are exposed by the
registry only when their transport adapters are implemented and tested.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from .market_data import timeframe_ms

_BYBIT_INTERVALS = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": "D",
    "1w": "W",
    "1M": "M",
}
_BASE_URL = "https://api.bybit.com/v5/market"
_OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
_TRADE_COLUMNS = ("timestamp", "price", "volume", "side")
_BOOK_COLUMNS = ("timestamp", "bid_price", "bid_size", "ask_price", "ask_size")
_MAX_KLINE_PAGE = 1000
_MAX_KLINE_TOTAL = 5000


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
        self._symbols_cache: dict[str, tuple[float, frozenset[str]]] = {}
        self._symbols_cache_ttl_seconds = 60.0

    @staticmethod
    def _category(market_type: str) -> str:
        if market_type == "spot":
            return "spot"
        if market_type == "futures":
            return "linear"
        raise ValueError("market_type must be spot or futures")

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        # Accept AICFA/CCXT contract notation such as XAU/USDT:USDT,
        # while sending the native Bybit instrument symbol XAUUSDT.
        raw = symbol.strip().upper()
        if ":" in raw:
            raw = raw.split(":", 1)[0]
        normalized = raw.replace("/", "").replace("-", "").replace("_", "")
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    @staticmethod
    def _validate_limit(limit: int) -> int:
        try:
            limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        if limit <= 0:
            raise ValueError("limit must be positive")
        if limit > _MAX_KLINE_TOTAL:
            raise ValueError(
                f"Bybit kline limit must be between 1 and {_MAX_KLINE_TOTAL}"
            )
        return limit

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
        requested = f"{normalized}{quote_asset.strip().upper()}"
        now = time.monotonic()
        cached = self._symbols_cache.get(market_type)
        if cached is not None and now - cached[0] < self._symbols_cache_ttl_seconds:
            symbols = cached[1]
            if normalized in symbols:
                return normalized
            if requested in symbols:
                return requested
            raise ValueError(f"no Bybit {quote_asset.upper()} market found for asset: {normalized}")

        cursor: str | None = None
        seen_cursors: set[str] = set()
        all_symbols: set[str] = set()

        while True:
            params: dict[str, object] = {"category": category, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            payload = self._get("instruments-info", params)
            result = payload.get("result", {})
            items = result.get("list", [])
            page_symbols = {
                str(item.get("symbol", "")).upper()
                for item in items
                if isinstance(item, dict)
                and item.get("status") in {None, "Trading"}
            }
            all_symbols.update(symbol for symbol in page_symbols if symbol)

            next_cursor = str(result.get("nextPageCursor") or "")
            if not next_cursor or next_cursor in seen_cursors:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        frozen = frozenset(all_symbols)
        self._symbols_cache[market_type] = (now, frozen)
        if normalized in frozen:
            return normalized
        if requested in frozen:
            return requested
        raise ValueError(f"no Bybit {quote_asset.upper()} market found for asset: {normalized}")

    def fetch_trades(self, *, symbol: str, market_type: str, limit: int) -> pd.DataFrame:
        try:
            limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        max_limit = 60 if market_type == "spot" else 1000
        if limit <= 0 or limit > max_limit:
            raise ValueError(f"Bybit trade limit must be between 1 and {max_limit}")
        payload = self._get(
            "recent-trade",
            {
                "category": self._category(market_type),
                "symbol": self._normalize_symbol(symbol),
                "limit": int(limit),
            },
        )
        rows = payload.get("result", {}).get("list", [])
        if not isinstance(rows, list):
            raise ValueError("Bybit trade result must contain a list")
        normalized = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Bybit trade row must be an object")
            if any(key not in row for key in ("time", "price", "size", "side")):
                raise ValueError("Bybit trade row is incomplete")
            side = {"Buy": 1, "Sell": -1}.get(str(row["side"]))
            if side is None:
                raise ValueError("Bybit trade side must be Buy or Sell")
            normalized.append([row["time"], row["price"], row["size"], side])
        return pd.DataFrame(normalized, columns=_TRADE_COLUMNS).sort_values(
            "timestamp"
        ).reset_index(drop=True)

    def fetch_order_book_history(
        self,
        *,
        symbol: str,
        market_type: str,
        snapshots: int,
        interval_seconds: float,
    ) -> pd.DataFrame:
        if snapshots <= 0:
            raise ValueError("snapshots must be positive")
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative")

        count = int(snapshots)

        def collect(index: int) -> dict:
            if interval_seconds and index:
                self._sleeper(float(index) * float(interval_seconds))
            frame = self.fetch_order_book(symbol=symbol, market_type=market_type, limit=1)
            return frame.iloc[0].to_dict()

        # Schedule snapshots at the requested sampling times. Network requests
        # may overlap, avoiding serial REST latency while preserving temporal
        # spacing between snapshot starts.
        with ThreadPoolExecutor(max_workers=count) as executor:
            rows = list(executor.map(collect, range(count)))
        return pd.DataFrame(rows, columns=_BOOK_COLUMNS)
    def fetch_order_book(self, *, symbol: str, market_type: str, limit: int = 1) -> pd.DataFrame:
        try:
            limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise ValueError("limit must be an integer") from exc
        max_limit = 50 if market_type == "spot" else 200
        if limit <= 0 or limit > max_limit:
            raise ValueError(f"Bybit order-book limit must be between 1 and {max_limit}")
        payload = self._get(
            "orderbook",
            {
                "category": self._category(market_type),
                "symbol": self._normalize_symbol(symbol),
                "limit": int(limit),
            },
        )
        result = payload.get("result", {})
        bids = result.get("b", [])
        asks = result.get("a", [])
        if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
            raise ValueError("Bybit order book must contain bids and asks")
        timestamp = result.get("ts")
        if timestamp is None:
            raise ValueError("Bybit order book is missing source timestamp")
        return pd.DataFrame(
            [[timestamp, bids[0][0], bids[0][1], asks[0][0], asks[0][1]]],
            columns=_BOOK_COLUMNS,
        )

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

        total = self._validate_limit(limit)
        normalized_symbol = self._normalize_symbol(symbol)
        interval = None if timeframe == "1M" else timeframe_ms(timeframe)
        rows: list[list[object]] = []
        remaining = total
        next_start = int(since_ms) if since_ms is not None else None
        next_end: int | None = None

        while remaining > 0:
            page_limit = min(_MAX_KLINE_PAGE, remaining)
            params: dict[str, object] = {
                "category": self._category(market_type),
                "symbol": normalized_symbol,
                "interval": _BYBIT_INTERVALS[timeframe],
                "limit": page_limit,
            }
            if next_start is not None:
                params["start"] = next_start
            elif next_end is not None:
                params["end"] = next_end

            payload = self._get("kline", params)
            page = payload.get("result", {}).get("list", [])
            if not isinstance(page, list):
                raise ValueError("Bybit kline result must contain a list")

            page_rows: list[list[object]] = []
            for row in page:
                if not isinstance(row, list) or len(row) < 6:
                    raise ValueError("Bybit kline row must contain at least 6 fields")
                page_rows.append(row[:6])
            if not page_rows:
                break

            rows.extend(page_rows)
            remaining -= len(page_rows)
            timestamps = [int(row[0]) for row in page_rows]

            if len(page_rows) < page_limit:
                break

            if next_start is not None:
                if interval is None:
                    next_value = int((pd.Timestamp(max(timestamps), unit="ms", tz="UTC") + pd.offsets.MonthBegin(1)).timestamp() * 1000)
                else:
                    next_value = max(timestamps) + interval
                if next_value <= next_start:
                    break
                next_start = next_value
            else:
                oldest = min(timestamps)
                next_value = oldest - 1
                if next_end is not None and next_value >= next_end:
                    break
                next_end = next_value

        if not rows:
            return pd.DataFrame(columns=_OHLCV_COLUMNS)

        frame = pd.DataFrame(rows, columns=_OHLCV_COLUMNS)
        frame = (
            frame.drop_duplicates(subset=["timestamp"], keep="last")
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        return frame.head(total) if since_ms is not None else frame.tail(total)

