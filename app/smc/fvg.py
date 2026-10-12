"""Fair Value Gap (FVG) detection from closed OHLC candles."""
from __future__ import annotations

from dataclasses import dataclass
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
    if any(high < low for high, low in zip(highs, lows)):
        raise ValueError("each high must be >= its low")

    gaps: list[FairValueGap] = []
    for index in range(2, len(highs)):
        first = index - 2
        if lows[index] > highs[first]:
            gaps.append(FairValueGap(
                "bullish", first, index, float(highs[first]), float(lows[index])
            ))
        elif highs[index] < lows[first]:
            gaps.append(FairValueGap(
                "bearish", first, index, float(highs[index]), float(lows[first])
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
    if gap.direction not in {"bullish", "bearish"} or gap.upper <= gap.lower:
        raise ValueError("gap direction or boundaries are invalid")
    if gap.confirmation_index < 0 or gap.confirmation_index >= len(highs):
        raise ValueError("gap confirmation index is outside the supplied candles")

    end = len(highs) - 1 if as_of_index is None else as_of_index
    if end < gap.confirmation_index or end >= len(highs):
        raise ValueError("as_of_index must be between confirmation and last candle")

    subsequent = range(gap.confirmation_index + 1, end + 1)
    width = gap.upper - gap.lower
    if gap.direction == "bullish":
        lowest = min((lows[i] for i in subsequent), default=gap.upper)
        penetration = min(width, max(0.0, gap.upper - lowest))
    else:
        highest = max((highs[i] for i in subsequent), default=gap.lower)
        penetration = min(width, max(0.0, highest - gap.lower))

    fill_percent = round(penetration / width * 100.0, 8)
    return FairValueGapFill(
        gap=gap,
        as_of_index=end,
        fill_percent=fill_percent,
        fully_filled=fill_percent >= 100.0,
    )
