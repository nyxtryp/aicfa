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
    source_timeframes: Sequence[str] = ("5m", "15m", "1h", "4h", "1d", "1w"),
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

        # Active liquidity prices are OHLCV-derived pool levels. Treat the
        # level itself as a zero-width POI; any candle wick that sweeps it arms
        # the symbol for full structural confirmation analysis.
        for pool_side, count_column, price_column in (
            ("buy_side", "active_buy_liquidity_pools", "active_buy_liquidity_price"),
            ("sell_side", "active_sell_liquidity_pools", "active_sell_liquidity_price"),
        ):
            if _active_count(row, count_column):
                level = _number(row, price_column)
                if level is not None:
                    zones.append(ArmedZone(timeframe, "LIQUIDITY", pool_side, level, level))

        # OTE bands are the 62%-79% retracement zones of the last confirmed
        # dealing range. Keep both directional bands in the watch cache; the
        # canonical setup pipeline resolves bias and direction before entry.
        range_high = _number(row, "structural_dealing_range_high")
        range_low = _number(row, "structural_dealing_range_low")
        if range_high is not None and range_low is not None and range_high > range_low:
            span = range_high - range_low
            zones.append(ArmedZone(
                timeframe, "OTE", "bullish",
                range_low + 0.21 * span,
                range_low + 0.38 * span,
            ))
            zones.append(ArmedZone(
                timeframe, "OTE", "bearish",
                range_low + 0.62 * span,
                range_low + 0.79 * span,
            ))

        # Recent confirmed swing and prior-period levels are structural
        # trigger prices. BOS/CHoCH candles can cross these without touching an
        # FVG/OB body, so retain these levels as arming points too.
        for level_name in (
            "swing_high_price", "swing_low_price",
            "previous_high", "previous_low",
            "sweep_high_level", "sweep_low_level",
        ):
            level = _number(row, level_name)
            if level is not None:
                zones.append(ArmedZone(timeframe, "STRUCTURE", level_name, level, level))

    # De-duplicate identical bounds that are surfaced by repeated feature views.
    unique: dict[tuple[str, str, float, float], ArmedZone] = {}
    for zone in zones:
        unique[(zone.timeframe, zone.source, zone.low, zone.high)] = zone
    return tuple(unique.values())


def merge_refreshed_zones(
    existing: Sequence[ArmedZone],
    refreshed: Sequence[ArmedZone],
    refreshed_timeframes: Sequence[str],
) -> tuple[ArmedZone, ...]:
    """Replace only the timeframes present in a new analysis snapshot."""
    refreshed_set = set(refreshed_timeframes)
    retained = tuple(zone for zone in existing if zone.timeframe not in refreshed_set)
    return retained + tuple(refreshed)


def zones_for_trigger_timeframe(
    zones: Sequence[ArmedZone],
    trigger_timeframe: str,
) -> tuple[ArmedZone, ...]:
    """Use cached higher-timeframe POIs to gate 5m; 1m may also use 5m zones."""
    if trigger_timeframe == "5m":
        return tuple(zone for zone in zones if zone.timeframe in {"15m", "1h", "4h", "1d", "1w"})
    return tuple(zones)


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


def should_skip_zone_scan(
    *,
    timeframe: str,
    ready: bool,
    scan_in_progress: bool,
    candle_low: float,
    candle_high: float,
    zones: Sequence[ArmedZone],
) -> bool:
    """Skip only a lower-TF candle with a valid, non-empty POI cache.

    Empty/stale caches and concurrent zone refreshes fail open: missing POIs
    must never silently suppress the canonical setup pipeline.
    """
    if timeframe not in {"1m", "5m"} or not ready or scan_in_progress or not zones:
        return False
    return not candle_intersects_armed_zone(candle_low, candle_high, zones)


__all__ = [
    "ArmedZone", "extract_active_smc_zones", "merge_refreshed_zones",
    "zones_for_trigger_timeframe", "candle_intersects_armed_zone",
    "should_skip_zone_scan",
]
