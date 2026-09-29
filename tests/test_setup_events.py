import numpy as np
import pandas as pd
import pytest

from aicfa.setup_events import build_setup_events


def state():
    ts = pd.date_range("2026-01-01", periods=7, freq="min", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts.astype("int64") // 10**6,
        "market_state_setup_active": [0, 1, 1, 1, 0, 1, 1],
        "market_state_setup_direction": [0, 1, 1, 1, 0, -1, -1],
        "market_state_setup_conflicted": [0, 0, 0, 0, 0, 0, 0],
        "market_state_setup_family": ["", "liquidity_reversal", "liquidity_reversal",
                                      "liquidity_reversal", "", "failed_breakout",
                                      "failed_breakout"],
        "market_state_changed": [1, 1, 0, 1, 1, 1, 0],
    })


def test_created_then_strengthened_and_repeated_state():
    out = build_setup_events(state())

    assert out.loc[1, "setup_event_type"] == "created"
    assert out.loc[1, "setup_event_created"] == 1
    assert out.loc[2, "setup_event_type"] == ""
    assert out.loc[3, "setup_event_type"] == "strengthened"


def test_invalidation_and_expiration_are_distinct():
    out = build_setup_events(state())

    assert out.loc[4, "setup_event_invalidated"] == 1
    assert out.loc[4, "setup_event_expired"] == 1
    assert out.loc[4, "setup_event_type"] == "expired"


def test_replacement_creates_new_event():
    out = build_setup_events(state())

    assert out.loc[5, "setup_event_type"] == "created"
    assert out.loc[5, "setup_event_created"] == 1
    assert out.loc[5, "setup_event_invalidated"] == 1
    assert out.loc[5, "setup_event_family"] == "failed_breakout"
    assert out.loc[5, "setup_event_direction"] == -1


def test_conflicted_setup_has_no_directional_event():
    frame = state()
    frame.loc[1, "market_state_setup_conflicted"] = 1
    out = build_setup_events(frame)

    assert out.loc[1, "setup_event_type"] == ""
    assert out.loc[1, "setup_event_direction"] == 0
    assert out.loc[1, "setup_event_family"] == ""
    assert out.loc[1, "setup_event_identity"] == ""


def test_outcome_is_never_generated_live():
    out = build_setup_events(state())
    assert (out["setup_event_outcome"] == "").all()


def test_future_changes_do_not_rewrite_earlier_events():
    frame = state()
    altered = frame.copy()
    altered.loc[5:, "market_state_setup_family"] = "wyckoff"
    altered.loc[5:, "market_state_setup_direction"] = 1

    original = build_setup_events(frame)
    changed = build_setup_events(altered)

    pd.testing.assert_frame_equal(
        original.iloc[:5],
        changed.iloc[:5],
        check_dtype=False,
    )


def test_missing_required_state_is_rejected():
    frame = state().drop(columns=["market_state_setup_family"])
    with pytest.raises(ValueError):
        build_setup_events(frame)
