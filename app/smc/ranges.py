"""Premium/Discount and OTE derived from confirmed swing legs only."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from typing import Sequence

from app.smc.structure import SwingPoint


@dataclass(frozen=True, slots=True)
class DealingRange:
    direction: str
    start_index: int
    end_index: int
    confirmation_index: int
    low: float
    high: float
    equilibrium: float
    ote_lower: float
    ote_upper: float


def find_dealing_range(
    swings: Sequence[SwingPoint],
    *,
    as_of_index: int,
    ote_min: float = 0.62,
    ote_max: float = 0.79,
    direction: str | None = None,
) -> DealingRange | None:
    """Return the latest alternating confirmed swing leg available as of index.

    Consecutive swings of the same kind collapse to the more extreme point
    (highest high or lowest low). No swing can participate before its
    confirmation_index. OTE bounds are the 62%-79% retracement of the impulse.
    """
    if isinstance(as_of_index, bool) or not isinstance(as_of_index, Integral) or as_of_index < 0:
        raise ValueError("as_of_index must be a non-negative integer")
    if not (0 < ote_min < ote_max < 1):
        raise ValueError("OTE bounds must satisfy 0 < ote_min < ote_max < 1")
    if direction not in (None, "bullish", "bearish"):
        raise ValueError("direction must be None, 'bullish', or 'bearish'")

    if any(
        isinstance(s.index, bool) or not isinstance(s.index, Integral)
        or isinstance(s.confirmation_index, bool)
        or not isinstance(s.confirmation_index, Integral)
        or s.index < 0 or s.confirmation_index < s.index
        for s in swings
    ):
        raise ValueError("swing indices must be integers satisfying 0 <= index <= confirmation_index")
    if any(s.kind not in {"high", "low"} for s in swings):
        raise ValueError("swing kind must be 'high' or 'low'")
    if any(not isfinite(s.price) for s in swings):
        raise ValueError("swing prices must be finite")
    available = sorted(
        (s for s in swings if s.confirmation_index <= as_of_index),
        key=lambda s: (s.confirmation_index, s.index),
    )

    collapsed: list[SwingPoint] = []
    for swing in available:
        if not collapsed or collapsed[-1].kind != swing.kind:
            collapsed.append(swing)
            continue
        previous = collapsed[-1]
        more_extreme = (
            swing.price > previous.price if swing.kind == "high"
            else swing.price < previous.price
        )
        if more_extreme:
            collapsed[-1] = swing

    if len(collapsed) < 2:
        return None
    # OTE must be measured on an impulse aligned with the HTF structure bias.
    # The newest confirmed leg may be a countertrend pullback; using it as the
    # entry impulse reverses the OTE side and silently filters valid setups.
    pair = None
    for end_position in range(len(collapsed) - 1, 0, -1):
        candidate_start, candidate_end = collapsed[end_position - 1], collapsed[end_position]
        if candidate_start.kind == candidate_end.kind:
            continue
        candidate_direction = (
            "bullish" if candidate_start.kind == "low" and candidate_end.kind == "high"
            else "bearish"
        )
        if direction is None or candidate_direction == direction:
            pair = (candidate_start, candidate_end)
            break
    if pair is None:
        return None
    start, end = pair

    if start.kind == "low" and end.kind == "high":
        direction = "bullish"
        low, high = float(start.price), float(end.price)
        ote_lower = high - (high - low) * ote_max
        ote_upper = high - (high - low) * ote_min
    elif start.kind == "high" and end.kind == "low":
        direction = "bearish"
        low, high = float(end.price), float(start.price)
        ote_lower = low + (high - low) * ote_min
        ote_upper = low + (high - low) * ote_max
    else:
        return None

    if high <= low:
        return None
    return DealingRange(
        direction=direction,
        start_index=start.index,
        end_index=end.index,
        confirmation_index=max(start.confirmation_index, end.confirmation_index),
        low=low,
        high=high,
        equilibrium=(low + high) / 2,
        ote_lower=float(ote_lower),
        ote_upper=float(ote_upper),
    )


def premium_discount(price: float, dealing_range: DealingRange) -> str:
    """Classify price relative to the 50% equilibrium of the current leg."""
    if price < dealing_range.equilibrium:
        return "discount"
    if price > dealing_range.equilibrium:
        return "premium"
    return "equilibrium"
