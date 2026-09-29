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


def test_derivatives_liquidation_imbalance_is_event_based_and_causal():
    base = base_frame()
    d = derivatives_frame()
    d["long_liquidation_volume"] = [4.0, 6.0, 2.0, 9.0, 3.0, 8.0]
    d["short_liquidation_volume"] = [6.0, 2.0, 8.0, 3.0, 7.0, 2.0]

    out = build_derivatives(base, d, baseline_window=2)

    assert np.isclose(out.loc[0, "liquidation_imbalance"], -0.2)
    assert pd.isna(out.loc[1, "liquidation_imbalance"])
    assert np.isclose(out.loc[2, "liquidation_imbalance"], 0.5)
    assert pd.isna(out.loc[3, "liquidation_imbalance"])
    assert np.isclose(out.loc[4, "liquidation_imbalance"], -0.6)

    altered = d.copy()
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:08:00Z"), "long_liquidation_volume"] *= 10
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:08:00Z"), "short_liquidation_volume"] *= 0.1
    changed = build_derivatives(base, altered, baseline_window=2)
    pd.testing.assert_frame_equal(out.iloc[:8], changed.iloc[:8], check_dtype=False)


def test_derivatives_liquidation_imbalance_handles_zero_event_volume():
    base = base_frame()
    d = derivatives_frame()
    d["long_liquidation_volume"] = [0.0] * len(d)
    d["short_liquidation_volume"] = [0.0] * len(d)

    out = build_derivatives(base, d, baseline_window=2)

    assert pd.isna(out.loc[0, "liquidation_imbalance"])


def test_derivatives_futures_volume_is_event_based_and_causal():
    base = base_frame()
    d = derivatives_frame()
    d["futures_volume"] = [100.0, 120.0, 90.0, 150.0, 80.0, 200.0]

    out = build_derivatives(base, d, baseline_window=2)

    assert out.loc[0, "futures_volume"] == 100.0
    assert pd.isna(out.loc[1, "futures_volume"])
    assert out.loc[2, "futures_volume"] == 120.0
    assert pd.isna(out.loc[3, "futures_volume"])
    assert out.loc[4, "futures_volume"] == 90.0
    assert "futures_volume_delta" in out
    assert "futures_volume_change_pct" in out
    assert "futures_volume_zscore" in out

    altered = d.copy()
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:08:00Z"), "futures_volume"] *= 10
    changed = build_derivatives(base, altered, baseline_window=2)
    pd.testing.assert_frame_equal(out.iloc[:8], changed.iloc[:8], check_dtype=False)


def test_derivatives_reject_negative_futures_volume():
    base = base_frame()
    d = derivatives_frame()
    d["futures_volume"] = [100.0] * len(d)
    d.loc[2, "futures_volume"] = -1.0

    with pytest.raises(ValueError):
        build_derivatives(base, d, baseline_window=2)


def test_derivatives_spot_futures_relationship_is_causal():
    base = base_frame()
    d = derivatives_frame()
    d["spot_price"] = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    d["futures_price"] = [100.2, 101.4, 101.7, 103.5, 104.8, 105.2]

    out = build_derivatives(base, d, baseline_window=2)

    assert out.loc[0, "spot_price"] == 100.0
    assert np.isclose(out.loc[1, "futures_spot_spread"], 0.4)
    assert np.isclose(out.loc[2, "futures_spot_spread"], -0.3)
    assert np.isclose(out.loc[2, "futures_spot_spread_pct"], 101.7 / 102.0 - 1.0)
    assert np.isclose(out.loc[3, "futures_spot_spread"], -0.3)
    assert "futures_spot_spread_delta" in out
    assert "futures_spot_spread_zscore" in out

    altered = d.copy()
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:08:00Z"), "spot_price"] *= 2
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:08:00Z"), "futures_price"] *= 3
    changed = build_derivatives(base, altered, baseline_window=2)
    pd.testing.assert_frame_equal(out.iloc[:8], changed.iloc[:8], check_dtype=False)


def test_derivatives_reject_nonpositive_spot_futures_prices():
    base = base_frame()
    d = derivatives_frame()
    d["spot_price"] = 100.0
    d["futures_price"] = 100.0
    d.loc[1, "spot_price"] = 0.0

    with pytest.raises(ValueError):
        build_derivatives(base, d, baseline_window=2)


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
    assert out.loc[1, "basis"] == 0.001
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
