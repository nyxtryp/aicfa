"""Deterministic, causal Wyckoff representation for AICFA.

The layer formalizes observable Wyckoff-inspired events and market-state
proxies. It does not claim to identify textbook accumulation/distribution
with certainty and does not emit trade signals.

Every value at row t uses only information available at or before t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12


def build_wyckoff(
    df: pd.DataFrame,
    *,
    range_lookback: int = 20,
    volume_window: int = 20,
    breakout_buffer: float = 0.0,
) -> pd.DataFrame:
    """Build causal, descriptive Wyckoff-inspired features from OHLC(V)."""
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if range_lookback < 3 or volume_window < 2:
        raise ValueError("lookback/window values are too small")
    if breakout_buffer < 0:
        raise ValueError("breakout_buffer must be >= 0")

    columns = required + (["volume"] if "volume" in df.columns else [])
    x = (
        df[columns]
        .copy()
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )

    o = x["open"].astype(float)
    h = x["high"].astype(float)
    l = x["low"].astype(float)
    c = x["close"].astype(float)
    candle_range = (h - l).clip(lower=EPS)
    body_abs = (c - o).abs()

    out = x.copy()

    # The trading-range boundaries are strictly prior observations.
    prior_high = h.shift(1).rolling(
        range_lookback, min_periods=range_lookback
    ).max()
    prior_low = l.shift(1).rolling(
        range_lookback, min_periods=range_lookback
    ).min()
    range_width = (prior_high - prior_low).clip(lower=EPS)
    range_position = (c - prior_low) / range_width

    out["wyckoff_range_high"] = prior_high
    out["wyckoff_range_low"] = prior_low
    out["wyckoff_range_width"] = range_width
    out["wyckoff_range_position"] = range_position
    out["wyckoff_in_range"] = (
        (c >= prior_low) & (c <= prior_high)
    ).astype("int8")

    # Observable boundary events. The buffer is expressed as a fraction of
    # the prior range width and is zero by default.
    up_level = prior_high + breakout_buffer * range_width
    down_level = prior_low - breakout_buffer * range_width

    out["wyckoff_breakout_up"] = (h > up_level).astype("int8")
    out["wyckoff_breakout_down"] = (l < down_level).astype("int8")

    out["wyckoff_failed_breakout_up"] = (
        (h > up_level) & (c <= prior_high)
    ).astype("int8")
    out["wyckoff_failed_breakout_down"] = (
        (l < down_level) & (c >= prior_low)
    ).astype("int8")

    # Spring / Upthrust candidates: boundary penetration followed by a
    # reclaim/failure close. These are event candidates, not proof of a
    # Wyckoff schematic phase.
    out["wyckoff_spring"] = (
        (l < down_level) & (c > prior_low)
    ).astype("int8")
    out["wyckoff_upthrust"] = (
        (h > up_level) & (c < prior_high)
    ).astype("int8")

    # Sign of Strength / Weakness are descriptive range escapes with a close
    # outside the prior boundary and a meaningful candle body.
    body_ratio = body_abs / candle_range
    out["wyckoff_sign_of_strength"] = (
        (c > up_level) & (body_ratio >= 0.5)
    ).astype("int8")
    out["wyckoff_sign_of_weakness"] = (
        (c < down_level) & (body_ratio >= 0.5)
    ).astype("int8")

    # Range expansion/compression context.
    range_pct = candle_range / c.clip(lower=EPS)
    prior_range_mean = range_pct.shift(1).rolling(
        range_lookback, min_periods=range_lookback
    ).mean()
    out["wyckoff_range_expansion"] = (
        range_pct / prior_range_mean.clip(lower=EPS)
    )
    out["wyckoff_range_compression"] = (
        out["wyckoff_range_expansion"] <= 0.75
    ).astype("int8")

    # Optional volume context. Missing volume is represented by absent
    # volume-derived columns rather than invented values.
    if "volume" in x.columns:
        volume = x["volume"].astype(float)
        prior_volume_mean = volume.shift(1).rolling(
            volume_window, min_periods=volume_window
        ).mean()
        out["wyckoff_relative_volume"] = (
            volume / prior_volume_mean.clip(lower=EPS)
        )
        out["wyckoff_volume_expansion"] = (
            out["wyckoff_relative_volume"] >= 1.5
        ).astype("int8")

    # A compact descriptive state. Event precedence is explicit and does not
    # imply a trading recommendation.
    state = pd.Series("neutral", index=out.index, dtype="object")
    state[out["wyckoff_in_range"].eq(1)] = "trading_range"
    state[out["wyckoff_breakout_up"].eq(1)] = "breakout_up"
    state[out["wyckoff_breakout_down"].eq(1)] = "breakout_down"
    state[out["wyckoff_spring"].eq(1)] = "spring_candidate"
    state[out["wyckoff_upthrust"].eq(1)] = "upthrust_candidate"
    state[out["wyckoff_sign_of_strength"].eq(1)] = "sign_of_strength"
    state[out["wyckoff_sign_of_weakness"].eq(1)] = "sign_of_weakness"
    out["wyckoff_state"] = state

    # Accumulation/distribution are intentionally proxy contexts, not claims
    # of hidden participant intent. A spring/upthrust inside the prior range
    # provides the observable basis for the proxy.
    out["wyckoff_accumulation_proxy"] = (
        (out["wyckoff_spring"] == 1)
        & (range_position <= 0.5)
    ).astype("int8")
    out["wyckoff_distribution_proxy"] = (
        (out["wyckoff_upthrust"] == 1)
        & (range_position >= 0.5)
    ).astype("int8")

    return out
