"""Build persistent AICFA research labels from raw OHLCV datasets."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from aicfa.labels import build_labels


DATA_DIR = Path(os.getenv("AICFA_DATA_DIR", str(ROOT / "data")))
RAW_DIR = DATA_DIR / "raw"
DATASET_DIR = DATA_DIR / "dataset"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["BTC/USDT"])
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=["1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M"],
    )
    parser.add_argument(
        "--horizons",
        nargs="+",
        type=int,
        default=[5, 20, 60],
        help="Future horizon lengths in candles.",
    )
    parser.add_argument(
        "--volatility-span",
        type=int,
        default=64,
        help="EWMA span for causal realized volatility.",
    )
    parser.add_argument(
        "--pt-mult",
        type=float,
        default=2.0,
        help="Profit-taking barrier in target-volatility units.",
    )
    parser.add_argument(
        "--sl-mult",
        type=float,
        default=1.0,
        help="Stop-loss barrier in target-volatility units.",
    )
    args = parser.parse_args()

    for symbol in args.symbols:
        safe_symbol = symbol.replace("/", "_")
        for timeframe in args.timeframes:
            source = RAW_DIR / safe_symbol / f"{timeframe}.csv"
            target_dir = DATASET_DIR / safe_symbol
            target = target_dir / f"{timeframe}_labels.csv"

            if not source.exists():
                print(f"{symbol} {timeframe}: raw file not found, skipping")
                continue

            raw = pd.read_csv(source)
            labels = build_labels(
                raw,
                horizons=tuple(args.horizons),
                volatility_span=args.volatility_span,
                pt_mult=args.pt_mult,
                sl_mult=args.sl_mult,
            )
            target_dir.mkdir(parents=True, exist_ok=True)
            labels.to_csv(target, index=False)
            print(f"{symbol} {timeframe}: {len(labels)} rows -> {target}")


if __name__ == "__main__":
    main()
