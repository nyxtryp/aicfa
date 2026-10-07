"""Causal fair-value-gap / imbalance engine for AICFA.

An FVG is created only when the three-candle gap is knowable at the current
candle. Lifecycle fields are updated only with candles at or after creation;
no future candle is used to create or classify an earlier event.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12

FVG_UNTOUCHED = "UNTOUCHED"
FVG_TOUCHED = "TOUCHED"
FVG_PARTIAL = "PARTIAL"
FVG_FILLED = "FILLED"
FVG_INVALIDATED = "INVALIDATED"

_LIFECYCLE_RANK = {
    FVG_UNTOUCHED: 0,
    FVG_TOUCHED: 1,
    FVG_PARTIAL: 2,
    FVG_FILLED: 3,
    FVG_INVALIDATED: 4,
}


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


def _lifecycle_state(*, low, high, gap_low, gap_high, bullish):
    width = max(gap_high - gap_low, EPS)
    if bullish:
        penetration = float(np.clip((gap_high - low) / width, 0.0, 1.0))
        touched = low <= gap_high
    else:
        penetration = float(np.clip((high - gap_low) / width, 0.0, 1.0))
        touched = high >= gap_low

    if penetration >= 1.0 - EPS:
        return FVG_FILLED, penetration
    if penetration > EPS:
        return FVG_PARTIAL, penetration
    if touched:
        return FVG_TOUCHED, 0.0
    return FVG_UNTOUCHED, 0.0


def _aggregate_active_state(zones):
    if not zones:
        return FVG_UNTOUCHED, 0.0
    zone = max(
        zones,
        key=lambda item: (
            _LIFECYCLE_RANK[item["state"]],
            item["penetration"],
            item["creation_index"],
        ),
    )
    return zone["state"], zone["penetration"]


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

    Gap bounds are fixed at creation. Every active zone is tracked separately,
    so a new FVG cannot erase an older still-active FVG.
    """
    if min_gap_pct < 0:
        raise ValueError("min_gap_pct must be non-negative")

    x = _validate(df)
    out = x.copy()
    n = len(x)

    for column in [
        "fvg_bullish", "fvg_bearish", "fvg", "fvg_mitigated", "fvg_filled",
        "fvg_invalidated", "fvg_active", "fvg_displacement_bullish",
        "fvg_displacement_bearish", "fvg_active_bullish_count",
        "fvg_active_bearish_count",
    ]:
        out[column] = 0
    for column in [
        "fvg_size", "fvg_size_pct", "fvg_bullish_low", "fvg_bullish_high",
        "fvg_bearish_low", "fvg_bearish_high", "fvg_bullish_penetration",
        "fvg_bearish_penetration", "fvg_bullish_creation_index",
        "fvg_bearish_creation_index", "fvg_bullish_creation_timestamp",
        "fvg_bearish_creation_timestamp",
    ]:
        out[column] = np.nan
    out["fvg_bullish_state"] = FVG_UNTOUCHED
    out["fvg_bearish_state"] = FVG_UNTOUCHED

    low = x["low"].to_numpy()
    high = x["high"].to_numpy()
    close = x["close"].to_numpy()
    timestamps = x["timestamp"].to_numpy()

    displacement = None
    if require_displacement:
        from .displacement import build_displacement
        displacement = build_displacement(x)

    bullish_zones = []
    bearish_zones = []

    for i in range(n):
        for zones, bullish in ((bullish_zones, True), (bearish_zones, False)):
            for zone in list(zones):
                state, penetration = _lifecycle_state(
                    low=low[i], high=high[i],
                    gap_low=zone["low"], gap_high=zone["high"],
                    bullish=bullish,
                )
                if bullish and close[i] < zone["low"] and low[i] < zone["low"]:
                    state = FVG_INVALIDATED
                elif not bullish and close[i] > zone["high"] and high[i] > zone["high"]:
                    state = FVG_INVALIDATED

                zone["state"] = state
                zone["penetration"] = penetration

                if state in {FVG_TOUCHED, FVG_PARTIAL, FVG_FILLED}:
                    out.at[i, "fvg_mitigated"] = 1
                if state == FVG_FILLED:
                    out.at[i, "fvg_filled"] = 1
                    zones.remove(zone)
                elif state == FVG_INVALIDATED:
                    out.at[i, "fvg_invalidated"] = 1
                    zones.remove(zone)

        # The zone remains an active SMC context after creation until its
        # lifecycle is filled or invalidated. Previously fvg_active was only
        # marked on the creation candle, so a later valid retest could not
        # be surfaced as active evidence.
        if bullish_zones or bearish_zones:
            out.at[i, "fvg_active"] = 1

        if i >= 2:
            bullish = low[i] > high[i - 2] + EPS
            bearish = high[i] < low[i - 2] - EPS

            if bullish:
                gap_low, gap_high = high[i - 2], low[i]
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
                        out.at[i, "fvg_bullish_creation_index"] = i
                        out.at[i, "fvg_bullish_creation_timestamp"] = timestamps[i]
                        out.at[i, "fvg_displacement_bullish"] = int(displacement is not None)
                        bullish_zones.append({
                            "low": gap_low, "high": gap_high,
                            "state": FVG_UNTOUCHED, "penetration": 0.0,
                            "creation_index": i,
                        })
                        out.at[i, "fvg_active"] = 1

            if bearish:
                gap_low, gap_high = high[i], low[i - 2]
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
                        out.at[i, "fvg_bearish_creation_index"] = i
                        out.at[i, "fvg_bearish_creation_timestamp"] = timestamps[i]
                        out.at[i, "fvg_displacement_bearish"] = int(displacement is not None)
                        bearish_zones.append({
                            "low": gap_low, "high": gap_high,
                            "state": FVG_UNTOUCHED, "penetration": 0.0,
                            "creation_index": i,
                        })
                        out.at[i, "fvg_active"] = 1

        out.at[i, "fvg_active_bullish_count"] = len(bullish_zones)
        out.at[i, "fvg_active_bearish_count"] = len(bearish_zones)

        if bullish_zones:
            state, penetration = _aggregate_active_state(bullish_zones)
            out.at[i, "fvg_bullish_state"] = state
            out.at[i, "fvg_bullish_penetration"] = penetration
        if bearish_zones:
            state, penetration = _aggregate_active_state(bearish_zones)
            out.at[i, "fvg_bearish_state"] = state
            out.at[i, "fvg_bearish_penetration"] = penetration

    return out
