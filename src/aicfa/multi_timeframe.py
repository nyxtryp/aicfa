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
        available = structure[state_columns].copy()
        available.insert(0, "_available_at", source_ts + pd.Timedelta(minutes=minutes))
        right = available.sort_values("_available_at").reset_index(drop=True)
        right = right.rename(columns={column: f"mtf_{timeframe}_{column}" for column in state_columns})

        left = pd.DataFrame({"_base_ts": base_ts})
        merged = pd.merge_asof(
            left.sort_values("_base_ts"),
            right,
            left_on="_base_ts",
            right_on="_available_at",
            direction="backward",
            allow_exact_matches=True,
        ).sort_index()

        for column in state_columns:
            target = f"mtf_{timeframe}_{column}"
            out[target] = merged[target].to_numpy()

    return out
