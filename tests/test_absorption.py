import numpy as np
import pandas as pd
import pytest

from aicfa.absorption import build_absorption


def _base():
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=5, freq="min", tz="UTC"),
        "open": [100, 100, 100, 100, 100],
        "high": [100, 101, 101, 101, 101],
        "low": [99, 99, 99, 99, 99],
        "close": [100, 100, 100, 100, 100],
    })


def _flow():
    ts = pd.date_range("2026-01-01T00:02:00Z", periods=3, freq="min", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "taker_buy_volume": [80, 80, 80],
        "taker_sell_volume": [20, 20, 20],
    })


def _levels():
    ts = pd.date_range("2026-01-01T00:01:00Z", periods=4, freq="min", tz="UTC")
    rows = []
    for t in ts:
        rows += [
            {"timestamp": t, "side": "ask", "price": 100.01, "size": 100.0 + 10.0 * (t.minute - 1)},
            {"timestamp": t, "side": "ask", "price": 100.02, "size": 10.0},
            {"timestamp": t, "side": "bid", "price": 99.99, "size": 10.0},
        ]
    return pd.DataFrame(rows)


def test_absorption_requires_flow_liquidity_replenishment_and_price_response():
    out = build_absorption(
        _base(), _flow(), _levels(),
        window="3min",
        proximity_bps=5,
        min_imbalance=0.3,
        min_liquidity_multiple=1.5,
        min_replenishment_ratio=0.5,
        min_persistence_snapshots=2,
        max_price_response_bps=8,
        max_directional_efficiency=0.5,
    )
    row = out.iloc[-1]
    assert row["absorption"]
    assert row["absorption_side"] == "buy"
    assert row["resting_liquidity_side"] == "ask"
    assert row["liquidity_multiple"] >= 1.5
    assert row["level_persistence_snapshots"] >= 2


def test_absorption_does_not_call_a_wall_absorption_without_replenishment():
    levels = _levels()
    levels.loc[levels["timestamp"] == pd.Timestamp("2026-01-01T00:04:00Z"), "size"] = [0, 10, 10]
    out = build_absorption(
        _base(), _flow(), levels,
        window="3min",
        min_replenishment_ratio=0.5,
    )
    assert not out.iloc[-1]["absorption"]


def test_absorption_is_causal_under_future_changes():
    base = _base()
    flow = _flow()
    levels = _levels()
    altered_base = base.copy()
    altered_flow = flow.copy()
    altered_levels = levels.copy()
    altered_base.loc[altered_base["timestamp"] > pd.Timestamp("2026-01-01T00:03:00Z"), ["high", "close"]] = [120, 120]
    altered_flow.loc[altered_flow["timestamp"] > pd.Timestamp("2026-01-01T00:03:00Z"), "taker_buy_volume"] = 1
    altered_levels.loc[altered_levels["timestamp"] > pd.Timestamp("2026-01-01T00:03:00Z"), "size"] = 1

    a = build_absorption(base, flow, levels)
    b = build_absorption(altered_base, altered_flow, altered_levels)
    pd.testing.assert_frame_equal(
        a[a["timestamp"] <= pd.Timestamp("2026-01-01T00:03:00Z")].reset_index(drop=True),
        b[b["timestamp"] <= pd.Timestamp("2026-01-01T00:03:00Z")].reset_index(drop=True),
        check_dtype=False,
    )


def test_absorption_rejects_invalid_window_thresholds():
    with pytest.raises(ValueError):
        build_absorption(_base(), _flow(), _levels(), min_persistence_snapshots=0)
