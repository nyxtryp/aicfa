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
    """Build future-outcome labels from OHLC candles."""
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
        complete = future_close.notna()

        out[f"future_return_{horizon}"] = future_close / c.clip(lower=EPS) - 1.0

        future_high_frame = pd.concat(
            [h.shift(-i) for i in range(1, horizon + 1)],
            axis=1,
        )
        future_low_frame = pd.concat(
            [l.shift(-i) for i in range(1, horizon + 1)],
            axis=1,
        )

        future_high = future_high_frame.max(axis=1)
        future_low = future_low_frame.min(axis=1)

        out[f"future_mfe_long_{horizon}"] = (
            future_high / c.clip(lower=EPS) - 1.0
        ).clip(lower=0.0)
        out[f"future_mfe_short_{horizon}"] = (
            1.0 - future_low / c.clip(lower=EPS)
        ).clip(lower=0.0)
        out[f"future_mae_long_{horizon}"] = (
            1.0 - future_low / c.clip(lower=EPS)
        ).clip(lower=0.0)
        out[f"future_mae_short_{horizon}"] = (
            future_high / c.clip(lower=EPS) - 1.0
        ).clip(lower=0.0)

        mfe_long_time = np.full(len(x), np.nan, dtype=float)
        mfe_short_time = np.full(len(x), np.nan, dtype=float)
        for i in range(len(x) - horizon):
            if not complete.iloc[i]:
                continue
            highs = h.iloc[i + 1 : i + horizon + 1].to_numpy(dtype=float)
            lows = l.iloc[i + 1 : i + horizon + 1].to_numpy(dtype=float)
            mfe_long_time[i] = float(np.nanargmax(highs) + 1)
            mfe_short_time[i] = float(np.nanargmin(lows) + 1)

        out[f"time_to_mfe_long_{horizon}"] = mfe_long_time
        out[f"time_to_mfe_short_{horizon}"] = mfe_short_time

        long_tp = c + barrier_atr * atr
        long_sl = c - barrier_atr * atr

        triple = np.full(len(x), np.nan, dtype=float)
        censored_time = float(horizon + 1)
        time_long_tp = np.full(len(x), np.nan, dtype=float)
        time_long_sl = np.full(len(x), np.nan, dtype=float)
        time_short_tp = np.full(len(x), np.nan, dtype=float)
        time_short_sl = np.full(len(x), np.nan, dtype=float)

        for i in range(len(x) - horizon):
            if not complete.iloc[i]:
                continue

            if pd.isna(atr.iloc[i]):
                time_long_tp[i] = censored_time
                time_long_sl[i] = censored_time
                time_short_tp[i] = censored_time
                time_short_sl[i] = censored_time
                continue

            time_long_tp[i] = censored_time
            time_long_sl[i] = censored_time
            time_short_tp[i] = censored_time
            time_short_sl[i] = censored_time

            tp_long = long_tp.iloc[i]
            sl_long = long_sl.iloc[i]

            result = 0.0
            for offset, j in enumerate(
                range(i + 1, i + horizon + 1), start=1
            ):
                hit_upper = h.iloc[j] >= tp_long
                hit_lower = l.iloc[j] <= sl_long

                # Upper = long TP + short SL.
                # Lower = long SL + short TP.
                # Both in one OHLC candle are ambiguous intrabar.
                if hit_upper and hit_lower:
                    time_long_tp[i] = offset
                    time_short_sl[i] = offset
                    time_long_sl[i] = offset
                    time_short_tp[i] = offset
                    result = 0.0
                    break

                if hit_upper:
                    time_long_tp[i] = offset
                    time_short_sl[i] = offset
                    result = 1.0
                    break

                if hit_lower:
                    time_long_sl[i] = offset
                    time_short_tp[i] = offset
                    result = -1.0
                    break

            triple[i] = result

        out[f"time_to_long_tp_{horizon}"] = time_long_tp
        out[f"time_to_long_sl_{horizon}"] = time_long_sl
        out[f"time_to_short_tp_{horizon}"] = time_short_tp
        out[f"time_to_short_sl_{horizon}"] = time_short_sl
        out[f"triple_barrier_{horizon}"] = triple

        for column in (
            f"future_return_{horizon}",
            f"future_mfe_long_{horizon}",
            f"future_mfe_short_{horizon}",
            f"future_mae_long_{horizon}",
            f"future_mae_short_{horizon}",
            f"time_to_mfe_long_{horizon}",
            f"time_to_mfe_short_{horizon}",
            f"time_to_long_tp_{horizon}",
            f"time_to_long_sl_{horizon}",
            f"time_to_short_tp_{horizon}",
            f"time_to_short_sl_{horizon}",
            f"triple_barrier_{horizon}",
        ):
            out.loc[~complete, column] = np.nan

    return out
