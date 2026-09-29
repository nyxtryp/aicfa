import numpy as np
import pandas as pd
import pytest

from aicfa.wyckoff import build_wyckoff


def frame(n: int = 60) -> pd.DataFrame:
    ts = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    close = np.full(n, 100.0)
    close[:20] = np.linspace(100, 104, 20)
    close[20:40] = np.linspace(103.5, 100.5, 20)
    close[40:] = np.linspace(101, 110, n - 40)
    return pd.DataFrame(
        {
            "timestamp": ts.astype("int64") // 10**6,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.linspace(10, 30, n),
        }
    )


def test_wyckoff_exposes_core_features():
    result = build_wyckoff(frame(), range_lookback=5, volume_window=5)
    for column in [
        "wyckoff_range_high",
        "wyckoff_range_low",
        "wyckoff_range_width",
        "wyckoff_range_position",
        "wyckoff_in_range",
        "wyckoff_breakout_up",
        "wyckoff_breakout_down",
        "wyckoff_failed_breakout_up",
        "wyckoff_failed_breakout_down",
        "wyckoff_spring",
        "wyckoff_upthrust",
        "wyckoff_sign_of_strength",
        "wyckoff_sign_of_weakness",
        "wyckoff_range_expansion",
        "wyckoff_range_compression",
        "wyckoff_relative_volume",
        "wyckoff_volume_expansion",
        "wyckoff_state",
        "wyckoff_accumulation_proxy",
        "wyckoff_distribution_proxy",
    ]:
        assert column in result.columns


def test_wyckoff_levels_are_strictly_prior():
    base = frame()
    result = build_wyckoff(base, range_lookback=5)
    assert pd.isna(result.loc[4, "wyckoff_range_high"])
    assert result.loc[5, "wyckoff_range_high"] == base.loc[:4, "high"].max()
    assert result.loc[5, "wyckoff_range_low"] == base.loc[:4, "low"].min()


def test_wyckoff_spring_and_upthrust_are_observable_candidates():
    base = frame(35)
    # Establish a range, then penetrate/reclaim its lower boundary.
    base.loc[30, ["open", "high", "low", "close"]] = [100.0, 101.0, 96.0, 100.5]
    spring = build_wyckoff(base, range_lookback=5)
    assert spring.loc[30, "wyckoff_spring"] == 1

    # Establish the same range, then penetrate/fail back below its upper boundary.
    base.loc[30, ["open", "high", "low", "close"]] = [100.0, 104.0, 99.0, 100.5]
    upthrust = build_wyckoff(base, range_lookback=5)
    assert upthrust.loc[30, "wyckoff_upthrust"] == 1


def test_wyckoff_future_changes_do_not_rewrite_earlier_rows():
    base = frame()
    altered = base.copy()
    altered.loc[40:, "high"] *= 1000
    altered.loc[40:, "low"] *= 0.001
    altered.loc[40:, "close"] *= 500
    altered.loc[40:, "volume"] *= 100

    original = build_wyckoff(base, range_lookback=5, volume_window=5)
    changed = build_wyckoff(altered, range_lookback=5, volume_window=5)
    pd.testing.assert_frame_equal(
        original.iloc[:40], changed.iloc[:40], check_dtype=False
    )


def test_wyckoff_works_without_volume():
    data = frame().drop(columns=["volume"])
    result = build_wyckoff(data, range_lookback=5)
    assert "wyckoff_relative_volume" not in result.columns
    assert "wyckoff_spring" in result.columns


def test_wyckoff_invalid_parameters():
    with pytest.raises(ValueError):
        build_wyckoff(frame(), range_lookback=2)
    with pytest.raises(ValueError):
        build_wyckoff(frame(), volume_window=1)
    with pytest.raises(ValueError):
        build_wyckoff(frame(), breakout_buffer=-0.1)
