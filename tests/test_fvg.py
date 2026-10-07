import numpy as np
import pandas as pd
import pytest

from aicfa.fvg import (
    FVG_FILLED,
    FVG_INVALIDATED,
    FVG_PARTIAL,
    FVG_TOUCHED,
    FVG_UNTOUCHED,
    build_fvg,
)


def frame(opens, highs, lows, closes, volumes=None):
    n = len(closes)
    if volumes is None:
        volumes = np.full(n, 10.0)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC").astype("int64") // 10**6,
        "open": np.asarray(opens, dtype=float),
        "high": np.asarray(highs, dtype=float),
        "low": np.asarray(lows, dtype=float),
        "close": np.asarray(closes, dtype=float),
        "volume": np.asarray(volumes, dtype=float),
    })


def test_bullish_fvg_is_created_at_third_candle():
    df = frame([100, 101, 105], [102, 103, 106], [99, 100, 105], [101, 102, 105.5])
    r = build_fvg(df)
    assert r.loc[2, "fvg_bullish"] == 1
    assert r.loc[2, "fvg"] == 1
    assert r.loc[2, "fvg_bullish_low"] == 102
    assert r.loc[2, "fvg_bullish_high"] == 105
    assert r.loc[2, "fvg_size"] == 3
    assert r.loc[2, "fvg_bullish_state"] == FVG_UNTOUCHED
    assert r.loc[2, "fvg_bullish_creation_index"] == 2


def test_bearish_fvg_is_created_at_third_candle():
    df = frame([100, 99, 97], [102, 100, 98], [99, 97, 94], [100, 98, 95])
    r = build_fvg(df)
    assert r.loc[2, "fvg_bearish"] == 1
    assert r.loc[2, "fvg"] == 1
    assert r.loc[2, "fvg_bearish_low"] == 98
    assert r.loc[2, "fvg_bearish_high"] == 99
    assert r.loc[2, "fvg_size"] == 1
    assert r.loc[2, "fvg_bearish_state"] == FVG_UNTOUCHED


def test_small_gap_can_be_filtered_by_percentage():
    df = frame(
        [100, 101, 102.2],
        [101, 102, 103],
        [99, 100.5, 102.01],
        [100, 101.5, 102.5],
    )
    r = build_fvg(df, min_gap_pct=0.02)
    assert r.loc[2, "fvg"] == 0


def test_bullish_fvg_lifecycle_touch_partial_fill_is_causal():
    df = frame(
        [100, 101, 105, 105, 104, 103],
        [102, 103, 106, 106, 106, 105],
        [99, 100, 105, 105, 103.5, 102],
        [101, 102, 105.5, 105.2, 104, 102],
    )
    r = build_fvg(df)
    assert r.loc[2, "fvg_bullish_state"] == FVG_UNTOUCHED
    assert r.loc[3, "fvg_bullish_state"] == FVG_TOUCHED
    assert r.loc[3, "fvg_active"] == 1
    assert r.loc[4, "fvg_bullish_state"] == FVG_PARTIAL
    assert r.loc[4, "fvg_active"] == 1
    assert 0.0 < r.loc[4, "fvg_bullish_penetration"] < 1.0
    assert r.loc[5, "fvg_filled"] == 1
    assert r.loc[5, "fvg_mitigated"] == 1


def test_fvg_invalidation_is_distinct_from_normal_fill():
    df = frame(
        [100, 101, 105, 101],
        [102, 103, 106, 106],
        [99, 100, 105, 100],
        [101, 102, 105.5, 101],
    )
    r = build_fvg(df)
    assert r.loc[3, "fvg_invalidated"] == 1
    assert r.loc[3, "fvg_filled"] == 0


def test_multiple_active_bullish_fvgs_are_not_overwritten():
    df = frame(
        [100, 101, 105, 106, 110],
        [102, 103, 106, 107, 111],
        [99, 100, 105, 106, 110],
        [101, 102, 105.5, 106.5, 110.5],
    )
    r = build_fvg(df)
    assert r.loc[2, "fvg_bullish"] == 1
    assert r.loc[4, "fvg_bullish"] == 1
    assert r.loc[4, "fvg_active_bullish_count"] >= 2


def test_fvg_creation_and_lifecycle_provenance_are_causal():
    df = frame(
        [100, 101, 105, 104, 104],
        [102, 103, 106, 106, 106],
        [99, 100, 105, 104, 101],
        [101, 102, 105.5, 104.5, 101.5],
    )
    altered = df.copy()
    altered.loc[4, ["high", "low", "close", "volume"]] = [1000, 1, 500, 1000]
    a = build_fvg(df)
    b = build_fvg(altered)
    pd.testing.assert_frame_equal(a.iloc[:4], b.iloc[:4], check_dtype=False)


def test_fvg_requires_current_displacement_when_requested():
    df = frame(
        [100] * 23,
        [101] * 23,
        [99] * 23,
        [100.5] * 23,
        [10] * 23,
    )
    df.loc[20, ["open", "high", "low", "close", "volume"]] = [100, 101, 99.8, 100.9, 10]
    df.loc[21, ["open", "high", "low", "close", "volume"]] = [100.9, 102, 100.8, 101.5, 10]
    df.loc[22, ["open", "high", "low", "close", "volume"]] = [103, 104, 102.9, 103.8, 10]
    r = build_fvg(df, require_displacement=True)
    assert r.loc[22, "fvg_bullish"] == 0


def test_invalid_parameters():
    df = frame([100, 101, 105], [102, 103, 106], [99, 100, 105], [101, 102, 105.5])
    with pytest.raises(ValueError):
        build_fvg(df, min_gap_pct=-0.01)
    with pytest.raises(ValueError):
        build_fvg(pd.DataFrame({
            "timestamp": [1, 2, 3],
            "open": [1, 1, 1],
            "high": [2, 2, 2],
            "low": [0, 0, 0],
            "close": [1, 1, 1],
            "volume": [-1, 1, 1],
        }))
