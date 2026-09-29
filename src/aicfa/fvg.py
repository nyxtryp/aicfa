"""Causal fair-value-gap / imbalance engine for AICFA.

An FVG is created only when the three-candle gap is knowable at the current
candle. Lifecycle fields are updated only with candles at or after creation;
no future candle is used to create or classify an earlier event.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    x = (
        df[required]
        .copy()
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )
    for column in required[1:]:
        x[column] = x[column].astype(float)

    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")
    if (x["volume"] < 0).any():
        raise ValueError("Invalid volume: negative values are not allowed")
    return x


def build_fvg(
    df: pd.DataFrame,
    *,
    min_gap_pct: float = 0.0,
    require_displacement: bool = False,
) -> pd.DataFrame:
    """Build causal bullish/bearish FVG and lifecycle features.

    Three-candle definition:
    - bullish FVG at t when low[t] > high[t-2];
    - bearish FVG at t when high[t] < low[t-2].

    The gap bounds are fixed at creation. Mitigation is the first later candle
    that trades into the gap. A fill occurs when price fully crosses the gap
    boundary. Invalidation is defined as a close through the opposite side.

    If require_displacement is enabled, the current candle must be a
    displacement candle from the causal displacement engine.
    """
    if min_gap_pct < 0:
        raise ValueError("min_gap_pct must be non-negative")

    x = _validate(df)
    out = x.copy()
    n = len(x)

    for column in [
        "fvg_bullish", "fvg_bearish", "fvg",
        "fvg_size", "fvg_size_pct",
        "fvg_displacement_bullish", "fvg_displacement_bearish",
        "fvg_mitigated", "fvg_filled", "fvg_invalidated",
        "fvg_active",
        "fvg_bullish_low", "fvg_bullish_high",
        "fvg_bearish_low", "fvg_bearish_high",
    ]:
        out[column] = 0 if column not in {
            "fvg_size", "fvg_size_pct",
            "fvg_bullish_low", "fvg_bullish_high",
            "fvg_bearish_low", "fvg_bearish_high",
        } else np.nan

    low = x["low"].to_numpy()
    high = x["high"].to_numpy()
    close = x["close"].to_numpy()

    displacement = None
    if require_displacement:
        from .displacement import build_displacement
        displacement = build_displacement(x)

    active_bullish = None
    active_bearish = None

    for i in range(n):
        # First update the existing lifecycle using the current candle.
        if active_bullish is not None:
            low_bound, high_bound = active_bullish
            if not out.at[i, "fvg_mitigated"] and low[i] <= high_bound:
                out.at[i, "fvg_mitigated"] = 1
            if low[i] <= low_bound:
                out.at[i, "fvg_filled"] = 1
                active_bullish = None
            elif close[i] < low_bound:
                out.at[i, "fvg_invalidated"] = 1
                active_bullish = None
            elif active_bullish is not None:
                out.at[i, "fvg_active"] = 1

        if active_bearish is not None:
            low_bound, high_bound = active_bearish
            if not out.at[i, "fvg_mitigated"] and high[i] >= low_bound:
                out.at[i, "fvg_mitigated"] = 1
            if high[i] >= high_bound:
                out.at[i, "fvg_filled"] = 1
                active_bearish = None
            elif close[i] > high_bound:
                out.at[i, "fvg_invalidated"] = 1
                active_bearish = None
            elif active_bearish is not None:
                out.at[i, "fvg_active"] = 1

        if i < 2:
            continue

        bullish = low[i] > high[i - 2] + EPS
        bearish = high[i] < low[i - 2] - EPS

        if bullish:
            gap_low = high[i - 2]
            gap_high = low[i]
            gap = gap_high - gap_low
            if gap / max(abs(close[i]), EPS) >= min_gap_pct:
                disp_ok = True if displacement is None else displacement.at[i, "displacement_up"] == 1
                if disp_ok:
                    out.at[i, "fvg_bullish"] = 1
                    out.at[i, "fvg"] = 1
                    out.at[i, "fvg_size"] = gap
                    out.at[i, "fvg_size_pct"] = gap / max(abs(close[i]), EPS)
                    out.at[i, "fvg_bullish_low"] = gap_low
                    out.at[i, "fvg_bullish_high"] = gap_high
                    out.at[i, "fvg_displacement_bullish"] = int(displacement is not None)
                    active_bullish = (gap_low, gap_high)
                    out.at[i, "fvg_active"] = 1

        if bearish:
            gap_low = high[i]
            gap_high = low[i - 2]
            gap = gap_high - gap_low
            if gap / max(abs(close[i]), EPS) >= min_gap_pct:
                disp_ok = True if displacement is None else displacement.at[i, "displacement_down"] == 1
                if disp_ok:
                    out.at[i, "fvg_bearish"] = 1
                    out.at[i, "fvg"] = 1
                    out.at[i, "fvg_size"] = gap
                    out.at[i, "fvg_size_pct"] = gap / max(abs(close[i]), EPS)
                    out.at[i, "fvg_bearish_low"] = gap_low
                    out.at[i, "fvg_bearish_high"] = gap_high
                    out.at[i, "fvg_displacement_bearish"] = int(displacement is not None)
                    active_bearish = (gap_low, gap_high)
                    out.at[i, "fvg_active"] = 1

    return out
