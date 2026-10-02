"""Provider-agnostic market-data contracts and causal OHLCV utilities.

The live scanner consumes completed candles only. Provider adapters are kept
outside this module so the analytical core does not depend on a specific
exchange or API.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import pandas as pd


BASE_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M")
_REQUIRED_OHLCV = ("timestamp", "open", "high", "low", "close", "volume")


def timeframe_ms(timeframe: str) -> int:
    """Return the fixed candle duration in milliseconds."""
    durations = {
        "1m": 60_000,
        "5m": 5 * 60_000,
        "15m": 15 * 60_000,
        "1h": 60 * 60_000,
        "4h": 4 * 60 * 60_000,
        "1d": 24 * 60 * 60_000,
        "1w": 7 * 24 * 60 * 60_000,
    }
    if timeframe not in durations:
        raise ValueError(f"Unsupported fixed timeframe: {timeframe}")
    return durations[timeframe]


@dataclass(frozen=True)
class MarketKey:
    exchange: str
    symbol: str
    market_type: str
    timeframe: str

    def __post_init__(self) -> None:
        if not self.exchange.strip():
            raise ValueError("exchange must not be empty")
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        if self.market_type not in {"spot", "futures"}:
            raise ValueError("market_type must be 'spot' or 'futures'")
        if self.timeframe not in BASE_TIMEFRAMES:
            raise ValueError(f"Unsupported timeframe: {self.timeframe}")


class MarketDataProvider(Protocol):
    """Minimal provider contract required by the centralized scanner."""

    def fetch_ohlcv(
        self,
        *,
        symbol: str,
        market_type: str,
        timeframe: str,
        since_ms: int | None,
        limit: int,
    ) -> pd.DataFrame:
        """Return OHLCV rows with provider-native candle-open timestamps."""

    def fetch_trades(
        self,
        *,
        symbol: str,
        market_type: str,
        limit: int,
    ) -> pd.DataFrame:
        """Return recent public trades with venue-provided aggressor side."""

    def fetch_order_book(
        self,
        *,
        symbol: str,
        market_type: str,
        limit: int,
    ) -> pd.DataFrame:
        """Return timestamped order-book snapshots normalized to L1."""

    def fetch_order_book_history(
        self,
        *,
        symbol: str,
        market_type: str,
        snapshots: int,
        interval_seconds: float,
    ) -> pd.DataFrame:
        """Collect a causal sequence of real-time L1 observations."""


def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize and validate an OHLCV frame without inventing missing data."""
    missing = [column for column in _REQUIRED_OHLCV if column not in df.columns]
    if missing:
        raise ValueError(f"Missing OHLCV columns: {missing}")

    out = df[list(_REQUIRED_OHLCV)].copy()
    out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce")
    numeric = ["open", "high", "low", "close", "volume"]
    for column in numeric:
        out[column] = pd.to_numeric(out[column], errors="coerce")

    if out["timestamp"].isna().any():
        raise ValueError("OHLCV timestamp contains invalid values")
    if out[numeric].isna().any().any():
        raise ValueError("OHLCV numeric fields contain invalid values")

    out["timestamp"] = out["timestamp"].astype("int64")
    if (out["timestamp"] < 0).any():
        raise ValueError("OHLCV timestamp must be non-negative")
    if (out[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (out["volume"] < 0).any():
        raise ValueError("OHLCV volume must be non-negative")
    if (out["high"] < out[["open", "close"]].max(axis=1)).any():
        raise ValueError("OHLC high is below open/close")
    if (out["low"] > out[["open", "close"]].min(axis=1)).any():
        raise ValueError("OHLC low is above open/close")

    return (
        out.drop_duplicates("timestamp", keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def completed_ohlcv(
    df: pd.DataFrame,
    *,
    timeframe: str,
    now_ms: int,
) -> pd.DataFrame:
    """Keep only candles whose full interval ended at or before now_ms."""
    out = validate_ohlcv(df)
    if timeframe == "1M":
        opened = pd.to_datetime(out["timestamp"], unit="ms", utc=True)
        closes = opened + pd.offsets.MonthBegin(1)
        completed = out.loc[closes.astype("int64") // 1_000_000 <= int(now_ms)]
        return completed.reset_index(drop=True)
    duration = timeframe_ms(timeframe)
    return out.loc[out["timestamp"] + duration <= int(now_ms)].reset_index(drop=True)


def merge_ohlcv(
    existing: pd.DataFrame | None,
    incoming: pd.DataFrame,
) -> pd.DataFrame:
    """Merge provider data idempotently, preserving the newest row per timestamp."""
    incoming_clean = validate_ohlcv(incoming)
    if existing is None or existing.empty:
        return incoming_clean

    existing_clean = validate_ohlcv(existing)
    return validate_ohlcv(pd.concat([existing_clean, incoming_clean], ignore_index=True))


def next_since_ms(
    existing: pd.DataFrame | None,
    *,
    timeframe: str,
) -> int | None:
    """Return the next candle-open timestamp needed after local history."""
    if existing is None or existing.empty:
        return None
    if timeframe == "1M":
        last = pd.to_datetime(int(existing["timestamp"].max()), unit="ms", utc=True)
        return int((last + pd.offsets.MonthBegin(1)).timestamp() * 1000)
    return int(existing["timestamp"].max()) + timeframe_ms(timeframe)
