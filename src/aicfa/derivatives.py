"""Causal derivatives observations for AICFA.

The engine aligns derivative observations to a base OHLCV timeline using only
information available at each base timestamp. It exposes descriptive market
state rather than trading signals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


_REQUIRED = {"timestamp", "funding_rate", "open_interest"}
_OPTIONAL_NONNEGATIVE = {
    "liquidation_volume",
    "long_liquidation_volume",
    "short_liquidation_volume",
}
_OPTIONAL_RATIO = {
    "long_short_ratio",
    "long_short_ratio_global",
    "long_short_ratio_top_trader",
}
_OPTIONAL_SIGNED = {"basis", "basis_pct"}


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    x = df.copy()
    x["timestamp"] = pd.to_datetime(x["timestamp"], utc=True)
    x = x.sort_values("timestamp").drop_duplicates("timestamp", keep="last").reset_index(drop=True)

    numeric = _REQUIRED - {"timestamp"}
    for col in numeric | (_OPTIONAL_NONNEGATIVE & set(x.columns)) | (_OPTIONAL_RATIO & set(x.columns)) | (_OPTIONAL_SIGNED & set(x.columns)):
        x[col] = pd.to_numeric(x[col], errors="coerce")

    if x[["funding_rate", "open_interest"]].isna().any().any():
        raise ValueError("funding_rate/open_interest must be numeric and non-null")
    if (x["open_interest"] < 0).any():
        raise ValueError("open_interest must be non-negative")

    for col in _OPTIONAL_NONNEGATIVE & set(x.columns):
        if x[col].dropna().lt(0).any():
            raise ValueError(f"{col} must be non-negative")
    for col in _OPTIONAL_RATIO & set(x.columns):
        if x[col].dropna().le(0).any():
            raise ValueError(f"{col} must be positive")

    return x


def _zscore_against_past(series: pd.Series, window: int) -> pd.Series:
    past = series.shift(1)
    mean = past.rolling(window, min_periods=window).mean()
    std = past.rolling(window, min_periods=window).std(ddof=0)
    return (series - mean) / std.replace(0, np.nan)


def _add_observation_features(d: pd.DataFrame, column: str, window: int) -> None:
    d[f"{column}_delta"] = d[column].diff()
    d[f"{column}_change_pct"] = (
        d[f"{column}_delta"] / d[column].shift(1).abs().replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan)
    d[f"{column}_zscore"] = _zscore_against_past(d[column], window)


def build_derivatives(
    base: pd.DataFrame,
    derivatives: pd.DataFrame,
    *,
    baseline_window: int = 24,
) -> pd.DataFrame:
    """Map causal funding/OI and optional positioning data onto base candles.

    Funding is point-in-time. OI is a state and is carried forward from the
    latest known observation. Optional positioning fields use the same causal
    carry-forward semantics because they describe the latest known state.
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

    # Compute changes/z-scores in source-observation order before alignment.
    _add_observation_features(d, "funding_rate", baseline_window)
    _add_observation_features(d, "open_interest", baseline_window)
    for col in sorted((_OPTIONAL_RATIO | _OPTIONAL_SIGNED) & set(d.columns)):
        _add_observation_features(d, col, baseline_window)
    for col in sorted(_OPTIONAL_NONNEGATIVE & set(d.columns)):
        d[f"{col}_delta"] = d[col].diff()

    # Funding is point-in-time; state/positioning fields carry forward only
    # from observations at or before the base timestamp.
    point_in_time = ["funding_rate", "funding_rate_delta", "funding_rate_change_pct", "funding_rate_zscore"]
    funding = d[["timestamp"] + point_in_time]
    state_columns = ["open_interest", "open_interest_delta", "open_interest_change_pct", "open_interest_zscore"]
    state_columns += [
        col for col in sorted((_OPTIONAL_RATIO | _OPTIONAL_SIGNED) & set(d.columns)
        ) for _ in [0]
    ]
    for col in state_columns:
        # Keep the base state column plus derived values for optional metrics.
        if col in d.columns:
            state_columns.extend([f"{col}_delta", f"{col}_change_pct", f"{col}_zscore"])
            break
    # Rebuild deterministically to avoid mutating a list while iterating.
    state_columns = ["open_interest", "open_interest_delta", "open_interest_change_pct", "open_interest_zscore"]
    for col in sorted((_OPTIONAL_RATIO | _OPTIONAL_SIGNED) & set(d.columns)):
        state_columns += [col, f"{col}_delta", f"{col}_change_pct", f"{col}_zscore"]

    aligned = b[["timestamp", "close"]].merge(funding, on="timestamp", how="left", sort=True)
    aligned = pd.merge_asof(
        aligned.sort_values("timestamp"),
        d[["timestamp"] + state_columns].sort_values("timestamp"),
        on="timestamp",
        direction="backward",
        allow_exact_matches=True,
    )

    # Liquidations are event observations: only the event at its own timestamp
    # is retained, rather than inventing repeated liquidation volume.
    for col in sorted(_OPTIONAL_NONNEGATIVE & set(d.columns)):
        liq = d[["timestamp", col]].copy()
        aligned = aligned.merge(liq, on="timestamp", how="left", sort=True, suffixes=("", "__liq"))
        if f"{col}__liq" in aligned:
            aligned[col] = aligned[f"{col}__liq"]
            aligned = aligned.drop(columns=[f"{col}__liq"])

    # When both directional liquidation streams are supplied, expose their
    # contemporaneous imbalance as an event feature. It is bounded to [-1, 1]
    # and remains empty when one side is unavailable; no values are carried
    # forward between liquidation events.
    if {"long_liquidation_volume", "short_liquidation_volume"} <= set(d.columns):
        long_liq = aligned["long_liquidation_volume"]
        short_liq = aligned["short_liquidation_volume"]
        total_liq = long_liq + short_liq
        aligned["liquidation_imbalance"] = (
            (long_liq - short_liq) / total_liq.replace(0, np.nan)
        )

    aligned["price_return"] = aligned["close"].pct_change()
    oi_delta_now = aligned["open_interest_delta"]
    ret = aligned["price_return"]
    has_oi = oi_delta_now.notna()
    aligned["oi_price_up_up"] = np.where(has_oi, ((oi_delta_now > 0) & (ret > 0)).astype(int), np.nan)
    aligned["oi_price_up_down"] = np.where(has_oi, ((oi_delta_now > 0) & (ret < 0)).astype(int), np.nan)
    aligned["oi_price_down_up"] = np.where(has_oi, ((oi_delta_now < 0) & (ret > 0)).astype(int), np.nan)
    aligned["oi_price_down_down"] = np.where(has_oi, ((oi_delta_now < 0) & (ret < 0)).astype(int), np.nan)

    out_cols = [
        "funding_rate", "funding_rate_delta", "funding_rate_change_pct", "funding_rate_zscore",
        "open_interest", "open_interest_delta", "open_interest_change_pct", "open_interest_zscore",
        "oi_price_up_up", "oi_price_up_down", "oi_price_down_up", "oi_price_down_down",
    ]
    for col in sorted((_OPTIONAL_RATIO | _OPTIONAL_SIGNED) & set(d.columns)):
        out_cols += [col, f"{col}_delta", f"{col}_change_pct", f"{col}_zscore"]
    out_cols += sorted(_OPTIONAL_NONNEGATIVE & set(d.columns))
    if "liquidation_imbalance" in aligned:
        out_cols.append("liquidation_imbalance")

    return aligned[out_cols]
