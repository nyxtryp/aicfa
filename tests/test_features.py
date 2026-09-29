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
        "smc_premium_discount",
        "smc_state_ready",
        "return_60",
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
