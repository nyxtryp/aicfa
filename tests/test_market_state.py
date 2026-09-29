import numpy as np
import pandas as pd
import pytest

from aicfa.market_state import build_market_state


def base_state(n: int = 8) -> pd.DataFrame:
    ts = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts.astype("int64") // 10**6,
        "close": np.linspace(100, 103, n),
        "smc_structure_direction": 1,
        "smc_state_ready": 1,
        "scenario_active": 0,
        "scenario_direction": 0,
        "scenario_event": "",
        "setup_candidate_active": 0,
        "setup_candidate_up": 0,
        "setup_candidate_down": 0,
        "setup_candidate_conflicted": 0,
        "setup_direction": 0,
        "setup_primary_family": "",
    })


def test_market_state_exposes_canonical_fields():
    frame = base_state()
    frame.loc[4, "scenario_active"] = 1
    frame.loc[4, "scenario_direction"] = 1
    frame.loc[4, "scenario_event"] = "expansion_up"
    frame.loc[4, "setup_candidate_active"] = 1
    frame.loc[4, "setup_candidate_up"] = 1
    frame.loc[4, "setup_direction"] = 1
    frame.loc[4, "setup_primary_family"] = "expansion"

    result = build_market_state(frame)

    assert result.loc[4, "market_state_structure_direction"] == 1
    assert result.loc[4, "market_state_scenario_event"] == "expansion_up"
    assert result.loc[4, "market_state_setup_active"] == 1
    assert result.loc[4, "market_state_setup_direction"] == 1
    assert result.loc[4, "market_state_setup_family"] == "expansion"
    assert result.loc[4, "market_state_smc_ready"] == 1


def test_conflicted_setup_remains_neutral_and_has_no_primary_family():
    frame = base_state()
    frame.loc[4, "setup_candidate_active"] = 1
    frame.loc[4, "setup_candidate_conflicted"] = 1
    frame.loc[4, "setup_primary_family"] = ""
    frame.loc[4, "setup_direction"] = 0

    result = build_market_state(frame)

    assert result.loc[4, "market_state_setup_active"] == 1
    assert result.loc[4, "market_state_setup_conflicted"] == 1
    assert result.loc[4, "market_state_setup_direction"] == 0
    assert result.loc[4, "market_state_setup_family"] == ""


def test_optional_sources_are_explicitly_unavailable():
    result = build_market_state(base_state())

    assert (result["market_state_cvd_available"] == 0).all()
    assert (result["market_state_taker_flow_available"] == 0).all()
    assert (result["market_state_absorption_available"] == 0).all()
    assert (result["market_state_order_book_available"] == 0).all()
    assert (result["market_state_context_availability_mask"] == 0).all()


def test_context_availability_mask_is_not_a_score():
    frame = base_state()
    frame["cvd_delta"] = 0.0
    frame["taker_net_volume"] = 0.0
    frame["absorption_candidate"] = 0
    frame["order_book_imbalance"] = 0.0

    result = build_market_state(frame)

    assert (result["market_state_cvd_available"] == 1).all()
    assert (result["market_state_taker_flow_available"] == 1).all()
    assert (result["market_state_absorption_available"] == 1).all()
    assert (result["market_state_order_book_available"] == 1).all()
    assert (result["market_state_context_availability_mask"] == 15).all()


def test_state_change_is_causal():
    frame = base_state(12)
    frame.loc[5, "setup_candidate_active"] = 1
    frame.loc[5, "setup_candidate_up"] = 1
    frame.loc[5, "setup_direction"] = 1

    altered = frame.copy()
    altered.loc[8:, "smc_structure_direction"] = -1
    altered.loc[8:, "scenario_event"] = "expansion_down"

    original = build_market_state(frame)
    changed = build_market_state(altered)

    pd.testing.assert_frame_equal(
        original.iloc[:8],
        changed.iloc[:8],
        check_dtype=False,
    )


def test_missing_required_state_is_rejected():
    frame = base_state().drop(columns=["setup_direction"])
    with pytest.raises(ValueError):
        build_market_state(frame)
