"""Causal cumulative volume delta (CVD) features for AICFA.

CVD is built from completed taker-flow intervals. The cumulative series is
defined over the supplied source sequence; it is not claimed to be an
exchange-native lifetime CVD unless the source itself guarantees that scope.

The optional reset field explicitly starts a new cumulative segment at
that observation. No future observation can alter an already available CVD.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_REQUIRED = {"timestamp", "taker_buy_volume", "taker_sell_volume"}

def _validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    x = x.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    for col in ("taker_buy_volume", "taker_sell_volume"):
        x[col] = pd.to_numeric(x[col], errors="coerce")
        if x[col].isna().any():
            raise ValueError(f"{col} must be numeric and non-null")
        if x[col].lt(0).any():
            raise ValueError(f"{col} must be non-negative")
    if "reset" in x:
        x["reset"] = x["reset"].fillna(False).astype(bool)
    return x

def build_cvd(base: pd.DataFrame, order_flow: pd.DataFrame) -> pd.DataFrame:
    """Align causal cumulative taker delta to base timestamps."""
    if "timestamp" not in base.columns:
        raise ValueError("missing required base columns: ['timestamp']")
    b = base.copy()
    b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True)
    b = b.sort_values("timestamp").reset_index(drop=True)
    d = _validate(order_flow)
    d["taker_delta"] = d["taker_buy_volume"] - d["taker_sell_volume"]
    if "reset" in d:
        segment = d["reset"].cumsum()
        d["cvd"] = d.groupby(segment, sort=False)["taker_delta"].cumsum()
    else:
        d["cvd"] = d["taker_delta"].cumsum()
    d["cvd_delta"] = d["cvd"].diff()
    d["cvd_change_pct"] = (d["cvd_delta"] / d["cvd"].shift(1).abs().replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    aligned = pd.merge_asof(
        b[["timestamp"]].sort_values("timestamp"),
        d[["timestamp", "cvd", "cvd_delta", "cvd_change_pct"]].sort_values("timestamp"),
        on="timestamp", direction="backward", allow_exact_matches=True,
    )
    return aligned[["cvd", "cvd_delta", "cvd_change_pct"]]
