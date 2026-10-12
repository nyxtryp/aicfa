"""Liquidity pools and wick-rejection sweeps using confirmed levels."""
from __future__ import annotations

from dataclasses import dataclass
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
    if tolerance_atr < 0 or max_age < 1:
        raise ValueError("tolerance_atr must be >= 0 and max_age >= 1")
    for swing in swings:
        if swing.kind not in {"high", "low"}:
            raise ValueError("swing kind must be 'high' or 'low'")

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
    if any(high < low or close > high or close < low
           for high, low, close in zip(highs, lows, closes)):
        raise ValueError("OHLC values are inconsistent")
    if max_age < 1:
        raise ValueError("max_age must be >= 1")

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
