"""Causal multi-timeframe market-structure engine for AICFA.

Higher-timeframe structure is only exposed to lower-timeframe rows after the
higher-timeframe candle has closed. The engine accepts already aggregated
OHLCV frames keyed by timeframe and never resamples a lower timeframe into a
higher timeframe implicitly, avoiding accidental partial-candle leakage.
"""
from __future__ import annotations
import re
import pandas as pd
from .structure import build_structure

_TIMEFRAME_RE = re.compile(r"^(\d+)(m|h|d|w)$")
_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440, "w": 10080}

def _timeframe_minutes(timeframe: str) -> int:
    if not isinstance(timeframe, str):
        raise ValueError("timeframe must be a string such as '5m' or '1h'")
    match = _TIMEFRAME_RE.fullmatch(timeframe.lower())
    if match is None:
        raise ValueError("invalid timeframe; expected <positive integer><m|h|d|w>")
    value = int(match.group(1))
    if value < 1:
        raise ValueError("timeframe value must be positive")
    return value * _UNIT_MINUTES[match.group(2)]

def _validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    x = df[required].copy().sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for column in required[1:]:
        x[column] = x[column].astype(float)
    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")
    if (x["volume"] < 0).any():
        raise ValueError("Invalid volume: negative values are not allowed")
    return x

def build_multi_timeframe_structure(
    base: pd.DataFrame,
    frames: dict[str, pd.DataFrame],
    *,
    structure_left: int = 2,
    structure_right: int = 2,
    equal_tolerance: float = 0.0,
) -> pd.DataFrame:
    """Map causal structure from closed higher-timeframe candles to a base frame.

    frames contains independently aggregated OHLCV data keyed by timeframe.
    Each source candle is timestamped at its opening time. Its structure state
    becomes available at open + timeframe duration. merge_asof then maps only
    states whose close time is <= the base-row timestamp.
    """
    base_x = _validate_ohlcv(base)
    if not frames:
        raise ValueError("frames must contain at least one timeframe")
    if len(set(frames)) != len(frames):
        raise ValueError("duplicate timeframe keys are not allowed")

    base_ts = pd.to_datetime(base_x["timestamp"], unit="ms", utc=True)
    out = base_x.copy()

    for timeframe, source in sorted(frames.items(), key=lambda item: _timeframe_minutes(item[0])):
        minutes = _timeframe_minutes(timeframe)
        source_x = _validate_ohlcv(source)
        source_ts = pd.to_datetime(source_x["timestamp"], unit="ms", utc=True)
        if len(source_ts) > 1:
            deltas = source_ts.diff().dropna()
            if (deltas < pd.Timedelta(minutes=minutes)).any():
                raise ValueError(f"{timeframe} source contains intervals shorter than its declared timeframe")

        structure = build_structure(
            source_x,
            left=structure_left,
            right=structure_right,
            equal_tolerance=equal_tolerance,
        )
        state_columns = [
            "structure_direction", "swing_high", "swing_low", "hh", "hl", "lh", "ll",
            "bos_up", "bos_down", "choch_up", "choch_down", "mss_up", "mss_down",
            "swing_high_price", "swing_low_price",
        ]
        # Source timestamps are sorted, so causal mapping only needs a
        # backward lookup. searchsorted avoids a wide merge_asof frame and
        # preserves the exact close-time boundary.
        available_at = source_x["timestamp"].to_numpy(dtype="int64") + minutes * 60_000
        base_millis = base_x["timestamp"].to_numpy(dtype="int64")
        source_indices = np.searchsorted(available_at, base_millis, side="right") - 1
        valid = source_indices >= 0

        mapped = {}
        for column in state_columns:
            values = structure[column].to_numpy()
            if np.issubdtype(values.dtype, np.number):
                mapped_values = np.full(len(base_x), np.nan, dtype=float)
            else:
                mapped_values = np.empty(len(base_x), dtype=object)
                mapped_values[:] = np.nan
            if valid.any():
                mapped_values[valid] = values[source_indices[valid]]
            mapped[f"mtf_{timeframe}_{column}"] = mapped_values

        out = pd.concat([out, pd.DataFrame(mapped, index=out.index)], axis=1)
    return out
