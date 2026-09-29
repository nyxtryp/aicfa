"""Causal structural dealing-range and Premium/Discount engine for AICFA.

The active dealing range is defined by the latest confirmed swing high and
latest confirmed swing low. Swing events are produced only when confirmation
is knowable, so the resulting range never uses future candles.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .structure import build_structure


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    x = (
        df[required]
        .copy()
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )
    for column in required[1:]:
        x[column] = x[column].astype(float)

    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")
    return x


def build_premium_discount(
    df: pd.DataFrame,
    *,
    left: int = 2,
    right: int = 2,
    equal_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Build a causal Premium/Discount state from confirmed structure."""

    x = _validate(df)
    structure = build_structure(
        x,
        left=left,
        right=right,
        equal_tolerance=equal_tolerance,
    )

    n = len(x)
    out = x.copy()
    for column in [
        "structural_dealing_range_high",
        "structural_dealing_range_low",
        "structural_equilibrium",
        "structural_dealing_range_position",
        "structural_premium_discount",
    ]:
        out[column] = np.nan

    out["premium"] = 0
    out["discount"] = 0
    out["equilibrium"] = 0

    latest_high = np.nan
    latest_low = np.nan
    closes = x["close"].to_numpy()

    for i in range(n):
        if structure.at[i, "swing_high"] == 1:
            latest_high = float(structure.at[i, "swing_high_price"])
        if structure.at[i, "swing_low"] == 1:
            latest_low = float(structure.at[i, "swing_low_price"])

        if not np.isfinite(latest_high) or not np.isfinite(latest_low):
            continue
        if latest_high <= latest_low:
            continue

        equilibrium = (latest_high + latest_low) / 2.0
        position = (closes[i] - latest_low) / (latest_high - latest_low)
        pd_score = position * 2.0 - 1.0

        out.at[i, "structural_dealing_range_high"] = latest_high
        out.at[i, "structural_dealing_range_low"] = latest_low
        out.at[i, "structural_equilibrium"] = equilibrium
        out.at[i, "structural_dealing_range_position"] = position
        out.at[i, "structural_premium_discount"] = pd_score
        out.at[i, "premium"] = int(position > 0.5)
        out.at[i, "discount"] = int(position < 0.5)
        out.at[i, "equilibrium"] = int(position == 0.5)

    return out
