"""Causal derivatives observations for AICFA.

The engine aligns derivative observations to a base OHLCV timeline using only
observations known at or before each base timestamp. It deliberately exposes
descriptive market-state features rather than trading signals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


_REQUIRED = {"timestamp", "funding_rate", "open_interest"}


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    x = x.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)

    for col in ("funding_rate", "open_interest"):
        x[col] = pd.to_numeric(x[col], errors="coerce")

    if x[["funding_rate", "open_interest"]].isna().any().any():
        raise ValueError("funding_rate/open_interest must be numeric and non-null")
    if (x["open_interest"] < 0).any():
        raise ValueError("open_interest must be non-negative")

    return x


def _zscore_against_past(series: pd.Series, window: int) -> pd.Series:
    if window < 2:
        raise ValueError("window must be >= 2")
    past = series.shift(1)
    mean = past.rolling(window, min_periods=window).mean()
    std = past.rolling(window, min_periods=window).std(ddof=0)
    return (series - mean) / std.replace(0, np.nan)


def build_derivatives(
    base: pd.DataFrame,
    derivatives: pd.DataFrame,
    *,
    baseline_window: int = 24,
) -> pd.DataFrame:
    """Map causal funding/OI observations onto a base candle timeline.

    Derivative observations are treated as point-in-time observations. A base
    candle may only see the latest derivative observation whose timestamp is
    <= the candle timestamp. No forward fill from future observations occurs.
    """
    if baseline_window < 2:
        raise ValueError("baseline_window must be >= 2")

    required_base = {"timestamp", "close"}
    missing = required_base - set(base.columns)
    if missing:
        raise ValueError(f"missing required base columns: {sorted(missing)}")

    b = base.copy()
    b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True)
    b = b.sort_values("timestamp").reset_index(drop=True)

    d = _validate(derivatives)

    aligned = pd.merge_asof(
        b[["timestamp", "close"]],
        d,
        on="timestamp",
        direction="backward",
        allow_exact_matches=True,
    )

    # Changes are computed in derivative-observation order before alignment.
    funding_delta = d["funding_rate"].diff()
    funding_pct = d["funding_rate"].replace(0, np.nan)
    funding_change_pct = funding_delta / funding_pct.shift(0).abs()
    oi_delta = d["open_interest"].diff()
    oi_pct = d["open_interest"].pct_change()

    d2 = d.copy()
    d2["funding_rate_delta"] = funding_delta
    d2["funding_rate_change_pct"] = funding_change_pct.replace([np.inf, -np.inf], np.nan)
    d2["funding_rate_zscore"] = _zscore_against_past(d2["funding_rate"], baseline_window)
    d2["open_interest_delta"] = oi_delta
    d2["open_interest_change_pct"] = oi_pct.replace([np.inf, -np.inf], np.nan)
    d2["open_interest_zscore"] = _zscore_against_past(d2["open_interest"], baseline_window)

    # Price/OI relationship is descriptive only and uses the current aligned
    # derivative observation plus the base candle return known at that candle.
    price_return = b["close"].pct_change()
    base_with_ret = b[["timestamp"]].copy()
    base_with_ret["price_return"] = price_return
    aligned2 = pd.merge_asof(
        base_with_ret,
        d2,
        on="timestamp",
        direction="backward",
        allow_exact_matches=True,
    )

    oi_delta_now = aligned2["open_interest_delta"]
    ret = aligned2["price_return"]
    aligned2["oi_price_up_up"] = ((oi_delta_now > 0) & (ret > 0)).astype(int)
    aligned2["oi_price_up_down"] = ((oi_delta_now > 0) & (ret < 0)).astype(int)
    aligned2["oi_price_down_up"] = ((oi_delta_now < 0) & (ret > 0)).astype(int)
    aligned2["oi_price_down_down"] = ((oi_delta_now < 0) & (ret < 0)).astype(int)

    optional = [c for c in ("liquidation_volume", "long_liquidation_volume", "short_liquidation_volume") if c in d.columns]
    if optional:
        # Keep optional liquidation observations causal when the historical
        # source provides them. No liquidation fields are invented otherwise.
        for col in optional:
            aligned2[col] = pd.to_numeric(aligned2[col], errors="coerce")
            if (aligned2[col].dropna() < 0).any():
                raise ValueError(f"{col} must be non-negative")

    out_cols = [
        "funding_rate",
        "funding_rate_delta",
        "funding_rate_change_pct",
        "funding_rate_zscore",
        "open_interest",
        "open_interest_delta",
        "open_interest_change_pct",
        "open_interest_zscore",
        "oi_price_up_up",
        "oi_price_up_down",
        "oi_price_down_up",
        "oi_price_down_down",
    ] + optional

    return aligned2[out_cols]
