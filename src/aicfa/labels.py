"""Research-grade causal labels for AICFA.

The module separates path statistics from trade-event labels.

Features are causal. Labels are allowed to use future market data and must
never be included in model inputs.

The event labels follow a volatility-scaled triple-barrier design:
profit-taking, stop-loss, and a maximum holding period. Horizontal barriers
are expressed as multiples of a causal realized-volatility target. When both
horizontal barriers are touched in the same OHLC bar, the intrabar order is
unknown; the event is marked ambiguous instead of inventing a winner.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12


def _validate_input(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [column for column in required if column not in df.columns]
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
        x[column] = x[column].astype(float)

    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")
    if (x["low"] <= 0).any() or (x["close"] <= 0).any():
        raise ValueError("Prices must be positive")

    return x


def _realized_volatility(close: pd.Series, span: int) -> pd.Series:
    """Causal EWMA standard deviation of log returns."""
    log_return = np.log(close.clip(lower=EPS)).diff()
    return log_return.ewm(span=span, min_periods=span, adjust=False).std(bias=False)


def _path_metrics(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    target_vol: pd.Series,
    horizon: int,
    out: pd.DataFrame,
) -> None:
    future_close = close.shift(-horizon)
    complete = future_close.notna()

    future_log_return = np.log(
        future_close.clip(lower=EPS) / close.clip(lower=EPS)
    )

    future_high = pd.concat(
        [high.shift(-i) for i in range(1, horizon + 1)],
        axis=1,
    ).max(axis=1)
    future_low = pd.concat(
        [low.shift(-i) for i in range(1, horizon + 1)],
        axis=1,
    ).min(axis=1)

    mfe_long = np.log(future_high.clip(lower=EPS) / close.clip(lower=EPS))
    mfe_short = np.log(close.clip(lower=EPS) / future_low.clip(lower=EPS))
    mae_long = np.log(close.clip(lower=EPS) / future_low.clip(lower=EPS))
    mae_short = np.log(future_high.clip(lower=EPS) / close.clip(lower=EPS))

    out[f"future_return_{horizon}"] = (
        future_close / close.clip(lower=EPS) - 1.0
    )
    out[f"future_log_return_{horizon}"] = future_log_return
    out[f"future_mfe_long_{horizon}"] = mfe_long.clip(lower=0.0)
    out[f"future_mfe_short_{horizon}"] = mfe_short.clip(lower=0.0)
    out[f"future_mae_long_{horizon}"] = mae_long.clip(lower=0.0)
    out[f"future_mae_short_{horizon}"] = mae_short.clip(lower=0.0)

    safe_vol = target_vol.replace(0.0, np.nan)
    out[f"future_mfe_long_r_{horizon}"] = (
        out[f"future_mfe_long_{horizon}"] / safe_vol
    )
    out[f"future_mfe_short_r_{horizon}"] = (
        out[f"future_mfe_short_{horizon}"] / safe_vol
    )
    out[f"future_mae_long_r_{horizon}"] = (
        out[f"future_mae_long_{horizon}"] / safe_vol
    )
    out[f"future_mae_short_r_{horizon}"] = (
        out[f"future_mae_short_{horizon}"] / safe_vol
    )
    out[f"target_vol_{horizon}"] = target_vol

    time_to_mfe_long = np.full(len(close), np.nan, dtype=float)
    time_to_mfe_short = np.full(len(close), np.nan, dtype=float)

    high_values = high.to_numpy(dtype=float)
    low_values = low.to_numpy(dtype=float)

    for i in range(len(close) - horizon):
        if not complete.iloc[i]:
            continue
        highs = high_values[i + 1 : i + horizon + 1]
        lows = low_values[i + 1 : i + horizon + 1]
        time_to_mfe_long[i] = float(np.nanargmax(highs) + 1)
        time_to_mfe_short[i] = float(np.nanargmin(lows) + 1)

    out[f"time_to_mfe_long_{horizon}"] = time_to_mfe_long
    out[f"time_to_mfe_short_{horizon}"] = time_to_mfe_short


def _triple_barrier(
    timestamp: pd.Series,
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    target_vol: pd.Series,
    horizon: int,
    pt_mult: float,
    sl_mult: float,
    out: pd.DataFrame,
) -> None:
    """Create path-aware event labels with explicit OHLC ambiguity handling."""

    n = len(close)
    close_values = close.to_numpy(dtype=float)
    high_values = high.to_numpy(dtype=float)
    low_values = low.to_numpy(dtype=float)
    vol_values = target_vol.to_numpy(dtype=float)

    event_outcome = np.full(n, np.nan, dtype=float)
    event_touch = np.full(n, np.nan, dtype=float)
    event_return = np.full(n, np.nan, dtype=float)
    event_log_return = np.full(n, np.nan, dtype=float)
    event_end_offset = np.full(n, np.nan, dtype=float)
    event_target = np.full(n, np.nan, dtype=float)
    event_ambiguous = np.full(n, np.nan, dtype=float)
    label_end_timestamp = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")

    for i in range(n - horizon):
        vol = vol_values[i]
        if not np.isfinite(vol) or vol <= 0:
            continue

        entry = close_values[i]
        upper = np.exp(pt_mult * vol) * entry
        lower = np.exp(-sl_mult * vol) * entry

        resolved = False

        for offset in range(1, horizon + 1):
            j = i + offset
            hit_upper = high_values[j] >= upper
            hit_lower = low_values[j] <= lower

            if hit_upper and hit_lower:
                event_ambiguous[i] = 1.0
                event_end_offset[i] = float(offset)
                event_target[i] = vol
                label_end_timestamp[i] = timestamp.iloc[j].to_datetime64()
                resolved = True
                break

            if hit_upper:
                event_outcome[i] = 1.0
                event_touch[i] = 1.0
                event_return[i] = upper / entry - 1.0
                event_log_return[i] = pt_mult * vol
                event_end_offset[i] = float(offset)
                event_target[i] = vol
                event_ambiguous[i] = 0.0
                label_end_timestamp[i] = timestamp.iloc[j].to_datetime64()
                resolved = True
                break

            if hit_lower:
                event_outcome[i] = -1.0
                event_touch[i] = -1.0
                event_return[i] = lower / entry - 1.0
                event_log_return[i] = -sl_mult * vol
                event_end_offset[i] = float(offset)
                event_target[i] = vol
                event_ambiguous[i] = 0.0
                label_end_timestamp[i] = timestamp.iloc[j].to_datetime64()
                resolved = True
                break

        if resolved:
            continue

        j = i + horizon
        final_log_return = np.log(close_values[j] / entry)
        event_log_return[i] = final_log_return
        event_return[i] = np.exp(final_log_return) - 1.0
        event_outcome[i] = float(np.sign(final_log_return))
        event_touch[i] = 0.0
        event_end_offset[i] = float(horizon)
        event_target[i] = vol
        event_ambiguous[i] = 0.0
        label_end_timestamp[i] = timestamp.iloc[j].to_datetime64()

    out[f"event_outcome_{horizon}"] = event_outcome
    out[f"event_touch_{horizon}"] = event_touch
    out[f"event_return_{horizon}"] = event_return
    out[f"event_log_return_{horizon}"] = event_log_return
    out[f"event_end_offset_{horizon}"] = event_end_offset
    out[f"event_target_vol_{horizon}"] = event_target
    out[f"event_ambiguous_{horizon}"] = event_ambiguous
    out[f"label_end_timestamp_{horizon}"] = pd.to_datetime(
        label_end_timestamp, utc=True
    )


def build_labels(
    df: pd.DataFrame,
    horizons: tuple[int, ...] = (5, 20, 60),
    volatility_span: int = 64,
    pt_mult: float = 2.0,
    sl_mult: float = 1.0,
) -> pd.DataFrame:
    """Build causal-to-past feature labels from future market outcomes.

    The output contains two distinct target families:

    1. Path targets: future return, MFE/MAE and time-to-MFE.
    2. Event targets: volatility-scaled triple-barrier outcomes.

    The barrier multipliers are configuration parameters for research. They
    are not claimed to be optimal trading parameters.
    """

    if not horizons or any(h <= 0 for h in horizons):
        raise ValueError("horizons must contain positive integers")
    if len(set(horizons)) != len(horizons):
        raise ValueError("horizons must be unique")
    if volatility_span < 2:
        raise ValueError("volatility_span must be at least 2")
    if pt_mult <= 0 or sl_mult <= 0:
        raise ValueError("pt_mult and sl_mult must be positive")

    x = _validate_input(df)
    close = x["close"]
    high = x["high"]
    low = x["low"]
    target_vol = _realized_volatility(close, volatility_span)
    timestamps = pd.to_datetime(x["timestamp"], utc=True)

    out = x.copy()

    for horizon in horizons:
        _path_metrics(close, high, low, target_vol, horizon, out)
        out[f"label_end_timestamp_{horizon}"] = timestamps.shift(-horizon)
        _triple_barrier(
            timestamps,
            close,
            high,
            low,
            target_vol,
            horizon,
            pt_mult,
            sl_mult,
            out,
        )

        future_complete = close.shift(-horizon).notna()
        label_columns = [
            column
            for column in out.columns
            if column.endswith(f"_{horizon}")
            or column.endswith(f"_{horizon}_r")
        ]
        for column in label_columns:
            out.loc[~future_complete, column] = np.nan

    return out
