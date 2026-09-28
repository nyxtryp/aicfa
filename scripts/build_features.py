"""Build persistent causal feature datasets from AICFA raw OHLCV CSVs."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from aicfa.features import build_features


DATA_DIR = Path(os.getenv("AICFA_DATA_DIR", str(ROOT / "data")))
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"


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
            source = RAW_DIR / safe_symbol / f"{timeframe}.csv"
            target_dir = PROCESSED_DIR / safe_symbol
            target = target_dir / f"{timeframe}.csv"

            if not source.exists():
                print(f"{symbol} {timeframe}: raw file not found, skipping")
                continue

            df = pd.read_csv(source)
            features = build_features(df)
            target_dir.mkdir(parents=True, exist_ok=True)
            features.to_csv(target, index=False)
            print(f"{symbol} {timeframe}: {len(features)} rows -> {target}")


if __name__ == "__main__":
    main()
