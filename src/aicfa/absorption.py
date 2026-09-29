"""Causal absorption features from synchronized taker flow, book levels and price.

Absorption is represented as a completed-window market-state observation.  It
requires aggressive taker flow, displayed liquidity on the opposing book side,
book replenishment/persistence, and a limited contemporaneous price response.

The module never uses prices or book states after the observation timestamp.
The resulting event is descriptive; it is not a LONG/SHORT signal.

Important limitation: without trade-price-by-trade-price data, this is an
absorption *candidate* based on synchronized market aggregates, not proof that
a specific resting order was actually executed and replenished.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .order_book_levels import build_level_changes


def _validate_base(base: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close"}
    missing = required - set(base.columns)
    if missing:
        raise ValueError(f"missing required base columns: {sorted(missing)}")
    x = base.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    for col in ["open", "high", "low", "close"]:
        x[col] = pd.to_numeric(x[col], errors="coerce")
    if x[["timestamp", "open", "high", "low", "close"]].isna().any().any():
        raise ValueError("timestamp and OHLC values must be non-null")
    if (x[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC values must be positive")
    if (x["high"] < x[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high must be >= open, low and close")
    if (x["low"] > x[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low must be <= open, high and close")
    return x.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)


def _validate_flow(flow: pd.DataFrame) -> pd.DataFrame:
    required = {"timestamp", "taker_buy_volume", "taker_sell_volume"}
    missing = required - set(flow.columns)
    if missing:
        raise ValueError(f"missing required flow columns: {sorted(missing)}")
    x = flow.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    for col in ["taker_buy_volume", "taker_sell_volume"]:
        x[col] = pd.to_numeric(x[col], errors="coerce")
    if x[["timestamp", "taker_buy_volume", "taker_sell_volume"]].isna().any().any():
        raise ValueError("flow timestamp and volumes must be non-null")
    if (x[["taker_buy_volume", "taker_sell_volume"]] < 0).any().any():
        raise ValueError("taker volumes must be non-negative")
    return x.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)


def build_absorption(
    base: pd.DataFrame,
    order_flow: pd.DataFrame,
    levels: pd.DataFrame,
    *,
    window: str = "3min",
    proximity_bps: float = 5.0,
    min_imbalance: float = 0.30,
    min_liquidity_multiple: float = 1.5,
    min_replenishment_ratio: float = 0.50,
    min_persistence_snapshots: int = 2,
    max_price_response_bps: float = 8.0,
    max_directional_efficiency: float = 0.50,
) -> pd.DataFrame:
    """Build causal descriptive absorption candidates over a backward window.

    At timestamp T only data with source timestamp <= T is used.  The window
    is (T-window, T].  Aggressive buying is evaluated against ask liquidity;
    aggressive selling is evaluated against bid liquidity.

    Parameters are deliberately explicit so later research can optimize them
    without changing the causal contract.
    """
    if proximity_bps <= 0 or min_imbalance <= 0 or min_imbalance >= 1:
        raise ValueError("invalid proximity_bps or min_imbalance")
    if min_liquidity_multiple <= 0 or min_replenishment_ratio < 0:
        raise ValueError("invalid liquidity/replenishment thresholds")
    if min_persistence_snapshots < 1:
        raise ValueError("min_persistence_snapshots must be >= 1")
    if max_price_response_bps < 0 or not 0 <= max_directional_efficiency <= 1:
        raise ValueError("invalid price-response thresholds")

    b = _validate_base(base)
    f = _validate_flow(order_flow)
    l = levels.copy()
    if "timestamp" not in l.columns:
        raise ValueError("missing required level columns: ['timestamp']")
    l["timestamp"] = pd.to_datetime(l["timestamp"], utc=True)
    changes = build_level_changes(l, persistence_snapshots=min_persistence_snapshots)

    rows = []
    delta = pd.Timedelta(window)
    for _, candle in b.iterrows():
        ts = candle["timestamp"]
        start = ts - delta
        fw = f[(f["timestamp"] > start) & (f["timestamp"] <= ts)]
        bw = l[(l["timestamp"] > start) & (l["timestamp"] <= ts)]
        cw = changes[(changes["timestamp"] > start) & (changes["timestamp"] <= ts)]
        pw = b[(b["timestamp"] > start) & (b["timestamp"] <= ts)]

        if fw.empty or bw.empty or pw.empty:
            continue

        buy = float(fw["taker_buy_volume"].sum())
        sell = float(fw["taker_sell_volume"].sum())
        total = buy + sell
        if total <= 0:
            continue
        imbalance = (buy - sell) / total
        if abs(imbalance) < min_imbalance:
            continue

        aggressive_side = "buy" if imbalance > 0 else "sell"
        resting_side = "ask" if aggressive_side == "buy" else "bid"

        first_open = float(pw.iloc[0]["open"])
        last_close = float(pw.iloc[-1]["close"])
        high = float(pw["high"].max())
        low = float(pw["low"].min())
        range_bps = (high - low) / last_close * 10000.0
        response_bps = abs(last_close - first_open) / first_open * 10000.0
        efficiency = 0.0 if high == low else abs(last_close - first_open) / (high - low)

        side_levels = bw[bw["side"].eq(resting_side) & bw["size"].gt(0)].copy()
        if resting_side == "ask":
            side_levels = side_levels[side_levels["price"] >= last_close]
        else:
            side_levels = side_levels[side_levels["price"] <= last_close]
        if side_levels.empty:
            continue

        side_levels["distance_bps"] = (
            (side_levels["price"] - last_close).abs() / last_close * 10000.0
        )
        near = side_levels[side_levels["distance_bps"] <= proximity_bps]
        if near.empty:
            continue

        nearest = near.sort_values(["distance_bps", "price"]).iloc[0]
        same_snapshot = bw[
            (bw["timestamp"] == nearest["timestamp"]) &
            (bw["side"] == resting_side) &
            (bw["size"] > 0)
        ]
        median_size = float(same_snapshot["size"].median())
        liquidity_multiple = (
            float(nearest["size"]) / median_size if median_size > 0 else np.nan
        )

        exact_level = bw[
            (bw["side"] == resting_side) &
            np.isclose(bw["price"], float(nearest["price"]))
        ]
        persistence = int(exact_level["timestamp"].nunique())

        side_changes = cw[cw["side"].eq(resting_side)]
        added = float(side_changes["added_size"].sum()) if not side_changes.empty else 0.0
        cancelled = float(side_changes["cancelled_size"].sum()) if not side_changes.empty else 0.0
        replenishment_ratio = added / cancelled if cancelled > 0 else (np.inf if added > 0 else 0.0)

        qualifies = (
            liquidity_multiple >= min_liquidity_multiple
            and persistence >= min_persistence_snapshots
            and replenishment_ratio >= min_replenishment_ratio
            and response_bps <= max_price_response_bps
            and efficiency <= max_directional_efficiency
            and range_bps >= response_bps
        )

        rows.append(
            {
                "timestamp": ts,
                "absorption": bool(qualifies),
                "absorption_side": aggressive_side,
                "resting_liquidity_side": resting_side,
                "window_start": start,
                "window_end": ts,
                "taker_buy_volume": buy,
                "taker_sell_volume": sell,
                "taker_imbalance": imbalance,
                "candidate_price": float(nearest["price"]),
                "candidate_size": float(nearest["size"]),
                "candidate_distance_bps": float(nearest["distance_bps"]),
                "liquidity_multiple": liquidity_multiple,
                "level_persistence_snapshots": persistence,
                "replenishment_added_size": added,
                "replenishment_cancelled_size": cancelled,
                "replenishment_ratio": replenishment_ratio,
                "price_range_bps": range_bps,
                "price_response_bps": response_bps,
                "directional_efficiency": efficiency,
            }
        )

    columns = [
        "timestamp", "absorption", "absorption_side", "resting_liquidity_side",
        "window_start", "window_end", "taker_buy_volume", "taker_sell_volume",
        "taker_imbalance", "candidate_price", "candidate_size",
        "candidate_distance_bps", "liquidity_multiple",
        "level_persistence_snapshots", "replenishment_added_size",
        "replenishment_cancelled_size", "replenishment_ratio",
        "price_range_bps", "price_response_bps", "directional_efficiency",
    ]
    return pd.DataFrame(rows, columns=columns).sort_values("timestamp").reset_index(drop=True)
