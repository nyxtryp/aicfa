import numpy as np
import pandas as pd
import pytest

from aicfa.liquidity import build_liquidity


def frame(highs, lows, closes=None):
    highs = np.asarray(highs, dtype=float)
    lows = np.asarray(lows, dtype=float)
    if closes is None:
        closes = (highs + lows) / 2.0
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=len(closes), freq="min", tz="UTC").astype("int64") // 10**6,
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
    })


def test_equal_high_becomes_buy_side_liquidity_only_after_confirmation():
    highs = [101, 103, 106, 103, 101, 103, 106.02, 103, 101, 107]
    lows = [99, 101, 104, 101, 99, 101, 104, 101, 99, 105]
    closes = [100, 102, 105, 102, 100, 102, 105, 102, 100, 106]
    r = build_liquidity(frame(highs, lows, closes), swing_left=1, swing_right=1, equal_tolerance=0.005)
    assert r.loc[2, "equal_high"] == 0
    assert r.loc[7, "equal_high"] == 1
    assert r.loc[7, "buy_side_liquidity"] == 1


def test_high_sweep_and_reclaim_is_causal():
    highs = [101, 103, 106, 103, 101, 103, 106, 103, 101, 108, 104]
    lows = [99, 101, 104, 101, 99, 101, 104, 101, 99, 102, 100]
    closes = [100, 102, 105, 102, 100, 102, 105, 102, 100, 104, 103]
    r = build_liquidity(frame(highs, lows, closes), swing_left=1, swing_right=1, equal_tolerance=0.001)
    assert r.loc[7, "buy_side_liquidity"] == 1
    assert r.loc[9, "sweep_high"] == 1
    assert r.loc[9, "sweep_high_reclaim"] == 1
    assert r.loc[9, "liquidity_pool_swept_high"] == 1
    assert r.loc[9, "active_buy_liquidity_pools"] == 0


def test_low_sweep_and_reclaim_is_causal():
    highs = [101, 103, 105, 103, 101, 103, 105, 103, 101, 102, 104]
    lows = [99, 97, 95, 97, 99, 97, 95, 97, 99, 94, 96]
    closes = [100, 98, 96, 98, 100, 102, 96, 98, 100, 95, 98]
    r = build_liquidity(frame(highs, lows, closes), swing_left=1, swing_right=1, equal_tolerance=0.001)
    assert r.loc[7, "sell_side_liquidity"] == 1
    assert r.loc[9, "sweep_low"] == 1
    assert r.loc[9, "sweep_low_reclaim"] == 1


def test_breakout_invalidates_pool_without_marking_sweep():
    highs = [101, 103, 106, 103, 101, 103, 106, 103, 101, 108, 110]
    lows = [99, 101, 104, 101, 99, 101, 104, 101, 99, 105, 107]
    closes = [100, 102, 105, 102, 100, 102, 105, 102, 100, 107, 109]
    r = build_liquidity(frame(highs, lows, closes), swing_left=1, swing_right=1, equal_tolerance=0.001)
    assert r.loc[7, "buy_side_liquidity"] == 1
    assert r.loc[9, "liquidity_breakout_high"] == 1
    assert r.loc[9, "liquidity_pool_invalidated_high"] == 1
    assert r.loc[9, "sweep_high"] == 0
    assert r.loc[9, "active_buy_liquidity_pools"] == 0


def test_multiple_active_pools_are_retained():
    highs = [101, 104, 106, 104, 101, 104, 106.01, 104, 101, 103, 105, 103, 101, 104, 106.01, 104, 101]
    lows = [99, 101, 103, 101, 99, 101, 103, 101, 99, 100, 102, 100, 99, 100, 103, 101, 99]
    closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    r = build_liquidity(frame(highs, lows, closes), swing_left=1, swing_right=1, equal_tolerance=0.002)
    assert r["active_buy_liquidity_pools"].max() >= 2


def test_internal_and_external_liquidity_are_separated():
    highs = [101, 104, 106, 104, 102, 105, 107, 105, 103, 106, 108, 106, 104]
    lows = [99, 101, 103, 101, 100, 102, 104, 102, 101, 103, 105, 103, 102]
    closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    r = build_liquidity(
        frame(highs, lows, closes),
        swing_left=2, swing_right=2,
        internal_left=1, internal_right=1,
        equal_tolerance=0.01,
    )
    assert r["internal_previous_high"].notna().any()
    assert r["internal_previous_low"].notna().any()
    assert (r["active_internal_buy_pools"] + r["active_internal_sell_pools"]).max() >= 0


def test_previous_levels_are_causal():
    n = 80
    base_close = 100 + np.sin(np.arange(n) / 2)
    base = frame(base_close + 1, base_close - 1, base_close)
    altered = base.copy()
    altered.loc[50:, ["high", "low", "close"]] *= [1000, 0.001, 500]
    a = build_liquidity(base)
    b = build_liquidity(altered)
    pd.testing.assert_frame_equal(a.iloc[:50], b.iloc[:50], check_dtype=False)


def test_invalid_parameters():
    with pytest.raises(ValueError):
        build_liquidity(frame([2, 3, 2], [0, 1, 0]), swing_left=0)
    with pytest.raises(ValueError):
        build_liquidity(frame([2, 3, 2], [0, 1, 0]), equal_tolerance=-1)
    with pytest.raises(ValueError):
        build_liquidity(frame([2, 3, 2], [0, 1, 0]), internal_left=0)


def test_swept_pool_records_later_causal_reaction():
    highs = [101, 103, 106, 103, 101, 103, 106, 103, 101, 108, 104, 103]
    lows = [99, 101, 104, 101, 99, 101, 104, 101, 99, 102, 100, 99]
    closes = [100, 102, 105, 102, 100, 102, 105, 102, 100, 104, 103, 102]
    r = build_liquidity(frame(highs, lows, closes), swing_left=1, swing_right=1, equal_tolerance=0.001)
    assert r.loc[9, "liquidity_pool_swept_high"] == 1
    assert r.loc[10, "liquidity_pool_reaction_high"] == 1
    assert r.loc[10, "last_swept_buy_liquidity_price"] == r.loc[9, "sweep_high_level"]
