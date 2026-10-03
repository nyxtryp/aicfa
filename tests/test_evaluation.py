from __future__ import annotations

import pandas as pd
import pytest

from aicfa.evaluation import (
    BatchEvaluation,
    EvaluationOutcome,
    analyze_rr_outcomes,
    analyze_rr_outcomes_by_folds,
    build_chronological_folds,
    evaluate_setup,
    evaluate_setups,
    purge_training_labels,
    summarize_outcomes_by_folds,
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
        {"setup_timestamp": "2026-01-01T00:00:00Z", "direction": "long", "entry_price": 100, "stop_price": 95, "target_price": 105},
        {"setup_timestamp": "2026-01-01T00:01:00Z", "direction": "short", "entry_price": 100, "stop_price": 105, "target_price": 95},
    ]
    result = evaluate_setups(candles([(100, 101, 99), (100, 106, 99), (100, 101, 94), (100, 101, 94)]), setups)
    assert [item.outcome for item in result.results] == [EvaluationOutcome.TP, EvaluationOutcome.TP]
    assert result.counts == {EvaluationOutcome.TP.value: 2, EvaluationOutcome.SL.value: 0, EvaluationOutcome.TIMEOUT.value: 0, EvaluationOutcome.AMBIGUOUS.value: 0}
    assert result.resolved_count == 2
    assert result.tp_rate == 1.0
    assert result.mean_gross_return > 0


def test_batch_statistics_do_not_treat_ambiguous_as_resolved() -> None:
    setups = [{"setup_timestamp": "2026-01-01T00:00:00Z", "direction": "long", "entry_price": 100, "stop_price": 95, "target_price": 105}]
    result = evaluate_setups(candles([(100, 101, 99), (100, 106, 94)]), setups)
    assert result.resolved_count == 0
    assert result.tp_rate is None
    assert result.mean_gross_return is None


def test_purge_removes_training_labels_reaching_validation_start() -> None:
    start = pd.Timestamp("2026-01-01T00:03:00Z")
    frame = pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z", "2026-01-01T00:02:00Z", "2026-01-01T00:03:00Z"]), "label_end_timestamp_5": pd.to_datetime(["2026-01-01T00:02:00Z", "2026-01-01T00:03:00Z", "2026-01-01T00:04:00Z", "2026-01-01T00:05:00Z"])})
    purged = purge_training_labels(frame, validation_start=start)
    assert purged["timestamp"].tolist() == [pd.Timestamp("2026-01-01T00:00:00Z")]


def test_purge_requires_label_end_column_and_drops_missing_intervals() -> None:
    frame = pd.DataFrame({"timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:01:00Z"]), "label_end_timestamp_5": pd.to_datetime(["2026-01-01T00:02:00Z", None])})
    with pytest.raises(ValueError, match="label end"):
        purge_training_labels(frame, validation_start="2026-01-01T00:03:00Z", label_end_column="missing")
    purged = purge_training_labels(frame, validation_start="2026-01-01T00:03:00Z")
    assert len(purged) == 1


def test_chronological_folds_are_forward_only_and_purged() -> None:
    timestamps = pd.date_range("2026-01-01", periods=8, freq="min", tz="UTC")
    frame = pd.DataFrame({"timestamp": timestamps, "feature": range(8), "label_end_timestamp_5": timestamps + pd.to_timedelta([1, 1, 1, 2, 2, 1, 1, 1], unit="min")})
    folds = build_chronological_folds(frame, validation_size=2, n_splits=2)
    assert len(folds) == 2
    train_0, validation_0 = folds[0]
    train_1, validation_1 = folds[1]
    assert validation_0["timestamp"].tolist() == list(timestamps[4:6])
    assert validation_1["timestamp"].tolist() == list(timestamps[6:8])
    assert train_0["timestamp"].max() < validation_0["timestamp"].min()
    assert train_1["timestamp"].max() < validation_1["timestamp"].min()
    assert train_0["timestamp"].tolist() == list(timestamps[:3])
    assert train_1["timestamp"].tolist() == list(timestamps[:4])


def test_chronological_folds_purge_labels_touching_validation_start() -> None:
    timestamps = pd.date_range("2026-01-01", periods=6, freq="min", tz="UTC")
    frame = pd.DataFrame({"timestamp": timestamps, "label_end_timestamp_5": [timestamps[0], timestamps[1], timestamps[2], timestamps[3], timestamps[4], timestamps[5]]})
    folds = build_chronological_folds(frame, validation_size=2, n_splits=1)
    train, validation = folds[0]
    assert validation["timestamp"].tolist() == list(timestamps[4:6])
    assert train["timestamp"].tolist() == list(timestamps[:4])
    assert train["label_end_timestamp_5"].max() < validation["timestamp"].min()


def test_chronological_folds_reject_invalid_window_sizes() -> None:
    frame = pd.DataFrame({"timestamp": pd.date_range("2026-01-01", periods=4, freq="min", tz="UTC"), "label_end_timestamp_5": pd.date_range("2026-01-01", periods=4, freq="min", tz="UTC")})
    with pytest.raises(ValueError, match="validation_size"):
        build_chronological_folds(frame, validation_size=0, n_splits=1)
    with pytest.raises(ValueError, match="n_splits"):
        build_chronological_folds(frame, validation_size=1, n_splits=0)
    with pytest.raises(ValueError, match="rows"):
        build_chronological_folds(frame, validation_size=3, n_splits=2)


def test_rr_analysis_derives_rr_from_structural_prices() -> None:
    setups = [
        {"setup_timestamp": "2026-01-01T00:00:00Z", "direction": "long", "entry_price": 100, "stop_price": 95, "target_price": 110},
        {"setup_timestamp": "2026-01-01T00:01:00Z", "direction": "short", "entry_price": 100, "stop_price": 105, "target_price": 90},
    ]
    evaluation = evaluate_setups(candles([(100, 101, 99), (100, 111, 99), (100, 101, 89)]), setups)
    analysis = analyze_rr_outcomes(setups, evaluation)
    assert [row.rr for row in analysis.observations] == [2.0, 2.0]
    assert [row.outcome for row in analysis.observations] == [EvaluationOutcome.TP, EvaluationOutcome.TP]
    assert analysis.resolved_count == 2
    assert analysis.tp_count == 2
    assert analysis.mean_rr == 2.0


def test_rr_analysis_keeps_unresolved_outcomes_visible() -> None:
    setups = [
        {"setup_timestamp": "2026-01-01T00:00:00Z", "direction": "long", "entry_price": 100, "stop_price": 95, "target_price": 105},
        {"setup_timestamp": "2026-01-01T00:01:00Z", "direction": "long", "entry_price": 100, "stop_price": 95, "target_price": 110},
    ]
    evaluation = evaluate_setups(candles([(100, 101, 99), (100, 106, 99), (100, 103, 97)]), setups, max_horizon=1)
    analysis = analyze_rr_outcomes(setups, evaluation)
    assert [row.outcome for row in analysis.observations] == [EvaluationOutcome.TP, EvaluationOutcome.TIMEOUT]
    assert analysis.resolved_count == 1
    assert analysis.tp_count == 1
    assert analysis.mean_rr == 1.0


def test_rr_analysis_rejects_mismatched_setup_and_evaluation_counts() -> None:
    setups = [{"setup_timestamp": "2026-01-01T00:00:00Z", "direction": "long", "entry_price": 100, "stop_price": 95, "target_price": 105}]
    evaluation = evaluate_setups(candles([(100, 101, 99), (100, 106, 99)]), [])
    with pytest.raises(ValueError, match="same number"):
        analyze_rr_outcomes(setups, evaluation)


def test_rr_analysis_by_folds_keeps_fold_boundaries_and_outcomes_separate() -> None:
    fold_0_setups = [{"setup_timestamp": "2026-01-01T00:00:00Z", "direction": "long", "entry_price": 100, "stop_price": 95, "target_price": 105}]
    fold_1_setups = [{"setup_timestamp": "2026-01-01T00:00:00Z", "direction": "long", "entry_price": 100, "stop_price": 90, "target_price": 120}]
    fold_0_eval = evaluate_setups(candles([(100, 101, 99), (100, 106, 99)]), fold_0_setups)
    fold_1_eval = evaluate_setups(candles([(100, 101, 99), (100, 111, 99), (100, 121, 99)]), fold_1_setups)

    analyses = analyze_rr_outcomes_by_folds([
        (fold_0_setups, fold_0_eval),
        (fold_1_setups, fold_1_eval),
    ])

    assert len(analyses) == 2
    assert analyses[0].observations[0].rr == 1.0
    assert analyses[0].observations[0].outcome is EvaluationOutcome.TP
    assert analyses[1].observations[0].rr == 2.0
    assert analyses[1].observations[0].outcome is EvaluationOutcome.TP


def test_rr_analysis_by_folds_rejects_mismatched_fold_lengths() -> None:
    setup = {"setup_timestamp": "2026-01-01T00:00:00Z", "direction": "long", "entry_price": 100, "stop_price": 95, "target_price": 105}
    evaluation = evaluate_setups(candles([(100, 101, 99), (100, 106, 99)]), [setup])
    with pytest.raises(ValueError, match="same number"):
        analyze_rr_outcomes_by_folds([([setup], evaluation), ([], evaluation)])


def test_outcome_statistics_by_folds_preserve_each_fold_without_pooling() -> None:
    first = BatchEvaluation(
        results=(),
        counts={"tp": 3, "sl": 1, "timeout": 2, "ambiguous": 0},
        resolved_count=4,
        tp_rate=0.75,
        mean_gross_return=0.01,
    )
    second = BatchEvaluation(
        results=(),
        counts={"tp": 1, "sl": 3, "timeout": 0, "ambiguous": 1},
        resolved_count=4,
        tp_rate=0.25,
        mean_gross_return=-0.01,
    )
    stats = summarize_outcomes_by_folds([first, second])
    assert [(item.fold_index, item.counts, item.resolved_count, item.tp_rate, item.mean_gross_return) for item in stats] == [
        (0, first.counts, 4, 0.75, 0.01),
        (1, second.counts, 4, 0.25, -0.01),
    ]


def test_outcome_statistics_by_folds_do_not_create_cross_fold_average() -> None:
    first = BatchEvaluation(
        counts={"tp": 10, "sl": 0, "timeout": 0, "ambiguous": 0},
        resolved_count=10,
        tp_rate=1.0,
        mean_gross_return=0.02,
    )
    second = BatchEvaluation(
        counts={"tp": 0, "sl": 10, "timeout": 0, "ambiguous": 0},
        resolved_count=10,
        tp_rate=0.0,
        mean_gross_return=-0.02,
    )
    stats = summarize_outcomes_by_folds([first, second])
    assert len(stats) == 2
    assert stats[0].tp_rate == 1.0
    assert stats[1].tp_rate == 0.0

