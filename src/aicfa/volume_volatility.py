"""Causal volume and volatility regime features for AICFA."""
from __future__ import annotations
import numpy as np
import pandas as pd

EPS = 1e-12

def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    x = df[required].copy().sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for column in required[1:]:
        x[column] = x[column].astype(float)
    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")
    if (x["volume"] < 0).any():
        raise ValueError("Volume must be non-negative")
    if (x["close"] <= 0).any():
        raise ValueError("Close must be positive")
    return x

def build_volume_volatility(df: pd.DataFrame, *, short_window: int = 15, long_window: int = 60) -> pd.DataFrame:
    if short_window < 2 or long_window <= short_window:
        raise ValueError("require 2 <= short_window < long_window")
    x = _validate(df)
    out = x.copy()
    close, high, low, volume = x["close"], x["high"], x["low"], x["volume"]
    log_return = np.log(close).diff()
    true_range = pd.concat([high-low, (high-close.shift(1)).abs(), (low-close.shift(1)).abs()], axis=1).max(axis=1)
    out["realized_volatility"] = log_return.rolling(short_window, min_periods=short_window).std()
    out["true_range"] = true_range
    out["atr"] = true_range.rolling(short_window, min_periods=short_window).mean()
    out["atr_pct"] = out["atr"] / close.clip(lower=EPS)
    range_pct = (high-low) / close.clip(lower=EPS)
    range_mean = range_pct.shift(1).rolling(long_window, min_periods=long_window).mean()
    range_std = range_pct.shift(1).rolling(long_window, min_periods=long_window).std()
    out["range_pct"] = range_pct
    out["range_zscore"] = (range_pct-range_mean) / range_std.clip(lower=EPS)
    volume_mean = volume.shift(1).rolling(long_window, min_periods=long_window).mean()
    volume_std = volume.shift(1).rolling(long_window, min_periods=long_window).std()
    out["volume_zscore"] = (volume-volume_mean) / volume_std.clip(lower=EPS)
    out["relative_volume_causal"] = volume / volume_mean.clip(lower=EPS)
    vol_baseline = out["realized_volatility"].shift(1).rolling(long_window, min_periods=long_window).mean()
    out["volatility_ratio"] = out["realized_volatility"] / vol_baseline.clip(lower=EPS)
    out["volatility_expansion"] = ((out["volatility_ratio"] > 1.5) & out["volatility_ratio"].notna()).astype("int8")
    out["volatility_compression"] = ((out["volatility_ratio"] < 0.75) & out["volatility_ratio"].notna()).astype("int8")
    out["volume_expansion"] = ((out["relative_volume_causal"] > 1.5) & out["relative_volume_causal"].notna()).astype("int8")
    out["volume_dry_up"] = ((out["relative_volume_causal"] < 0.75) & out["relative_volume_causal"].notna()).astype("int8")
    out["volatility_regime"] = np.select([out["volatility_expansion"].eq(1), out["volatility_compression"].eq(1)], ["expansion", "compression"], default="normal")
    out["volume_regime"] = np.select([out["volume_expansion"].eq(1), out["volume_dry_up"].eq(1)], ["expansion", "dry_up"], default="normal")
    return out
