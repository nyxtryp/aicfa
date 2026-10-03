from __future__ import annotations

import pandas as pd
import pytest

from aicfa.evaluation import (
    EvaluationOutcome,
    build_chronological_folds,
    evaluate_setup,
    evaluate_setups,
    purge_training_labels,
)


def candles(rows: list[tuple[float, float, float]]) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=len(rows), freq="min", tz="UTC")
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [o for o, _, _ in rows],
        "high": [h for _, h, _ in rows],
        "low": [l for _, _, l in rows],
        "close": [o for o, _, _ in rows],
    })


def test_long_tp_hit_before_sl() -> None:
    result = evaluate_setup(candles([(100, 101, 99), (100, 106, 99)]),
        setup_timestamp="2026-01-01T00:00:00Z", direction="long",
        entry_price=100, stop_price=95, target_price=105)
    assert result.outcome is EvaluationOutcome.TP
    assert result.outcome_offset == 1
    assert result.exit_price == 105


def test_long_sl_hit_before_tp() -> None:
    result = evaluate_setup(candles([(100, 101, 99), (100, 101, 94), (100, 106, 99)]),
        setup_timestamp="2026-01-01T00:00:00Z", direction="long",
        entry_price=100, stop_price=95, target_price=105)
    assert result.outcome is EvaluationOutcome.SL


def test_same_bar_tp_and_sl_is_ambiguous() -> None:
    result = evaluate_setup(candles([(100, 101, 99), (100, 106, 94)]),
        setup_timestamp="2026-01-01T00:00:00Z", direction="long",
        entry_price=100, stop_price=95, target_price=105)
    assert result.outcome is EvaluationOutcome.AMBIGUOUS
    assert result.outcome_offset == 1
    assert result.exit_price is None


def test_timeout_is_explicit_and_does_not_guess_winner() -> None:
    result = evaluate_setup(candles([(100, 101, 99), (100, 103, 98), (100, 104, 97)]),
        setup_timestamp="2026-01-01T00:00:00Z", direction="long",
        entry_price=100, stop_price=95, target_price=105, max_horizon=2)
    assert result.outcome is EvaluationOutcome.TIMEOUT
    assert result.outcome_offset == 2
    assert result.exit_price is None


def test_short_is_symmetric() -> None:
    result = evaluate_setup(candles([(100, 101, 99), (100, 101, 94)]),
        setup_timestamp="2026-01-01T00:00:00Z", direction="short",
        entry_price=100, stop_price=105, target_price=95)
    assert result.outcome is EvaluationOutcome.TP
    assert result.exit_price == 95


def test_future_rows_before_setup_are_not_used() -> None:
    frame = candles([(100, 101, 99), (100, 106, 99), (100, 101, 94)])
    frame.loc[0, "timestamp"] = pd.Timestamp("2026-01-01T00:00:00Z")
    frame.loc[1, "timestamp"] = pd.Timestamp("2025-12-31T23:59:00Z")
    frame.loc[2, "timestamp"] = pd.Timestamp("2026-01-01T00:01:00Z")
    result = evaluate_setup(frame, setup_timestamp="2026-01-01T00:00:00Z",
        direction="long", entry_price=100, stop_price=95, target_price=105)
    assert result.outcome is EvaluationOutcome.SL


def test_invalid_geometry_is_rejected() -> None:
    with pytest.raises(ValueError, match="entry"):
        evaluate_setup(candles([(100, 101, 99), (100, 106, 94)]),
            setup_timestamp="2026-01-01T00:00:00Z", direction="long",
            entry_price=100, stop_price=105, target_price=95)


def test_batch_evaluation_returns_individual_results_and_counts() -> None:
    setups = [
        {
            "setup_timestamp": "2026-01-01T00:00:00Z",
            "direction": "long",
            "entry_price": 100,
            "stop_price": 95,
            "target_price": 105,
        },
        {
            "setup_timestamp": "2026-01-01T00:01:00Z",
            "direction": "short",
            "entry_price": 100,
            "stop_price": 105,
            "target_price": 95,
        },
    ]
    result = evaluate_setups(
        candles([(100, 101, 99), (100, 106, 99), (100, 101, 94), (100, 101, 94)]),
        setups,
    )
    assert [item.outcome for item in result.results] == [
        EvaluationOutcome.TP, EvaluationOutcome.TP
    ]
    assert result.counts == {
        EvaluationOutcome.TP.value: 2,
        EvaluationOutcome.SL.value: 0,
        EvaluationOutcome.TIMEOUT.value: 0,
        EvaluationOutcome.AMBIGUOUS.value: 0,
    }
    assert result.resolved_count == 2
    assert result.tp_rate == 1.0
    assert result.mean_gross_return > 0


def test_batch_statistics_do_not_treat_ambiguous_as_resolved() -> None:
    setups = [{
        "setup_timestamp": "2026-01-01T00:00:00Z",
        "direction": "long",
        "entry_price": 100,
        "stop_price": 95,
        "target_price": 105,
    }]
    result = evaluate_setups(
        candles([(100, 101, 99), (100, 106, 94)]),
        setups,
    )
    assert result.resolved_count == 0
    assert result.tp_rate is None
    assert result.mean_gross_return is None


def test_purge_removes_training_labels_reaching_validation_start() -> None:
    start = pd.Timestamp("2026-01-01T00:03:00Z")
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z",
            "2026-01-01T00:02:00Z", "2026-01-01T00:03:00Z",
        ]),
        "label_end_timestamp_5": pd.to_datetime([
            "2026-01-01T00:02:00Z", "2026-01-01T00:03:00Z",
            "2026-01-01T00:04:00Z", "2026-01-01T00:05:00Z",
        ]),
    })
    purged = purge_training_labels(frame, validation_start=start)
    assert purged["timestamp"].tolist() == [
        pd.Timestamp("2026-01-01T00:00:00Z")
    ]


def test_purge_requires_label_end_column_and_drops_missing_intervals() -> None:
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime([
            "2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"
        ]),
        "label_end_timestamp_5": pd.to_datetime([
            "2026-01-01T00:02:00Z", None
        ]),
    })
    with pytest.raises(ValueError, match="label end"):
        purge_training_labels(frame, validation_start="2026-01-01T00:03:00Z",
            label_end_column="missing")
    purged = purge_training_labels(frame, validation_start="2026-01-01T00:03:00Z")
    assert len(purged) == 1


def test_chronological_folds_are_forward_only_and_purged() -> None:
    timestamps = pd.date_range("2026-01-01", periods=8, freq="min", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": timestamps,
        "feature": range(8),
        "label_end_timestamp_5": timestamps + pd.to_timedelta(
            [1, 1, 1, 2, 2, 1, 1, 1], unit="min"
        ),
    })
    folds = build_chronological_folds(frame, validation_size=2, n_splits=2)

    assert len(folds) == 2
    train_0, validation_0 = folds[0]
    train_1, validation_1 = folds[1]

    assert validation_0["timestamp"].tolist() == list(timestamps[4:6])
    assert validation_1["timestamp"].tolist() == list(timestamps[6:8])
    assert train_0["timestamp"].max() < validation_0["timestamp"].min()
    assert train_1["timestamp"].max() < validation_1["timestamp"].min()
    assert train_0["timestamp"].tolist() == list(timestamps[:2])
    assert train_1["timestamp"].tolist() == list(timestamps[:4])


def test_chronological_folds_purge_labels_touching_validation_start() -> None:
    timestamps = pd.date_range("2026-01-01", periods=6, freq="min", tz="UTC")
    frame = pd.DataFrame({
        "timestamp": timestamps,
        "label_end_timestamp_5": [
            timestamps[0], timestamps[1], timestamps[2], timestamps[3],
            timestamps[4], timestamps[5],
        ],
    })
    folds = build_chronological_folds(frame, validation_size=2, n_splits=1)
    train, validation = folds[0]

    assert validation["timestamp"].tolist() == list(timestamps[4:6])
    assert train["timestamp"].tolist() == list(timestamps[:4])
    assert train["label_end_timestamp_5"].max() < validation["timestamp"].min()


def test_chronological_folds_reject_invalid_window_sizes() -> None:
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="min", tz="UTC"),
        "label_end_timestamp_5": pd.date_range("2026-01-01", periods=4, freq="min", tz="UTC"),
    })
    with pytest.raises(ValueError, match="validation_size"):
        build_chronological_folds(frame, validation_size=0, n_splits=1)
    with pytest.raises(ValueError, match="n_splits"):
        build_chronological_folds(frame, validation_size=1, n_splits=0)
    with pytest.raises(ValueError, match="rows"):
        build_chronological_folds(frame, validation_size=3, n_splits=2)
