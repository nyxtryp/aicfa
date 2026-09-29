"""Build leak-safe, task-specific training datasets from causal features and future labels."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_COLUMNS = {"open", "high", "low", "close", "volume"}

TASK_TARGETS = {
    "direction": ("event_outcome_", "label_end_timestamp_"),
    "event": (
        "event_outcome_", "event_touch_", "event_return_", "event_log_return_",
        "event_end_offset_", "event_target_vol_", "event_ambiguous_",
        "label_end_timestamp_",
    ),
    "path": (
        "future_return_", "future_log_return_", "future_mfe_", "future_mae_",
        "future_mfe_long_r_", "future_mfe_short_r_",
        "future_mae_long_r_", "future_mae_short_r_",
        "time_to_mfe_", "target_vol_", "label_end_timestamp_",
    ),
}


def _target_columns(labels: pd.DataFrame, task: str, horizon: int) -> list[str]:
    if task not in TASK_TARGETS:
        raise ValueError(f"Unknown task: {task}. Choose from {sorted(TASK_TARGETS)}")

    suffix = f"_{horizon}"
    columns = [
        column for column in labels.columns
        if column.endswith(suffix) and column.startswith(TASK_TARGETS[task])
    ]
    if task == "direction":
        required = f"event_outcome_{horizon}"
        columns = [required] if required in labels.columns else []

    if not columns:
        raise ValueError(
            f"labels contains no targets for task={task!r}, horizon={horizon}"
        )
    return columns


def build_dataset(
    features: pd.DataFrame,
    labels: pd.DataFrame,
    *,
    task: str = "direction",
    horizon: int = 20,
) -> pd.DataFrame:
    """Join causal features with only the targets required by one task.

    The label interval is preserved through label_end_timestamp_<horizon>
    so leakage-aware validation can purge overlapping training labels.
    """
    if "timestamp" not in features.columns or "timestamp" not in labels.columns:
        raise ValueError("Both features and labels must contain timestamp")
    if horizon <= 0:
        raise ValueError("horizon must be positive")

    feature_frame = features.copy()
    label_frame = labels.copy()
    feature_frame["timestamp"] = pd.to_datetime(
        feature_frame["timestamp"], unit="ms", utc=True, errors="raise"
    )
    label_frame["timestamp"] = pd.to_datetime(
        label_frame["timestamp"], unit="ms", utc=True, errors="raise"
    )

    if feature_frame["timestamp"].duplicated().any():
        raise ValueError("features contains duplicate timestamps")
    if label_frame["timestamp"].duplicated().any():
        raise ValueError("labels contains duplicate timestamps")

    feature_columns = [
        c for c in feature_frame.columns
        if c not in RAW_COLUMNS and c != "timestamp"
    ]
    if not feature_columns:
        raise ValueError("features contains no engineered feature columns")

    label_columns = _target_columns(label_frame, task, horizon)
    dataset = (
        feature_frame[["timestamp", *feature_columns]]
        .merge(
            label_frame[["timestamp", *label_columns]],
            on="timestamp",
            how="inner",
            validate="one_to_one",
        )
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    required_targets = [
        c for c in label_columns if not c.startswith("label_end_timestamp_")
    ]
    dataset = dataset.dropna(
        subset=[*feature_columns, *required_targets]
    ).reset_index(drop=True)

    if dataset.empty:
        raise ValueError(
            "No rows remain after joining and removing incomplete features/targets"
        )

    end_column = f"label_end_timestamp_{horizon}"
    if end_column in dataset.columns:
        dataset[end_column] = pd.to_datetime(
            dataset[end_column], utc=True, errors="raise"
        )
        dataset = dataset[dataset[end_column].notna()].reset_index(drop=True)

    return dataset


def build_dataset_from_csv(
    features_path: Path,
    labels_path: Path,
    target_path: Path,
    *,
    task: str = "direction",
    horizon: int = 20,
) -> int:
    """Build one persistent task-specific dataset CSV."""
    features = pd.read_csv(features_path)
    labels = pd.read_csv(labels_path)
    dataset = build_dataset(features, labels, task=task, horizon=horizon)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(target_path, index=False)
    return len(dataset)
