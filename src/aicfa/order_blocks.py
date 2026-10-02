"""Causal Order Block engine for AICFA.

Order Blocks are defined mechanically as the most recent opposite-direction
candle before a confirmed displacement event. The OB is recognized on the
displacement candle, never backdated to the source candle.

Lifecycle is causal:
- creation/recognition at the displacement candle;
- lifecycle depth when later candles touch and penetrate the zone;
- invalidation when a later close crosses the opposite zone boundary;
- prior-volume comparison is metadata only, never a mandatory OB filter;
- breaker transition on a later retest from the invalidated side followed by
  a close rejecting back through the original boundary.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


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


def build_order_blocks(
    df: pd.DataFrame,
    *,
    require_displacement: bool = True,
) -> pd.DataFrame:
    """Build causal bullish/bearish Order Block lifecycle features.

    Definition:
    - bullish OB: most recent bearish candle before a bullish displacement;
    - bearish OB: most recent bullish candle before a bearish displacement.

    The source candle is only referenced after the displacement is known.
    Zone boundaries are the full source candle high/low.

    A later candle mitigates an active OB when it trades into its zone.
    Invalidation occurs when a later close crosses the opposite boundary.
    After invalidation, a later retest from the other side that rejects back
    through the original boundary converts the OB into a breaker.
    """
    x = _validate(df)
    out = x.copy()
    n = len(x)

    for column in [
        "order_block_bullish", "order_block_bearish", "order_block",
        "order_block_mitigated", "order_block_invalidated", "order_block_active",
        "breaker_bullish", "breaker_bearish", "breaker",
        "order_block_displacement_bullish", "order_block_displacement_bearish",
    ]:
        out[column] = 0
    for column in [
        "order_block_bullish_low", "order_block_bullish_high",
        "order_block_bearish_low", "order_block_bearish_high",
        "order_block_bullish_penetration", "order_block_bearish_penetration",
        "order_block_bullish_volume_ratio", "order_block_bearish_volume_ratio",
    ]:
        out[column] = np.nan
    for column in ["order_block_bullish_state", "order_block_bearish_state"]:
        out[column] = "NONE"
    for column in ["order_block_bullish_volume_confirmed", "order_block_bearish_volume_confirmed"]:
        out[column] = 0

    from .displacement import build_displacement

    displacement = build_displacement(x) if require_displacement else None

    # Active state: (low, high, lifecycle_state).
    active_bullish = None
    active_bearish = None
    last_bullish_state = "NONE"
    last_bearish_state = "NONE"
    # Compare event volume only with prior candles; the current candle is
    # excluded from its own baseline. Confirmation is descriptive evidence.
    prior_volume_mean = x["volume"].shift(1).rolling(20, min_periods=5).mean()
    volume = x["volume"].to_numpy()
    volume_baseline = prior_volume_mean.to_numpy()
    # Invalidated state: (low, high, breaker_already_emitted).
    invalidated_bullish = None
    invalidated_bearish = None

    opens = x["open"].to_numpy()
    highs = x["high"].to_numpy()
    lows = x["low"].to_numpy()
    closes = x["close"].to_numpy()

    for i in range(n):
        # Breaker checks deliberately happen BEFORE the current active OB
        # lifecycle, so an OB invalidated on candle i cannot become a breaker
        # until a strictly later candle.
        if invalidated_bullish is not None:
            low_bound, high_bound, emitted = invalidated_bullish
            if not emitted and highs[i] >= low_bound and closes[i] < low_bound:
                out.at[i, "breaker_bearish"] = 1
                out.at[i, "breaker"] = 1
                invalidated_bullish = (low_bound, high_bound, True)

        if invalidated_bearish is not None:
            low_bound, high_bound, emitted = invalidated_bearish
            if not emitted and lows[i] <= high_bound and closes[i] > high_bound:
                out.at[i, "breaker_bullish"] = 1
                out.at[i, "breaker"] = 1
                invalidated_bearish = (low_bound, high_bound, True)

        # Existing active bullish OB lifecycle.
        if active_bullish is not None:
            low_bound, high_bound, state = active_bullish
            width = max(high_bound - low_bound, 1e-12)
            touched = lows[i] <= high_bound and highs[i] >= low_bound
            penetration = float(np.clip((high_bound - max(low_bound, lows[i])) / width, 0.0, 1.0)) if touched else 0.0
            if closes[i] < low_bound:
                state = "INVALIDATED"
                out.at[i, "order_block_invalidated"] = 1
                invalidated_bullish = (low_bound, high_bound, False)
                active_bullish = None
            else:
                if touched:
                    out.at[i, "order_block_mitigated"] = int(state == "UNTOUCHED")
                    if penetration <= 0.0:
                        state = "TOUCHED"
                    elif penetration < 0.5:
                        state = "PARTIAL"
                    else:
                        state = "DEEP"
                active_bullish = (low_bound, high_bound, state)
                out.at[i, "order_block_active"] = 1
            last_bullish_state = state
            out.at[i, "order_block_bullish_state"] = state
            out.at[i, "order_block_bullish_penetration"] = penetration

        # Existing active bearish OB lifecycle.
        if active_bearish is not None:
            low_bound, high_bound, state = active_bearish
            width = max(high_bound - low_bound, 1e-12)
            touched = lows[i] <= high_bound and highs[i] >= low_bound
            penetration = float(np.clip((min(high_bound, highs[i]) - low_bound) / width, 0.0, 1.0)) if touched else 0.0
            if closes[i] > high_bound:
                state = "INVALIDATED"
                out.at[i, "order_block_invalidated"] = 1
                invalidated_bearish = (low_bound, high_bound, False)
                active_bearish = None
            else:
                if touched:
                    out.at[i, "order_block_mitigated"] = int(state == "UNTOUCHED")
                    if penetration <= 0.0:
                        state = "TOUCHED"
                    elif penetration < 0.5:
                        state = "PARTIAL"
                    else:
                        state = "DEEP"
                active_bearish = (low_bound, high_bound, state)
                out.at[i, "order_block_active"] = 1
            last_bearish_state = state
            out.at[i, "order_block_bearish_state"] = state
            out.at[i, "order_block_bearish_penetration"] = penetration

        if i < 1:
            continue

        disp_up = True if displacement is None else displacement.at[i, "displacement_up"] == 1
        disp_down = True if displacement is None else displacement.at[i, "displacement_down"] == 1

        # The source candle is the immediately preceding opposite candle.
        # Recognition is written only at i, when the displacement is known.
        if opens[i - 1] > closes[i - 1] and disp_up:
            low_bound = lows[i - 1]
            high_bound = highs[i - 1]
            out.at[i, "order_block_bullish"] = 1
            out.at[i, "order_block"] = 1
            out.at[i, "order_block_bullish_low"] = low_bound
            out.at[i, "order_block_bullish_high"] = high_bound
            out.at[i, "order_block_displacement_bullish"] = int(require_displacement)
            active_bullish = (low_bound, high_bound, "UNTOUCHED")
            last_bullish_state = "UNTOUCHED"
            out.at[i, "order_block_bullish_state"] = "UNTOUCHED"
            baseline = volume_baseline[i]
            if np.isfinite(baseline) and baseline > 0:
                ratio = float(volume[i] / baseline)
                out.at[i, "order_block_bullish_volume_ratio"] = ratio
                out.at[i, "order_block_bullish_volume_confirmed"] = int(ratio >= 1.5)
            out.at[i, "order_block_active"] = 1

        if opens[i - 1] < closes[i - 1] and disp_down:
            low_bound = lows[i - 1]
            high_bound = highs[i - 1]
            out.at[i, "order_block_bearish"] = 1
            out.at[i, "order_block"] = 1
            out.at[i, "order_block_bearish_low"] = low_bound
            out.at[i, "order_block_bearish_high"] = high_bound
            out.at[i, "order_block_displacement_bearish"] = int(require_displacement)
            active_bearish = (low_bound, high_bound, "UNTOUCHED")
            last_bearish_state = "UNTOUCHED"
            out.at[i, "order_block_bearish_state"] = "UNTOUCHED"
            baseline = volume_baseline[i]
            if np.isfinite(baseline) and baseline > 0:
                ratio = float(volume[i] / baseline)
                out.at[i, "order_block_bearish_volume_ratio"] = ratio
                out.at[i, "order_block_bearish_volume_confirmed"] = int(ratio >= 1.5)
            out.at[i, "order_block_active"] = 1

    return out
