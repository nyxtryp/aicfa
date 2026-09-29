import numpy as np
import pandas as pd
import pytest

from aicfa.features import build_features


def sample_frame(n: int = 100) -> pd.DataFrame:
    ts = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    close = np.arange(n, dtype=float) + 100.0
    return pd.DataFrame({
        "timestamp": ts.astype("int64") // 10**6,
        "open": close - 0.5,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": np.linspace(10, 20, n),
    })


def test_feature_columns_and_shape():
    result = build_features(sample_frame())
    assert len(result) == 100
    for column in [
        "return_1",
        "log_return_1",
        "body_pct_range",
        "volatility_15",
        "relative_volume_15",
        "rolling_high_30",
        "dealing_range_position",
        "breakout_up",
        "sweep_high_reject",
        "smc_structure_direction",
        "smc_displacement_direction",
        "smc_previous_high",
        "smc_previous_low",
        "smc_active_buy_liquidity_pools",
        "smc_active_sell_liquidity_pools",
        "smc_liquidity_breakout_high",
        "smc_liquidity_pool_swept_high",
        "smc_premium_discount",
        "smc_state_ready",
        "realized_volatility",
        "atr",
        "volume_zscore",
        "volatility_ratio",
        "volatility_regime",
        "volume_regime",
        "return_60",
        "pa_body",
        "pa_breakout_up",
        "pa_retest_up",
        "pa_bullish_rejection",
        "pa_expansion",
        "pa_compression",
        "pa_consolidation",
    ]:
        assert column in result.columns


def test_no_future_lookahead():
    base = sample_frame(120)
    altered = base.copy()
    altered.loc[100:, "high"] = altered.loc[100:, "high"] * 1000
    altered.loc[100:, "low"] = altered.loc[100:, "low"] * 0.001
    altered.loc[100:, "close"] = altered.loc[100:, "close"] * 500

    a = build_features(base)
    b = build_features(altered)

    # Rows before the mutation must remain identical.
    pd.testing.assert_frame_equal(a.iloc[:100], b.iloc[:100], check_dtype=False)


def test_invalid_input():
    with pytest.raises(ValueError):
        build_features(pd.DataFrame({"timestamp": [1], "close": [1]}))


def aggregate_minutes(base: pd.DataFrame, minutes: int) -> pd.DataFrame:
    source = base.copy()
    source["timestamp_dt"] = pd.to_datetime(source["timestamp"], unit="ms", utc=True)
    source = source.set_index("timestamp_dt")
    grouped = source.resample(f"{minutes}min", label="left", closed="left").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna().reset_index()
    grouped["timestamp"] = grouped["timestamp_dt"].astype("int64") // 10**6
    return grouped[["timestamp", "open", "high", "low", "close", "volume"]]


def test_feature_integration_exposes_required_higher_timeframes():
    base = sample_frame(7 * 24 * 60)
    frames = {
        "5m": aggregate_minutes(base, 5),
        "15m": aggregate_minutes(base, 15),
        "1h": aggregate_minutes(base, 60),
        "4h": aggregate_minutes(base, 240),
        "1d": aggregate_minutes(base, 1440),
        "1w": aggregate_minutes(base, 10080),
    }
    result = build_features(base, multi_timeframe_frames=frames)
    assert len(result) == len(base)
    for timeframe in frames:
        assert f"mtf_{timeframe}_structure_direction" in result.columns
        assert f"mtf_{timeframe}_bos_up" in result.columns
        assert f"mtf_{timeframe}_swing_high_price" in result.columns


def test_feature_mtf_future_changes_do_not_rewrite_earlier_rows():
    base = sample_frame(7 * 24 * 60)
    frames = {"5m": aggregate_minutes(base, 5), "15m": aggregate_minutes(base, 15)}
    altered = {key: value.copy() for key, value in frames.items()}
    cutoff = 4 * 24 * 60
    for frame in altered.values():
        mask = frame["timestamp"] >= base.loc[cutoff, "timestamp"]
        frame.loc[mask, "high"] *= 1000
        frame.loc[mask, "low"] *= 0.001
        frame.loc[mask, "close"] *= 500
    original = build_features(base, multi_timeframe_frames=frames)
    changed = build_features(base, multi_timeframe_frames=altered)
    pd.testing.assert_frame_equal(original.iloc[:cutoff], changed.iloc[:cutoff], check_dtype=False)


def test_feature_build_without_mtf_remains_supported():
    base = sample_frame()
    result = build_features(base)
    assert len(result) == len(base)
    assert not any(column.startswith("mtf_") for column in result.columns)


def test_feature_integration_exposes_refined_liquidity():
    result = build_features(sample_frame(180))
    for column in [
        "previous_high", "previous_low",
        "internal_previous_high", "internal_previous_low",
        "active_buy_liquidity_pools", "active_sell_liquidity_pools",
        "active_external_buy_pools", "active_external_sell_pools",
        "active_internal_buy_pools", "active_internal_sell_pools",
        "liquidity_breakout_high", "liquidity_breakout_low",
        "liquidity_pool_created_high", "liquidity_pool_created_low",
        "liquidity_pool_swept_high", "liquidity_pool_swept_low",
        "liquidity_pool_invalidated_high", "liquidity_pool_invalidated_low",
        "smc_previous_high", "smc_previous_low",
        "smc_active_buy_liquidity_pools", "smc_active_sell_liquidity_pools",
        "smc_liquidity_breakout_high", "smc_liquidity_pool_swept_high",
    ]:
        assert column in result.columns


def test_feature_integration_exposes_volume_volatility_regimes():
    result = build_features(sample_frame(180))
    for column in [
        "realized_volatility", "true_range", "atr", "atr_pct",
        "range_zscore", "volume_zscore", "relative_volume_causal",
        "volatility_ratio", "volatility_expansion",
        "volatility_compression", "volume_expansion", "volume_dry_up",
        "volatility_regime", "volume_regime",
    ]:
        assert column in result.columns


def test_feature_integration_exposes_causal_derivatives():
    base = sample_frame(180)
    ts = pd.to_datetime(base["timestamp"], unit="ms", utc=True)
    derivatives = pd.DataFrame({
        "timestamp": ts.iloc[::5].to_numpy(),
        "funding_rate": np.linspace(-0.001, 0.002, len(ts.iloc[::5])),
        "open_interest": np.linspace(1000, 1500, len(ts.iloc[::5])),
    })
    result = build_features(base, derivatives_frame=derivatives)
    for column in [
        "funding_rate", "funding_rate_delta", "funding_rate_zscore",
        "open_interest", "open_interest_delta", "open_interest_zscore",
        "oi_price_up_up", "oi_price_up_down", "oi_price_down_up",
        "oi_price_down_down",
    ]:
        assert column in result.columns


def test_feature_derivatives_future_changes_do_not_rewrite_earlier_rows():
    base = sample_frame(180)
    ts = pd.to_datetime(base["timestamp"], unit="ms", utc=True)
    derivatives = pd.DataFrame({
        "timestamp": ts.iloc[::5].to_numpy(),
        "funding_rate": np.linspace(-0.001, 0.002, len(ts.iloc[::5])),
        "open_interest": np.linspace(1000, 1500, len(ts.iloc[::5])),
    })
    altered = derivatives.copy()
    cutoff = base.loc[100, "timestamp"]
    mask = altered["timestamp"].astype("int64") // 10**6 >= cutoff
    altered.loc[mask, "funding_rate"] *= 100
    altered.loc[mask, "open_interest"] *= 10
    original = build_features(base, derivatives_frame=derivatives)
    changed = build_features(base, derivatives_frame=altered)
    pd.testing.assert_frame_equal(original.iloc[:100], changed.iloc[:100], check_dtype=False)
