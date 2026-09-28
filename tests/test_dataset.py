from __future__ import annotations

import numpy as np
import pandas as pd

from aicfa.dataset import build_dataset


def make_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    timestamp = pd.date_range("2026-01-01", periods=8, freq="min", tz="UTC")
    features = pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": np.arange(8, dtype=float) + 100,
            "high": np.arange(8, dtype=float) + 101,
            "low": np.arange(8, dtype=float) + 99,
            "close": np.arange(8, dtype=float) + 100.5,
            "volume": 100.0,
            "return_1": np.linspace(0.01, 0.08, 8),
            "relative_volume_5": np.linspace(1.0, 1.7, 8),
        }
    )
    labels = pd.DataFrame(
        {
            "timestamp": timestamp,
            "open": features["open"],
            "high": features["high"],
            "low": features["low"],
            "close": features["close"],
            "future_return_5": np.linspace(0.01, 0.08, 8),
            "future_mfe_long_5": np.linspace(0.02, 0.09, 8),
            "triple_barrier_5": [1, 0, -1, 1, 0, -1, 1, np.nan],
        }
    )
    return features, labels


def test_dataset_contains_features_and_targets_only() -> None:
    features, labels = make_inputs()
    dataset = build_dataset(features, labels)

    assert list(dataset.columns) == [
        "timestamp",
        "return_1",
        "relative_volume_5",
        "future_return_5",
        "future_mfe_long_5",
        "triple_barrier_5",
    ]
    assert "close" not in dataset.columns
    assert len(dataset) == 7


def test_dataset_is_sorted_and_drops_incomplete_rows() -> None:
    features, labels = make_inputs()
    features = features.iloc[::-1].reset_index(drop=True)
    labels = labels.iloc[::-1].reset_index(drop=True)

    dataset = build_dataset(features, labels)

    assert dataset["timestamp"].is_monotonic_increasing
    assert dataset["future_return_5"].notna().all()
    assert dataset["triple_barrier_5"].notna().all()


def test_dataset_rejects_duplicate_timestamps() -> None:
    features, labels = make_inputs()
    features = pd.concat([features, features.iloc[[0]]], ignore_index=True)

    try:
        build_dataset(features, labels)
    except ValueError as exc:
        assert "duplicate timestamps" in str(exc)
    else:
        raise AssertionError("Expected duplicate timestamp validation error")
