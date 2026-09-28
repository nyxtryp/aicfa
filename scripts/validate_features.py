"""Validate AICFA processed feature datasets.

Checks shape, schema, NaN warmup, finite values, causal lookahead,
and basic feature ranges without modifying source data.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd

from aicfa.features import build_features


DATA_DIR = Path(os.getenv("AICFA_DATA_DIR", str(ROOT / "data")))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

REQUIRED = ["timestamp", "open", "high", "low", "close", "volume"]


def validate(symbol: str, timeframe: str) -> None:
    safe = symbol.replace("/", "_")
    raw_path = RAW_DIR / safe / f"{timeframe}.csv"
    processed_path = PROCESSED_DIR / safe / f"{timeframe}.csv"

    if not raw_path.exists():
        print(f"{symbol} {timeframe}: raw file not found")
        return
    if not processed_path.exists():
        print(f"{symbol} {timeframe}: processed file not found")
        return

    raw = pd.read_csv(raw_path)
    processed = pd.read_csv(processed_path)

    expected = build_features(raw)

    if len(processed) != len(raw):
        raise AssertionError(f"row count mismatch: raw={len(raw)} processed={len(processed)}")
    if list(processed.columns) != list(expected.columns):
        raise AssertionError("processed schema does not match feature engine output")
    if not processed["timestamp"].equals(expected["timestamp"]):
        raise AssertionError("processed timestamps differ from raw timestamps")

    feature_cols = [c for c in processed.columns if c not in REQUIRED]
    numeric = processed[feature_cols].apply(pd.to_numeric, errors="coerce")
    non_finite = int((~np.isfinite(numeric.to_numpy())).sum())
    if non_finite:
        raise AssertionError(f"non-finite feature values: {non_finite}")

    nan_counts = numeric.isna().sum()
    if (nan_counts > 0).any():
        print(f"  warmup NaNs: {int(nan_counts.sum())} total across {int((nan_counts > 0).sum())} columns")

    bounded = {
        "close_location": (0.0, 1.0),
        "direction": (-1.0, 1.0),
        "dealing_range_position": (0.0, 1.0),
        "breakout_up": (0.0, 1.0),
        "breakout_down": (0.0, 1.0),
        "sweep_high_reject": (0.0, 1.0),
        "sweep_low_reclaim": (0.0, 1.0),
        "hour_utc": (0.0, 23.0),
        "day_of_week": (0.0, 6.0),
    }
    for column, (lo, hi) in bounded.items():
        values = processed[column].dropna()
        if not values.between(lo, hi).all():
            raise AssertionError(f"{column} out of bounds")

    # Strong causal check: mutate only future raw candles and rebuild.
    if len(raw) >= 120:
        cut = len(raw) // 2
        altered = raw.copy()
        altered.loc[cut:, "high"] *= 1000.0
        altered.loc[cut:, "low"] *= 0.001
        altered.loc[cut:, "close"] *= 500.0
        altered_features = build_features(altered)
        pd.testing.assert_frame_equal(
            expected.iloc[:cut],
            altered_features.iloc[:cut],
            check_dtype=False,
        )

    print(
        f"{symbol} {timeframe}: OK | rows={len(processed)} "
        f"| features={len(feature_cols)} | columns={len(processed.columns)}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDT"])
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"],
    )
    args = parser.parse_args()

    for symbol in args.symbols:
        for timeframe in args.timeframes:
            validate(symbol, timeframe)


if __name__ == "__main__":
    main()
