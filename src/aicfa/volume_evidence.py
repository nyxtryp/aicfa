"""Causal volume evidence layer for AICFA.

This module attaches volume observations to already-causal market events. It
does not produce a directional score or BUY/SELL verdict.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

_EPS = 1e-12
_BASELINE_WINDOW = 60


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    x = (
        df[required]
        .copy()
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )
    for column in required[1:]:
        x[column] = pd.to_numeric(x[column], errors="coerce")
        if x[column].isna().any():
            raise ValueError(f"{column} must be numeric and non-null")

    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")
    if (x["volume"] < 0).any():
        raise ValueError("Volume must be non-negative")
    if (x["close"] <= 0).any():
        raise ValueError("Close must be positive")
    return x


def _event_column(
    frame: pd.DataFrame | None,
    name: str,
    n: int,
) -> pd.Series:
    if frame is None or name not in frame.columns:
        return pd.Series(np.zeros(n, dtype="int8"))
    if len(frame) != n:
        raise ValueError(f"Component length mismatch for {name}")
    values = pd.to_numeric(frame[name], errors="coerce").fillna(0)
    return values.ne(0).astype("int8").reset_index(drop=True)


def build_volume_evidence(
    df: pd.DataFrame,
    *,
    structure: pd.DataFrame | None = None,
    liquidity: pd.DataFrame | None = None,
    displacement: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build causal volume observations and attach them to causal events.

    The baseline for row t uses only volume from rows strictly before t.
    Event columns are copied as observations; they are never converted into
    a directional score or trading verdict.
    """
    x = _validate(df)
    n = len(x)
    out = x.copy()

    volume = x["volume"]
    baseline = volume.shift(1).rolling(
        _BASELINE_WINDOW, min_periods=_BASELINE_WINDOW
    )
    mean = baseline.mean()
    std = baseline.std()

    relative = volume / mean.clip(lower=_EPS)
    zscore = (volume - mean) / std.clip(lower=_EPS)

    out["volume_evidence_relative"] = relative
    out["volume_evidence_zscore"] = zscore
    out["volume_evidence_expansion"] = (
        relative.gt(1.5) & relative.notna()
    ).astype("int8")
    out["volume_evidence_dry_up"] = (
        relative.lt(0.75) & relative.notna()
    ).astype("int8")

    bos_up = _event_column(structure, "bos_up", n)
    bos_down = _event_column(structure, "bos_down", n)
    sweep_high = _event_column(liquidity, "sweep_high", n)
    sweep_low = _event_column(liquidity, "sweep_low", n)
    displacement_up = _event_column(displacement, "displacement_up", n)
    displacement_down = _event_column(displacement, "displacement_down", n)

    # Breakout evidence is explicitly tied to the structure engine's causal
    # BOS event, rather than inferred from future candles.
    out["volume_evidence_breakout_up"] = (
        bos_up.eq(1) & out["volume_evidence_expansion"].eq(1)
    ).astype("int8")
    out["volume_evidence_breakout_down"] = (
        bos_down.eq(1) & out["volume_evidence_expansion"].eq(1)
    ).astype("int8")

    # A liquidity sweep is also the causal rejection observation here:
    # high sweep -> rejection at highs, low sweep -> rejection at lows.
    out["volume_evidence_rejection_high"] = (
        sweep_high.eq(1) & out["volume_evidence_expansion"].eq(1)
    ).astype("int8")
    out["volume_evidence_rejection_low"] = (
        sweep_low.eq(1) & out["volume_evidence_expansion"].eq(1)
    ).astype("int8")
    out["volume_evidence_liquidity_sweep_high"] = sweep_high
    out["volume_evidence_liquidity_sweep_low"] = sweep_low

    out["volume_evidence_displacement_up"] = (
        displacement_up.eq(1) & out["volume_evidence_expansion"].eq(1)
    ).astype("int8")
    out["volume_evidence_displacement_down"] = (
        displacement_down.eq(1) & out["volume_evidence_expansion"].eq(1)
    ).astype("int8")

    return out
