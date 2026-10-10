"""Generic CCXT public market-data adapter for AICFA.

Uses CCXT's unified public market-data interface so AICFA can add supported
venues without duplicating transport code for every exchange. Provider
selection remains outside this adapter.
"""
from __future__ import annotations

import time
from typing import Callable

import ccxt
import pandas as pd

from .market_data import MarketDataProvider, validate_ohlcv

_OHLCV_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
_TRADE_COLUMNS = ("timestamp", "price", "volume", "side")
_BOOK_COLUMNS = ("timestamp", "bid_price", "bid_size", "ask_price", "ask_size")


_LOT_MULTIPLIER_PREFIXES = ("1000000", "100000", "10000", "1000", "1M")
_BASE_SYMBOL_ALIASES = {
    # Common exchange ticker differences after asset migrations/rebrands.
    "BTC": ("XBT",),
    "POL": ("MATIC",),
    "RENDER": ("RNDR",),
}


def _is_lot_multiplier_alias(market_base: str, canonical_base: str) -> bool:
    """Return whether a futures contract represents a scaled token lot."""
    return any(
        market_base.startswith(prefix) and market_base[len(prefix):] == canonical_base
        for prefix in _LOT_MULTIPLIER_PREFIXES
    )


class CcxtMarketDataProvider:
    """Public CCXT adapter for a single exchange venue."""

    def __init__(
        self,
        exchange_id: str,
        *,
        timeout_seconds: float = 10.0,
        exchange_factory: Callable[[str], object] | None = None,
    ) -> None:
        exchange_id = exchange_id.strip().lower()
        if not exchange_id:
            raise ValueError("exchange_id must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        factory = exchange_factory or self._default_factory
        self.exchange = exchange_id
        self.timeout_seconds = float(timeout_seconds)
        self._exchange = factory(exchange_id)
        self._exchange.timeout = int(self.timeout_seconds * 1000)
        self._markets_loaded = False

    @staticmethod
    def _default_factory(exchange_id: str) -> object:
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"unsupported CCXT exchange: {exchange_id}")
        return exchange_class({"enableRateLimit": True})

    @staticmethod
    def _validate_market_type(market_type: str) -> str:
        if market_type not in {"spot", "futures"}:
            raise ValueError("market_type must be spot or futures")
        return market_type

    def _load_markets(self) -> dict:
        if not self._markets_loaded:
            markets = self._exchange.load_markets()
            if not isinstance(markets, dict):
                raise ValueError("CCXT load_markets() must return a mapping")
            self._markets_loaded = True
        return self._exchange.markets

    def _market_candidates(self, asset: str, market_type: str) -> list[dict]:
        self._validate_market_type(market_type)
        normalized = asset.strip().upper().replace("/", "").replace("-", "").replace("_", "")
        if not normalized:
            raise ValueError("asset must not be empty")
        quote = "USDT"
        markets = self._load_markets()
        candidates = []
        for market in markets.values():
            symbol = str(market.get("symbol", "")).upper()
            base = str(market.get("base", "")).upper()
            quote_name = str(market.get("quote", "")).upper()
            raw_id = str(market.get("id", "")).upper().replace("/", "").replace("-", "").replace("_", "")
            if base + quote_name != normalized and raw_id != normalized and symbol.replace("/", "") != normalized:
                continue
            if market_type == "spot":
                if market.get("spot") is True:
                    candidates.append(market)
            else:
                if market.get("contract") and (
                    market.get("swap") or market.get("future")
                ) and quote_name == quote:
                    candidates.append(market)
        return candidates

    def resolve_symbol(
        self,
        asset: str,
        *,
        quote_asset: str = "USDT",
        market_type: str = "spot",
    ) -> str:
        self._validate_market_type(market_type)
        raw_asset = asset.strip().upper().replace("-", "/").replace("_", "/")
        if "/" in raw_asset:
            base_asset, asset_quote = (part.strip() for part in raw_asset.split("/", 1))
            quote = asset_quote or quote_asset.strip().upper()
        else:
            quote = quote_asset.strip().upper()
            base_asset = raw_asset.removesuffix(quote)
        if not base_asset or not quote:
            raise ValueError("asset must contain a base and quote")
        markets = self._load_markets()
        candidates = []
        for market in markets.values():
            market_quote = str(market.get("quote", "")).upper()
            market_base = str(market.get("base", "")).upper()
            if market_quote != quote:
                continue
            if market_type == "spot":
                eligible = market.get("spot") is True
            else:
                eligible = bool(market.get("contract")) and bool(
                    market.get("swap") or market.get("future")
                )
            if not eligible:
                continue
            # Some futures venues list meme coins in lots of 1,000/10,000/
            # 1,000,000 tokens (e.g. 1000PEPE/USDT:USDT). AICFA keeps the
            # canonical asset name, but must resolve it to the venue's actual
            # contract symbol. Exact base matches always win over multipliers.
            if market_base == base_asset:
                candidates.append((0, market))
            elif market_base in _BASE_SYMBOL_ALIASES.get(base_asset, ()):
                candidates.append((1, market))
            elif market_type == "futures" and _is_lot_multiplier_alias(market_base, base_asset):
                candidates.append((2, market))
        if not candidates:
            normalized = f"{base_asset}{quote}"
            raise ValueError(
                f"no {self.exchange} {market_type} market found for asset: {normalized}"
            )
        candidates.sort(key=lambda item: item[0])
        return str(candidates[0][1]["symbol"])

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        market_type: str,
        timeframe: str,
        since_ms: int | None,
        limit: int,
    ) -> pd.DataFrame:
        self._validate_market_type(market_type)
        if limit <= 0:
            raise ValueError("limit must be positive")
        rows = self._exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            since=since_ms,
            limit=int(limit),
        )
        frame = pd.DataFrame(rows, columns=_OHLCV_COLUMNS)
        if frame.empty:
            raise ValueError(f"{self.exchange} returned no OHLCV rows")
        return validate_ohlcv(frame)

    def fetch_trades(
        self, *, symbol: str, market_type: str, limit: int
    ) -> pd.DataFrame:
        self._validate_market_type(market_type)
        if limit <= 0:
            raise ValueError("limit must be positive")
        rows = self._exchange.fetch_trades(symbol, limit=int(limit))
        normalized = []
        side_map = {"buy": 1, "sell": -1}
        for row in rows:
            raw_side = row.get("side")
            if isinstance(raw_side, str):
                side = side_map.get(raw_side.strip().lower())
            else:
                try:
                    side = float(raw_side) if raw_side is not None else None
                except (TypeError, ValueError):
                    side = None
            normalized.append([
                row.get("timestamp"),
                row.get("price"),
                row.get("amount"),
                side,
            ])
        frame = pd.DataFrame(normalized, columns=_TRADE_COLUMNS)
        if frame.empty:
            raise ValueError(f"{self.exchange} returned no trades")
        return frame

    def fetch_order_book(
        self, *, symbol: str, market_type: str, limit: int
    ) -> pd.DataFrame:
        self._validate_market_type(market_type)
        if limit <= 0:
            raise ValueError("limit must be positive")
        book = self._exchange.fetch_order_book(symbol, limit=int(limit))
        bids = book.get("bids") or []
        asks = book.get("asks") or []
        if not bids or not asks:
            raise ValueError(f"{self.exchange} returned an incomplete order book")
        timestamp = book.get("timestamp") or int(time.time() * 1000)
        return pd.DataFrame(
            [[timestamp, bids[0][0], bids[0][1], asks[0][0], asks[0][1]]],
            columns=_BOOK_COLUMNS,
        )

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
        rows = []
        for index in range(int(snapshots)):
            frame = self.fetch_order_book(symbol=symbol, market_type=market_type, limit=1)
            rows.append(frame.iloc[0].to_dict())
            if index + 1 < int(snapshots) and interval_seconds:
                time.sleep(float(interval_seconds))
        return pd.DataFrame(rows, columns=_BOOK_COLUMNS)
