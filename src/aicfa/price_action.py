"""Deterministic, causal Price Action feature layer for AICFA.

The layer describes candle behaviour and level interactions without producing
trade signals. Every value at row t uses only rows at or before t.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12


def build_price_action(
    df: pd.DataFrame,
    *,
    level_lookback: int = 20,
    regime_window: int = 20,
    compression_threshold: float = 0.75,
    expansion_threshold: float = 1.5,
) -> pd.DataFrame:
    """Build causal Price Action features from OHLCV candles."""
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    if level_lookback < 2 or regime_window < 2:
        raise ValueError("lookback/window values must be >= 2")
    if not 0 < compression_threshold < 1:
        raise ValueError("compression_threshold must be in (0, 1)")
    if expansion_threshold <= 1:
        raise ValueError("expansion_threshold must be > 1")

    x = (
        df[required]
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
    body = c - o
    body_abs = body.abs()

    out = x.copy()
    out["pa_body"] = body
    out["pa_body_pct_range"] = body / candle_range
    out["pa_upper_wick_pct_range"] = (h - np.maximum(o, c)) / candle_range
    out["pa_lower_wick_pct_range"] = (np.minimum(o, c) - l) / candle_range
    out["pa_close_location"] = (c - l) / candle_range
    out["pa_direction"] = np.sign(body).astype("int8")

    # Candle rejection: the wick dominates the candle and the close finishes
    # away from the rejected extreme. These are descriptive classifications.
    out["pa_bullish_rejection"] = (
        (out["pa_lower_wick_pct_range"] >= 0.5)
        & (out["pa_close_location"] >= 0.6)
        & (body_abs / candle_range <= 0.6)
    ).astype("int8")
    out["pa_bearish_rejection"] = (
        (out["pa_upper_wick_pct_range"] >= 0.5)
        & (out["pa_close_location"] <= 0.4)
        & (body_abs / candle_range <= 0.6)
    ).astype("int8")

    # Important levels are strictly from prior candles.
    prior_high = h.shift(1).rolling(level_lookback, min_periods=level_lookback).max()
    prior_low = l.shift(1).rolling(level_lookback, min_periods=level_lookback).min()
    out["pa_resistance_level"] = prior_high
    out["pa_support_level"] = prior_low

    out["pa_breakout_up"] = (h > prior_high).astype("int8")
    out["pa_breakout_down"] = (l < prior_low).astype("int8")
    out["pa_failed_breakout_up"] = (
        (h > prior_high) & (c <= prior_high)
    ).astype("int8")
    out["pa_failed_breakout_down"] = (
        (l < prior_low) & (c >= prior_low)
    ).astype("int8")

    # A retest is only recognized after a previously observed breakout and
    # requires the current candle to interact with the prior breakout level
    # while closing back on the breakout side.
    last_up_level = prior_high.where(out["pa_breakout_up"].astype(bool)).ffill().shift(1)
    last_down_level = prior_low.where(out["pa_breakout_down"].astype(bool)).ffill().shift(1)
    out["pa_retest_up"] = (
        last_up_level.notna()
        & (l <= last_up_level)
        & (c > last_up_level)
    ).astype("int8")
    out["pa_retest_down"] = (
        last_down_level.notna()
        & (h >= last_down_level)
        & (c < last_down_level)
    ).astype("int8")

    # Short causal candle sequences.
    prev_close = c.shift(1)
    out["pa_two_candle_bullish_continuation"] = (
        (body > 0) & (body.shift(1) > 0) & (c > prev_close)
    ).astype("int8")
    out["pa_two_candle_bearish_continuation"] = (
        (body < 0) & (body.shift(1) < 0) & (c < prev_close)
    ).astype("int8")
    out["pa_bullish_reversal"] = (
        (body > 0) & (body.shift(1) < 0) & (c > h.shift(1))
    ).astype("int8")
    out["pa_bearish_reversal"] = (
        (body < 0) & (body.shift(1) > 0) & (c < l.shift(1))
    ).astype("int8")

    # Expansion/compression and trading-range description.
    range_pct = candle_range / c.clip(lower=EPS)
    range_mean = range_pct.rolling(regime_window, min_periods=regime_window).mean()
    rolling_high = h.rolling(regime_window, min_periods=regime_window).max()
    rolling_low = l.rolling(regime_window, min_periods=regime_window).min()
    rolling_width = (rolling_high - rolling_low) / c.clip(lower=EPS)

    out["pa_range_ratio"] = range_pct / range_mean.clip(lower=EPS)
    out["pa_expansion"] = (out["pa_range_ratio"] >= expansion_threshold).astype("int8")
    out["pa_compression"] = (
        out["pa_range_ratio"] <= compression_threshold
    ).astype("int8")
    out["pa_consolidation"] = (
        rolling_width <= rolling_width.rolling(regime_window, min_periods=regime_window).median()
    ).astype("int8")

    return out
