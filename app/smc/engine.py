"""Causal snapshot orchestration for the deterministic SMC primitives."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from typing import Sequence

from app.smc.breaks import StructureBreak, detect_structure_breaks
from app.smc.fvg import FairValueGap, FairValueGapFill, find_fair_value_gaps, measure_fvg_fill
from app.smc.indicators import calculate_atr, calculate_average_volume
from app.smc.liquidity import (
    LiquidityLevel,
    LiquiditySweep,
    detect_liquidity_sweeps,
    detect_current_day_sweeps,
    find_current_day_extremes,
    find_liquidity_levels,
    find_previous_day_extremes,
    is_level_near_zone,
)
from app.smc.order_blocks import (
    OrderBlock,
    OrderBlockMitigation,
    find_order_blocks,
    measure_order_block_mitigation,
)
from app.smc.ranges import DealingRange, find_dealing_range, premium_discount
from app.smc.structure import SwingPoint, find_confirmed_swings


@dataclass(frozen=True, slots=True)
class SMCAnalysis:
    as_of_index: int
    swings: tuple[SwingPoint, ...]
    structure_breaks: tuple[StructureBreak, ...]
    order_blocks: tuple[OrderBlock, ...]
    order_block_mitigation: tuple[OrderBlockMitigation, ...]
    fvg: tuple[FairValueGap, ...]
    fvg_fill: tuple[FairValueGapFill, ...]
    liquidity_levels: tuple[LiquidityLevel, ...]
    sweeps: tuple[LiquiditySweep, ...]
    dealing_range: DealingRange | None
    premium_discount: str | None
    atr: tuple[float | None, ...]
    average_volume: tuple[float | None, ...]


def analyze_smc(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    timestamps_ms: Sequence[int],
    *,
    as_of_index: int | None = None,
    swing_left: int = 2,
    swing_right: int = 2,
    atr_period: int = 14,
    volume_period: int = 20,
    liquidity_tolerance_atr: float = 0.1,
    liquidity_max_age: int = 500,
    zone_bounds: tuple[float, float] | None = None,
    max_zone_distance_atr: float = 0.0,
) -> SMCAnalysis:
    """Analyze a closed-candle prefix; candles after as_of_index are invisible.

    This is a pure calculation only: it does not persist events or emit signals.
    When zone_bounds is supplied, only liquidity levels inside/near that zone
    are included, using ATR at as_of_index and max_zone_distance_atr.
    """
    lengths = {
        len(opens), len(highs), len(lows), len(closes), len(volumes), len(timestamps_ms)
    }
    if len(lengths) != 1:
        raise ValueError("OHLCV and timestamps must have the same length")
    size = len(closes)
    if size == 0:
        raise ValueError("at least one candle is required")
    end = size - 1 if as_of_index is None else as_of_index
    if end < 0 or end >= size:
        raise ValueError("as_of_index is outside the supplied candles")

    # Slice first, before invoking any detector, to make future data inaccessible.
    op = tuple(float(x) for x in opens[:end + 1])
    hi = tuple(float(x) for x in highs[:end + 1])
    lo = tuple(float(x) for x in lows[:end + 1])
    cl = tuple(float(x) for x in closes[:end + 1])
    vol = tuple(float(x) for x in volumes[:end + 1])
    raw_timestamps = tuple(timestamps_ms[:end + 1])
    if any(isinstance(value, bool) or not isinstance(value, Integral) for value in raw_timestamps):
        raise ValueError("timestamps must be integer milliseconds")
    ts = tuple(int(x) for x in raw_timestamps)
    if any(not isfinite(value) for values in (op, hi, lo, cl, vol) for value in values):
        raise ValueError("OHLCV values must be finite")
    if any(volume < 0 for volume in vol):
        raise ValueError("volumes must be >= 0")
    if any(h < l or o < l or o > h or c < l or c > h
           for o, h, l, c in zip(op, hi, lo, cl)):
        raise ValueError("OHLC candle values are inconsistent")
    if any(ts[i] >= ts[i + 1] for i in range(len(ts) - 1)):
        raise ValueError("timestamps must be strictly increasing")
    if zone_bounds is not None:
        zone_lower, zone_upper = zone_bounds
        if not isfinite(zone_lower) or not isfinite(zone_upper) or zone_lower > zone_upper:
            raise ValueError("zone_bounds must be finite and ordered")
    if not isfinite(max_zone_distance_atr) or max_zone_distance_atr < 0:
        raise ValueError("max_zone_distance_atr must be finite and >= 0")

    swings = find_confirmed_swings(hi, lo, left=swing_left, right=swing_right)
    breaks = detect_structure_breaks(cl, swings)
    blocks = find_order_blocks(op, hi, lo, cl, breaks)
    block_mitigation = tuple(
        measure_order_block_mitigation(block, cl, as_of_index=end)
        for block in blocks
    )
    gaps = find_fair_value_gaps(hi, lo)
    fills = tuple(measure_fvg_fill(gap, hi, lo, as_of_index=end) for gap in gaps)

    atr = calculate_atr(hi, lo, cl, period=atr_period)
    avg_volume = calculate_average_volume(vol, period=volume_period)
    levels = list(find_liquidity_levels(
        swings, atr, tolerance_atr=liquidity_tolerance_atr, max_age=liquidity_max_age
    ))
    levels.extend(find_previous_day_extremes(hi, lo, ts))
    current_day_levels = find_current_day_extremes(ts, hi, lo, as_of_index=end)
    levels.extend(current_day_levels)

    if zone_bounds is not None:
        zone_lower, zone_upper = zone_bounds
        current_atr = atr[end]
        if current_atr is None or current_atr <= 0:
            levels = []
        else:
            levels = [
                level for level in levels
                if is_level_near_zone(
                    level.price, zone_lower, zone_upper, current_atr,
                    max_distance_atr=max_zone_distance_atr,
                )
            ]

    historical_levels = [level for level in levels if level not in current_day_levels]
    historical_sweeps = detect_liquidity_sweeps(
        hi, lo, cl, historical_levels, max_age=liquidity_max_age
    )
    current_day_sweeps = detect_current_day_sweeps(ts, hi, lo, cl)
    if zone_bounds is not None:
        current_atr = atr[end]
        if current_atr is None or current_atr <= 0:
            current_day_sweeps = ()
        else:
            current_day_sweeps = tuple(
                event for event in current_day_sweeps
                if is_level_near_zone(
                    event.level, zone_bounds[0], zone_bounds[1], current_atr,
                    max_distance_atr=max_zone_distance_atr,
                )
            )
    # Current-day extremes are computed per candle from prior candles only;
    # do not let the end-of-snapshot level retrospectively create events.
    sweeps = tuple(sorted(
        (*historical_sweeps, *current_day_sweeps),
        key=lambda event: (event.candle_index, event.level_kind, event.level),
    ))
    dealing_range = find_dealing_range(swings, as_of_index=end)
    pd = premium_discount(cl[-1], dealing_range) if dealing_range else None

    return SMCAnalysis(
        as_of_index=end,
        swings=swings,
        structure_breaks=breaks,
        order_blocks=blocks,
        order_block_mitigation=block_mitigation,
        fvg=gaps,
        fvg_fill=fills,
        liquidity_levels=tuple(levels),
        sweeps=sweeps,
        dealing_range=dealing_range,
        premium_discount=pd,
        atr=atr,
        average_volume=avg_volume,
    )
