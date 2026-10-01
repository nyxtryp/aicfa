"""Deterministic, causal Order Flow / Microstructure primitives.

This module only transforms already-observed trade and top-of-book data. It does
not fetch market data and it does not emit LONG/SHORT decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class TradeFlow:
    buy_volume: float
    sell_volume: float
    signed_volume: float
    imbalance: float
    buy_count: int
    sell_count: int

@dataclass(frozen=True)
class BookState:
    bid_price: float
    ask_price: float
    bid_size: float
    ask_size: float
    spread: float
    spread_bps: float
    imbalance: float

def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"missing microstructure columns: {missing}")

def _validate_timestamps(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    out = frame.copy()
    out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce")
    if out["timestamp"].isna().any():
        raise ValueError("timestamp contains invalid values")
    if (out["timestamp"].diff().dropna() < 0).any():
        raise ValueError("microstructure data must be sorted causally by timestamp")
    return out

def _safe_ratio(numerator: float, denominator: float) -> float:
    return 0.0 if denominator == 0 else numerator / denominator

def compute_trade_flow(trades: pd.DataFrame) -> TradeFlow:
    """Aggregate signed trade flow from venue-provided aggressor side."""
    _require_columns(trades, ("timestamp", "price", "volume", "side"))
    frame = _validate_timestamps(trades)
    if frame.empty:
        return TradeFlow(0.0, 0.0, 0.0, 0.0, 0, 0)
    numeric = frame[["price", "volume", "side"]].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        raise ValueError("trade price, volume, and side must be numeric")
    if (numeric["price"] <= 0).any():
        raise ValueError("trade price must be positive")
    if (numeric["volume"] < 0).any():
        raise ValueError("trade volume must be non-negative")
    if not numeric["side"].isin((-1, 1)).all():
        raise ValueError("trade side must be -1 or +1")
    buy = float(numeric.loc[numeric["side"] == 1, "volume"].sum())
    sell = float(numeric.loc[numeric["side"] == -1, "volume"].sum())
    return TradeFlow(buy, sell, buy - sell, _safe_ratio(buy - sell, buy + sell),
                     int((numeric["side"] == 1).sum()), int((numeric["side"] == -1).sum()))

def compute_book_state(book: pd.DataFrame) -> BookState:
    """Read the latest causally available L1 quote and derive book pressure."""
    _require_columns(book, ("timestamp", "bid_price", "bid_size", "ask_price", "ask_size"))
    frame = _validate_timestamps(book)
    if frame.empty:
        raise ValueError("book must not be empty")
    row = frame.iloc[-1]
    values = {key: float(pd.to_numeric(row[key], errors="coerce"))
              for key in ("bid_price", "bid_size", "ask_price", "ask_size")}
    if any(pd.isna(value) for value in values.values()):
        raise ValueError("book numeric fields must be valid")
    if values["bid_price"] <= 0 or values["ask_price"] <= 0:
        raise ValueError("book prices must be positive")
    if values["bid_size"] < 0 or values["ask_size"] < 0:
        raise ValueError("book sizes must be non-negative")
    if values["ask_price"] < values["bid_price"]:
        raise ValueError("ask price must not be below bid price")
    spread = values["ask_price"] - values["bid_price"]
    mid = (values["ask_price"] + values["bid_price"]) / 2.0
    return BookState(values["bid_price"], values["ask_price"], values["bid_size"],
                     values["ask_size"], spread, _safe_ratio(spread, mid) * 10_000,
                     _safe_ratio(values["bid_size"] - values["ask_size"],
                                 values["bid_size"] + values["ask_size"]))
