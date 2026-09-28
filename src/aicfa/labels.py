"""Causal-to-past feature labels built from future market outcomes.

Labels intentionally look forward from each candle. They are targets for
training/evaluation and must never be fed into the feature set.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


EPS = 1e-12


def build_labels(
    df: pd.DataFrame,
    horizons: tuple[int, ...] = (5, 20, 60),
    barrier_atr: float = 1.0,
) -> pd.DataFrame:
    """Build future-outcome labels from OHLC candles.

    For each row t, all label values may use candles after t. This function
    must therefore only be used to create targets, never model inputs.

    The triple-barrier label is:
      +1: long take-profit reached before long stop
      -1: short take-profit reached before short stop
       0: neither barrier reached, or both barriers are touched in the same
          candle and their intrabar order cannot be known from OHLC data.
    """
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    x = df[required].copy()
    x = x.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

    if not horizons or any(h <= 0 for h in horizons):
        raise ValueError("horizons must contain positive integers")
    if barrier_atr <= 0:
        raise ValueError("barrier_atr must be positive")

    c = x["close"].astype(float)
    h = x["high"].astype(float)
    l = x["low"].astype(float)

    # Wilder-style ATR proxy using only candles up to the current row.
    prev_close = c.shift(1)
    true_range = pd.concat(
        [
            h - l,
            (h - prev_close).abs(),
            (l - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.rolling(14, min_periods=14).mean()

    out = x.copy()

    for horizon in horizons:
        future_close = c.shift(-horizon)
        out[f"future_return_{horizon}"] = future_close / c.clip(lower=EPS) - 1.0

        future_high = pd.concat(
            [h.shift(-i) for i in range(1, horizon + 1)],
            axis=1,
        ).max(axis=1)
        future_low = pd.concat(
            [l.shift(-i) for i in range(1, horizon + 1)],
            axis=1,
        ).min(axis=1)

        out[f"future_mfe_long_{horizon}"] = (
            future_high / c.clip(lower=EPS) - 1.0
        )
        out[f"future_mfe_short_{horizon}"] = (
            1.0 - future_low / c.clip(lower=EPS)
        )

        # Only complete future windows can receive a valid horizon label.
        complete = future_close.notna()

        long_tp = c + barrier_atr * atr
        long_sl = c - barrier_atr * atr
        short_tp = c - barrier_atr * atr
        short_sl = c + barrier_atr * atr

        values = np.zeros(len(x), dtype=np.int8)

        for i in range(len(x) - horizon):
            if not complete.iloc[i] or pd.isna(atr.iloc[i]):
                continue

            tp_long = long_tp.iloc[i]
            sl_long = long_sl.iloc[i]
            tp_short = short_tp.iloc[i]
            sl_short = short_sl.iloc[i]

            for j in range(i + 1, i + horizon + 1):
                hit_long_tp = h.iloc[j] >= tp_long
                hit_long_sl = l.iloc[j] <= sl_long
                hit_short_tp = l.iloc[j] <= tp_short
                hit_short_sl = h.iloc[j] >= sl_short

                if (hit_long_tp and hit_long_sl) or (hit_short_tp and hit_short_sl):
                    values[i] = 0
                    break

                if hit_long_tp or hit_short_sl:
                    values[i] = 1
                    break

                if hit_long_sl or hit_short_tp:
                    values[i] = -1
                    break

        values[~complete.to_numpy()] = 0
        out[f"triple_barrier_{horizon}"] = values

        # Final rows have no complete future window and are explicitly NaN,
        # rather than pretending that zero is a real observed outcome.
        out.loc[~complete, f"triple_barrier_{horizon}"] = np.nan
        out.loc[~complete, f"future_return_{horizon}"] = np.nan
        out.loc[~complete, f"future_mfe_long_{horizon}"] = np.nan
        out.loc[~complete, f"future_mfe_short_{horizon}"] = np.nan

    return out
