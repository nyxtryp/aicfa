"""Causal liquidity engine for AICFA.

Liquidity pools are inferred only from information known at the current row.
Swing-derived pools become visible when the corresponding swing is confirmed;
a sweep is recorded when the current candle trades through a known pool and
closes back across it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    x = df[required].copy().sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for column in required[1:]:
        x[column] = x[column].astype(float)
    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")
    return x


def build_liquidity(
    df: pd.DataFrame,
    *,
    swing_left: int = 2,
    swing_right: int = 2,
    equal_tolerance: float = 0.001,
) -> pd.DataFrame:
    """Build causal liquidity pools and sweep/reclaim events.

    Equal highs form buy-side liquidity; equal lows form sell-side liquidity.
    A pool is emitted only after both component swings are confirmed.
    """
    if swing_left < 1 or swing_right < 1:
        raise ValueError("swing_left and swing_right must be positive")
    if equal_tolerance < 0:
        raise ValueError("equal_tolerance must be non-negative")

    x = _validate(df)
    n = len(x)
    out = x.copy()

    binary = [
        "equal_high",
        "equal_low",
        "buy_side_liquidity",
        "sell_side_liquidity",
        "sweep_high",
        "sweep_low",
        "sweep_high_reclaim",
        "sweep_low_reclaim",
    ]
    for column in binary:
        out[column] = 0

    for column in [
        "buy_side_liquidity_price",
        "sell_side_liquidity_price",
        "sweep_high_level",
        "sweep_low_level",
    ]:
        out[column] = np.nan

    highs = x["high"].to_numpy()
    lows = x["low"].to_numpy()
    closes = x["close"].to_numpy()

    # Confirmed swing candidates: pivot becomes knowable only at pivot + right.
    confirmed_highs: list[tuple[int, float]] = []
    confirmed_lows: list[tuple[int, float]] = []
    active_buy_level: float | None = None
    active_sell_level: float | None = None
    swept_buy_level: float | None = None
    swept_sell_level: float | None = None

    for confirmation in range(swing_left + swing_right, n):
        pivot = confirmation - swing_right

        high_window = highs[pivot - swing_left : pivot + swing_right + 1]
        low_window = lows[pivot - swing_left : pivot + swing_right + 1]
        is_high = highs[pivot] >= np.max(high_window) and np.count_nonzero(high_window == highs[pivot]) == 1
        is_low = lows[pivot] <= np.min(low_window) and np.count_nonzero(low_window == lows[pivot]) == 1

        if is_high:
            price = highs[pivot]
            confirmed_highs.append((confirmation, price))
            if len(confirmed_highs) >= 2:
                previous = confirmed_highs[-2][1]
                if abs(price - previous) <= max(abs(previous) * equal_tolerance, 1e-12):
                    level = (price + previous) / 2.0
                    active_buy_level = level
                    swept_buy_level = None
                    out.at[confirmation, "equal_high"] = 1
                    out.at[confirmation, "buy_side_liquidity"] = 1
                    out.at[confirmation, "buy_side_liquidity_price"] = level

        if is_low:
            price = lows[pivot]
            confirmed_lows.append((confirmation, price))
            if len(confirmed_lows) >= 2:
                previous = confirmed_lows[-2][1]
                if abs(price - previous) <= max(abs(previous) * equal_tolerance, 1e-12):
                    level = (price + previous) / 2.0
                    active_sell_level = level
                    swept_sell_level = None
                    out.at[confirmation, "equal_low"] = 1
                    out.at[confirmation, "sell_side_liquidity"] = 1
                    out.at[confirmation, "sell_side_liquidity_price"] = level

        # Sweep/reclaim is evaluated against pools known before this candle.
        if active_buy_level is not None and swept_buy_level != active_buy_level:
            if highs[confirmation] > active_buy_level:
                out.at[confirmation, "sweep_high"] = 1
                out.at[confirmation, "sweep_high_level"] = active_buy_level
                if closes[confirmation] < active_buy_level:
                    out.at[confirmation, "sweep_high_reclaim"] = 1
                    swept_buy_level = active_buy_level

        if active_sell_level is not None and swept_sell_level != active_sell_level:
            if lows[confirmation] < active_sell_level:
                out.at[confirmation, "sweep_low"] = 1
                out.at[confirmation, "sweep_low_level"] = active_sell_level
                if closes[confirmation] > active_sell_level:
                    out.at[confirmation, "sweep_low_reclaim"] = 1
                    swept_sell_level = active_sell_level

    return out
