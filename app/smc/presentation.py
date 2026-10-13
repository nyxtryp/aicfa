"""Chart-ready, timestamped serialization of causal SMC snapshots."""
from __future__ import annotations

from numbers import Integral
from typing import Sequence

from app.smc.engine import SMCAnalysis


def to_chart_payload(
    analysis: SMCAnalysis,
    timestamps_ms: Sequence[int],
) -> dict[str, object]:
    """Convert index-based SMC events into a stable time/price chart payload.

    Only timestamps through analysis.as_of_index are exposed. This function
    serializes analysis; it does not recompute detectors or generate signals.
    """
    end = analysis.as_of_index
    if end < 0 or end >= len(timestamps_ms):
        raise ValueError("analysis index is outside the supplied timestamps")
    raw_timestamps = timestamps_ms[:end + 1]
    if any(isinstance(value, bool) or not isinstance(value, Integral) for value in raw_timestamps):
        raise ValueError("timestamps must be integer milliseconds")
    timestamps = tuple(int(value) for value in raw_timestamps)
    if any(timestamps[i] >= timestamps[i + 1] for i in range(len(timestamps) - 1)):
        raise ValueError("timestamps must be strictly increasing")
    if len(analysis.order_blocks) != len(analysis.order_block_mitigation):
        raise ValueError("order block mitigation states must align with order blocks")
    if len(analysis.fvg) != len(analysis.fvg_fill):
        raise ValueError("FVG fill states must align with FVG zones")

    def stamp(index: int) -> int:
        if index < 0 or index > end:
            raise ValueError("event index is outside the analysis snapshot")
        return timestamps[index]

    swings = [{
        "kind": item.kind,
        "index": item.index,
        "timestamp_ms": stamp(item.index),
        "confirmation_index": item.confirmation_index,
        "confirmation_timestamp_ms": stamp(item.confirmation_index),
        "price": item.price,
    } for item in analysis.swings]

    breaks = [{
        "kind": item.kind,
        "direction": item.direction,
        "candle_index": item.candle_index,
        "timestamp_ms": stamp(item.candle_index),
        "swing_index": item.swing_index,
        "swing_timestamp_ms": stamp(item.swing_index),
        "level": item.level,
    } for item in analysis.structure_breaks]

    blocks = []
    for block, state in zip(analysis.order_blocks, analysis.order_block_mitigation):
        blocks.append({
            "direction": block.direction,
            "candle_index": block.candle_index,
            "timestamp_ms": stamp(block.candle_index),
            "confirmation_index": block.confirmation_index,
            "confirmation_timestamp_ms": stamp(block.confirmation_index),
            "lower": block.lower,
            "upper": block.upper,
            "source_kind": block.source_kind,
            "source_swing_index": block.source_swing_index,
            "mitigated": state.mitigated,
            "mitigation_index": state.mitigation_index,
            "mitigation_timestamp_ms": (
                stamp(state.mitigation_index) if state.mitigation_index is not None else None
            ),
        })

    gaps = []
    for gap, fill in zip(analysis.fvg, analysis.fvg_fill):
        gaps.append({
            "direction": gap.direction,
            "first_candle_index": gap.first_candle_index,
            "first_timestamp_ms": stamp(gap.first_candle_index),
            "confirmation_index": gap.confirmation_index,
            "confirmation_timestamp_ms": stamp(gap.confirmation_index),
            "lower": gap.lower,
            "upper": gap.upper,
            "fill_percent": fill.fill_percent,
            "fully_filled": fill.fully_filled,
        })

    levels = [{
        "kind": level.kind,
        "price": level.price,
        "source_indices": list(level.source_indices),
        "source_timestamps_ms": [stamp(index) for index in level.source_indices],
        "confirmation_index": level.confirmation_index,
        "confirmation_timestamp_ms": stamp(level.confirmation_index),
        "equal_level": level.equal_level,
    } for level in analysis.liquidity_levels]

    sweeps = [{
        "direction": sweep.direction,
        "candle_index": sweep.candle_index,
        "timestamp_ms": stamp(sweep.candle_index),
        "level": sweep.level,
        "level_kind": sweep.level_kind,
        "source_indices": list(sweep.source_indices),
        "source_timestamps_ms": [stamp(index) for index in sweep.source_indices],
    } for sweep in analysis.sweeps]

    dealing_range = None
    if analysis.dealing_range is not None:
        item = analysis.dealing_range
        dealing_range = {
            "direction": item.direction,
            "start_index": item.start_index,
            "start_timestamp_ms": stamp(item.start_index),
            "end_index": item.end_index,
            "end_timestamp_ms": stamp(item.end_index),
            "confirmation_index": item.confirmation_index,
            "confirmation_timestamp_ms": stamp(item.confirmation_index),
            "low": item.low,
            "high": item.high,
            "equilibrium": item.equilibrium,
            "ote_lower": item.ote_lower,
            "ote_upper": item.ote_upper,
        }

    return {
        "as_of_index": end,
        "as_of_timestamp_ms": timestamps[end],
        "swings": swings,
        "structure_breaks": breaks,
        "order_blocks": blocks,
        "fvg": gaps,
        "liquidity_levels": levels,
        "sweeps": sweeps,
        "dealing_range": dealing_range,
        "premium_discount": analysis.premium_discount,
        "atr": analysis.atr[end],
        "average_volume": analysis.average_volume[end],
    }
