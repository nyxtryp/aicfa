import numpy as np
import pandas as pd
import pytest

from aicfa.derivatives import build_derivatives


def base_frame(n=12):
    ts = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "close": np.arange(n, dtype=float) + 100,
    })


def derivatives_frame():
    ts = pd.date_range("2026-01-01", periods=6, freq="2min", tz="UTC")
    return pd.DataFrame({
        "timestamp": ts,
        "funding_rate": [-0.001, 0.0, 0.001, 0.002, 0.001, 0.003],
        "open_interest": [100, 110, 120, 115, 130, 140],
    })


def test_derivatives_align_only_known_observations():
    out = build_derivatives(base_frame(), derivatives_frame(), baseline_window=2)
    assert out.loc[0, "funding_rate"] == -0.001
    assert pd.isna(out.loc[1, "funding_rate"])
    assert out.loc[2, "funding_rate"] == 0.0
    assert out.loc[3, "open_interest"] == 110


def test_derivatives_are_causal_under_future_changes():
    base = base_frame(12)
    d = derivatives_frame()
    altered = d.copy()
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:08:00Z"), "funding_rate"] *= 100
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:08:00Z"), "open_interest"] *= 10

    a = build_derivatives(base, d, baseline_window=2)
    b = build_derivatives(base, altered, baseline_window=2)
    pd.testing.assert_frame_equal(a.iloc[:8], b.iloc[:8], check_dtype=False)


def test_derivatives_optional_liquidations_are_preserved_and_causal():
    base = base_frame()
    d = derivatives_frame()
    d["liquidation_volume"] = np.arange(len(d), dtype=float)
    d["long_liquidation_volume"] = d["liquidation_volume"] * 0.4
    d["short_liquidation_volume"] = d["liquidation_volume"] * 0.6

    out = build_derivatives(base, d, baseline_window=2)
    assert "liquidation_volume" in out
    assert "long_liquidation_volume" in out
    assert "short_liquidation_volume" in out
    assert out.loc[4, "liquidation_volume"] == 2


def test_derivatives_positioning_basis_features_are_causal():
    base = base_frame()
    d = derivatives_frame()
    d["long_short_ratio_global"] = [1.1, 1.2, 0.9, 1.3, 1.0, 1.4]
    d["long_short_ratio_top_trader"] = [1.0, 1.1, 0.95, 1.2, 0.98, 1.3]
    d["basis"] = [0.001, 0.002, 0.0015, -0.001, 0.0, 0.003]

    out = build_derivatives(base, d, baseline_window=2)

    assert out.loc[3, "long_short_ratio_global"] == 1.2
    assert out.loc[3, "long_short_ratio_top_trader"] == 1.1
    assert out.loc[3, "basis"] == 0.002
    assert pd.isna(out.loc[1, "basis"])
    assert "long_short_ratio_global_zscore" in out
    assert "basis_delta" in out


def test_derivatives_positioning_future_changes_do_not_rewrite_history():
    base = base_frame()
    d = derivatives_frame()
    d["long_short_ratio_global"] = [1.1, 1.2, 0.9, 1.3, 1.0, 1.4]
    d["basis"] = [0.001, 0.002, 0.0015, -0.001, 0.0, 0.003]

    altered = d.copy()
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:08:00Z"), "long_short_ratio_global"] *= 5
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:08:00Z"), "basis"] *= 10

    a = build_derivatives(base, d, baseline_window=2)
    b = build_derivatives(base, altered, baseline_window=2)
    pd.testing.assert_frame_equal(a.iloc[:8], b.iloc[:8], check_dtype=False)


def test_derivatives_reject_invalid_input():
    with pytest.raises(ValueError):
        build_derivatives(base_frame(), derivatives_frame().assign(open_interest=-1), baseline_window=2)
    with pytest.raises(ValueError):
        build_derivatives(base_frame(), derivatives_frame().drop(columns=["funding_rate"]), baseline_window=2)
    with pytest.raises(ValueError):
        build_derivatives(base_frame(), derivatives_frame(), baseline_window=1)

    invalid_ratio = derivatives_frame().assign(long_short_ratio_global=0)
    with pytest.raises(ValueError):
        build_derivatives(base_frame(), invalid_ratio, baseline_window=2)
