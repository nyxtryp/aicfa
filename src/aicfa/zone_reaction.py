"""Causal unified zone-reaction layer for AICFA.

This layer does not create trade signals. It normalizes support/resistance,
liquidity, order-block and FVG interactions into a common causal lifecycle:
creation -> distance -> touch -> reaction -> retest -> break/cancellation.

Every state at row t uses only information known at or before t. A zone is
created on the row where its source event becomes available; it is never
backdated to a pivot/source candle that was not yet confirmed.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ZONE_UNTOUCHED = "UNTOUCHED"
ZONE_TOUCHED = "TOUCHED"
ZONE_REACTED = "REACTED"
ZONE_RETESTED = "RETESTED"
ZONE_BROKEN = "BROKEN"
ZONE_CANCELLED = "CANCELLED"


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    x = (
        df[required].copy()
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
    return x


def _value(row: pd.Series, column: str, default=np.nan):
    value = row.get(column, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _add_zone(zones, *, source, side, low, high, created):
    if not np.isfinite(low) or not np.isfinite(high):
        return False
    lo, hi = sorted((float(low), float(high)))
    if hi < lo:
        return False
    zones.append(
        {
            "source": source,
            "side": side,
            "low": lo,
            "high": hi,
            "created": created,
            "state": ZONE_UNTOUCHED,
            "touched": False,
            "reacted": False,
            "retested": False,
        }
    )
    return True


def _touch(zone, *, high: float, low: float, threshold: float) -> bool:
    width = max(zone["high"] - zone["low"], 0.0)
    pad = max(abs(zone["high"] if zone["side"] == "resistance" else zone["low"]) * threshold, 1e-12)
    if width > 0:
        return high >= zone["low"] - pad and low <= zone["high"] + pad
    if zone["side"] == "resistance":
        return high >= zone["high"] - pad
    return low <= zone["low"] + pad


def _reaction(zone, *, close: float, threshold: float) -> bool:
    if zone["side"] == "resistance":
        return close <= zone["high"] * (1.0 + threshold)
    return close >= zone["low"] * (1.0 - threshold)


def _break(zone, *, close: float, threshold: float) -> bool:
    if zone["side"] == "resistance":
        return close > zone["high"] * (1.0 + threshold)
    return close < zone["low"] * (1.0 - threshold)


def _retest(zone, *, high: float, low: float, close: float, threshold: float) -> bool:
    if not zone["reacted"]:
        return False
    touched = _touch(zone, high=high, low=low, threshold=threshold)
    if not touched:
        return False
    if zone["side"] == "resistance":
        return close > zone["high"] and not _break(zone, close=close, threshold=threshold)
    return close < zone["low"] and not _break(zone, close=close, threshold=threshold)


def build_zone_reaction(
    df: pd.DataFrame,
    *,
    structure: pd.DataFrame | None = None,
    fvg: pd.DataFrame | None = None,
    order_blocks: pd.DataFrame | None = None,
    liquidity: pd.DataFrame | None = None,
    reaction_threshold_pct: float = 0.005,
    break_threshold_pct: float = 0.0,
) -> pd.DataFrame:
    """Build causal unified zone/level reaction features.

    Support/resistance levels come from confirmed structure rows. FVG/OB and
    liquidity zones are accepted as already-causal source frames. Existing
    source lifecycles remain authoritative; this layer only adds normalized
    interaction evidence.
    """
    if reaction_threshold_pct <= 0:
        raise ValueError("reaction_threshold_pct must be positive")
    if break_threshold_pct < 0:
        raise ValueError("break_threshold_pct must be non-negative")

    x = _validate(df)
    n = len(x)
    frames = {
        name: frame.reset_index(drop=True)
        for name, frame in (
            ("structure", structure),
            ("fvg", fvg),
            ("order_blocks", order_blocks),
            ("liquidity", liquidity),
        )
        if frame is not None
    }
    for name, frame in frames.items():
        if len(frame) != n:
            raise ValueError(f"{name} length must match input")

    out = x.copy()
    binary = [
        "zone_created_support", "zone_created_resistance",
        "zone_touch_support", "zone_touch_resistance",
        "zone_reaction_support", "zone_reaction_resistance",
        "zone_retest_support", "zone_retest_resistance",
        "zone_break_support", "zone_break_resistance",
        "zone_cancel_support", "zone_cancel_resistance",
        "zone_created_fvg", "zone_created_order_block",
        "zone_created_liquidity",
    ]
    for column in binary:
        out[column] = 0

    numeric = [
        "zone_support_price", "zone_resistance_price",
        "zone_distance_to_support", "zone_distance_to_resistance",
        "zone_source_count",
    ]
    for column in numeric:
        out[column] = np.nan

    out["zone_support_state"] = ZONE_UNTOUCHED
    out["zone_resistance_state"] = ZONE_UNTOUCHED
    out["zone_active_support"] = 0
    out["zone_active_resistance"] = 0

    zones = []
    source_specs = (
        ("fvg", "fvg_bullish", "fvg_bullish_low", "fvg_bullish_high", "support"),
        ("fvg", "fvg_bearish", "fvg_bearish_low", "fvg_bearish_high", "resistance"),
        ("order_block", "order_block_bullish", "order_block_bullish_low", "order_block_bullish_high", "support"),
        ("order_block", "order_block_bearish", "order_block_bearish_low", "order_block_bearish_high", "resistance"),
    )

    for i in range(n):
        created_count = 0

        if structure is not None:
            s = structure.iloc[i]
            if int(_value(s, "swing_high", 0) or 0) == 1:
                price = _value(s, "swing_high_price")
                if np.isfinite(price):
                    _add_zone(zones, source="resistance", side="resistance",
                              low=price, high=price, created=i)
                    out.at[i, "zone_created_resistance"] = 1
                    out.at[i, "zone_resistance_price"] = price
                    created_count += 1
            if int(_value(s, "swing_low", 0) or 0) == 1:
                price = _value(s, "swing_low_price")
                if np.isfinite(price):
                    _add_zone(zones, source="support", side="support",
                              low=price, high=price, created=i)
                    out.at[i, "zone_created_support"] = 1
                    out.at[i, "zone_support_price"] = price
                    created_count += 1

        for source, flag, low_col, high_col, side in source_specs:
            frame = frames.get("fvg" if source == "fvg" else "order_blocks")
            if frame is None:
                continue
            row = frame.iloc[i]
            if int(_value(row, flag, 0) or 0) != 1:
                continue
            lo, hi = _value(row, low_col), _value(row, high_col)
            if _add_zone(zones, source=source, side=side, low=lo, high=hi, created=i):
                out.at[i, "zone_created_fvg" if source == "fvg" else "zone_created_order_block"] += 1
                created_count += 1

        if liquidity is not None:
            row = liquidity.iloc[i]
            for col, side in (
                ("liquidity_pool_created_low", "support"),
                ("liquidity_pool_created_high", "resistance"),
            ):
                price = _value(row, col)
                if np.isfinite(price):
                    _add_zone(zones, source="liquidity", side=side,
                              low=price, high=price, created=i)
                    out.at[i, "zone_created_liquidity"] += 1
                    created_count += 1

        out.at[i, "zone_source_count"] = created_count

        # Existing zones are evaluated only after their creation row. New zones
        # therefore cannot react to their own creation candle.
        active = [z for z in zones if z["state"] not in {ZONE_BROKEN, ZONE_CANCELLED}]
        support = [z for z in active if z["side"] == "support"]
        resistance = [z for z in active if z["side"] == "resistance"]

        for side, candidates in (("support", support), ("resistance", resistance)):
            if not candidates:
                continue
            candidates.sort(key=lambda z: (abs(float(x["close"].iloc[i]) - (z["low"] + z["high"]) / 2.0), z["created"]))
            z = candidates[0]
            level = (z["low"] + z["high"]) / 2.0
            distance = abs(float(x["close"].iloc[i]) - level) / max(abs(float(x["close"].iloc[i])), 1e-12)
            out.at[i, f"zone_{side}_price"] = level
            out.at[i, f"zone_distance_to_{side}"] = distance
            out.at[i, f"zone_{side}_state"] = z["state"]
            out.at[i, f"zone_active_{side}"] = 1

            if z["created"] >= i:
                continue

            h = float(x["high"].iloc[i])
            l = float(x["low"].iloc[i])
            c = float(x["close"].iloc[i])

            if _break(z, close=c, threshold=break_threshold_pct):
                z["state"] = ZONE_BROKEN
                out.at[i, f"zone_break_{side}"] = 1
            elif not z["touched"] and _touch(z, high=h, low=l, threshold=reaction_threshold_pct):
                z["touched"] = True
                z["state"] = ZONE_TOUCHED
                out.at[i, f"zone_touch_{side}"] = 1
            elif z["touched"] and not z["reacted"] and _reaction(z, close=c, threshold=reaction_threshold_pct):
                z["reacted"] = True
                z["state"] = ZONE_REACTED
                out.at[i, f"zone_reaction_{side}"] = 1
            elif _retest(z, high=h, low=l, close=c, threshold=reaction_threshold_pct):
                z["retested"] = True
                z["state"] = ZONE_RETESTED
                out.at[i, f"zone_retest_{side}"] = 1

            out.at[i, f"zone_{side}_state"] = z["state"]
            out.at[i, f"zone_active_{side}"] = int(z["state"] not in {ZONE_BROKEN, ZONE_CANCELLED})

    return out
