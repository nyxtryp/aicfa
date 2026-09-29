"""Causal order-book / market-depth features for AICFA.

Inputs are completed order-book snapshots and their availability timestamps.
The timestamp means when the snapshot is known to AICFA. A snapshot may be
used only at base timestamps at or after that availability time.

This module exposes descriptive market-state features only; it does not create
trading signals.

The initial contract deliberately uses normalized top-of-book and optional
aggregated depth fields. Individual liquidity walls and absorption require
additional level-by-level / trade-response source contracts and are deferred.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


_REQUIRED = {"timestamp", "bid_price", "ask_price", "bid_size", "ask_size"}
_OPTIONAL = {"bid_depth_volume", "ask_depth_volume"}


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

    for col in (_REQUIRED - {"timestamp"}) | (_OPTIONAL & set(x.columns)):
        x[col] = pd.to_numeric(x[col], errors="coerce")

    for col in _REQUIRED - {"timestamp"}:
        if x[col].isna().any():
            raise ValueError(f"{col} must be numeric and non-null")
        if x[col].lt(0).any():
            raise ValueError(f"{col} must be non-negative")

    if (x["bid_price"] > x["ask_price"]).any():
        raise ValueError("bid_price cannot exceed ask_price")

    for col in _OPTIONAL & set(x.columns):
        if x[col].isna().any():
            raise ValueError(f"{col} must be numeric and non-null")
        if x[col].lt(0).any():
            raise ValueError(f"{col} must be non-negative")

    return x


def _change_pct(series: pd.Series) -> pd.Series:
    return (
        series.diff() / series.shift(1).abs().replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan)


def build_order_book(
    base: pd.DataFrame,
    order_book: pd.DataFrame,
) -> pd.DataFrame:
    """Align completed order-book snapshots causally to base timestamps.

    order_book.timestamp is the source availability timestamp. A base
    observation at T may use a snapshot available at or before T, never a
    snapshot that becomes available later.

    Required fields are best bid/ask prices and sizes. Optional
    bid_depth_volume / ask_depth_volume represent an exchange/source defined
    aggregate depth region and are not interpreted as individual liquidity
    walls.
    """
    if "timestamp" not in base.columns:
        raise ValueError("missing required base columns: ['timestamp']")

    b = base.copy()
    b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True)
    b = b.sort_values("timestamp").reset_index(drop=True)
    d = _validate(order_book)

    d["mid_price"] = (d["bid_price"] + d["ask_price"]) / 2
    d["spread"] = d["ask_price"] - d["bid_price"]
    d["spread_pct"] = d["spread"] / d["mid_price"].replace(0, np.nan)

    top_total = d["bid_size"] + d["ask_size"]
    d["bid_ask_imbalance"] = (
        (d["bid_size"] - d["ask_size"]) / top_total.replace(0, np.nan)
    )
    d["microprice"] = (
        (d["ask_price"] * d["bid_size"] + d["bid_price"] * d["ask_size"])
        / top_total.replace(0, np.nan)
    )

    for col in ("bid_size", "ask_size", "spread", "mid_price", "microprice"):
        d[f"{col}_delta"] = d[col].diff()
        d[f"{col}_change_pct"] = _change_pct(d[col])

    columns = [
        "bid_price",
        "ask_price",
        "bid_size",
        "ask_size",
        "mid_price",
        "spread",
        "spread_pct",
        "microprice",
        "bid_ask_imbalance",
        "bid_size_delta",
        "bid_size_change_pct",
        "ask_size_delta",
        "ask_size_change_pct",
        "spread_delta",
        "spread_change_pct",
        "mid_price_delta",
        "mid_price_change_pct",
        "microprice_delta",
        "microprice_change_pct",
    ]

    if {"bid_depth_volume", "ask_depth_volume"} <= set(d.columns):
        depth_total = d["bid_depth_volume"] + d["ask_depth_volume"]
        d["depth_imbalance"] = (
            (d["bid_depth_volume"] - d["ask_depth_volume"])
            / depth_total.replace(0, np.nan)
        )
        d["depth_total_volume"] = depth_total
        d["bid_depth_volume_delta"] = d["bid_depth_volume"].diff()
        d["ask_depth_volume_delta"] = d["ask_depth_volume"].diff()
        d["depth_imbalance_delta"] = d["depth_imbalance"].diff()
        columns += [
            "bid_depth_volume",
            "ask_depth_volume",
            "depth_total_volume",
            "depth_imbalance",
            "bid_depth_volume_delta",
            "ask_depth_volume_delta",
            "depth_imbalance_delta",
        ]

    aligned = pd.merge_asof(
        b[["timestamp"]].sort_values("timestamp"),
        d[["timestamp"] + columns].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
        allow_exact_matches=True,
    )

    return aligned[columns]
