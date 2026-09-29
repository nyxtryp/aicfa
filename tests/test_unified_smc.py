import numpy as np
import pandas as pd

from aicfa.unified_smc import build_unified_smc


def frame(n=80):
    ts = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    close = np.linspace(100, 120, n)
    return pd.DataFrame({
        "timestamp": ts.astype("int64") // 10**6,
        "open": close - 0.4,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.linspace(10, 30, n),
    })


def test_unified_smc_exposes_canonical_state_columns():
    result = build_unified_smc(frame())
    expected = [
        "smc_structure_direction",
        "smc_structure_event",
        "smc_structure_shift",
        "smc_liquidity_event",
        "smc_displacement_direction",
        "smc_fvg_event",
        "smc_fvg_lifecycle",
        "smc_fvg_active",
        "smc_order_block_event",
        "smc_order_block_lifecycle",
        "smc_order_block_active",
        "smc_dealing_range_position",
        "smc_premium_discount",
        "smc_state_ready",
    ]
    for column in expected:
        assert column in result.columns
    assert len(result) == len(frame())


def test_unified_smc_does_not_create_directional_score():
    result = build_unified_smc(frame())
    assert "smc_score" not in result.columns
    assert "smc_signal" not in result.columns


def test_unified_smc_is_causal_under_future_changes():
    base = frame(100)
    altered = base.copy()
    altered.loc[70:, "high"] *= 1000
    altered.loc[70:, "low"] *= 0.001
    altered.loc[70:, "close"] *= 500
    altered.loc[70:, "volume"] *= 100

    a = build_unified_smc(base)
    b = build_unified_smc(altered)
    pd.testing.assert_frame_equal(a.iloc[:70], b.iloc[:70], check_dtype=False)
