"""Conservative, causal evaluation of already-defined setups.

This module evaluates historical OHLC after setup timestamps. It does not
create Entry/SL/TP levels and does not infer intrabar ordering when both
barriers are touched by the same candle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

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


@dataclass(frozen=True)
class BatchEvaluation:
    results: tuple[SetupEvaluation, ...]
    counts: dict[str, int]
    resolved_count: int
    tp_rate: float | None
    mean_gross_return: float | None


@dataclass(frozen=True)
class RRObservation:
    rr: float
    outcome: EvaluationOutcome


@dataclass(frozen=True)
class RRAnalysis:
    observations: tuple[RRObservation, ...]
    resolved_count: int
    tp_count: int
    mean_rr: float | None


def _validate_geometry(direction: str, entry_price: float, stop_price: float, target_price: float) -> None:
    if direction not in {"long", "short"}:
        raise ValueError("direction must be 'long' or 'short'")
    if direction == "long":
        if not stop_price < entry_price < target_price:
            raise ValueError("long entry geometry requires stop < entry < target")
    else:
        if not target_price < entry_price < stop_price:
            raise ValueError("short entry geometry requires target < entry < stop")


def _risk_reward(direction: str, entry_price: float, stop_price: float, target_price: float) -> float:
    _validate_geometry(direction, entry_price, stop_price, target_price)
    if direction == "long":
        return (target_price - entry_price) / (entry_price - stop_price)
    return (entry_price - target_price) / (stop_price - entry_price)


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
    """Evaluate TP/SL/timeout from the first candle strictly after setup time."""
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


def evaluate_setups(
    candles: pd.DataFrame,
    setups: Sequence[Mapping[str, object]],
    *,
    max_horizon: int | None = None,
) -> BatchEvaluation:
    """Evaluate multiple already-defined setups and summarize resolved outcomes."""
    results = tuple(
        evaluate_setup(
            candles,
            setup_timestamp=setup["setup_timestamp"],
            direction=str(setup["direction"]),
            entry_price=float(setup["entry_price"]),
            stop_price=float(setup["stop_price"]),
            target_price=float(setup["target_price"]),
            max_horizon=max_horizon,
        )
        for setup in setups
    )
    counts = {outcome.value: 0 for outcome in EvaluationOutcome}
    for result in results:
        counts[result.outcome.value] += 1

    resolved = [result for result in results if result.outcome in {
        EvaluationOutcome.TP, EvaluationOutcome.SL
    }]
    tp_results = [result for result in resolved if result.outcome is EvaluationOutcome.TP]
    mean_return = (
        sum(result.gross_return for result in resolved) / len(resolved)
        if resolved else None
    )
    return BatchEvaluation(
        results=results,
        counts=counts,
        resolved_count=len(resolved),
        tp_rate=len(tp_results) / len(resolved) if resolved else None,
        mean_gross_return=mean_return,
    )


def analyze_rr_outcomes(
    setups: Sequence[Mapping[str, object]],
    evaluation: BatchEvaluation,
) -> RRAnalysis:
    """Relate derived structural RR to already-observed causal outcomes."""
    if len(setups) != len(evaluation.results):
        raise ValueError("setups and evaluation must contain the same number of results")

    observations: list[RRObservation] = []
    for setup, result in zip(setups, evaluation.results):
        rr = _risk_reward(
            str(setup["direction"]),
            float(setup["entry_price"]),
            float(setup["stop_price"]),
            float(setup["target_price"]),
        )
        observations.append(RRObservation(rr=rr, outcome=result.outcome))

    resolved = [
        observation for observation in observations
        if observation.outcome in {EvaluationOutcome.TP, EvaluationOutcome.SL}
    ]
    return RRAnalysis(
        observations=tuple(observations),
        resolved_count=len(resolved),
        tp_count=sum(
            observation.outcome is EvaluationOutcome.TP
            for observation in resolved
        ),
        mean_rr=(
            sum(observation.rr for observation in resolved) / len(resolved)
            if resolved else None
        ),
    )


def analyze_rr_outcomes_by_folds(
    folds: Sequence[tuple[Sequence[Mapping[str, object]], BatchEvaluation]],
) -> tuple[RRAnalysis, ...]:
    """Analyze RR against observed outcomes independently for each causal fold.

    Fold boundaries are preserved: observations from one chronological
    validation fold are never mixed into another fold's analysis.
    """
    analyses: list[RRAnalysis] = []
    for setups, evaluation in folds:
        analyses.append(analyze_rr_outcomes(setups, evaluation))
    return tuple(analyses)


def purge_training_labels(
    dataset: pd.DataFrame,
    *,
    validation_start: str | pd.Timestamp,
    label_end_column: str = "label_end_timestamp_5",
) -> pd.DataFrame:
    """Remove training rows whose future label reaches validation_start."""
    if "timestamp" not in dataset.columns:
        raise ValueError("dataset must contain timestamp")
    if label_end_column not in dataset.columns:
        raise ValueError(f"dataset missing label end column: {label_end_column}")

    frame = dataset.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    ends = pd.to_datetime(frame[label_end_column], utc=True, errors="coerce")
    validation_time = pd.to_datetime(validation_start, utc=True)

    safe = (
        frame["timestamp"].lt(validation_time)
        & ends.notna()
        & ends.lt(validation_time)
    )
    return frame.loc[safe].reset_index(drop=True)


def build_chronological_folds(
    dataset: pd.DataFrame,
    *,
    validation_size: int,
    n_splits: int,
    label_end_column: str = "label_end_timestamp_5",
) -> tuple[tuple[pd.DataFrame, pd.DataFrame], ...]:
    """Build expanding chronological validation folds with causal purging."""
    if validation_size <= 0:
        raise ValueError("validation_size must be positive")
    if n_splits <= 0:
        raise ValueError("n_splits must be positive")
    if "timestamp" not in dataset.columns:
        raise ValueError("dataset must contain timestamp")
    if label_end_column not in dataset.columns:
        raise ValueError(f"dataset missing label end column: {label_end_column}")

    frame = dataset.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if frame["timestamp"].duplicated().any():
        raise ValueError("dataset contains duplicate timestamps")
    frame = frame.sort_values("timestamp").reset_index(drop=True)

    required_rows = validation_size * n_splits
    if len(frame) <= required_rows:
        raise ValueError("dataset does not contain enough rows for requested validation windows")

    validation_start_index = len(frame) - required_rows
    folds: list[tuple[pd.DataFrame, pd.DataFrame]] = []

    for fold_index in range(n_splits):
        start = validation_start_index + fold_index * validation_size
        end = start + validation_size
        validation = frame.iloc[start:end].reset_index(drop=True)
        training = frame.iloc[:start].reset_index(drop=True)
        training = purge_training_labels(
            training,
            validation_start=validation["timestamp"].iloc[0],
            label_end_column=label_end_column,
        )
        folds.append((training, validation))

    return tuple(folds)
