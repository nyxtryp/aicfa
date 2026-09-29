"""Causal Order Block engine for AICFA.

Order Blocks are defined mechanically as the most recent opposite-direction
candle before a confirmed displacement event. The OB is recognized on the
displacement candle, never backdated to the source candle.

Lifecycle is causal:
- creation/recognition at the displacement candle;
- mitigation when a later candle trades into the zone;
- invalidation when a later close crosses the opposite zone boundary;
- breaker transition on a later retest from the invalidated side followed by
  a close rejecting back through the original boundary.
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

    columns = {
        "order_block_bullish": 0,
        "order_block_bearish": 0,
        "order_block": 0,
        "order_block_mitigated": 0,
        "order_block_invalidated": 0,
        "order_block_active": 0,
        "breaker_bullish": 0,
        "breaker_bearish": 0,
        "breaker": 0,
        "order_block_displacement_bullish": 0,
        "order_block_displacement_bearish": 0,
    }
    for column, default in columns.items():
        out[column] = default
    for column in [
        "order_block_bullish_low",
        "order_block_bullish_high",
        "order_block_bearish_low",
        "order_block_bearish_high",
    ]:
        out[column] = np.nan

    from .displacement import build_displacement

    displacement = build_displacement(x) if require_displacement else None

    # Each state stores [low, high, invalidated, breaker, mitigated].
    active_bullish = None
    active_bearish = None
    invalidated_bullish = None
    invalidated_bearish = None

    opens = x["open"].to_numpy()
    highs = x["high"].to_numpy()
    lows = x["low"].to_numpy()
    closes = x["close"].to_numpy()

    for i in range(n):
        # Existing active bullish OB lifecycle.
        if active_bullish is not None:
            low_bound, high_bound, mitigated = active_bullish
            if not mitigated and lows[i] <= high_bound and highs[i] >= low_bound:
                mitigated = True
                out.at[i, "order_block_mitigated"] = 1

            if closes[i] < low_bound:
                out.at[i, "order_block_invalidated"] = 1
                invalidated_bullish = (low_bound, high_bound, False)
                active_bullish = None
            else:
                active_bullish = (low_bound, high_bound, mitigated)
                out.at[i, "order_block_active"] = 1

        # Existing active bearish OB lifecycle.
        if active_bearish is not None:
            low_bound, high_bound, mitigated = active_bearish
            if not mitigated and lows[i] <= high_bound and highs[i] >= low_bound:
                mitigated = True
                out.at[i, "order_block_mitigated"] = 1

            if closes[i] > high_bound:
                out.at[i, "order_block_invalidated"] = 1
                invalidated_bearish = (low_bound, high_bound, False)
                active_bearish = None
            else:
                active_bearish = (low_bound, high_bound, mitigated)
                out.at[i, "order_block_active"] = 1

        # Invalidated bullish OB -> bearish breaker on a later retest from below.
        if invalidated_bullish is not None:
            low_bound, high_bound, breaker_emitted = invalidated_bullish
            if not breaker_emitted and highs[i] >= low_bound and closes[i] < low_bound:
                out.at[i, "breaker_bearish"] = 1
                out.at[i, "breaker"] = 1
                invalidated_bullish = (low_bound, high_bound, True)

        # Invalidated bearish OB -> bullish breaker on a later retest from above.
        if invalidated_bearish is not None:
            low_bound, high_bound, breaker_emitted = invalidated_bearish
            if not breaker_emitted and lows[i] <= high_bound and closes[i] > high_bound:
                out.at[i, "breaker_bullish"] = 1
                out.at[i, "breaker"] = 1
                invalidated_bearish = (low_bound, high_bound, True)

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
            active_bullish = (low_bound, high_bound, False)
            out.at[i, "order_block_active"] = 1

        if opens[i - 1] < closes[i - 1] and disp_down:
            low_bound = lows[i - 1]
            high_bound = highs[i - 1]
            out.at[i, "order_block_bearish"] = 1
            out.at[i, "order_block"] = 1
            out.at[i, "order_block_bearish_low"] = low_bound
            out.at[i, "order_block_bearish_high"] = high_bound
            out.at[i, "order_block_displacement_bearish"] = int(require_displacement)
            active_bearish = (low_bound, high_bound, False)
            out.at[i, "order_block_active"] = 1

    return out
