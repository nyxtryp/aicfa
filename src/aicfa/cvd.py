"""Causal cumulative volume delta (CVD) features for AICFA.

CVD is built from the supplied taker-flow sequence. The cumulative series is
scoped to that source sequence; it is not claimed to be exchange-native
lifetime CVD unless the source itself guarantees that scope.

Trade-level CVD preserves individual trades, including multiple trades sharing
the same millisecond timestamp. No future observation can alter an already
available CVD.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_REQUIRED = {"timestamp", "taker_buy_volume", "taker_sell_volume"}
_TRADE_REQUIRED = {"timestamp", "volume", "side"}


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


def _align_cvd(base: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" not in base.columns:
        raise ValueError("missing required base columns: ['timestamp']")
    b = base.copy()
    b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True)
    b = b.sort_values("timestamp").reset_index(drop=True)
    aligned = pd.merge_asof(
        b[["timestamp"]].sort_values("timestamp"),
        source[["timestamp", "cvd", "cvd_delta", "cvd_change_pct"]].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
        allow_exact_matches=True,
    )
    return aligned[["cvd", "cvd_delta", "cvd_change_pct"]]


def build_cvd(base: pd.DataFrame, order_flow: pd.DataFrame) -> pd.DataFrame:
    """Align causal cumulative taker delta to base timestamps."""
    d = _validate(order_flow)
    d["taker_delta"] = d["taker_buy_volume"] - d["taker_sell_volume"]
    if "reset" in d:
        segment = d["reset"].cumsum()
        d["cvd"] = d.groupby(segment, sort=False)["taker_delta"].cumsum()
    else:
        d["cvd"] = d["taker_delta"].cumsum()
    d["cvd_delta"] = d["cvd"].diff()
    d["cvd_change_pct"] = (
        d["cvd_delta"] / d["cvd"].shift(1).abs().replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan)
    return _align_cvd(base, d)


def build_trade_cvd(base: pd.DataFrame, trades: pd.DataFrame) -> pd.DataFrame:
    """Build causal CVD directly from individual venue-provided trades."""
    missing = _TRADE_REQUIRED - set(trades.columns)
    if missing:
        raise ValueError(f"missing required trade columns: {sorted(missing)}")
    if "timestamp" not in base.columns:
        raise ValueError("missing required base columns: ['timestamp']")

    d = trades.copy()
    if pd.api.types.is_numeric_dtype(d["timestamp"]):
        d["timestamp"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
    else:
        d["timestamp"] = pd.to_datetime(d["timestamp"], utc=True)
    d["volume"] = pd.to_numeric(d["volume"], errors="coerce")
    d["side"] = pd.to_numeric(d["side"], errors="coerce")
    if d[["volume", "side"]].isna().any().any():
        raise ValueError("trade volume and side must be numeric and non-null")
    if d["volume"].lt(0).any():
        raise ValueError("trade volume must be non-negative")
    if not d["side"].isin([-1, 1]).all():
        raise ValueError("trade side must be venue-provided +1 or -1")

    d = d.sort_values("timestamp", kind="stable").reset_index(drop=True)
    d["taker_delta"] = d["volume"].where(d["side"].eq(1), 0.0) - d["volume"].where(
        d["side"].eq(-1), 0.0
    )
    d["cvd"] = d["taker_delta"].cumsum()
    d["cvd_delta"] = d["taker_delta"]
    d["cvd_change_pct"] = (
        d["cvd_delta"] / d["cvd"].shift(1).abs().replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan)
    return _align_cvd(base, d)
