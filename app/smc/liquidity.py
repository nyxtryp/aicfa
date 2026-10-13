"""Liquidity pools and wick-rejection sweeps using confirmed levels."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from numbers import Real
from typing import Sequence

from app.smc.structure import SwingPoint


@dataclass(frozen=True, slots=True)
class LiquidityLevel:
    kind: str
    price: float
    source_indices: tuple[int, ...]
    confirmation_index: int
    equal_level: bool = False


@dataclass(frozen=True, slots=True)
class LiquiditySweep:
    direction: str
    candle_index: int
    level: float
    level_kind: str
    source_indices: tuple[int, ...]


def find_liquidity_levels(
    swings: Sequence[SwingPoint],
    atr: Sequence[float],
    *,
    tolerance_atr: float = 0.1,
    max_age: int = 500,
) -> tuple[LiquidityLevel, ...]:
    """Create swing levels and merge nearby same-kind swings into equal pools.

    Equal-level tolerance is ATR at the later swing multiplied by
    tolerance_atr. Only swings with an available positive ATR are considered.
    Levels are confirmed no earlier than their latest member's confirmation.
    """
    if isinstance(tolerance_atr, bool) or not isinstance(tolerance_atr, Real) or not isfinite(float(tolerance_atr)) or tolerance_atr < 0:
        raise ValueError("tolerance_atr must be finite and >= 0")
    if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age < 1:
        raise ValueError("max_age must be a positive integer")
    for value in atr:
        if value is not None and (isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value))):
            raise ValueError("ATR values must be finite real numbers or None")
    for swing in swings:
        if swing.kind not in {"high", "low"}:
            raise ValueError("swing kind must be 'high' or 'low'")
        if isinstance(swing.index, bool) or not isinstance(swing.index, int) or isinstance(swing.confirmation_index, bool) or not isinstance(swing.confirmation_index, int) or swing.index < 0 or swing.confirmation_index < swing.index:
            raise ValueError("swing indices must be valid non-negative integers")
        if isinstance(swing.price, bool) or not isinstance(swing.price, Real) or not isfinite(float(swing.price)):
            raise ValueError("swing price must be a finite real number")

    grouped: list[list[SwingPoint]] = []
    for swing in sorted(swings, key=lambda item: (item.confirmation_index, item.index)):
        if swing.confirmation_index >= len(atr):
            continue
        atr_value = atr[swing.confirmation_index]
        if atr_value is None or atr_value <= 0:
            continue
        match = None
        for group in reversed(grouped):
            last = group[-1]
            if swing.confirmation_index - last.confirmation_index > max_age:
                continue
            if swing.kind != last.kind:
                continue
            if abs(swing.price - last.price) <= atr_value * tolerance_atr:
                match = group
                break
        if match is None:
            grouped.append([swing])
        else:
            match.append(swing)

    levels: list[LiquidityLevel] = []
    for group in grouped:
        latest = group[-1]
        price = sum(point.price for point in group) / len(group)
        levels.append(LiquidityLevel(
            kind=latest.kind,
            price=float(price),
            source_indices=tuple(point.index for point in group),
            confirmation_index=max(point.confirmation_index for point in group),
            equal_level=len(group) > 1,
        ))
    return tuple(sorted(levels, key=lambda level: (level.confirmation_index, level.kind, level.price)))


def detect_liquidity_sweeps(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    levels: Sequence[LiquidityLevel],
    *,
    max_age: int = 500,
) -> tuple[LiquiditySweep, ...]:
    """Detect a wick beyond a known level followed by a close back across it.

    High-side sweep: high > level and close < level (bearish sweep).
    Low-side sweep: low < level and close > level (bullish sweep).
    A level can generate at most one sweep, and only after confirmation.
    """
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows, and closes must have the same length")
    for values in (highs, lows, closes):
        if any(isinstance(v, bool) or not isinstance(v, Real) or not isfinite(float(v)) for v in values):
            raise ValueError("OHLC values must be finite real numbers")
    if any(high < low or close > high or close < low
           for high, low, close in zip(highs, lows, closes)):
        raise ValueError("OHLC values are inconsistent")
    if isinstance(max_age, bool) or not isinstance(max_age, int) or max_age < 1:
        raise ValueError("max_age must be a positive integer")

    events: list[LiquiditySweep] = []
    used: set[int] = set()
    for index, (high, low, close) in enumerate(zip(highs, lows, closes)):
        for position, level in enumerate(levels):
            if position in used or index <= level.confirmation_index:
                continue
            if index - level.confirmation_index > max_age:
                continue
            swept = (
                level.kind == "high" and high > level.price and close < level.price
            ) or (
                level.kind == "low" and low < level.price and close > level.price
            )
            if not swept:
                continue
            events.append(LiquiditySweep(
                direction="bearish" if level.kind == "high" else "bullish",
                candle_index=index,
                level=float(level.price),
                level_kind=level.kind,
                source_indices=level.source_indices,
            ))
            used.add(position)
    return tuple(events)


def find_previous_day_extremes(
    highs: Sequence[float],
    lows: Sequence[float],
    timestamps_ms: Sequence[int],
) -> tuple[LiquidityLevel, ...]:
    """Return prior UTC-day high/low levels once the next day is observed.

    Timestamps are candle-open Unix milliseconds in UTC. A day's extrema are
    never exposed on candles belonging to that same day. The level becomes
    eligible after the first closed candle whose UTC date is later than the
    source date, avoiding intraday look-ahead. Missing days are allowed.
    """
    if not (len(highs) == len(lows) == len(timestamps_ms)):
        raise ValueError("highs, lows, and timestamps must have the same length")
    for values in (highs, lows):
        if any(isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) for value in values):
            raise ValueError("OHLC values must be finite real numbers")
    if any(high < low for high, low in zip(highs, lows)):
        raise ValueError("each high must be >= its low")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in timestamps_ms):
        raise ValueError("timestamps must be integer Unix milliseconds")
    if any(timestamps_ms[i] >= timestamps_ms[i + 1] for i in range(len(timestamps_ms) - 1)):
        raise ValueError("timestamps must be strictly increasing")

    day_keys = [
        datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date()
        for timestamp in timestamps_ms
    ]
    levels: list[LiquidityLevel] = []
    start = 0
    while start < len(day_keys):
        day = day_keys[start]
        end = start + 1
        while end < len(day_keys) and day_keys[end] == day:
            end += 1
        # The day is usable only if a later UTC date is present in the input.
        if end < len(day_keys):
            high_index = max(range(start, end), key=lambda i: highs[i])
            low_index = min(range(start, end), key=lambda i: lows[i])
            # The source day's last closed candle confirms the level; the
            # first candle of the next UTC day may already sweep it.
            confirmation = end - 1
            levels.append(LiquidityLevel(
                kind="high",
                price=float(highs[high_index]),
                source_indices=(high_index,),
                confirmation_index=confirmation,
                equal_level=False,
            ))
            levels.append(LiquidityLevel(
                kind="low",
                price=float(lows[low_index]),
                source_indices=(low_index,),
                confirmation_index=confirmation,
                equal_level=False,
            ))
        start = end
    return tuple(sorted(levels, key=lambda level: (level.confirmation_index, level.kind)))



def find_current_day_extremes(
    timestamps_ms: Sequence[int],
    highs: Sequence[float],
    lows: Sequence[float],
    *,
    as_of_index: int,
) -> tuple[LiquidityLevel, ...]:
    """Return current UTC-day high/low known immediately before as_of_index.

    The candle at as_of_index and all future candles are excluded. This allows
    the current candle to sweep a previously observed intraday extreme without
    leaking its own high/low into the level being tested.
    """
    if not (len(timestamps_ms) == len(highs) == len(lows)):
        raise ValueError("timestamps, highs, and lows must have the same length")
    if isinstance(as_of_index, bool) or not isinstance(as_of_index, int):
        raise ValueError("as_of_index must be an integer")
    if as_of_index < 0 or as_of_index >= len(highs):
        raise ValueError("as_of_index is outside the supplied candles")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in timestamps_ms):
        raise ValueError("timestamps must be integer Unix milliseconds")
    if any(timestamps_ms[i] >= timestamps_ms[i + 1] for i in range(len(timestamps_ms) - 1)):
        raise ValueError("timestamps must be strictly increasing")
    for values in (highs, lows):
        if any(isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) for value in values):
            raise ValueError("OHLC values must be finite real numbers")
    if any(high < low for high, low in zip(highs, lows)):
        raise ValueError("each high must be >= its low")
    if as_of_index == 0:
        return ()

    current_day = datetime.fromtimestamp(
        timestamps_ms[as_of_index] / 1000, tz=timezone.utc
    ).date()
    prior_indices = [
        i for i in range(as_of_index)
        if datetime.fromtimestamp(timestamps_ms[i] / 1000, tz=timezone.utc).date() == current_day
    ]
    if not prior_indices:
        return ()

    day_high = max(highs[i] for i in prior_indices)
    day_low = min(lows[i] for i in prior_indices)
    high_sources = tuple(i for i in prior_indices if highs[i] == day_high)
    low_sources = tuple(i for i in prior_indices if lows[i] == day_low)
    confirmation = max(prior_indices)
    return (
        LiquidityLevel("high", float(day_high), high_sources, confirmation, False),
        LiquidityLevel("low", float(day_low), low_sources, confirmation, False),
    )


def is_level_near_zone(
    level_price: float,
    zone_lower: float,
    zone_upper: float,
    atr_value: float,
    *,
    max_distance_atr: float,
) -> bool:
    """Return whether a liquidity level is inside/near a zone within ATR distance."""
    values = (level_price, zone_lower, zone_upper, atr_value, max_distance_atr)
    if any(isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) for value in values):
        raise ValueError("level, zone, ATR, and distance values must be finite real numbers")
    if zone_lower > zone_upper:
        raise ValueError("zone_lower must be <= zone_upper")
    if atr_value <= 0 or max_distance_atr < 0:
        raise ValueError("atr_value must be > 0 and max_distance_atr >= 0")
    if zone_lower <= level_price <= zone_upper:
        return True
    distance = zone_lower - level_price if level_price < zone_lower else level_price - zone_upper
    return distance <= atr_value * max_distance_atr


def detect_current_day_sweeps(
    timestamps_ms: Sequence[int],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
) -> tuple[LiquiditySweep, ...]:
    """Detect intraday-extreme sweeps causally, candle by candle.

    For each candle, the reference high/low is calculated only from earlier
    closed candles with the same UTC date. The current candle is never part of
    its own reference level. A sweep requires a wick beyond that prior extreme
    and a close back across it.
    """
    if not (len(timestamps_ms) == len(highs) == len(lows) == len(closes)):
        raise ValueError("timestamps, highs, lows, and closes must have the same length")
    for values in (highs, lows, closes):
        if any(isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) for value in values):
            raise ValueError("OHLC values must be finite real numbers")
    if any(high < low or close < low or close > high
           for high, low, close in zip(highs, lows, closes)):
        raise ValueError("OHLC values are inconsistent")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in timestamps_ms):
        raise ValueError("timestamps must be integer Unix milliseconds")
    if any(timestamps_ms[i] >= timestamps_ms[i + 1]
           for i in range(len(timestamps_ms) - 1)):
        raise ValueError("timestamps must be strictly increasing")

    days = [
        datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc).date()
        for timestamp in timestamps_ms
    ]
    events: list[LiquiditySweep] = []
    prior_high: dict[object, tuple[float, tuple[int, ...]]] = {}
    prior_low: dict[object, tuple[float, tuple[int, ...]]] = {}

    for index, day in enumerate(days):
        if day in prior_high:
            high_level, high_sources = prior_high[day]
            if highs[index] > high_level and closes[index] < high_level:
                events.append(LiquiditySweep(
                    "bearish", index, float(high_level), "high", high_sources
                ))
        if day in prior_low:
            low_level, low_sources = prior_low[day]
            if lows[index] < low_level and closes[index] > low_level:
                events.append(LiquiditySweep(
                    "bullish", index, float(low_level), "low", low_sources
                ))

        # Update references only after checking the current candle.
        if day not in prior_high or highs[index] > prior_high[day][0]:
            prior_high[day] = (float(highs[index]), (index,))
        elif highs[index] == prior_high[day][0]:
            prior_high[day] = (prior_high[day][0], prior_high[day][1] + (index,))
        if day not in prior_low or lows[index] < prior_low[day][0]:
            prior_low[day] = (float(lows[index]), (index,))
        elif lows[index] == prior_low[day][0]:
            prior_low[day] = (prior_low[day][0], prior_low[day][1] + (index,))

    return tuple(events)
