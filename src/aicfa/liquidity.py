"""Causal liquidity engine for AICFA.

Liquidity pools are inferred only from information known at the current row.
Confirmed swing highs/lows provide previous-level context; equal confirmed
swings form persistent internal/external liquidity pools. Pool lifecycle is
explicit: active -> swept or broken. A sweep requires a wick through the
known level followed by a close back across it; a breakout closes beyond the
level and invalidates the pool.
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


def _confirmed_swings(highs: np.ndarray, lows: np.ndarray, left: int, right: int):
    confirmed_highs = []
    confirmed_lows = []
    for confirmation in range(left + right, len(highs)):
        pivot = confirmation - right
        high_window = highs[pivot - left : pivot + right + 1]
        low_window = lows[pivot - left : pivot + right + 1]
        is_high = highs[pivot] >= np.max(high_window) and np.count_nonzero(high_window == highs[pivot]) == 1
        is_low = lows[pivot] <= np.min(low_window) and np.count_nonzero(low_window == lows[pivot]) == 1
        if is_high:
            confirmed_highs.append((confirmation, float(highs[pivot])))
        if is_low:
            confirmed_lows.append((confirmation, float(lows[pivot])))
    return confirmed_highs, confirmed_lows


def build_liquidity(
    df: pd.DataFrame,
    *,
    swing_left: int = 2,
    swing_right: int = 2,
    equal_tolerance: float = 0.001,
    internal_left: int = 1,
    internal_right: int = 1,
) -> pd.DataFrame:
    """Build causal liquidity pools, previous levels, and lifecycle events."""
    if swing_left < 1 or swing_right < 1 or internal_left < 1 or internal_right < 1:
        raise ValueError("all swing sensitivities must be positive")
    if equal_tolerance < 0:
        raise ValueError("equal_tolerance must be non-negative")

    x = _validate(df)
    n = len(x)
    out = x.copy()
    highs = x["high"].to_numpy()
    lows = x["low"].to_numpy()
    closes = x["close"].to_numpy()

    binary = [
        "equal_high", "equal_low", "buy_side_liquidity", "sell_side_liquidity",
        "sweep_high", "sweep_low", "sweep_high_reclaim", "sweep_low_reclaim",
        "liquidity_breakout_high", "liquidity_breakout_low",
        "liquidity_pool_created_high", "liquidity_pool_created_low",
        "liquidity_pool_swept_high", "liquidity_pool_swept_low",
        "liquidity_pool_invalidated_high", "liquidity_pool_invalidated_low",
        "liquidity_pool_reaction_high", "liquidity_pool_reaction_low",
    ]
    for column in binary:
        out[column] = 0

    numeric = [
        "buy_side_liquidity_price", "sell_side_liquidity_price",
        "sweep_high_level", "sweep_low_level",
        "previous_high", "previous_low",
        "internal_previous_high", "internal_previous_low",
        "active_buy_liquidity_price", "active_sell_liquidity_price",
        "last_swept_buy_liquidity_price", "last_swept_sell_liquidity_price",
    ]
    for column in numeric:
        out[column] = np.nan

    counts = [
        "active_buy_liquidity_pools", "active_sell_liquidity_pools",
        "active_external_buy_pools", "active_external_sell_pools",
        "active_internal_buy_pools", "active_internal_sell_pools",
    ]
    for column in counts:
        out[column] = 0

    flags = [
        "external_buy_side_liquidity", "external_sell_side_liquidity",
        "internal_buy_side_liquidity", "internal_sell_side_liquidity",
    ]
    for column in flags:
        out[column] = 0

    ext_highs, ext_lows = _confirmed_swings(highs, lows, swing_left, swing_right)
    int_highs, int_lows = _confirmed_swings(highs, lows, internal_left, internal_right)
    ext_high_by_row = {i: p for i, p in ext_highs}
    ext_low_by_row = {i: p for i, p in ext_lows}
    int_high_by_row = {i: p for i, p in int_highs}
    int_low_by_row = {i: p for i, p in int_lows}

    pools = []
    swept_pool_reaction_candidates = []
    last_ext_high = last_ext_low = None
    last_int_high = last_int_low = None
    prev_ext_high = prev_ext_low = None
    prev_int_high = prev_int_low = None

    def add_pool(side, level, external, row):
        pools.append({
            "side": side, "level": float(level), "external": bool(external),
            "created": row, "state": "active",
        })
        out.at[row, "liquidity_pool_created_high" if side == "buy" else "liquidity_pool_created_low"] = 1
        out.at[row, "equal_high" if side == "buy" else "equal_low"] = 1
        out.at[row, "buy_side_liquidity" if side == "buy" else "sell_side_liquidity"] = 1
        out.at[row, "buy_side_liquidity_price" if side == "buy" else "sell_side_liquidity_price"] = level
        out.at[row, "external_buy_side_liquidity" if side == "buy" else "external_sell_side_liquidity"] = int(external)
        out.at[row, "internal_buy_side_liquidity" if side == "buy" else "internal_sell_side_liquidity"] = int(not external)

    def maybe_pool(row, side, price, previous_price, external):
        if previous_price is not None and abs(price - previous_price) <= max(abs(previous_price) * equal_tolerance, 1e-12):
            add_pool(row=row, side=side, level=(price + previous_price) / 2.0, external=external)

    for row in range(n):
        for candidate in swept_pool_reaction_candidates:
            if candidate["state"] != "pending" or candidate["row"] >= row:
                continue
            level = candidate["level"]
            if candidate["side"] == "buy" and closes[row] < level:
                out.at[row, "liquidity_pool_reaction_high"] = 1
                candidate["state"] = "reacted"
            elif candidate["side"] == "sell" and closes[row] > level:
                out.at[row, "liquidity_pool_reaction_low"] = 1
                candidate["state"] = "reacted"

        for pool in pools
            if pool["state"] != "active" or pool["created"] >= row:
                continue
            side = pool["side"]
            level = float(pool["level"])
            if side == "buy" and highs[row] > level:
                if closes[row] < level:
                    pool["state"] = "swept"
                    out.at[row, "sweep_high"] = 1
                    out.at[row, "sweep_high_reclaim"] = 1
                    out.at[row, "sweep_high_level"] = level
                    out.at[row, "liquidity_pool_swept_high"] = 1
                    out.at[row, "last_swept_buy_liquidity_price"] = level
                    swept_pool_reaction_candidates.append({"side": "buy", "level": level, "row": row, "state": "pending"})
                elif closes[row] > level:
                    pool["state"] = "broken"
                    out.at[row, "sweep_high_level"] = level
                    out.at[row, "liquidity_breakout_high"] = 1
                    out.at[row, "liquidity_pool_invalidated_high"] = 1
            elif side == "sell" and lows[row] < level:
                if closes[row] >= level:
                    pool["state"] = "swept"
                    out.at[row, "sweep_low"] = 1
                    out.at[row, "sweep_low_reclaim"] = 1
                    out.at[row, "sweep_low_level"] = level
                    out.at[row, "liquidity_pool_swept_low"] = 1
                    out.at[row, "last_swept_sell_liquidity_price"] = level
                    swept_pool_reaction_candidates.append({"side": "sell", "level": level, "row": row, "state": "pending"})
                elif closes[row] < level:
                    pool["state"] = "broken"
                    out.at[row, "sweep_low_level"] = level
                    out.at[row, "liquidity_breakout_low"] = 1
                    out.at[row, "liquidity_pool_invalidated_low"] = 1

        if row in ext_high_by_row:
            price = ext_high_by_row[row]
            prev_ext_high, last_ext_high = last_ext_high, price
            out.at[row, "previous_high"] = price
            maybe_pool(row, "buy", price, prev_ext_high, True)
        elif last_ext_high is not None:
            out.at[row, "previous_high"] = last_ext_high

        if row in ext_low_by_row:
            price = ext_low_by_row[row]
            prev_ext_low, last_ext_low = last_ext_low, price
            out.at[row, "previous_low"] = price
            maybe_pool(row, "sell", price, prev_ext_low, True)
        elif last_ext_low is not None:
            out.at[row, "previous_low"] = last_ext_low

        if row in int_high_by_row:
            price = int_high_by_row[row]
            prev_int_high, last_int_high = last_int_high, price
            out.at[row, "internal_previous_high"] = price
            maybe_pool(row, "buy", price, prev_int_high, False)
        elif last_int_high is not None:
            out.at[row, "internal_previous_high"] = last_int_high

        if row in int_low_by_row:
            price = int_low_by_row[row]
            prev_int_low, last_int_low = last_int_low, price
            out.at[row, "internal_previous_low"] = price
            maybe_pool(row, "sell", price, prev_int_low, False)
        elif last_int_low is not None:
            out.at[row, "internal_previous_low"] = last_int_low

        active = [p for p in pools if p["state"] == "active"]
        active_buy = [p for p in active if p["side"] == "buy"]
        active_sell = [p for p in active if p["side"] == "sell"]
        active_ext_buy = [p for p in active_buy if p["external"]]
        active_ext_sell = [p for p in active_sell if p["external"]]
        active_int_buy = [p for p in active_buy if not p["external"]]
        active_int_sell = [p for p in active_sell if not p["external"]]
        out.at[row, "active_buy_liquidity_pools"] = len(active_buy)
        out.at[row, "active_sell_liquidity_pools"] = len(active_sell)
        out.at[row, "active_external_buy_pools"] = len(active_ext_buy)
        out.at[row, "active_external_sell_pools"] = len(active_ext_sell)
        out.at[row, "active_internal_buy_pools"] = len(active_int_buy)
        out.at[row, "active_internal_sell_pools"] = len(active_int_sell)
        if active_buy:
            out.at[row, "active_buy_liquidity_price"] = float(active_buy[-1]["level"])
        if active_sell:
            out.at[row, "active_sell_liquidity_price"] = float(active_sell[-1]["level"])

    return out
