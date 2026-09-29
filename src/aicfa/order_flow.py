"""Causal taker-flow / order-flow features for AICFA.

Inputs represent completed market-data intervals and their availability time.
The timestamp is the time at which the interval became fully known, not the
interval open time. This prevents using a completed interval before it exists.

The module exposes descriptive market-state features only; it does not create
trading signals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


_REQUIRED = {"timestamp", "taker_buy_volume"}
_OPTIONAL = {"taker_sell_volume", "total_volume"}


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    x = (
        x.sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )

    for col in _REQUIRED - {"timestamp"}:
        x[col] = pd.to_numeric(x[col], errors="coerce")
    for col in _OPTIONAL & set(x.columns):
        x[col] = pd.to_numeric(x[col], errors="coerce")

    if x["taker_buy_volume"].isna().any():
        raise ValueError("taker_buy_volume must be numeric and non-null")
    if x["taker_buy_volume"].lt(0).any():
        raise ValueError("taker_buy_volume must be non-negative")

    if "taker_sell_volume" in x:
        if x["taker_sell_volume"].isna().any():
            raise ValueError("taker_sell_volume must be numeric and non-null")
        if x["taker_sell_volume"].lt(0).any():
            raise ValueError("taker_sell_volume must be non-negative")

    if "total_volume" in x:
        if x["total_volume"].isna().any():
            raise ValueError("total_volume must be numeric and non-null")
        if x["total_volume"].lt(0).any():
            raise ValueError("total_volume must be non-negative")

    if "taker_sell_volume" not in x:
        if "total_volume" not in x:
            raise ValueError(
                "provide taker_sell_volume or total_volume to derive taker sell volume"
            )
        x["taker_sell_volume"] = x["total_volume"] - x["taker_buy_volume"]
        if x["taker_sell_volume"].lt(-1e-12).any():
            raise ValueError("taker_buy_volume cannot exceed total_volume")
        x["taker_sell_volume"] = x["taker_sell_volume"].clip(lower=0)

    if "total_volume" in x:
        expected = x["taker_buy_volume"] + x["taker_sell_volume"]
        if not np.allclose(
            expected.to_numpy(dtype=float),
            x["total_volume"].to_numpy(dtype=float),
            rtol=1e-9,
            atol=1e-12,
            equal_nan=False,
        ):
            raise ValueError(
                "total_volume must equal taker_buy_volume + taker_sell_volume"
            )

    return x


def _zscore_against_past(series: pd.Series, window: int) -> pd.Series:
    past = series.shift(1)
    mean = past.rolling(window, min_periods=window).mean()
    std = past.rolling(window, min_periods=window).std(ddof=0)
    return (series - mean) / std.replace(0, np.nan)


def build_order_flow(
    base: pd.DataFrame,
    order_flow: pd.DataFrame,
    *,
    baseline_window: int = 24,
) -> pd.DataFrame:
    """Align completed taker-flow intervals causally to base timestamps.

    order_flow.timestamp is the source availability timestamp. For a
    completed exchange kline this should be the close/availability time, not
    the open time. A base candle at T may use an observation available at or
    before T, never one that becomes available later.
    """
    if baseline_window < 2:
        raise ValueError("baseline_window must be >= 2")

    if "timestamp" not in base.columns:
        raise ValueError("missing required base columns: ['timestamp']")

    b = base.copy()
    b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True)
    b = b.sort_values("timestamp").reset_index(drop=True)
    d = _validate(order_flow)

    d["taker_net_volume"] = (
        d["taker_buy_volume"] - d["taker_sell_volume"]
    )
    total = d["taker_buy_volume"] + d["taker_sell_volume"]
    d["taker_imbalance"] = (
        d["taker_net_volume"] / total.replace(0, np.nan)
    )
    d["taker_buy_share"] = (
        d["taker_buy_volume"] / total.replace(0, np.nan)
    )
    d["taker_sell_share"] = (
        d["taker_sell_volume"] / total.replace(0, np.nan)
    )

    for col in (
        "taker_buy_volume",
        "taker_sell_volume",
        "taker_net_volume",
        "taker_imbalance",
        "taker_buy_share",
        "taker_sell_share",
    ):
        d[f"{col}_delta"] = d[col].diff()
        d[f"{col}_change_pct"] = (
            d[f"{col}_delta"] / d[col].shift(1).abs().replace(0, np.nan)
        ).replace([np.inf, -np.inf], np.nan)
        d[f"{col}_zscore"] = _zscore_against_past(d[col], baseline_window)

    columns = [
        "taker_buy_volume",
        "taker_sell_volume",
        "taker_net_volume",
        "taker_imbalance",
        "taker_buy_share",
        "taker_sell_share",
    ]
    for col in list(columns):
        columns += [
            f"{col}_delta",
            f"{col}_change_pct",
            f"{col}_zscore",
        ]

    aligned = pd.merge_asof(
        b[["timestamp"]].sort_values("timestamp"),
        d[["timestamp"] + columns].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
        allow_exact_matches=True,
    )

    return aligned[columns]
