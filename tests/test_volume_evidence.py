import numpy as np
import pandas as pd
import pytest

from aicfa.volume_evidence import build_volume_evidence


def frame(n=140):
    close = np.linspace(100, 114, n)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC").astype("int64") // 10**6,
        "open": close - 0.2,
        "high": close + 0.8,
        "low": close - 0.8,
        "close": close,
        "volume": np.full(n, 10.0),
    })


def test_volume_evidence_exposes_causal_observations():
    result = build_volume_evidence(frame())
    for column in [
        "volume_evidence_relative",
        "volume_evidence_zscore",
        "volume_evidence_expansion",
        "volume_evidence_dry_up",
        "volume_evidence_breakout_up",
        "volume_evidence_breakout_down",
        "volume_evidence_rejection_high",
        "volume_evidence_rejection_low",
        "volume_evidence_liquidity_sweep_high",
        "volume_evidence_liquidity_sweep_low",
        "volume_evidence_displacement_up",
        "volume_evidence_displacement_down",
    ]:
        assert column in result.columns
    assert len(result) == len(frame())


def test_volume_expansion_uses_only_prior_volume_baseline():
    x = frame()
    x.loc[100, "volume"] = 100.0
    result = build_volume_evidence(x)
    assert result.loc[100, "volume_evidence_expansion"] == 1
    assert result.loc[100, "volume_evidence_relative"] > 1.5


def test_volume_dry_up_uses_only_prior_volume_baseline():
    x = frame()
    x.loc[100, "volume"] = 1.0
    result = build_volume_evidence(x)
    assert result.loc[100, "volume_evidence_dry_up"] == 1
    assert result.loc[100, "volume_evidence_relative"] < 0.75


def test_volume_evidence_attaches_to_causal_market_events():
    x = frame()
    x.loc[100, "volume"] = 100.0
    structure = pd.DataFrame({
        "bos_up": np.zeros(len(x), dtype=np.int8),
        "bos_down": np.zeros(len(x), dtype=np.int8),
    })
    structure.loc[100, "bos_up"] = 1
    liquidity = pd.DataFrame({
        "sweep_high": np.zeros(len(x), dtype=np.int8),
        "sweep_low": np.zeros(len(x), dtype=np.int8),
    })
    liquidity.loc[100, "sweep_high"] = 1
    result = build_volume_evidence(x, structure=structure, liquidity=liquidity)
    assert result.loc[100, "volume_evidence_breakout_up"] == 1
    assert result.loc[100, "volume_evidence_liquidity_sweep_high"] == 1
    assert result.loc[100, "volume_evidence_rejection_high"] == 1


def test_volume_evidence_can_attach_displacement_without_creating_a_signal():
    x = frame()
    x.loc[100, "volume"] = 100.0
    displacement = pd.DataFrame({
        "displacement_up": np.zeros(len(x), dtype=np.int8),
        "displacement_down": np.zeros(len(x), dtype=np.int8),
    })
    displacement.loc[100, "displacement_up"] = 1
    result = build_volume_evidence(x, displacement=displacement)
    assert result.loc[100, "volume_evidence_displacement_up"] == 1
    assert "volume_evidence_score" not in result.columns


def test_future_changes_do_not_rewrite_prior_volume_evidence():
    base = frame()
    altered = base.copy()
    altered.loc[100:, "volume"] = 1000.0
    altered.loc[100:, "high"] *= 2
    altered.loc[100:, "low"] *= 0.5
    altered.loc[100:, "close"] *= 1.5
    a = build_volume_evidence(base)
    b = build_volume_evidence(altered)
    pd.testing.assert_frame_equal(a.iloc[:100], b.iloc[:100], check_dtype=False)


def test_volume_evidence_rejects_invalid_input():
    x = frame()
    x.loc[10, "volume"] = -1.0
    with pytest.raises(ValueError):
        build_volume_evidence(x)


def test_volume_evidence_propagates_through_unified_smc():
    x = frame()
    x.loc[100, "volume"] = 100.0
    structure = pd.DataFrame({
        "bos_up": np.zeros(len(x), dtype=np.int8),
        "bos_down": np.zeros(len(x), dtype=np.int8),
    })
    structure.loc[100, "bos_up"] = 1
    liquidity = pd.DataFrame({
        "sweep_high": np.zeros(len(x), dtype=np.int8),
        "sweep_low": np.zeros(len(x), dtype=np.int8),
    })
    liquidity.loc[100, "sweep_high"] = 1
    displacement = pd.DataFrame({
        "displacement_up": np.zeros(len(x), dtype=np.int8),
        "displacement_down": np.zeros(len(x), dtype=np.int8),
    })
    displacement.loc[100, "displacement_up"] = 1

    evidence = build_volume_evidence(
        x, structure=structure, liquidity=liquidity, displacement=displacement
    )
    from aicfa.unified_smc import build_unified_smc
    result = build_unified_smc(
        x,
        structure=structure,
        liquidity=liquidity,
        displacement=displacement,
        volume_evidence=evidence,
    )

    for column in [
        "smc_volume_evidence_relative",
        "smc_volume_evidence_zscore",
        "smc_volume_evidence_expansion",
        "smc_volume_evidence_breakout_up",
        "smc_volume_evidence_rejection_high",
        "smc_volume_evidence_liquidity_sweep_high",
        "smc_volume_evidence_displacement_up",
    ]:
        assert column in result.columns
    assert result.loc[100, "smc_volume_evidence_breakout_up"] == 1
    assert result.loc[100, "smc_volume_evidence_rejection_high"] == 1
    assert "smc_volume_evidence_score" not in result.columns


def test_features_expose_volume_evidence():
    from aicfa.features import build_features
    result = build_features(frame())
    for column in [
        "volume_evidence_relative",
        "volume_evidence_zscore",
        "volume_evidence_expansion",
        "volume_evidence_dry_up",
        "volume_evidence_breakout_up",
        "volume_evidence_breakout_down",
        "volume_evidence_rejection_high",
        "volume_evidence_rejection_low",
        "volume_evidence_liquidity_sweep_high",
        "volume_evidence_liquidity_sweep_low",
        "volume_evidence_displacement_up",
        "volume_evidence_displacement_down",
        "smc_volume_evidence_relative",
        "smc_volume_evidence_expansion",
        "smc_volume_evidence_breakout_up",
        "smc_volume_evidence_rejection_high",
        "smc_volume_evidence_liquidity_sweep_high",
        "smc_volume_evidence_displacement_up",
    ]:
        assert column in result.columns
