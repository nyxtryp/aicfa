"""Fair Value Gap (FVG) detection from closed OHLC candles."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral, Real
from typing import Sequence


@dataclass(frozen=True, slots=True)
class FairValueGap:
    direction: str
    first_candle_index: int
    confirmation_index: int
    lower: float
    upper: float


def find_fair_value_gaps(
    highs: Sequence[float],
    lows: Sequence[float],
) -> tuple[FairValueGap, ...]:
    """Find three-candle gaps; each gap is known only when candle three closes.

    Bullish: low[i] > high[i-2], zone [high[i-2], low[i]].
    Bearish: high[i] < low[i-2], zone [high[i], low[i-2]].
    """
    if len(highs) != len(lows):
        raise ValueError("highs and lows must have the same length")
    if any(
        isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value)
        for value in (*highs, *lows)
    ):
        raise ValueError("highs and lows must contain finite real numbers")
    high_values = tuple(float(value) for value in highs)
    low_values = tuple(float(value) for value in lows)
    if any(high < low for high, low in zip(high_values, low_values)):
        raise ValueError("each high must be >= its low")

    gaps: list[FairValueGap] = []
    for index in range(2, len(high_values)):
        first = index - 2
        if low_values[index] > high_values[first]:
            gaps.append(FairValueGap(
                "bullish", first, index, high_values[first], low_values[index]
            ))
        elif high_values[index] < low_values[first]:
            gaps.append(FairValueGap(
                "bearish", first, index, high_values[index], low_values[first]
            ))
    return tuple(gaps)



@dataclass(frozen=True, slots=True)
class FairValueGapFill:
    """Fill progress for one FVG as known at a specific candle index."""

    gap: FairValueGap
    as_of_index: int
    fill_percent: float
    fully_filled: bool


def measure_fvg_fill(
    gap: FairValueGap,
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    as_of_index: int | None = None,
) -> FairValueGapFill:
    """Measure zone penetration using candles after FVG confirmation only.

    Bullish gaps fill from upper to lower using subsequent lows; bearish gaps
    fill from lower to upper using subsequent highs. The formation candles are
    not counted as mitigation. Full fill occurs only when price reaches or
    crosses the opposite edge of the zone.
    """
    if len(highs) != len(lows):
        raise ValueError("highs and lows must have the same length")
    if any(high < low for high, low in zip(highs, lows)):
        raise ValueError("each high must be >= its low")
    if any(
        isinstance(value, bool) or not isinstance(value, Real) or not isfinite(value)
        for value in (gap.lower, gap.upper)
    ) or gap.direction not in {"bullish", "bearish"} or gap.upper <= gap.lower:
        raise ValueError("gap direction or boundaries are invalid")
    for name, value in (
        ("first_candle_index", gap.first_candle_index),
        ("confirmation_index", gap.confirmation_index),
    ):
        if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
            raise ValueError(f"gap {name} must be a non-negative integer")
    if gap.first_candle_index > gap.confirmation_index - 2:
        raise ValueError("gap first candle must precede confirmation by two candles")
    if gap.confirmation_index >= len(highs):
        raise ValueError("gap confirmation index is outside the supplied candles")

    if as_of_index is not None and (
        isinstance(as_of_index, bool) or not isinstance(as_of_index, Integral)
    ):
        raise ValueError("as_of_index must be an integer")
    end = len(highs) - 1 if as_of_index is None else int(as_of_index)
    if end < gap.confirmation_index or end >= len(highs):
        raise ValueError("as_of_index must be between confirmation and last candle")

    high_values = tuple(float(value) for value in highs)
    low_values = tuple(float(value) for value in lows)
    subsequent = range(gap.confirmation_index + 1, end + 1)
    width = gap.upper - gap.lower
    if gap.direction == "bullish":
        lowest = min((low_values[i] for i in subsequent), default=gap.upper)
        penetration = min(width, max(0.0, gap.upper - lowest))
    else:
        highest = max((high_values[i] for i in subsequent), default=gap.lower)
        penetration = min(width, max(0.0, highest - gap.lower))

    fully_filled = penetration >= width
    fill_percent = 100.0 if fully_filled else min(
        round(penetration / width * 100.0, 8), 99.99999999
    )
    return FairValueGapFill(
        gap=gap,
        as_of_index=end,
        fill_percent=fill_percent,
        fully_filled=fully_filled,
    )
