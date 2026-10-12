"""Deterministic, closed-candle SMC structure primitives.

Swing points are emitted only after the required right-hand candles have closed.
For equal extrema, the earliest candle in a plateau wins.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class SwingPoint:
    kind: str
    index: int
    confirmation_index: int
    price: float


def find_confirmed_swings(
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    left: int,
    right: int,
) -> tuple[SwingPoint, ...]:
    """Return confirmed swing highs/lows using only fully available candle windows.

    A high is a swing when it is strictly higher than all candles to its left
    and greater than or equal to all candles to its right. The inverse rule is
    used for lows. This resolves equal-price plateaus deterministically in
    favor of the earliest candle.
    """
    if left < 1 or right < 1:
        raise ValueError("left and right must both be >= 1")
    if len(highs) != len(lows):
        raise ValueError("highs and lows must have the same length")
    if any(high < low for high, low in zip(highs, lows)):
        raise ValueError("each high must be >= its low")

    points: list[SwingPoint] = []
    for index in range(left, len(highs) - right):
        high = highs[index]
        low = lows[index]
        left_highs = highs[index - left:index]
        right_highs = highs[index + 1:index + right + 1]
        left_lows = lows[index - left:index]
        right_lows = lows[index + 1:index + right + 1]

        if high > max(left_highs) and high >= max(right_highs):
            points.append(SwingPoint("high", index, index + right, float(high)))
        if low < min(left_lows) and low <= min(right_lows):
            points.append(SwingPoint("low", index, index + right, float(low)))

    return tuple(sorted(points, key=lambda point: (point.confirmation_index, point.index, point.kind)))
