"""Closed-candle ATR and average-volume indicators with fixed methods."""
from __future__ import annotations

from typing import Sequence


def calculate_atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    *,
    period: int = 14,
) -> tuple[float | None, ...]:
    """Calculate Wilder ATR.

    True range at index 0 is high-low. The first ATR is the arithmetic mean of
    the first period true ranges; later values use Wilder smoothing:
    ((previous ATR * (period - 1)) + current TR) / period.
    Values before the seed window are None. Only current and prior candles are
    used at each index.
    """
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows, and closes must have the same length")
    if period < 1:
        raise ValueError("period must be >= 1")
    if any(high < low or close < low or close > high
           for high, low, close in zip(highs, lows, closes)):
        raise ValueError("OHLC values are inconsistent")

    true_ranges: list[float] = []
    for index, (high, low) in enumerate(zip(highs, lows)):
        if index == 0:
            true_ranges.append(float(high - low))
        else:
            previous_close = closes[index - 1]
            true_ranges.append(float(max(
                high - low,
                abs(high - previous_close),
                abs(low - previous_close),
            )))

    result: list[float | None] = [None] * len(true_ranges)
    if len(true_ranges) < period:
        return tuple(result)

    atr_value = sum(true_ranges[:period]) / period
    result[period - 1] = atr_value
    for index in range(period, len(true_ranges)):
        atr_value = ((atr_value * (period - 1)) + true_ranges[index]) / period
        result[index] = atr_value
    return tuple(result)


def calculate_average_volume(
    volumes: Sequence[float],
    *,
    period: int = 20,
) -> tuple[float | None, ...]:
    """Return trailing simple average volume; early values are None."""
    if period < 1:
        raise ValueError("period must be >= 1")
    if any(volume < 0 for volume in volumes):
        raise ValueError("volumes must be >= 0")

    result: list[float | None] = [None] * len(volumes)
    running_sum = 0.0
    for index, volume in enumerate(volumes):
        running_sum += volume
        if index >= period:
            running_sum -= volumes[index - period]
        if index >= period - 1:
            result[index] = running_sum / period
    return tuple(result)
