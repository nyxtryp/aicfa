"""Causal market-structure engine for AICFA.

Swing points are confirmed only after right subsequent candles. Therefore
all emitted structure events are timestamped at the first row where the
information is knowable; no future candle is written backward into features.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing: raise ValueError(f"Missing required columns: {missing}")
    x = df[required].copy().sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for column in required[1:]: x[column] = x[column].astype(float)
    if (x["high"] < x[["open", "close"]].max(axis=1)).any(): raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any(): raise ValueError("Invalid OHLC: low is above open/close")
    return x

def build_structure(df: pd.DataFrame, *, left: int = 2, right: int = 2, equal_tolerance: float = 0.0) -> pd.DataFrame:
    """Build causal swing structure and break events."""
    if left < 1 or right < 1: raise ValueError("left and right must be positive")
    if equal_tolerance < 0: raise ValueError("equal_tolerance must be non-negative")
    x = _validate(df); n = len(x); out = x.copy()
    binary = ["swing_high","swing_low","hh","hl","lh","ll","bos_up","bos_down","choch_up","choch_down","mss_up","mss_down"]
    for column in binary: out[column] = 0
    out["swing_high_price"] = np.nan; out["swing_low_price"] = np.nan; out["structure_direction"] = 0
    highs, lows, closes = x["high"].to_numpy(), x["low"].to_numpy(), x["close"].to_numpy()
    last_high = last_low = None; direction = 0; broken_high = broken_low = None
    for confirmation in range(left + right, n):
        pivot = confirmation - right
        high_window = highs[pivot-left:pivot+right+1]; low_window = lows[pivot-left:pivot+right+1]
        is_high = highs[pivot] >= np.max(high_window) and np.count_nonzero(high_window == highs[pivot]) == 1
        is_low = lows[pivot] <= np.min(low_window) and np.count_nonzero(low_window == lows[pivot]) == 1
        if is_high:
            out.at[confirmation, "swing_high"] = 1; out.at[confirmation, "swing_high_price"] = highs[pivot]
            if last_high is not None:
                if highs[pivot] > last_high * (1 + equal_tolerance): out.at[confirmation, "hh"] = 1
                elif highs[pivot] < last_high * (1 - equal_tolerance): out.at[confirmation, "lh"] = 1
            last_high = highs[pivot]
        if is_low:
            out.at[confirmation, "swing_low"] = 1; out.at[confirmation, "swing_low_price"] = lows[pivot]
            if last_low is not None:
                if lows[pivot] > last_low * (1 + equal_tolerance): out.at[confirmation, "hl"] = 1
                elif lows[pivot] < last_low * (1 - equal_tolerance): out.at[confirmation, "ll"] = 1
            last_low = lows[pivot]
        if last_high is not None and closes[confirmation] > last_high * (1 + equal_tolerance) and broken_high != last_high:
            out.at[confirmation, "bos_up"] = 1
            if direction < 0: out.at[confirmation, "choch_up"] = 1
            direction = 1; broken_high = last_high
        if last_low is not None and closes[confirmation] < last_low * (1 - equal_tolerance) and broken_low != last_low:
            out.at[confirmation, "bos_down"] = 1
            if direction > 0: out.at[confirmation, "choch_down"] = 1
            direction = -1; broken_low = last_low
        out.at[confirmation, "structure_direction"] = direction
    return out
