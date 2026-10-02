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

    # Store zones in fixed NumPy-backed arrays.  The previous implementation
    # rebuilt Python lists of active zones and then iterated every active zone
    # on every candle.  On long MTF frames that created avoidable Python-level
    # O(n * zones) work.  A bounded array keeps the lifecycle work in NumPy.
    max_zones = max(1, n * 8)
    zone_low = np.full(max_zones, np.nan, dtype=float)
    zone_high = np.full(max_zones, np.nan, dtype=float)
    zone_created = np.full(max_zones, -1, dtype=np.int32)
    zone_side = np.zeros(max_zones, dtype=np.int8)
    zone_state = np.zeros(max_zones, dtype=np.int8)
    zone_touched = np.zeros(max_zones, dtype=bool)
    zone_reacted = np.zeros(max_zones, dtype=bool)
    zone_retested = np.zeros(max_zones, dtype=bool)
    zone_source = np.empty(max_zones, dtype=object)
    zone_count = 0

    STATE_CODE = {
        ZONE_UNTOUCHED: 0,
        ZONE_TOUCHED: 1,
        ZONE_REACTED: 2,
        ZONE_RETESTED: 3,
        ZONE_BROKEN: 4,
        ZONE_CANCELLED: 5,
    }
    STATE_NAME = np.array(
        [
            ZONE_UNTOUCHED,
            ZONE_TOUCHED,
            ZONE_REACTED,
            ZONE_RETESTED,
            ZONE_BROKEN,
            ZONE_CANCELLED,
        ],
        dtype=object,
    )

    def _append_zone(*, source, side, low, high, created):
        nonlocal zone_count
        if zone_count >= max_zones:
            raise RuntimeError("zone capacity exceeded")
        if not np.isfinite(low) or not np.isfinite(high):
            return False
        lo, hi = sorted((float(low), float(high)))
        zone_low[zone_count] = lo
        zone_high[zone_count] = hi
        zone_created[zone_count] = created
        zone_side[zone_count] = 1 if side == "support" else -1
        zone_state[zone_count] = STATE_CODE[ZONE_UNTOUCHED]
        zone_source[zone_count] = source
        zone_count += 1
        return True

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
                if _append_zone(
                    source="resistance", side="resistance",
                    low=price, high=price, created=i
                ):
                    out.at[i, "zone_created_resistance"] = 1
                    out.at[i, "zone_resistance_price"] = price
                    created_count += 1
            if int(_value(s, "swing_low", 0) or 0) == 1:
                price = _value(s, "swing_low_price")
                if _append_zone(
                    source="support", side="support",
                    low=price, high=price, created=i
                ):
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
            if _append_zone(
                source=source, side=side, low=lo, high=hi, created=i
            ):
                out.at[
                    i,
                    "zone_created_fvg"
                    if source == "fvg"
                    else "zone_created_order_block",
                ] += 1
                created_count += 1

        if liquidity is not None:
            row = liquidity.iloc[i]
            for col, side in (
                ("liquidity_pool_created_low", "support"),
                ("liquidity_pool_created_high", "resistance"),
            ):
                price = _value(row, col)
                if np.isfinite(price):
                    _append_zone(
                        source="liquidity", side=side,
                        low=price, high=price, created=i
                    )
                    out.at[i, "zone_created_liquidity"] += 1
                    created_count += 1

        out.at[i, "zone_source_count"] = created_count

        if zone_count == 0:
            continue

        h = float(x["high"].iloc[i])
        l = float(x["low"].iloc[i])
        close = float(x["close"].iloc[i])

        active = (
            (zone_created[:zone_count] < i)
            & (zone_state[:zone_count] != STATE_CODE[ZONE_BROKEN])
            & (zone_state[:zone_count] != STATE_CODE[ZONE_CANCELLED])
        )
        if not active.any():
            continue

        idx = np.flatnonzero(active)
        lows = zone_low[idx]
        highs = zone_high[idx]
        sides = zone_side[idx]

        widths = np.maximum(highs - lows, 0.0)
        pads = np.maximum(
            np.abs(np.where(sides == -1, highs, lows))
            * reaction_threshold_pct,
            1e-12,
        )
        overlap = (h >= lows - pads) & (l <= highs + pads)
        point_touch = np.where(
            sides == -1,
            h >= highs - pads,
            l <= lows + pads,
        )
        touched_now = np.where(widths > 0.0, overlap, point_touch)

        reaction_now = np.where(
            sides == -1,
            close <= highs * (1.0 + reaction_threshold_pct),
            close >= lows * (1.0 - reaction_threshold_pct),
        )
        break_now = np.where(
            sides == -1,
            close > highs * (1.0 + break_threshold_pct),
            close < lows * (1.0 - break_threshold_pct),
        )

        touched_before = zone_touched[idx]
        reacted_before = zone_reacted[idx]
        retested_before = zone_retested[idx]

        break_mask = retested_before & break_now
        touch_mask = ~touched_before & touched_now & ~break_mask
        reaction_mask = (
            touched_before
            & ~reacted_before
            & reaction_now
            & ~break_mask
            & ~touch_mask
        )
        retest_mask = (
            reacted_before
            & touched_now
            & np.where(
                sides == -1,
                close > highs,
                close < lows,
            )
            & ~break_mask
            & ~touch_mask
            & ~reaction_mask
        )

        if break_mask.any():
            break_idx = idx[break_mask]
            zone_state[break_idx] = STATE_CODE[ZONE_BROKEN]
            out.at[i, "zone_break_support"] |= int(np.any(zone_side[break_idx] == 1))
            out.at[i, "zone_break_resistance"] |= int(np.any(zone_side[break_idx] == -1))

        if touch_mask.any():
            touch_idx = idx[touch_mask]
            zone_touched[touch_idx] = True
            zone_state[touch_idx] = STATE_CODE[ZONE_TOUCHED]
            out.at[i, "zone_touch_support"] |= int(np.any(zone_side[touch_idx] == 1))
            out.at[i, "zone_touch_resistance"] |= int(np.any(zone_side[touch_idx] == -1))

        if reaction_mask.any():
            reaction_idx = idx[reaction_mask]
            zone_reacted[reaction_idx] = True
            zone_state[reaction_idx] = STATE_CODE[ZONE_REACTED]
            out.at[i, "zone_reaction_support"] |= int(np.any(zone_side[reaction_idx] == 1))
            out.at[i, "zone_reaction_resistance"] |= int(np.any(zone_side[reaction_idx] == -1))

        if retest_mask.any():
            retest_idx = idx[retest_mask]
            zone_retested[retest_idx] = True
            zone_state[retest_idx] = STATE_CODE[ZONE_RETESTED]
            out.at[i, "zone_retest_support"] |= int(np.any(zone_side[retest_idx] == 1))
            out.at[i, "zone_retest_resistance"] |= int(np.any(zone_side[retest_idx] == -1))

        active_after = (
            (zone_created[:zone_count] < i)
            & (zone_state[:zone_count] != STATE_CODE[ZONE_BROKEN])
            & (zone_state[:zone_count] != STATE_CODE[ZONE_CANCELLED])
        )
        for side_name, side_value in (("support", 1), ("resistance", -1)):
            candidates = np.flatnonzero(
                active_after & (zone_side[:zone_count] == side_value)
            )
            if candidates.size == 0:
                continue
            levels = (zone_low[candidates] + zone_high[candidates]) / 2.0
            distances = np.abs(close - levels)
            best_local = int(np.argmin(distances))
            best = candidates[best_local]
            level = float(levels[best_local])
            distance = abs(close - level) / max(abs(close), 1e-12)
            out.at[i, f"zone_{side_name}_price"] = level
            out.at[i, f"zone_distance_to_{side_name}"] = distance
            out.at[i, f"zone_{side_name}_state"] = STATE_NAME[zone_state[best]]
            out.at[i, f"zone_active_{side_name}"] = 1

        for side_name in ("support", "resistance"):
            if out.at[i, f"zone_break_{side_name}"] == 1:
                out.at[i, f"zone_{side_name}_state"] = ZONE_BROKEN
                out.at[i, f"zone_active_{side_name}"] = 0

    return out
