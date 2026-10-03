"""Conservative, causal evaluation of one already-defined setup.

This module evaluates historical OHLC after a setup timestamp. It does not
create Entry/SL/TP levels and does not infer intrabar ordering when both
barriers are touched by the same candle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


class EvaluationOutcome(str, Enum):
    TP = "tp"
    SL = "sl"
    TIMEOUT = "timeout"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class SetupEvaluation:
    outcome: EvaluationOutcome
    outcome_offset: int
    exit_price: float | None
    gross_return: float | None


def _validate_geometry(direction: str, entry_price: float, stop_price: float, target_price: float) -> None:
    if direction not in {"long", "short"}:
        raise ValueError("direction must be 'long' or 'short'")
    if direction == "long":
        if not stop_price < entry_price < target_price:
            raise ValueError("long entry geometry requires stop < entry < target")
    else:
        if not target_price < entry_price < stop_price:
            raise ValueError("short entry geometry requires target < entry < stop")


def evaluate_setup(
    candles: pd.DataFrame,
    *,
    setup_timestamp: str | pd.Timestamp,
    direction: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    max_horizon: int | None = None,
) -> SetupEvaluation:
    """Evaluate TP/SL/timeout from the first candle strictly after setup time.

    The caller supplies already-established Entry/SL/TP levels. Historical
    candles are used only after the setup timestamp. If one candle touches
    both TP and SL, the result is AMBIGUOUS because OHLC does not reveal
    which level was reached first.

    max_horizon counts future candles after setup time. If omitted, all
    available future candles are evaluated.
    """
    _validate_geometry(direction, float(entry_price), float(stop_price), float(target_price))

    if max_horizon is not None and max_horizon <= 0:
        raise ValueError("max_horizon must be positive")
    required = {"timestamp", "high", "low"}
    missing = required.difference(candles.columns)
    if missing:
        raise ValueError(f"candles missing required columns: {sorted(missing)}")

    frame = candles.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    frame = frame.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    setup_time = pd.to_datetime(setup_timestamp, utc=True)
    future = frame.loc[frame["timestamp"] > setup_time].reset_index(drop=True)

    if max_horizon is not None:
        future = future.iloc[:max_horizon]

    if future.empty:
        raise ValueError("no future candles exist after setup_timestamp")

    for offset, row in enumerate(future.itertuples(index=False), start=1):
        high = float(row.high)
        low = float(row.low)

        if direction == "long":
            hit_target = high >= target_price
            hit_stop = low <= stop_price
        else:
            hit_target = low <= target_price
            hit_stop = high >= stop_price

        if hit_target and hit_stop:
            return SetupEvaluation(EvaluationOutcome.AMBIGUOUS, offset, None, None)

        if hit_target:
            gross_return = target_price / entry_price - 1.0
            if direction == "short":
                gross_return = entry_price / target_price - 1.0
            return SetupEvaluation(EvaluationOutcome.TP, offset, float(target_price), float(gross_return))

        if hit_stop:
            gross_return = stop_price / entry_price - 1.0
            if direction == "short":
                gross_return = entry_price / stop_price - 1.0
            return SetupEvaluation(EvaluationOutcome.SL, offset, float(stop_price), float(gross_return))

    return SetupEvaluation(EvaluationOutcome.TIMEOUT, len(future), None, None)
