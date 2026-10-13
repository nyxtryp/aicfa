"""Pure risk/reward and tick-size-safe entry limits for TZ §6–7."""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from math import isfinite
from numbers import Real


def _number(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)


def calculate_risk_reward(direction: str, entry: float, stop: float, target: float) -> float:
    """Calculate positive R multiple for a directional entry, stop and TP."""
    entry = _number("entry", entry)
    stop = _number("stop", stop)
    target = _number("target", target)
    if direction == "long":
        risk, reward = entry - stop, target - entry
    elif direction == "short":
        risk, reward = stop - entry, entry - target
    else:
        raise ValueError("direction must be 'long' or 'short'")
    if risk <= 0 or reward <= 0:
        raise ValueError("prices must satisfy stop < entry < target for long or target < entry < stop for short")
    return reward / risk


def acceptable_entry_limit(
    direction: str,
    target: float,
    stop: float,
    *,
    min_rr: float = 1.5,
    tick_size: float,
) -> float:
    """Return the tick-rounded boundary that preserves at least min_rr.

    For LONG this is the highest acceptable entry (round down). For SHORT it
    is the lowest acceptable entry (round up). TP and SL are prices, not
    distances. Call calculate_risk_reward again after tick rounding.
    """
    target = _number("target", target)
    stop = _number("stop", stop)
    min_rr = _number("min_rr", min_rr)
    tick_size = _number("tick_size", tick_size)
    if min_rr <= 0 or tick_size <= 0:
        raise ValueError("min_rr and tick_size must be > 0")
    if direction == "long":
        if target <= stop:
            raise ValueError("long target must be above stop")
        rounding = ROUND_FLOOR
    elif direction == "short":
        if stop <= target:
            raise ValueError("short stop must be above target")
        rounding = ROUND_CEILING
    else:
        raise ValueError("direction must be 'long' or 'short'")

    raw = (Decimal(str(target)) + Decimal(str(min_rr)) * Decimal(str(stop))) / (
        Decimal(1) + Decimal(str(min_rr))
    )
    tick = Decimal(str(tick_size))
    rounded = (raw / tick).to_integral_value(rounding=rounding) * tick
    result = float(rounded)
    # A tick-rounded limit must still lie strictly between stop and target.
    if direction == "long" and not stop < result < target:
        raise ValueError("no valid long entry limit for the supplied prices and tick size")
    if direction == "short" and not target < result < stop:
        raise ValueError("no valid short entry limit for the supplied prices and tick size")
    return result
