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
            "event_outcome_5": [1, -1, 0, 1, -1, 1, np.nan, np.nan],
            "event_touch_5": [1, -1, 0, 1, -1, 1, np.nan, np.nan],
            "event_return_5": [0.02, -0.01, 0.001, 0.02, -0.01, 0.02, np.nan, np.nan],
            "event_end_offset_5": [2, 2, 5, 1, 3, 4, np.nan, np.nan],
            "event_target_vol_5": [0.001] * 6 + [np.nan, np.nan],
            "event_ambiguous_5": [0, 0, 0, 0, 0, 0, np.nan, np.nan],
            "label_end_timestamp_5": [
                timestamp[2], timestamp[3], timestamp[7], timestamp[4],
                timestamp[7], timestamp[7], pd.NaT, pd.NaT
            ],
            "future_return_5": np.linspace(0.01, 0.08, 8),
            "future_mfe_long_5": np.linspace(0.02, 0.09, 8),
        }
    )
    return features, labels


def test_direction_dataset_selects_only_direction_target() -> None:
    features, labels = make_inputs()
    dataset = build_dataset(features, labels, task="direction", horizon=5)
    assert list(dataset.columns) == [
        "timestamp", "return_1", "relative_volume_5", "event_outcome_5"
    ]
    assert len(dataset) == 6
    assert "close" not in dataset.columns


def test_event_dataset_preserves_label_interval() -> None:
    features, labels = make_inputs()
    dataset = build_dataset(features, labels, task="event", horizon=5)
    assert "label_end_timestamp_5" in dataset.columns
    assert pd.api.types.is_datetime64tz_dtype(dataset["label_end_timestamp_5"])
    assert dataset["label_end_timestamp_5"].notna().all()


def test_path_dataset_does_not_require_event_targets() -> None:
    features, labels = make_inputs()
    labels = labels.drop(
        columns=[
            "event_outcome_5", "event_touch_5", "event_return_5",
            "event_end_offset_5", "event_target_vol_5",
            "event_ambiguous_5", "label_end_timestamp_5",
        ]
    )
    dataset = build_dataset(features, labels, task="path", horizon=5)
    assert len(dataset) == 8
    assert "future_return_5" in dataset.columns


def test_dataset_rejects_duplicate_timestamps() -> None:
    features, labels = make_inputs()
    features = pd.concat([features, features.iloc[[0]]], ignore_index=True)
    try:
        build_dataset(features, labels, task="direction", horizon=5)
    except ValueError as exc:
        assert "duplicate timestamps" in str(exc)
    else:
        raise AssertionError("Expected duplicate timestamp validation error")
