"""Deterministic bridge from AICFA feature/state columns to MarketEvidence.

This adapter never invents observations for unavailable timeframes. It emits
only concepts whose deterministic columns are present and active on the
selected completed row.
"""
from __future__ import annotations

import pandas as pd

from .market_evidence import MarketEvidence, MarketObservation

_DIRECTION_COLUMNS = {
    "market_structure.bos": ("bos_up", "bos_down"),
    "displacement": ("displacement_up", "displacement_down"),
    "imbalance.fvg": ("fvg_bullish", "fvg_bearish"),
    "order_block.bullish": ("order_block_bullish", None),
    "order_block.bearish": (None, "order_block_bearish"),
    "liquidity.sweep": ("sweep_low", "sweep_high"),
}


def _active(value: object) -> bool:
    try:
        return bool(float(value))
    except (TypeError, ValueError):
        return False


def _observation(
    concept_id: str,
    timeframe: str,
    row: pd.Series,
    columns: tuple[str | None, str | None],
) -> MarketObservation | None:
    long_column, short_column = columns
    long_active = long_column is not None and _active(row.get(long_column, 0))
    short_active = short_column is not None and _active(row.get(short_column, 0))

    if not long_active and not short_active:
        return None

    direction = "long" if long_active and not short_active else "short" if short_active and not long_active else None
    active_columns = tuple(column for column, active in ((long_column, long_active), (short_column, short_active)) if column and active)
    evidence = tuple(f"{column}={row[column]!r}" for column in active_columns)

    return MarketObservation(
        concept_id=concept_id,
        timeframe=timeframe,
        state="observed",
        confidence=1.0,
        evidence=evidence,
        direction=direction,
        notes="deterministic feature column",
    )


def build_market_evidence(
    analysis: pd.DataFrame,
    *,
    asset: str,
    base_timeframe: str = "1m",
    timeframes: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "1d", "1w"),
) -> MarketEvidence:
    """Convert the latest completed feature row into canonical market evidence."""
    if analysis.empty:
        raise ValueError("analysis must not be empty")
    if not asset.strip():
        raise ValueError("asset must not be empty")
    if not timeframes:
        raise ValueError("timeframes must not be empty")
    if base_timeframe not in timeframes:
        raise ValueError("base_timeframe must be included in timeframes")

    latest = analysis.sort_values("timestamp").iloc[-1]
    observations: list[MarketObservation] = []
    missing: list[str] = []

    for timeframe in timeframes:
        prefix = "" if timeframe == base_timeframe else f"mtf_{timeframe}_"
        emitted = False

        for concept_id, columns in _DIRECTION_COLUMNS.items():
            actual_columns = tuple(
                None if column is None else f"{prefix}{column}"
                for column in columns
            )
            item = _observation(concept_id, timeframe, latest, actual_columns)
            if item is not None:
                observations.append(item)
                emitted = True

        if not emitted:
            missing.append(f"{timeframe}:no_active_supported_observation")

    directions = {item.direction for item in observations if item.direction in {"long", "short"}}
    conflicts = ("explicit long and short observations coexist",) if directions == {"long", "short"} else ()

    return MarketEvidence(
        asset=asset,
        observations=tuple(observations),
        timeframes=timeframes,
        missing_context=tuple(missing),
        conflicts=conflicts,
    )


def build_market_evidence_from_frames(
    analyses: dict[str, pd.DataFrame],
    *,
    asset: str,
    timeframes: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "1d", "1w"),
) -> MarketEvidence:
    """Build evidence from independently analyzed completed timeframe frames."""
    if not analyses:
        raise ValueError("analyses must not be empty")
    if not timeframes:
        raise ValueError("timeframes must not be empty")

    observations: list[MarketObservation] = []
    missing: list[str] = []

    for timeframe in timeframes:
        frame = analyses.get(timeframe)
        if frame is None:
            missing.append(f"{timeframe}:analysis_not_available")
            continue
        item = build_market_evidence(
            frame,
            asset=asset,
            base_timeframe=timeframe,
            timeframes=(timeframe,),
        )
        observations.extend(item.observations)
        missing.extend(item.missing_context)

    directions = {
        item.direction
        for item in observations
        if item.direction in {"long", "short"}
    }
    conflicts = (
        ("explicit long and short observations coexist",)
        if directions == {"long", "short"}
        else ()
    )

    return MarketEvidence(
        asset=asset,
        observations=tuple(observations),
        timeframes=timeframes,
        missing_context=tuple(missing),
        conflicts=conflicts,
    )
