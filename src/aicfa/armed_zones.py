"""Active OHLCV-derived SMC zones used to gate 1m confirmation scans."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class ArmedZone:
    timeframe: str
    source: str
    side: str
    low: float
    high: float

    def __post_init__(self) -> None:
        if not (math.isfinite(self.low) and math.isfinite(self.high)):
            raise ValueError("armed zone bounds must be finite")
        if self.low > self.high:
            raise ValueError("armed zone low must not exceed high")


def _number(row: pd.Series, key: str) -> float | None:
    value = row.get(key)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _active_count(row: pd.Series, key: str) -> bool:
    value = _number(row, key)
    return value is not None and value > 0


def extract_active_smc_zones(
    analyses: Mapping[str, pd.DataFrame],
    *,
    source_timeframes: Sequence[str] = ("5m", "15m", "1h", "4h", "1d"),
) -> tuple[ArmedZone, ...]:
    """Extract only live, finite FVG/OB bounds from the latest closed row.

    These zones are watch context, not entry signals. Actual confirmation and
    structural risk/target checks remain in the canonical AICFA setup pipeline.
    """
    zones: list[ArmedZone] = []
    for timeframe in source_timeframes:
        frame = analyses.get(timeframe)
        if frame is None or frame.empty:
            continue
        row = frame.iloc[-1]
        for side in ("bullish", "bearish"):
            if _active_count(row, f"fvg_active_{side}_count"):
                low = _number(row, f"fvg_{side}_low")
                high = _number(row, f"fvg_{side}_high")
                if low is not None and high is not None and low <= high:
                    zones.append(ArmedZone(timeframe, "FVG", side, low, high))

            ob_state = str(row.get(f"order_block_{side}_state", "NONE")).upper()
            ob_active = _number(row, "order_block_active")
            low = _number(row, f"order_block_{side}_low")
            high = _number(row, f"order_block_{side}_high")
            if (
                ob_active is not None and ob_active > 0
                and ob_state not in {"NONE", "INVALIDATED", "BROKEN", "CANCELLED"}
                and low is not None and high is not None and low <= high
            ):
                zones.append(ArmedZone(timeframe, "OB", side, low, high))

    # De-duplicate identical bounds that are surfaced by repeated feature views.
    unique: dict[tuple[str, str, float, float], ArmedZone] = {}
    for zone in zones:
        unique[(zone.timeframe, zone.source, zone.low, zone.high)] = zone
    return tuple(unique.values())


def candle_intersects_armed_zone(
    candle_low: float,
    candle_high: float,
    zones: Sequence[ArmedZone],
) -> bool:
    """Return true when the closed candle range overlaps any active SMC zone."""
    low, high = sorted((float(candle_low), float(candle_high)))
    if not (math.isfinite(low) and math.isfinite(high)):
        return False
    return any(high >= zone.low and low <= zone.high for zone in zones)


__all__ = ["ArmedZone", "extract_active_smc_zones", "candle_intersects_armed_zone"]
