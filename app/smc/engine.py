"""Causal snapshot orchestration for the deterministic SMC primitives."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.smc.breaks import StructureBreak, detect_structure_breaks
from app.smc.fvg import FairValueGap, FairValueGapFill, find_fair_value_gaps, measure_fvg_fill
from app.smc.indicators import calculate_atr, calculate_average_volume
from app.smc.liquidity import (
    LiquidityLevel,
    LiquiditySweep,
    detect_liquidity_sweeps,
    find_current_day_extremes,
    find_liquidity_levels,
    find_previous_day_extremes,
    is_level_near_zone,
)
from app.smc.order_blocks import OrderBlock, find_order_blocks
from app.smc.ranges import DealingRange, find_dealing_range, premium_discount
from app.smc.structure import SwingPoint, find_confirmed_swings


@dataclass(frozen=True, slots=True)
class SMCAnalysis:
    as_of_index: int
    swings: tuple[SwingPoint, ...]
    structure_breaks: tuple[StructureBreak, ...]
    order_blocks: tuple[OrderBlock, ...]
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
    ts = tuple(int(x) for x in timestamps_ms[:end + 1])
    if any(h < l or o < l or o > h or c < l or c > h
           for o, h, l, c in zip(op, hi, lo, cl)):
        raise ValueError("OHLC candle values are inconsistent")
    if any(ts[i] > ts[i + 1] for i in range(len(ts) - 1)):
        raise ValueError("timestamps must be ordered")

    swings = find_confirmed_swings(hi, lo, left=swing_left, right=swing_right)
    breaks = detect_structure_breaks(cl, swings)
    blocks = find_order_blocks(op, hi, lo, cl, breaks)
    gaps = find_fair_value_gaps(hi, lo)
    fills = tuple(measure_fvg_fill(gap, hi, lo, as_of_index=end) for gap in gaps)

    atr = calculate_atr(hi, lo, cl, period=atr_period)
    avg_volume = calculate_average_volume(vol, period=volume_period)
    levels = list(find_liquidity_levels(
        swings, atr, tolerance_atr=liquidity_tolerance_atr, max_age=liquidity_max_age
    ))
    levels.extend(find_previous_day_extremes(hi, lo, ts))
    levels.extend(find_current_day_extremes(ts, hi, lo, as_of_index=end))

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

    sweeps = detect_liquidity_sweeps(hi, lo, cl, levels, max_age=liquidity_max_age)
    dealing_range = find_dealing_range(swings, as_of_index=end)
    pd = premium_discount(cl[-1], dealing_range) if dealing_range else None

    return SMCAnalysis(
        as_of_index=end,
        swings=swings,
        structure_breaks=breaks,
        order_blocks=blocks,
        fvg=gaps,
        fvg_fill=fills,
        liquidity_levels=tuple(levels),
        sweeps=sweeps,
        dealing_range=dealing_range,
        premium_discount=pd,
        atr=atr,
        average_volume=avg_volume,
    )
