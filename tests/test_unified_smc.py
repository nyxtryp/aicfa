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
        "smc_internal_hh",
        "smc_internal_hl",
        "smc_internal_lh",
        "smc_internal_ll",
        "smc_internal_bos_up",
        "smc_internal_bos_down",
        "smc_internal_choch_up",
        "smc_internal_choch_down",
        "smc_internal_structure_direction",
        "smc_mss_up",
        "smc_mss_down",
        "smc_protected_high_price",
        "smc_protected_low_price",
        "smc_protected_high_active",
        "smc_protected_low_active",
        "smc_protected_high_created",
        "smc_protected_low_created",
        "smc_protected_high_broken",
        "smc_protected_low_broken",
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


def test_unified_smc_propagates_refined_structure_observations():
    from aicfa.displacement import build_displacement
    from aicfa.structure import build_structure

    base = frame(120)
    structure = build_structure(base, displacement=build_displacement(base))
    result = build_unified_smc(base, structure=structure)

    for column in [
        "smc_internal_hh", "smc_internal_hl", "smc_internal_lh", "smc_internal_ll",
        "smc_internal_bos_up", "smc_internal_bos_down",
        "smc_internal_choch_up", "smc_internal_choch_down",
        "smc_internal_structure_direction", "smc_mss_up", "smc_mss_down",
        "smc_protected_high_price", "smc_protected_low_price",
        "smc_protected_high_active", "smc_protected_low_active",
        "smc_protected_high_created", "smc_protected_low_created",
        "smc_protected_high_broken", "smc_protected_low_broken",
    ]:
        assert column in result.columns

    np.testing.assert_array_equal(result["smc_internal_hh"], structure["internal_hh"])
    np.testing.assert_array_equal(result["smc_mss_up"], structure["mss_up"])
    np.testing.assert_array_equal(result["smc_mss_down"], structure["mss_down"])
    np.testing.assert_allclose(
        result["smc_protected_high_price"],
        structure["protected_high_price"],
        equal_nan=True,
    )


def test_unified_smc_refined_structure_is_causal():
    base = frame(120)
    altered = base.copy()
    altered.loc[85:, "high"] *= 1000
    altered.loc[85:, "low"] *= 0.001
    altered.loc[85:, "close"] *= 500
    altered.loc[85:, "volume"] *= 100

    a = build_unified_smc(base)
    b = build_unified_smc(altered)
    pd.testing.assert_frame_equal(a.iloc[:85], b.iloc[:85], check_dtype=False)


def test_unified_smc_propagates_refined_liquidity():
    from aicfa.liquidity import build_liquidity

    base = frame(180)
    liquidity = build_liquidity(base)
    result = build_unified_smc(base, liquidity=liquidity)

    for column in [
        "smc_previous_high", "smc_previous_low",
        "smc_internal_previous_high", "smc_internal_previous_low",
        "smc_active_buy_liquidity_pools", "smc_active_sell_liquidity_pools",
        "smc_active_external_buy_pools", "smc_active_external_sell_pools",
        "smc_active_internal_buy_pools", "smc_active_internal_sell_pools",
        "smc_liquidity_breakout_high", "smc_liquidity_breakout_low",
        "smc_liquidity_pool_created_high", "smc_liquidity_pool_created_low",
        "smc_liquidity_pool_swept_high", "smc_liquidity_pool_swept_low",
        "smc_liquidity_pool_invalidated_high", "smc_liquidity_pool_invalidated_low",
    ]:
        assert column in result.columns

    np.testing.assert_array_equal(
        result["smc_active_buy_liquidity_pools"],
        liquidity["active_buy_liquidity_pools"],
    )
    np.testing.assert_array_equal(
        result["smc_liquidity_breakout_high"],
        liquidity["liquidity_breakout_high"],
    )


def test_unified_smc_refined_liquidity_is_causal():
    base = frame(180)
    altered = base.copy()
    altered.loc[120:, "high"] *= 1000
    altered.loc[120:, "low"] *= 0.001
    altered.loc[120:, "close"] *= 500

    a = build_unified_smc(base)
    b = build_unified_smc(altered)
    pd.testing.assert_frame_equal(a.iloc[:120], b.iloc[:120], check_dtype=False)
