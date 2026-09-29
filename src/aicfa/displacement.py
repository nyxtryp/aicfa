"""Causal displacement engine for AICFA.

Displacement is treated as a multi-factor event, not simply a large candle.
Every feature at row t uses only candles at or before t. Rolling baselines are
shifted so the current candle does not define its own reference regime.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close", "volume"]
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
    if (x["volume"] < 0).any():
        raise ValueError("Invalid volume: negative values are not allowed")
    return x


def build_displacement(
    df: pd.DataFrame,
    *,
    baseline: int = 20,
    range_expansion_threshold: float = 1.5,
    body_expansion_threshold: float = 1.5,
    relative_volume_threshold: float = 1.2,
    close_efficiency_threshold: float = 0.6,
    impulsive_close_threshold: float = 0.75,
) -> pd.DataFrame:
    """Build causal displacement features and events.

    A displacement event requires simultaneous evidence of:
    - expanded candle range;
    - expanded real body;
    - efficient directional close;
    - elevated relative volume;
    - an impulsive close near the candle extreme.

    displacement_up/down are therefore deliberately stricter than a generic
    "large candle" flag. Structural-break relationships are exposed as
    displacement_bos_up/down after causal structure confirmation.
    """
    if baseline < 2:
        raise ValueError("baseline must be at least 2")
    for name, value in (
        ("range_expansion_threshold", range_expansion_threshold),
        ("body_expansion_threshold", body_expansion_threshold),
        ("relative_volume_threshold", relative_volume_threshold),
        ("close_efficiency_threshold", close_efficiency_threshold),
    ):
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    if not 0.5 <= impulsive_close_threshold < 1.0:
        raise ValueError("impulsive_close_threshold must be in [0.5, 1)")

    x = _validate(df)
    out = x.copy()

    o = x["open"]
    h = x["high"]
    l = x["low"]
    c = x["close"]
    v = x["volume"]

    candle_range = (h - l).clip(lower=EPS)
    body = c - o
    body_abs = body.abs()

    # References use only completed candles strictly before t.
    range_baseline = candle_range.shift(1).rolling(baseline, min_periods=baseline).mean()
    body_baseline = body_abs.shift(1).rolling(baseline, min_periods=baseline).mean()
    volume_baseline = v.shift(1).rolling(baseline, min_periods=baseline).mean()

    out["displacement_range_expansion"] = candle_range / range_baseline.clip(lower=EPS)
    out["displacement_body_expansion"] = body_abs / body_baseline.clip(lower=EPS)
    out["displacement_close_efficiency"] = body_abs / candle_range
    out["displacement_relative_volume"] = v / volume_baseline.clip(lower=EPS)
    out["displacement_close_location"] = (c - l) / candle_range

    bullish_close = out["displacement_close_location"] >= impulsive_close_threshold
    bearish_close = out["displacement_close_location"] <= (1.0 - impulsive_close_threshold)

    out["impulsive_close_up"] = bullish_close.astype("int8")
    out["impulsive_close_down"] = bearish_close.astype("int8")

    out["directional_displacement"] = (
        np.sign(body)
        * out["displacement_range_expansion"]
        * out["displacement_body_expansion"]
        * out["displacement_close_efficiency"]
        * out["displacement_relative_volume"]
    )

    common = (
        (out["displacement_range_expansion"] >= range_expansion_threshold)
        & (out["displacement_body_expansion"] >= body_expansion_threshold)
        & (out["displacement_close_efficiency"] >= close_efficiency_threshold)
        & (out["displacement_relative_volume"] >= relative_volume_threshold)
    )

    out["displacement_up"] = (common & (body > 0) & bullish_close).astype("int8")
    out["displacement_down"] = (common & (body < 0) & bearish_close).astype("int8")
    out["displacement"] = (
        (out["displacement_up"] == 1) | (out["displacement_down"] == 1)
    ).astype("int8")

    # Structure is independently causal; a relationship is only true when
    # both the displacement and the confirmed structural break are known now.
    from .structure import build_structure

    structure = build_structure(x)
    out["displacement_bos_up"] = (
        (out["displacement_up"] == 1) & (structure["bos_up"] == 1)
    ).astype("int8")
    out["displacement_bos_down"] = (
        (out["displacement_down"] == 1) & (structure["bos_down"] == 1)
    ).astype("int8")

    return out
