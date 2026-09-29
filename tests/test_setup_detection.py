import numpy as np
import pandas as pd
import pytest

from aicfa.setup_detection import build_setup_candidates


def base_frame(n: int = 8) -> pd.DataFrame:
    ts = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    close = np.linspace(100, 103, n)
    return pd.DataFrame({
        "timestamp": ts.astype("int64") // 10**6,
        "open": close - 0.2,
        "high": close + 0.5,
        "low": close - 0.5,
        "close": close,
    })


def test_setup_candidate_families_are_descriptive():
    frame = base_frame()
    frame["smc_sweep_low_reclaim"] = 0
    frame["smc_structure_shift"] = 0
    frame["pa_bullish_rejection"] = 0
    frame.loc[4, "smc_sweep_low_reclaim"] = 1
    frame.loc[4, "smc_structure_shift"] = 1

    result = build_setup_candidates(frame)

    assert result.loc[4, "setup_liquidity_reversal_up"] == 1
    assert result.loc[4, "setup_candidate_up"] == 1
    assert result.loc[4, "setup_direction"] == 1
    assert result.loc[4, "setup_primary_family"] == "liquidity_reversal"
    assert result.loc[4, "setup_candidate_conflicted"] == 0


def test_conflicting_candidates_are_not_forced_into_one_direction():
    frame = base_frame()
    frame["smc_sweep_low_reclaim"] = 0
    frame["smc_sweep_high_reclaim"] = 0
    frame["smc_structure_shift"] = 0
    frame["pa_bullish_rejection"] = 0
    frame["pa_bearish_rejection"] = 0
    frame.loc[4, "smc_sweep_low_reclaim"] = 1
    frame.loc[4, "smc_sweep_high_reclaim"] = 1
    frame.loc[4, "pa_bullish_rejection"] = 1
    frame.loc[4, "pa_bearish_rejection"] = 1

    result = build_setup_candidates(frame)

    assert result.loc[4, "setup_candidate_conflicted"] == 1
    assert result.loc[4, "setup_direction"] == 0
    assert result.loc[4, "setup_primary_family"] == ""
    assert result.loc[4, "setup_candidate_active"] == 1


def test_future_changes_do_not_rewrite_earlier_candidates():
    frame = base_frame(12)
    frame["smc_sweep_low_reclaim"] = 0
    frame["smc_structure_shift"] = 0
    frame.loc[5, ["smc_sweep_low_reclaim", "smc_structure_shift"]] = [1, 1]
    altered = frame.copy()
    altered.loc[8:, "close"] *= 100
    altered.loc[8:, "high"] *= 100
    altered.loc[8:, "low"] *= 0.01

    original = build_setup_candidates(frame)
    changed = build_setup_candidates(altered)
    pd.testing.assert_frame_equal(original.iloc[:8], changed.iloc[:8], check_dtype=False)


def test_context_columns_are_safe_when_sources_are_unavailable():
    result = build_setup_candidates(base_frame())
    assert (result["setup_fvg_bullish_context"] == 0).all()
    assert (result["setup_order_block_active_context"] == 0).all()
    assert (result["setup_absorption_context"] == 0).all()


def test_invalid_ohlc_is_rejected():
    frame = base_frame()
    frame.loc[2, "high"] = frame.loc[2, "open"] - 1
    with pytest.raises(ValueError):
        build_setup_candidates(frame)
