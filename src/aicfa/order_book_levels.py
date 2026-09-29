"""Causal level-by-level order-book state and liquidity-wall features.

Input is a sequence of complete book snapshots in long format:
timestamp, side, price, size

timestamp is the availability timestamp of the complete snapshot.

The module computes descriptive state changes only. A liquidity wall is a
persistent, unusually large displayed level relative to the observed same-side
book; it is not a trading signal.

Absorption is intentionally deferred because it requires synchronized trade
flow and a defined price-response window.
"""

from __future__ import annotations

import pandas as pd

_REQUIRED = {"timestamp", "side", "price", "size"}


def _validate(levels: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED - set(levels.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    x = levels.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    x["side"] = x["side"].astype(str).str.lower()
    x["price"] = pd.to_numeric(x["price"], errors="coerce")
    x["size"] = pd.to_numeric(x["size"], errors="coerce")

    if x[["timestamp", "price", "size"]].isna().any().any():
        raise ValueError("timestamp, price and size must be non-null")
    if (~x["side"].isin(["bid", "ask"])).any():
        raise ValueError("side must be 'bid' or 'ask'")
    if x["price"].le(0).any():
        raise ValueError("price must be positive")
    if x["size"].lt(0).any():
        raise ValueError("size must be non-negative")

    return (
        x.sort_values(["timestamp", "side", "price"])
        .drop_duplicates(["timestamp", "side", "price"], keep="last")
        .reset_index(drop=True)
    )


def build_level_changes(
    levels: pd.DataFrame,
    *,
    persistence_snapshots: int = 3,
) -> pd.DataFrame:
    """Calculate causal per-level additions, cancellations and persistence."""
    if persistence_snapshots < 1:
        raise ValueError("persistence_snapshots must be >= 1")

    x = _validate(levels)
    snapshots = [
        group[["side", "price", "size"]].copy().set_index(["side", "price"])
        for _, group in x.groupby("timestamp", sort=True)
    ]
    timestamps = list(x.groupby("timestamp", sort=True).groups)

    rows = []
    for i in range(1, len(snapshots)):
        previous = snapshots[i - 1]["size"]
        current = snapshots[i]["size"]
        index = previous.index.union(current.index)
        previous = previous.reindex(index).fillna(0.0)
        current = current.reindex(index).fillna(0.0)
        delta = current - previous

        for (side, price), value in delta.items():
            if value == 0:
                continue
            rows.append(
                {
                    "timestamp": timestamps[i],
                    "side": side,
                    "price": price,
                    "size": float(current.loc[(side, price)]),
                    "previous_size": float(previous.loc[(side, price)]),
                    "size_delta": float(value),
                    "added_size": max(float(value), 0.0),
                    "cancelled_size": max(float(-value), 0.0),
                    "level_changed": True,
                    "level_added": bool(previous.loc[(side, price)] == 0 and current.loc[(side, price)] > 0),
                    "level_removed": bool(previous.loc[(side, price)] > 0 and current.loc[(side, price)] == 0),
                }
            )

    if not rows:
        return pd.DataFrame(
            columns=[
                "timestamp", "side", "price", "size", "previous_size",
                "size_delta", "added_size", "cancelled_size",
                "level_changed", "level_added", "level_removed",
                "persistence_count",
            ]
        )

    out = pd.DataFrame(rows).sort_values(
        ["side", "price", "timestamp"]
    ).reset_index(drop=True)

    active = out["size"].gt(0)
    out["persistence_count"] = (
        active.astype(int)
        .groupby([out["side"], out["price"]])
        .transform(
            lambda s: s.rolling(
                persistence_snapshots, min_periods=1
            ).sum()
        )
        .where(active, 0)
    )
    return out.sort_values(["timestamp", "side", "price"]).reset_index(drop=True)


def build_liquidity_walls(
    levels: pd.DataFrame,
    *,
    min_persistence: int = 3,
    quantile: float = 0.9,
) -> pd.DataFrame:
    """Identify persistent unusually large displayed levels by side."""
    if min_persistence < 1:
        raise ValueError("min_persistence must be >= 1")
    if not 0 < quantile < 1:
        raise ValueError("quantile must be between 0 and 1")

    x = _validate(levels)
    changes = build_level_changes(x, persistence_snapshots=min_persistence)

    # Wall detection must inspect every visible level, including levels whose
    # size did not change between snapshots. Persistence is therefore computed
    # from the complete snapshot sequence rather than from change rows alone.
    x = x.sort_values(["side", "price", "timestamp"]).reset_index(drop=True)
    x["visible"] = x["size"].gt(0)
    x["persistence_count"] = (
        x["visible"].astype(int)
        .groupby([x["side"], x["price"]])
        .transform(
            lambda s: s.rolling(
                min_persistence, min_periods=min_persistence
            ).sum()
        )
        .fillna(0)
    )

    thresholds = (
        x.groupby(["timestamp", "side"])["size"]
        .quantile(quantile)
        .rename("wall_size_threshold")
        .reset_index()
    )
    out = x.merge(thresholds, on=["timestamp", "side"], how="left")
    out["liquidity_wall"] = (
        out["size"].ge(out["wall_size_threshold"])
        & out["persistence_count"].ge(min_persistence)
        & out["size"].gt(0)
    )
    out["wall_size_multiple"] = (
        out["size"] / out["wall_size_threshold"].replace(0, pd.NA)
    )
    return out


def build_order_book_flow(levels: pd.DataFrame) -> pd.DataFrame:
    """Aggregate displayed-level additions and cancellations by snapshot."""
    changes = build_level_changes(levels)
    if changes.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "bid_added_volume",
                "bid_cancelled_volume",
                "ask_added_volume",
                "ask_cancelled_volume",
                "net_displayed_bid_change",
                "net_displayed_ask_change",
            ]
        )

    grouped = changes.groupby(["timestamp", "side"], as_index=False).agg(
        added_size=("added_size", "sum"),
        cancelled_size=("cancelled_size", "sum"),
    )
    pivot = grouped.pivot(
        index="timestamp",
        columns="side",
        values=["added_size", "cancelled_size"],
    )
    pivot.columns = [f"{action}_{side}_volume" for action, side in pivot.columns]
    pivot = pivot.reset_index()

    for col in (
        "added_size_bid_volume",
        "cancelled_size_bid_volume",
        "added_size_ask_volume",
        "cancelled_size_ask_volume",
    ):
        if col not in pivot:
            pivot[col] = 0.0

    pivot = pivot.rename(
        columns={
            "added_size_bid_volume": "bid_added_volume",
            "cancelled_size_bid_volume": "bid_cancelled_volume",
            "added_size_ask_volume": "ask_added_volume",
            "cancelled_size_ask_volume": "ask_cancelled_volume",
        }
    )
    pivot["net_displayed_bid_change"] = (
        pivot["bid_added_volume"] - pivot["bid_cancelled_volume"]
    )
    pivot["net_displayed_ask_change"] = (
        pivot["ask_added_volume"] - pivot["ask_cancelled_volume"]
    )
    return pivot.sort_values("timestamp").reset_index(drop=True)
