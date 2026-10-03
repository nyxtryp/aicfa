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

    # Keep the hot loop entirely on NumPy arrays. Scalar pandas .at/.iloc
    # operations are disproportionately expensive on the 10k-row integration
    # path; assemble the DataFrame once after the causal loop finishes.
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
    numeric = [
        "zone_support_price", "zone_resistance_price",
        "zone_distance_to_support", "zone_distance_to_resistance",
        "zone_source_count",
    ]
    result_binary = {column: np.zeros(n, dtype=np.int8) for column in binary}
    result_numeric = {column: np.full(n, np.nan, dtype=float) for column in numeric}
    result_state = {
        "zone_support_state": np.full(n, ZONE_UNTOUCHED, dtype=object),
        "zone_resistance_state": np.full(n, ZONE_UNTOUCHED, dtype=object),
    }
    result_active = {
        "zone_active_support": np.zeros(n, dtype=np.int8),
        "zone_active_resistance": np.zeros(n, dtype=np.int8),
    }

    highs = x["high"].to_numpy(dtype=float, copy=False)
    lows = x["low"].to_numpy(dtype=float, copy=False)
    closes = x["close"].to_numpy(dtype=float, copy=False)

    def _column_array(frame: pd.DataFrame | None, column: str, default):
        if frame is None or column not in frame.columns:
            return np.full(n, default)
        return frame[column].to_numpy(copy=False)

    # Store zone state in fixed NumPy-backed arrays.  Lifecycle queries are
    # spatially indexed by logarithmic price buckets instead of scanning all
    # historical zones on every candle.  This keeps the long MTF path close
    # to O(n * local_zones) rather than O(n * total_zones).
    max_zones = max(1, n * 8)
    zone_low = np.full(max_zones, np.nan, dtype=float)
    zone_high = np.full(max_zones, np.nan, dtype=float)
    zone_created = np.full(max_zones, -1, dtype=np.int32)
    zone_side = np.zeros(max_zones, dtype=np.int8)
    zone_state = np.zeros(max_zones, dtype=np.int8)
    zone_touched = np.zeros(max_zones, dtype=bool)
    zone_reacted = np.zeros(max_zones, dtype=bool)
    zone_retested = np.zeros(max_zones, dtype=bool)
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

    # One logarithmic bucket is approximately one reaction-threshold step.
    # Zone ranges are registered into every bucket they can touch.  Very wide
    # zones are kept separately so the index never sacrifices correctness.
    bucket_step = np.log1p(reaction_threshold_pct)
    # Candle bucket bounds are independent of zone state; calculate them once
    # with NumPy instead of performing two scalar logarithms per candle.
    candle_first_buckets = np.floor(
        np.log(np.maximum(lows, 1e-300)) / bucket_step
    ).astype(np.int64)
    candle_last_buckets = np.floor(
        np.log(np.maximum(highs, 1e-300)) / bucket_step
    ).astype(np.int64)
    zone_buckets: dict[int, list[int]] = {}
    wide_zones: list[int] = []
    # Reuse a marker array for per-candle candidate deduplication rather than
    # allocating and hashing a new Python set on every row.
    candidate_marks = np.zeros(max_zones, dtype=np.int32)
    MAX_BUCKET_SPAN = 64

    # Sorted active level indexes provide exact nearest support/resistance
    # lookup without scanning every zone. Entries are (level, zone_id).
    support_levels: list[tuple[float, int]] = []
    resistance_levels: list[tuple[float, int]] = []
    import bisect
    import heapq

    # Retested zones are the only zones eligible for a break. Heaps let us
    # remove all crossed retested levels without scanning unrelated zones.
    support_break_heap: list[tuple[float, int]] = []
    resistance_break_heap: list[tuple[float, int]] = []

    def _bucket(value: float) -> int:
        return int(np.floor(np.log(max(value, 1e-300)) / bucket_step))

    def _register_zone(zone_id: int):
        lo = float(zone_low[zone_id])
        hi = float(zone_high[zone_id])
        side = int(zone_side[zone_id])
        pad_base = hi if side == -1 else lo
        pad = max(abs(pad_base) * reaction_threshold_pct, 1e-12)
        padded_lo = max(lo - pad, 1e-300)
        padded_hi = max(hi + pad, padded_lo)
        first = _bucket(padded_lo)
        last = _bucket(padded_hi)
        if last - first > MAX_BUCKET_SPAN:
            wide_zones.append(zone_id)
        else:
            for bucket_id in range(first, last + 1):
                zone_buckets.setdefault(bucket_id, []).append(zone_id)

        level = (lo + hi) / 2.0
        levels = support_levels if side == 1 else resistance_levels
        bisect.insort(levels, (level, zone_id))

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
        _register_zone(zone_count)
        zone_count += 1
        return True

    source_specs = (
        ("fvg", "fvg_bullish", "fvg_bullish_low", "fvg_bullish_high", "support"),
        ("fvg", "fvg_bearish", "fvg_bearish_low", "fvg_bearish_high", "resistance"),
        ("order_block", "order_block_bullish", "order_block_bullish_low", "order_block_bullish_high", "support"),
        ("order_block", "order_block_bearish", "order_block_bearish_low", "order_block_bearish_high", "resistance"),
    )

    structure_arrays = {
        "swing_high": _column_array(structure, "swing_high", 0),
        "swing_high_price": _column_array(structure, "swing_high_price", np.nan),
        "swing_low": _column_array(structure, "swing_low", 0),
        "swing_low_price": _column_array(structure, "swing_low_price", np.nan),
    }
    fvg_arrays = {
        "fvg_bullish": _column_array(fvg, "fvg_bullish", 0),
        "fvg_bullish_low": _column_array(fvg, "fvg_bullish_low", np.nan),
        "fvg_bullish_high": _column_array(fvg, "fvg_bullish_high", np.nan),
        "fvg_bearish": _column_array(fvg, "fvg_bearish", 0),
        "fvg_bearish_low": _column_array(fvg, "fvg_bearish_low", np.nan),
        "fvg_bearish_high": _column_array(fvg, "fvg_bearish_high", np.nan),
    }
    order_block_arrays = {
        "order_block_bullish": _column_array(order_blocks, "order_block_bullish", 0),
        "order_block_bullish_low": _column_array(order_blocks, "order_block_bullish_low", np.nan),
        "order_block_bullish_high": _column_array(order_blocks, "order_block_bullish_high", np.nan),
        "order_block_bearish": _column_array(order_blocks, "order_block_bearish", 0),
        "order_block_bearish_low": _column_array(order_blocks, "order_block_bearish_low", np.nan),
        "order_block_bearish_high": _column_array(order_blocks, "order_block_bearish_high", np.nan),
    }
    liquidity_arrays = {
        "liquidity_pool_created_low": _column_array(liquidity, "liquidity_pool_created_low", np.nan),
        "liquidity_pool_created_high": _column_array(liquidity, "liquidity_pool_created_high", np.nan),
    }

    def _active_level(levels, close: float):
        if not levels:
            return None
        pos = bisect.bisect_left(levels, (close, -1))
        # Broken/cancelled zones are removed from the sorted index, so the
        # nearest active level can only be one of the two immediate neighbors.
        candidates = []
        if pos:
            candidates.append(levels[pos - 1])
        if pos < len(levels):
            candidates.append(levels[pos])
        if not candidates:
            return None
        level, zone_id = min(candidates, key=lambda item: abs(close - item[0]))
        return zone_id, level, abs(close - level)

    def _remove_level(levels, zone_id: int):
        level = float((zone_low[zone_id] + zone_high[zone_id]) / 2.0)
        pos = bisect.bisect_left(levels, (level, zone_id))
        if pos < len(levels) and levels[pos] == (level, zone_id):
            levels.pop(pos)

    for i in range(n):
        created_count = 0

        if structure is not None:
            if int(structure_arrays["swing_high"][i] or 0) == 1:
                price = float(structure_arrays["swing_high_price"][i])
                if _append_zone(source="resistance", side="resistance", low=price, high=price, created=i):
                    result_binary["zone_created_resistance"][i] = 1
                    result_numeric["zone_resistance_price"][i] = price
                    created_count += 1
            if int(structure_arrays["swing_low"][i] or 0) == 1:
                price = float(structure_arrays["swing_low_price"][i])
                if _append_zone(source="support", side="support", low=price, high=price, created=i):
                    result_binary["zone_created_support"][i] = 1
                    result_numeric["zone_support_price"][i] = price
                    created_count += 1

        for source, flag, low_col, high_col, side in source_specs:
            arrays = fvg_arrays if source == "fvg" else order_block_arrays
            if int(arrays[flag][i] or 0) != 1:
                continue
            lo, hi = float(arrays[low_col][i]), float(arrays[high_col][i])
            if _append_zone(source=source, side=side, low=lo, high=hi, created=i):
                result_binary["zone_created_fvg" if source == "fvg" else "zone_created_order_block"][i] += 1
                created_count += 1

        if liquidity is not None:
            for col, side in (
                ("liquidity_pool_created_low", "support"),
                ("liquidity_pool_created_high", "resistance"),
            ):
                price = float(liquidity_arrays[col][i])
                if np.isfinite(price):
                    _append_zone(source="liquidity", side=side, low=price, high=price, created=i)
                    result_binary["zone_created_liquidity"][i] += 1
                    created_count += 1

        result_numeric["zone_source_count"][i] = created_count
        if zone_count == 0:
            continue

        h = highs[i]
        l = lows[i]
        close = closes[i]

        # Breaks are only possible after retest.  Use the retest heaps so a
        # large candle can break distant zones without a global zone scan.
        break_support = []
        support_limit = close / max(1.0 + break_threshold_pct, 1e-12)
        while support_break_heap and -support_break_heap[0][0] > support_limit:
            _, zone_id = heapq.heappop(support_break_heap)
            if zone_state[zone_id] == STATE_CODE[ZONE_RETESTED] and close < zone_low[zone_id] * (1.0 + break_threshold_pct):
                zone_state[zone_id] = STATE_CODE[ZONE_BROKEN]
                break_support.append(zone_id)
                _remove_level(support_levels, zone_id)

        break_resistance = []
        while resistance_break_heap and resistance_break_heap[0][0] * (1.0 + break_threshold_pct) < close:
            _, zone_id = heapq.heappop(resistance_break_heap)
            if zone_state[zone_id] == STATE_CODE[ZONE_RETESTED] and close > zone_high[zone_id] * (1.0 + break_threshold_pct):
                zone_state[zone_id] = STATE_CODE[ZONE_BROKEN]
                break_resistance.append(zone_id)
                _remove_level(resistance_levels, zone_id)

        # Query only price buckets intersecting the current candle. This is the
        # critical path optimization: unrelated historical zones are skipped.
        first_bucket = int(candle_first_buckets[i])
        last_bucket = int(candle_last_buckets[i])
        stamp = i + 1
        candidate_ids = []
        for zone_id in wide_zones:
            if candidate_marks[zone_id] != stamp:
                candidate_marks[zone_id] = stamp
                candidate_ids.append(zone_id)
        for bucket_id in range(first_bucket, last_bucket + 1):
            for zone_id in zone_buckets.get(bucket_id, ()):
                if candidate_marks[zone_id] != stamp:
                    candidate_marks[zone_id] = stamp
                    candidate_ids.append(zone_id)
        if candidate_ids:
            idx = np.asarray(
                [
                    zone_id for zone_id in candidate_ids
                    if zone_created[zone_id] < i
                    and zone_state[zone_id] != STATE_CODE[ZONE_BROKEN]
                    and zone_state[zone_id] != STATE_CODE[ZONE_CANCELLED]
                ],
                dtype=np.intp,
            )
        else:
            idx = np.empty(0, dtype=np.intp)

        if idx.size:
            zone_lows = zone_low[idx]
            zone_highs = zone_high[idx]
            sides = zone_side[idx]
            widths = np.maximum(zone_highs - zone_lows, 0.0)
            pads = np.maximum(
                np.abs(np.where(sides == -1, zone_highs, zone_lows)) * reaction_threshold_pct,
                1e-12,
            )
            overlap = (h >= zone_lows - pads) & (l <= zone_highs + pads)
            point_touch = np.where(sides == -1, h >= zone_highs - pads, l <= zone_lows + pads)
            touched_now = np.where(widths > 0.0, overlap, point_touch)
            reaction_now = np.where(
                sides == -1,
                close <= zone_highs * (1.0 + reaction_threshold_pct),
                close >= zone_lows * (1.0 - reaction_threshold_pct),
            )
            break_now = np.where(
                sides == -1,
                close > zone_highs * (1.0 + break_threshold_pct),
                close < zone_lows * (1.0 - break_threshold_pct),
            )
            touched_before = zone_touched[idx]
            reacted_before = zone_reacted[idx]
            retested_before = zone_retested[idx]

            break_mask = retested_before & break_now
            touch_mask = ~touched_before & touched_now & ~break_mask
            reaction_mask = touched_before & ~reacted_before & reaction_now & ~break_mask & ~touch_mask
            retest_mask = (
                reacted_before & touched_now
                & np.where(sides == -1, close > zone_highs, close < zone_lows)
                & ~break_mask & ~touch_mask & ~reaction_mask
            )

            if break_mask.any():
                break_idx = idx[break_mask]
                for zone_id in break_idx.tolist():
                    if zone_state[zone_id] != STATE_CODE[ZONE_BROKEN]:
                        zone_state[zone_id] = STATE_CODE[ZONE_BROKEN]
                        _remove_level(support_levels if zone_side[zone_id] == 1 else resistance_levels, zone_id)
                result_binary["zone_break_support"][i] |= int(np.any(zone_side[break_idx] == 1))
                result_binary["zone_break_resistance"][i] |= int(np.any(zone_side[break_idx] == -1))

            if touch_mask.any():
                touch_idx = idx[touch_mask]
                zone_touched[touch_idx] = True
                zone_state[touch_idx] = STATE_CODE[ZONE_TOUCHED]
                result_binary["zone_touch_support"][i] |= int(np.any(zone_side[touch_idx] == 1))
                result_binary["zone_touch_resistance"][i] |= int(np.any(zone_side[touch_idx] == -1))

            if reaction_mask.any():
                reaction_idx = idx[reaction_mask]
                zone_reacted[reaction_idx] = True
                zone_state[reaction_idx] = STATE_CODE[ZONE_REACTED]
                result_binary["zone_reaction_support"][i] |= int(np.any(zone_side[reaction_idx] == 1))
                result_binary["zone_reaction_resistance"][i] |= int(np.any(zone_side[reaction_idx] == -1))

            if retest_mask.any():
                retest_idx = idx[retest_mask]
                zone_retested[retest_idx] = True
                zone_state[retest_idx] = STATE_CODE[ZONE_RETESTED]
                for zone_id in retest_idx.tolist():
                    level = (zone_low[zone_id] + zone_high[zone_id]) / 2.0
                    if zone_side[zone_id] == 1:
                        heapq.heappush(support_break_heap, (-float(zone_low[zone_id]), zone_id))
                    else:
                        heapq.heappush(resistance_break_heap, (float(zone_high[zone_id]), zone_id))
                result_binary["zone_retest_support"][i] |= int(np.any(zone_side[retest_idx] == 1))
                result_binary["zone_retest_resistance"][i] |= int(np.any(zone_side[retest_idx] == -1))

        best_support = _active_level(support_levels, close)
        best_resistance = _active_level(resistance_levels, close)
        if best_support is not None:
            zone_id, level, distance = best_support
            result_numeric["zone_support_price"][i] = level
            result_numeric["zone_distance_to_support"][i] = distance / max(abs(close), 1e-12)
            result_state["zone_support_state"][i] = STATE_NAME[zone_state[zone_id]]
            result_active["zone_active_support"][i] = 1
        if best_resistance is not None:
            zone_id, level, distance = best_resistance
            result_numeric["zone_resistance_price"][i] = level
            result_numeric["zone_distance_to_resistance"][i] = distance / max(abs(close), 1e-12)
            result_state["zone_resistance_state"][i] = STATE_NAME[zone_state[zone_id]]
            result_active["zone_active_resistance"][i] = 1

        if break_support:
            result_binary["zone_break_support"][i] = 1
            result_state["zone_support_state"][i] = ZONE_BROKEN
            result_active["zone_active_support"][i] = 0
        if break_resistance:
            result_binary["zone_break_resistance"][i] = 1
            result_state["zone_resistance_state"][i] = ZONE_BROKEN
            result_active["zone_active_resistance"][i] = 0

    for column, values in result_binary.items():
        out[column] = values
    for column, values in result_numeric.items():
        out[column] = values
    for column, values in result_state.items():
        out[column] = values
    for column, values in result_active.items():
        out[column] = values
    return out
