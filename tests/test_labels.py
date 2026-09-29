from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aicfa.labels import build_labels


def make_ohlc(n: int = 160) -> pd.DataFrame:
    close = np.linspace(100.0, 110.0, n)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="min"),
            "open": close,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
        }
    )


def test_new_label_schema() -> None:
    labels = build_labels(make_ohlc(), horizons=(5, 20))

    assert len(labels) == 160
    assert "future_return_5" in labels.columns
    assert "future_log_return_20" in labels.columns
    assert "future_mfe_long_5" in labels.columns
    assert "future_mae_short_20" in labels.columns
    assert "future_mfe_long_r_5" in labels.columns
    assert "time_to_mfe_short_20" in labels.columns
    assert "event_outcome_5" in labels.columns
    assert "event_touch_20" in labels.columns
    assert "event_return_20" in labels.columns
    assert "event_end_offset_20" in labels.columns
    assert "event_target_vol_20" in labels.columns
    assert "event_ambiguous_20" in labels.columns
    assert "label_end_timestamp_5" in labels.columns
    assert "label_end_timestamp_20" in labels.columns


def test_future_rows_are_nan() -> None:
    labels = build_labels(make_ohlc(), horizons=(5,))

    for column in (
        "future_return_5",
        "future_log_return_5",
        "future_mfe_long_5",
        "future_mae_short_5",
        "event_outcome_5",
        "event_return_5",
        "event_end_offset_5",
    ):
        assert labels[column].iloc[-5:].isna().all()


def test_mfe_and_mae_are_non_negative() -> None:
    labels = build_labels(make_ohlc(), horizons=(5,))

    valid = labels.dropna(
        subset=["future_mfe_long_5", "future_mae_long_5"]
    )
    assert (valid["future_mfe_long_5"] >= 0).all()
    assert (valid["future_mfe_short_5"] >= 0).all()
    assert (valid["future_mae_long_5"] >= 0).all()
    assert (valid["future_mae_short_5"] >= 0).all()


def test_time_to_mfe_is_inside_horizon() -> None:
    labels = build_labels(make_ohlc(), horizons=(5,))

    valid = labels.dropna(subset=["time_to_mfe_long_5"])
    assert valid["time_to_mfe_long_5"].between(1, 5).all()
    assert valid["time_to_mfe_short_5"].between(1, 5).all()


def test_event_outcomes_are_valid_codes() -> None:
    labels = build_labels(make_ohlc(), horizons=(5,))

    valid = labels.dropna(subset=["event_outcome_5"])
    assert set(valid["event_outcome_5"].unique()).issubset({-1.0, 0.0, 1.0})
    assert set(valid["event_touch_5"].unique()).issubset({-1.0, 0.0, 1.0})


def test_ambiguous_ohlc_bar_is_not_assigned_a_winner() -> None:
    df = make_ohlc(20)

    # With volatility_span=2 the first finite causal volatility target is
    # available at index 2. Create the ambiguous bar immediately after it.
    anchor = 2
    df.loc[anchor + 1, "high"] = df.loc[anchor, "close"] * 1.2
    df.loc[anchor + 1, "low"] = df.loc[anchor, "close"] * 0.8

    labels = build_labels(
        df,
        horizons=(5,),
        volatility_span=2,
        pt_mult=1.0,
        sl_mult=1.0,
    )

    assert labels.loc[anchor, "event_ambiguous_5"] == 1.0
    assert np.isnan(labels.loc[anchor, "event_outcome_5"])


def test_no_infinite_numeric_labels() -> None:
    labels = build_labels(make_ohlc(), horizons=(5, 20, 60))
    numeric = labels.select_dtypes(include=[np.number]).to_numpy()
    assert np.isfinite(numeric[~np.isnan(numeric)]).all()


def test_input_validation() -> None:
    with pytest.raises(ValueError, match="positive"):
        build_labels(make_ohlc(), horizons=(5,), pt_mult=0)

    with pytest.raises(ValueError, match="volatility_span"):
        build_labels(make_ohlc(), horizons=(5,), volatility_span=1)
