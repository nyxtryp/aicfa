from __future__ import annotations

import pandas as pd

from aicfa.evaluation import EvaluationResult, evaluate_setup


def candles(rows: list[tuple[float, float, float]]) -> pd.DataFrame:
    timestamps = pd.date_range("2026-01-01", periods=len(rows), freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [o for o, _, _ in rows],
            "high": [h for _, h, _ in rows],
            "low": [l for _, _, l in rows],
            "close": [o for o, _, _ in rows],
        }
    )


def test_long_tp_hit_before_sl() -> None:
    result = evaluate_setup(
        candles([(100, 101, 99), (100, 106, 99)]),
        setup_timestamp="2026-01-01T00:00:00Z",
        direction="long",
        entry_price=100,
        stop_price=95,
        target_price=105,
    )
    assert result is EvaluationResult.TP
    assert result.outcome_offset == 1
    assert result.exit_price == 105


def test_long_sl_hit_before_tp() -> None:
    result = evaluate_setup(
        candles([(100, 101, 99), (100, 101, 94), (100, 106, 99)]),
        setup_timestamp="2026-01-01T00:00:00Z",
        direction="long",
        entry_price=100,
        stop_price=95,
        target_price=105,
    )
    assert result.outcome is EvaluationResult.SL


def test_same_bar_tp_and_sl_is_ambiguous() -> None:
    result = evaluate_setup(
        candles([(100, 101, 99), (100, 106, 94)]),
        setup_timestamp="2026-01-01T00:00:00Z",
        direction="long",
        entry_price=100,
        stop_price=95,
        target_price=105,
    )
    assert result.outcome is EvaluationResult.AMBIGUOUS
    assert result.outcome_offset == 1
    assert result.exit_price is None


def test_timeout_is_explicit_and_does_not_guess_winner() -> None:
    result = evaluate_setup(
        candles([(100, 101, 99), (100, 103, 98), (100, 104, 97)]),
        setup_timestamp="2026-01-01T00:00:00Z",
        direction="long",
        entry_price=100,
        stop_price=95,
        target_price=105,
        max_horizon=2,
    )
    assert result.outcome is EvaluationResult.TIMEOUT
    assert result.outcome_offset == 2
    assert result.exit_price is None


def test_short_is_symmetric() -> None:
    result = evaluate_setup(
        candles([(100, 101, 99), (100, 94, 101)]),
        setup_timestamp="2026-01-01T00:00:00Z",
        direction="short",
        entry_price=100,
        stop_price=105,
        target_price=95,
    )
    assert result.outcome is EvaluationResult.TP
    assert result.exit_price == 95


def test_future_rows_before_setup_are_not_used() -> None:
    frame = candles([(100, 101, 99), (100, 106, 99), (100, 101, 94)])
    frame.loc[0, "timestamp"] = pd.Timestamp("2026-01-01T00:00:00Z")
    frame.loc[1, "timestamp"] = pd.Timestamp("2025-12-31T23:59:00Z")
    frame.loc[2, "timestamp"] = pd.Timestamp("2026-01-01T00:01:00Z")

    result = evaluate_setup(
        frame,
        setup_timestamp="2026-01-01T00:00:00Z",
        direction="long",
        entry_price=100,
        stop_price=95,
        target_price=105,
    )
    assert result.outcome is EvaluationResult.SL


def test_invalid_geometry_is_rejected() -> None:
    import pytest

    with pytest.raises(ValueError, match="entry"):
        evaluate_setup(
            candles([(100, 101, 99), (100, 106, 94)]),
            setup_timestamp="2026-01-01T00:00:00Z",
            direction="long",
            entry_price=100,
            stop_price=105,
            target_price=95,
        )
