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


def test_low_sweep_and_reclaim_is_causal():
    highs = [101, 103, 105, 103, 101, 103, 105, 103, 101, 102, 104]
    lows = [99, 97, 95, 97, 99, 97, 95, 97, 99, 94, 96]
    closes = [100, 98, 96, 98, 100, 98, 96, 98, 100, 95, 98]
    r = build_liquidity(frame(highs, lows, closes), swing_left=1, swing_right=1, equal_tolerance=0.001)
    assert r.loc[7, "sell_side_liquidity"] == 1
    assert r.loc[9, "sweep_low"] == 1
    assert r.loc[9, "sweep_low_reclaim"] == 1


def test_no_future_lookahead():
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
