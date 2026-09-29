import numpy as np
import pandas as pd
import pytest

from aicfa.order_blocks import build_order_blocks


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


def test_bullish_order_block_is_recognized_on_displacement_candle():
    df = frame(
        [100, 102, 99, 100],
        [103, 103, 104, 105],
        [99, 100, 98, 99],
        [102, 101, 103, 104],
    )
    r = build_order_blocks(df, require_displacement=False)
    assert r.loc[1, "order_block_bullish"] == 0
    assert r.loc[2, "order_block_bullish"] == 1
    assert r.loc[2, "order_block_bullish_low"] == 100
    assert r.loc[2, "order_block_bullish_high"] == 103


def test_bearish_order_block_is_recognized_on_displacement_candle():
    df = frame(
        [100, 98, 101, 100],
        [102, 100, 104, 101],
        [98, 97, 96, 95],
        [98, 99, 97, 96],
    )
    r = build_order_blocks(df, require_displacement=False)
    assert r.loc[1, "order_block_bearish"] == 0
    assert r.loc[2, "order_block_bearish"] == 1
    assert r.loc[2, "order_block_bearish_low"] == 97
    assert r.loc[2, "order_block_bearish_high"] == 100


def test_order_block_lifecycle_mitigation_invalidation_and_later_breaker():
    df = frame(
        [100, 102, 99, 98, 101],
        [103, 103, 104, 102, 103],
        [99, 100, 98, 95, 99],
        [102, 101, 103, 97, 99],
    )
    r = build_order_blocks(df, require_displacement=False)

    assert r.loc[2, "order_block_bullish"] == 1
    assert r.loc[2, "order_block_active"] == 1
    assert r.loc[3, "order_block_invalidated"] == 1
    assert r.loc[3, "breaker"] == 0
    assert r.loc[4, "breaker_bearish"] == 1
    assert r.loc[4, "breaker"] == 1


def test_order_block_mitigation_is_recorded_before_invalidation():
    df = frame(
        [100, 102, 104, 101],
        [103, 103, 105, 104],
        [99, 100, 101, 99],
        [102, 101, 104, 100],
    )
    r = build_order_blocks(df, require_displacement=False)
    assert r.loc[2, "order_block_bullish"] == 1
    assert r.loc[3, "order_block_mitigated"] == 1


def test_order_block_requires_displacement_when_requested():
    base_n = 22
    df = frame(
        [100] * base_n,
        [101] * base_n,
        [99] * base_n,
        [100.5] * base_n,
        [10] * base_n,
    )
    df.loc[20, ["open", "high", "low", "close", "volume"]] = [101, 102, 98, 99, 10]
    df.loc[21, ["open", "high", "low", "close", "volume"]] = [99, 105, 98.5, 104.5, 20]

    r = build_order_blocks(df, require_displacement=True)
    assert r.loc[21, "order_block_bullish"] == 1
    assert r.loc[21, "order_block_displacement_bullish"] == 1


def test_order_block_is_causal_under_future_changes():
    df = frame(
        [100, 102, 99, 98, 101],
        [103, 103, 104, 102, 103],
        [99, 100, 98, 95, 99],
        [102, 101, 103, 97, 99],
    )
    altered = df.copy()
    altered.loc[4, ["high", "low", "close", "volume"]] = [1000, 1, 500, 1000]

    a = build_order_blocks(df, require_displacement=False)
    b = build_order_blocks(altered, require_displacement=False)
    pd.testing.assert_frame_equal(a.iloc[:4], b.iloc[:4], check_dtype=False)


def test_invalid_parameters_and_validation():
    df = frame([100, 101], [102, 103], [99, 100], [101, 102])
    with pytest.raises(ValueError):
        build_order_blocks(pd.DataFrame({
            "timestamp": [1, 2],
            "open": [1, 1],
            "high": [2, 2],
            "low": [0, 0],
            "close": [1, 1],
            "volume": [-1, 1],
        }))
