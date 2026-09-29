import numpy as np
import pandas as pd
import pytest

from aicfa.volume_volatility import build_volume_volatility

def frame(n=140):
    close = np.linspace(100, 114, n)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC").astype("int64") // 10**6,
        "open": close - 0.2, "high": close + 0.8, "low": close - 0.8,
        "close": close, "volume": np.linspace(10, 30, n),
    })

def test_volume_volatility_outputs_causal_regime_features():
    r = build_volume_volatility(frame())
    for c in ["realized_volatility","true_range","atr","atr_pct","range_zscore",
              "volume_zscore","relative_volume_causal","volatility_ratio",
              "volatility_expansion","volatility_compression","volume_expansion",
              "volume_dry_up","volatility_regime","volume_regime"]:
        assert c in r.columns
    assert len(r) == 140

def test_expansion_uses_prior_baseline():
    x = frame(140)
    x.loc[139, "volume"] = 1000.0
    r = build_volume_volatility(x)
    assert r.loc[139, "volume_expansion"] == 1
    assert r.loc[139, "volume_zscore"] > 1.0

def test_future_changes_do_not_rewrite_prior_rows():
    base = frame(150)
    altered = base.copy()
    altered.loc[120:, ["high","low","close","volume"]] *= [1000, 0.001, 500, 100]
    a = build_volume_volatility(base)
    b = build_volume_volatility(altered)
    pd.testing.assert_frame_equal(a.iloc[:120], b.iloc[:120], check_dtype=False)

def test_invalid_parameters_and_volume():
    with pytest.raises(ValueError):
        build_volume_volatility(frame(), short_window=1)
    with pytest.raises(ValueError):
        build_volume_volatility(frame(), short_window=60, long_window=15)
    x = frame(20)
    x.loc[5, "volume"] = -1
    with pytest.raises(ValueError):
        build_volume_volatility(x)
