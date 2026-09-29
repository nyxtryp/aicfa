"""Deterministic, causal market feature engine for AICFA.

All features at row t use only candles at or before t.
Future-looking labels belong to a separate pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


EPS = 1e-12


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build causal market-state features from OHLCV candles.

    Required columns: timestamp, open, high, low, close, volume.
    """
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    x = df[required].copy()
    x = x.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    o = x["open"].astype(float)
    h = x["high"].astype(float)
    l = x["low"].astype(float)
    c = x["close"].astype(float)
    v = x["volume"].astype(float)

    out = x.copy()
    candle_range = (h - l).clip(lower=EPS)
    body = c - o
    upper_wick = h - np.maximum(o, c)
    lower_wick = np.minimum(o, c) - l

    out["return_1"] = c.pct_change()
    out["log_return_1"] = np.log(c).diff()
    out["body"] = body
    out["body_pct_range"] = body / candle_range
    out["upper_wick_pct_range"] = upper_wick / candle_range
    out["lower_wick_pct_range"] = lower_wick / candle_range
    out["range_pct"] = candle_range / c.clip(lower=EPS)
    out["close_location"] = (c - l) / candle_range
    out["direction"] = np.sign(body).astype("int8")

    for n in (5, 15, 30, 60):
        out[f"volatility_{n}"] = out["log_return_1"].rolling(n, min_periods=n).std()
        out[f"range_mean_{n}"] = out["range_pct"].rolling(n, min_periods=n).mean()
        out[f"volume_mean_{n}"] = v.rolling(n, min_periods=n).mean()
        out[f"relative_volume_{n}"] = v / out[f"volume_mean_{n}"].clip(lower=EPS)
        out[f"rolling_high_{n}"] = h.rolling(n, min_periods=n).max()
        out[f"rolling_low_{n}"] = l.rolling(n, min_periods=n).min()
        out[f"distance_to_high_{n}"] = (out[f"rolling_high_{n}"] - c) / c.clip(lower=EPS)
        out[f"distance_to_low_{n}"] = (c - out[f"rolling_low_{n}"]) / c.clip(lower=EPS)

    out["range_expansion_15"] = out["range_pct"] / out["range_mean_15"].clip(lower=EPS)
    out["volume_expansion_15"] = out["relative_volume_15"]
    out["impulse_score_15"] = out["body_pct_range"].abs() * out["range_expansion_15"]
    out["compression_15"] = out["range_pct"] / out["range_mean_60"].clip(lower=EPS)

    # Past-only rolling dealing range: no centered windows and no future pivots.
    dr_high = h.rolling(60, min_periods=60).max()
    dr_low = l.rolling(60, min_periods=60).min()
    dr_width = (dr_high - dr_low).clip(lower=EPS)
    out["dealing_range_position"] = (c - dr_low) / dr_width
    out["premium_discount"] = out["dealing_range_position"] * 2.0 - 1.0

    # Simple causal breakout / sweep proxies.
    prev_high = h.shift(1).rolling(30, min_periods=30).max()
    prev_low = l.shift(1).rolling(30, min_periods=30).min()
    out["breakout_up"] = (h > prev_high).astype("int8")
    out["breakout_down"] = (l < prev_low).astype("int8")
    out["sweep_high_reject"] = ((h > prev_high) & (c < prev_high)).astype("int8")
    out["sweep_low_reclaim"] = ((l < prev_low) & (c > prev_low)).astype("int8")

    # Causal market structure. Swings are emitted only after right-side confirmation.
    from .structure import build_structure
    structure = build_structure(x)
    for column in ["swing_high","swing_low","hh","hl","lh","ll","bos_up","bos_down","choch_up","choch_down","mss_up","mss_down","swing_high_price","swing_low_price","structure_direction"]:
        out[column] = structure[column].to_numpy()

    # Causal liquidity pools and sweep/reclaim events.
    from .liquidity import build_liquidity
    liquidity = build_liquidity(x)
    for column in [
        "equal_high", "equal_low", "buy_side_liquidity", "sell_side_liquidity",
        "sweep_high", "sweep_low", "sweep_high_reclaim", "sweep_low_reclaim",
        "buy_side_liquidity_price", "sell_side_liquidity_price",
        "sweep_high_level", "sweep_low_level",
    ]:
        out[column] = liquidity[column].to_numpy()

    # Trend proxies from causal rolling return and close-vs-mean location.
    for n in (15, 60):
        out[f"return_{n}"] = c.pct_change(n)
        mean_n = c.rolling(n, min_periods=n).mean()
        out[f"close_vs_mean_{n}"] = c / mean_n.clip(lower=EPS) - 1.0

    # Time context; all derived from the current candle timestamp.
    ts = pd.to_datetime(out["timestamp"], unit="ms", utc=True)
    out["hour_utc"] = ts.dt.hour.astype("int8")
    out["day_of_week"] = ts.dt.dayofweek.astype("int8")

    return out
