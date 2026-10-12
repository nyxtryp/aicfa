"""Order Block zones derived from confirmed BOS/CHoCH events."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.smc.breaks import StructureBreak


@dataclass(frozen=True, slots=True)
class OrderBlock:
    direction: str
    candle_index: int
    confirmation_index: int
    lower: float
    upper: float
    source_kind: str
    source_swing_index: int


def find_order_blocks(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    events: Sequence[StructureBreak],
) -> tuple[OrderBlock, ...]:
    """Find the last opposing candle between the broken swing and break candle.

    For a bullish break, the OB is the last bearish candle after the referenced
    swing candle and before the break candle; bearish breaks use the last
    bullish candle. The zone is the candle body, not its wick. An OB is only
    emitted when the source break candle exists in the supplied closed-candle
    data. This deterministic window avoids searching unrelated older candles.
    """
    lengths = {len(opens), len(highs), len(lows), len(closes)}
    if len(lengths) != 1:
        raise ValueError("OHLC arrays must have the same length")
    if any(high < low or high < open_ or high < close or low > open_ or low > close
           for open_, high, low, close in zip(opens, highs, lows, closes)):
        raise ValueError("OHLC candle values are inconsistent")

    result: list[OrderBlock] = []
    emitted: set[tuple[str, int, int]] = set()
    for event in events:
        if event.direction not in {"bullish", "bearish"}:
            raise ValueError("event direction must be bullish or bearish")
        if event.candle_index < 0 or event.candle_index >= len(closes):
            continue
        start = max(0, event.swing_index + 1)
        end = event.candle_index
        if start >= end:
            continue

        candidate: int | None = None
        for index in range(start, end):
            bearish_candle = closes[index] < opens[index]
            bullish_candle = closes[index] > opens[index]
            if event.direction == "bullish" and bearish_candle:
                candidate = index
            elif event.direction == "bearish" and bullish_candle:
                candidate = index

        if candidate is None:
            continue
        identity = (event.direction, candidate, event.candle_index)
        if identity in emitted:
            continue
        emitted.add(identity)
        result.append(OrderBlock(
            direction=event.direction,
            candle_index=candidate,
            confirmation_index=event.candle_index,
            lower=float(min(opens[candidate], closes[candidate])),
            upper=float(max(opens[candidate], closes[candidate])),
            source_kind=event.kind,
            source_swing_index=event.swing_index,
        ))

    return tuple(result)


def is_order_block_mitigated(block: OrderBlock, close: float) -> bool:
    """A block is mitigated after a close beyond its far edge."""
    if block.direction == "bullish":
        return close < block.lower
    if block.direction == "bearish":
        return close > block.upper
    raise ValueError("block direction must be bullish or bearish")
