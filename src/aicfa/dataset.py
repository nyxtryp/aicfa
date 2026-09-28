"""Build leak-safe training datasets from causal features and future labels."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_COLUMNS = {"open", "high", "low", "close", "volume"}
LABEL_PREFIXES = (
    "future_return_",
    "future_mfe_",
    "future_mae_",
    "time_to_mfe_",
    "time_to_long_tp_",
    "time_to_long_sl_",
    "time_to_short_tp_",
    "time_to_short_sl_",
    "triple_barrier_",
)


def build_dataset(features: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    """Join causal features with future targets without exposing raw market columns.

    The returned dataset contains timestamp, engineered causal features, and
    future-outcome targets. Raw OHLCV columns are intentionally excluded from
    model inputs; they remain available in the source datasets for backtesting.
    """
    if "timestamp" not in features.columns or "timestamp" not in labels.columns:
        raise ValueError("Both features and labels must contain timestamp")

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

    label_columns = [
        column
        for column in label_frame.columns
        if column.startswith(LABEL_PREFIXES)
    ]
    if not label_columns:
        raise ValueError("labels contains no recognized target columns")

    feature_columns = [
        column
        for column in feature_frame.columns
        if column not in RAW_COLUMNS and column != "timestamp"
    ]
    if not feature_columns:
        raise ValueError("features contains no engineered feature columns")

    selected_features = feature_frame[["timestamp", *feature_columns]]
    selected_labels = label_frame[["timestamp", *label_columns]]

    dataset = selected_features.merge(
        selected_labels,
        on="timestamp",
        how="inner",
        validate="one_to_one",
    ).sort_values("timestamp").reset_index(drop=True)

    dataset = dataset.dropna(
        subset=[*feature_columns, *label_columns]
    ).reset_index(drop=True)

    if dataset.empty:
        raise ValueError("No complete rows remain after joining and removing warmup/future rows")

    return dataset


def build_dataset_from_csv(
    features_path: Path,
    labels_path: Path,
    target_path: Path,
) -> int:
    """Build one persistent dataset CSV and return its row count."""
    features = pd.read_csv(features_path)
    labels = pd.read_csv(labels_path)
    dataset = build_dataset(features, labels)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(target_path, index=False)
    return len(dataset)
