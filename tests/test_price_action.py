import numpy as np
import pandas as pd
import pytest

from aicfa.price_action import build_price_action


def frame() -> pd.DataFrame:
    ts = pd.date_range("2026-01-01", periods=40, freq="min", tz="UTC")
    close = np.full(40, 100.0)
    close[:20] = np.arange(100, 120)
    close[20:] = np.arange(120, 140)
    return pd.DataFrame(
        {
            "timestamp": ts.astype("int64") // 10**6,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
        }
    )


def test_price_action_exposes_required_features():
    result = build_price_action(frame(), level_lookback=5, regime_window=5)
    for column in [
        "pa_body",
        "pa_upper_wick_pct_range",
        "pa_lower_wick_pct_range",
        "pa_close_location",
        "pa_resistance_level",
        "pa_support_level",
        "pa_breakout_up",
        "pa_breakout_down",
        "pa_failed_breakout_up",
        "pa_failed_breakout_down",
        "pa_retest_up",
        "pa_retest_down",
        "pa_two_candle_bullish_continuation",
        "pa_two_candle_bearish_continuation",
        "pa_bullish_reversal",
        "pa_bearish_reversal",
        "pa_expansion",
        "pa_compression",
        "pa_consolidation",
    ]:
        assert column in result.columns


def test_price_action_levels_are_strictly_prior():
    result = build_price_action(frame(), level_lookback=5, regime_window=5)
    assert pd.isna(result.loc[4, "pa_resistance_level"])
    assert result.loc[5, "pa_resistance_level"] == frame().loc[:4, "high"].max()


def test_price_action_future_changes_do_not_rewrite_earlier_rows():
    base = frame()
    altered = base.copy()
    altered.loc[25:, "high"] *= 1000
    altered.loc[25:, "low"] *= 0.001
    altered.loc[25:, "close"] *= 500

    original = build_price_action(base, level_lookback=5, regime_window=5)
    changed = build_price_action(altered, level_lookback=5, regime_window=5)
    pd.testing.assert_frame_equal(original.iloc[:25], changed.iloc[:25], check_dtype=False)


def test_price_action_rejection_classification():
    data = frame().iloc[:8].copy()
    data.loc[7, "open"] = 100.0
    data.loc[7, "high"] = 101.0
    data.loc[7, "low"] = 95.0
    data.loc[7, "close"] = 100.5
    result = build_price_action(data, level_lookback=3, regime_window=3)
    assert result.loc[7, "pa_bullish_rejection"] == 1


def test_price_action_invalid_parameters():
    with pytest.raises(ValueError):
        build_price_action(frame(), level_lookback=1)
    with pytest.raises(ValueError):
        build_price_action(frame(), compression_threshold=1.0)
    with pytest.raises(ValueError):
        build_price_action(frame(), expansion_threshold=1.0)
