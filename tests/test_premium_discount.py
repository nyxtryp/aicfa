import numpy as np
import pandas as pd
import pytest

from aicfa.premium_discount import build_premium_discount


def frame():
    n = 9
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC").astype("int64") // 10**6,
        "open": [100, 104, 106, 103, 94, 96, 99, 102, 103],
        "high": [103, 106, 110, 105, 100, 101, 102, 106, 107],
        "low": [97, 99, 104, 95, 90, 95, 96, 97, 98],
        "close": [101, 105, 108, 96, 95, 98, 100, 105, 104],
    })


def test_structural_dealing_range_uses_confirmed_swings():
    result = build_premium_discount(frame())

    assert pd.isna(result.loc[5, "structural_dealing_range_high"])
    assert pd.isna(result.loc[5, "structural_dealing_range_low"])

    assert result.loc[6, "structural_dealing_range_high"] == 110
    assert result.loc[6, "structural_dealing_range_low"] == 90
    assert result.loc[6, "structural_equilibrium"] == 100
    assert result.loc[6, "structural_dealing_range_position"] == 0.5
    assert result.loc[6, "structural_premium_discount"] == 0.0
    assert result.loc[6, "equilibrium"] == 1


def test_premium_and_discount_are_classified_from_structural_range():
    result = build_premium_discount(frame())

    assert result.loc[7, "structural_dealing_range_position"] == 0.75
    assert result.loc[7, "structural_premium_discount"] == 0.5
    assert result.loc[7, "premium"] == 1
    assert result.loc[7, "discount"] == 0
    assert result.loc[8, "structural_dealing_range_position"] == 0.7
    assert result.loc[8, "premium"] == 1


def test_structural_range_is_causal_under_future_changes():
    base = frame()
    altered = base.copy()
    altered.loc[7:, ["high", "low", "close"]] = [
        [1000, 1, 500],
        [2000, 0.5, 1000],
    ]

    a = build_premium_discount(base)
    b = build_premium_discount(altered)

    pd.testing.assert_frame_equal(a.iloc[:7], b.iloc[:7], check_dtype=False)


def test_invalid_parameters_and_validation():
    with pytest.raises(ValueError):
        build_premium_discount(frame(), left=0)

    invalid = frame()
    invalid.loc[0, "low"] = 102
    with pytest.raises(ValueError):
        build_premium_discount(invalid)
