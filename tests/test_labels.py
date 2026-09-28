from __future__ import annotations

import numpy as np
import pandas as pd

from aicfa.labels import build_labels


def make_ohlc(n: int = 100) -> pd.DataFrame:
    close = np.linspace(100.0, 110.0, n)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="min"),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 100.0,
        }
    )


def test_labels_keep_input_schema_and_expected_columns() -> None:
    df = make_ohlc()
    labels = build_labels(df, horizons=(5, 20))

    assert len(labels) == len(df)
    assert list(labels.columns[:6]) == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "future_return_5",
    ]
    assert "future_return_20" in labels.columns
    assert "future_mfe_long_5" in labels.columns
    assert "triple_barrier_20" in labels.columns


def test_final_rows_have_no_fake_future_outcomes() -> None:
    labels = build_labels(make_ohlc(), horizons=(5,))

    assert labels["future_return_5"].iloc[-1:].isna().all()
    assert labels["future_mfe_long_5"].iloc[-5:].isna().all()
    assert labels["triple_barrier_5"].iloc[-5:].isna().all()


def test_labels_are_allowed_to_depend_on_future_prices() -> None:
    base = make_ohlc()
    altered = base.copy()
    altered.loc[60:, "high"] *= 2.0
    altered.loc[60:, "close"] *= 2.0

    a = build_labels(base, horizons=(5,))
    b = build_labels(altered, horizons=(5,))

    # A target at t may change when a future candle changes. This is expected.
    assert a["future_return_5"].iloc[56] != b["future_return_5"].iloc[56]


def test_no_infinite_labels() -> None:
    labels = build_labels(make_ohlc(), horizons=(5, 20, 60))
    numeric = labels.drop(columns=["timestamp"]).to_numpy(dtype=float)
    assert np.isfinite(numeric[~np.isnan(numeric)]).all()
