"""Build leak-safe training datasets from processed features and labels."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from aicfa.dataset import build_dataset_from_csv


DATA_DIR = Path(os.getenv("AICFA_DATA_DIR", str(ROOT / "data")))
PROCESSED_DIR = DATA_DIR / "processed"
DATASET_DIR = DATA_DIR / "dataset"


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
        safe_symbol = symbol.replace("/", "_")
        for timeframe in args.timeframes:
            features_path = PROCESSED_DIR / safe_symbol / f"{timeframe}.csv"
            labels_path = DATASET_DIR / safe_symbol / f"{timeframe}_labels.csv"
            target_path = DATASET_DIR / safe_symbol / f"{timeframe}.csv"

            if not features_path.exists():
                print(f"{symbol} {timeframe}: features file not found, skipping")
                continue
            if not labels_path.exists():
                print(f"{symbol} {timeframe}: labels file not found, skipping")
                continue

            rows = build_dataset_from_csv(
                features_path,
                labels_path,
                target_path,
            )
            print(f"{symbol} {timeframe}: {rows} training rows -> {target_path}")


if __name__ == "__main__":
    main()
