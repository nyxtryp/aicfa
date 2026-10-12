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
