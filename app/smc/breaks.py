"""Deterministic BOS/CHoCH events from confirmed swings and closed candles."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Sequence

from app.smc.structure import SwingPoint


@dataclass(frozen=True, slots=True)
class StructureBreak:
    """A single close-confirmed break of a previously confirmed swing."""

    kind: str
    direction: str
    candle_index: int
    swing_index: int
    level: float


def detect_structure_breaks(
    closes: Sequence[float],
    swings: Sequence[SwingPoint],
) -> tuple[StructureBreak, ...]:
    """Return BOS/CHoCH events without look-ahead.

    A swing can only be broken at or after its confirmation_index. The close
    must be strictly beyond the swing level; wicks are intentionally ignored.
    The first break establishes direction and is BOS. A break in the current
    direction is BOS; the first break in the opposite direction is CHoCH and
    flips the structure direction. Each swing level can emit at most one event.
    If a candle crosses several eligible swings, only the latest confirmed
    swing in that direction is considered.
    """
    normalized_closes: list[float] = []
    for close in closes:
        if isinstance(close, bool) or not isinstance(close, Real) or not isfinite(float(close)):
            raise ValueError("closes must contain only finite real numbers")
        normalized_closes.append(float(close))
    closes = normalized_closes

    for swing in swings:
        if swing.kind not in {"high", "low"}:
            raise ValueError("swing kind must be 'high' or 'low'")
        if (
            isinstance(swing.index, bool) or not isinstance(swing.index, int)
            or isinstance(swing.confirmation_index, bool)
            or not isinstance(swing.confirmation_index, int)
            or swing.index < 0 or swing.confirmation_index < swing.index
        ):
            raise ValueError("swing indices must be valid non-negative integers")
        if isinstance(swing.price, bool) or not isinstance(swing.price, Real) or not isfinite(float(swing.price)):
            raise ValueError("swing price must be a finite real number")
        if swing.confirmation_index >= len(closes):
            # It is valid to pass future/unconfirmed swings; they are ignored.
            continue

    direction: str | None = None
    broken: set[int] = set()
    events: list[StructureBreak] = []

    for candle_index, close in enumerate(closes):
        # A level already crossed before its confirmation was knowable must
        # not create a delayed, false break event when price stays beyond it.
        if candle_index > 0:
            previous_close = closes[candle_index - 1]
            for position, swing in enumerate(swings):
                if swing.confirmation_index != candle_index or position in broken:
                    continue
                if (swing.kind == "high" and previous_close > swing.price) or (
                    swing.kind == "low" and previous_close < swing.price
                ):
                    broken.add(position)

        eligible = [
            (position, swing)
            for position, swing in enumerate(swings)
            if swing.confirmation_index <= candle_index and position not in broken
        ]
        previous_close = closes[candle_index - 1] if candle_index > 0 else None
        highs = [
            (position, swing) for position, swing in eligible
            if swing.kind == "high" and close > swing.price
            and previous_close is not None and previous_close <= swing.price
        ]
        lows = [
            (position, swing) for position, swing in eligible
            if swing.kind == "low" and close < swing.price
            and previous_close is not None and previous_close >= swing.price
        ]

        # Prefer the most recently confirmed crossed swing on each side.
        candidates = []
        if highs:
            candidates.append(max(highs, key=lambda item: (item[1].confirmation_index, item[1].index)))
        if lows:
            candidates.append(max(lows, key=lambda item: (item[1].confirmation_index, item[1].index)))
        if not candidates:
            continue

        # A single candle may not generate two opposing structure events.
        position, swing = max(candidates, key=lambda item: (item[1].confirmation_index, item[1].index))
        break_direction = "bullish" if swing.kind == "high" else "bearish"
        kind = "BOS" if direction is None or direction == break_direction else "CHoCH"
        events.append(StructureBreak(
            kind=kind,
            direction=break_direction,
            candle_index=candle_index,
            swing_index=swing.index,
            level=float(swing.price),
        ))
        direction = break_direction
        broken.add(position)

    return tuple(events)
