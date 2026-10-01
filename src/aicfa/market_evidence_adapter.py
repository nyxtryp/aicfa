"""Deterministic bridge from AICFA feature/state columns to MarketEvidence.

This adapter never invents observations for unavailable timeframes. It emits
causally relevant recent events and currently active lifecycle states from
completed deterministic analysis frames.
"""
from __future__ import annotations

import pandas as pd

from .market_evidence import MarketEvidence, MarketObservation


_DIRECTION_COLUMNS = {
    "market_structure.bos": ("bos_up", "bos_down"),
    "market_structure.choch": ("choch_up", "choch_down"),
    "displacement": ("displacement_up", "displacement_down"),
    "imbalance.fvg": ("fvg_bullish", "fvg_bearish"),
    "order_block.bullish": ("order_block_bullish", None),
    "order_block.bearish": (None, "order_block_bearish"),
    "liquidity.sweep": ("sweep_low", "sweep_high"),
}

_ACTIVE_COLUMNS = {
    "imbalance.fvg": "fvg_active",
    "order_block.bullish": "order_block_active",
    "order_block.bearish": "order_block_active",
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
    *,
    notes: str,
) -> MarketObservation | None:
    long_column, short_column = columns
    long_active = long_column is not None and _active(row.get(long_column, 0))
    short_active = short_column is not None and _active(row.get(short_column, 0))

    if not long_active and not short_active:
        return None

    direction = (
        "long"
        if long_active and not short_active
        else "short"
        if short_active and not long_active
        else None
    )
    active_columns = tuple(
        column
        for column, active in (
            (long_column, long_active),
            (short_column, short_active),
        )
        if column and active
    )
    evidence = tuple(f"{column}={row[column]!r}" for column in active_columns)

    return MarketObservation(
        concept_id=concept_id,
        timeframe=timeframe,
        state="observed",
        confidence=1.0,
        evidence=evidence,
        direction=direction,
        notes=notes,
    )


def _latest_event(
    analysis: pd.DataFrame,
    concept_id: str,
    timeframe: str,
) -> MarketObservation | None:
    columns = _DIRECTION_COLUMNS[concept_id]
    available = [
        column for column in columns
        if column is not None and column in analysis.columns
    ]
    if not available:
        return None

    mask = analysis[available].fillna(0).applymap(_active).any(axis=1)
    if not mask.any():
        return None

    row = analysis.loc[mask].iloc[-1]
    return _observation(
        concept_id,
        timeframe,
        row,
        columns,
        notes="latest causally knowable event in available analysis",
    )


def _latest_active(
    analysis: pd.DataFrame,
    concept_id: str,
    timeframe: str,
) -> MarketObservation | None:
    active_column = _ACTIVE_COLUMNS.get(concept_id)
    if active_column is None or active_column not in analysis.columns:
        return None

    latest = analysis.sort_values("timestamp").iloc[-1]
    if not _active(latest.get(active_column, 0)):
        return None

    # Lifecycle columns are stateful rather than directional. Recover the
    # direction from the latest creation event at or before the active row.
    event = _latest_event(analysis, concept_id, timeframe)
    if event is None:
        return None

    return MarketObservation(
        concept_id=event.concept_id,
        timeframe=event.timeframe,
        state="observed",
        confidence=1.0,
        evidence=event.evidence + (f"{active_column}=1",),
        direction=event.direction,
        notes="currently active lifecycle state",
    )


def build_market_evidence(
    analysis: pd.DataFrame,
    *,
    asset: str,
    base_timeframe: str = "1m",
    timeframes: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "1d", "1w"),
) -> MarketEvidence:
    """Convert causal recent events and active states into market evidence."""
    if analysis.empty:
        raise ValueError("analysis must not be empty")
    if not asset.strip():
        raise ValueError("asset must not be empty")
    if not timeframes:
        raise ValueError("timeframes must not be empty")
    if base_timeframe not in timeframes:
        raise ValueError("base_timeframe must be included in timeframes")

    observations: list[MarketObservation] = []
    missing: list[str] = []

    for timeframe in timeframes:
        emitted = False

        # Active lifecycle state has priority over the creation event because
        # it represents the current state that remains relevant at the latest
        # completed candle.
        for concept_id in ("imbalance.fvg", "order_block.bullish", "order_block.bearish"):
            item = _latest_active(analysis, concept_id, timeframe)
            if item is not None:
                observations.append(item)
                emitted = True

        for concept_id in _DIRECTION_COLUMNS:
            if concept_id in {"imbalance.fvg", "order_block.bullish", "order_block.bearish"}:
                if emitted:
                    continue
            item = _latest_event(analysis, concept_id, timeframe)
            if item is not None:
                observations.append(item)
                emitted = True

        if not emitted:
            missing.append(f"{timeframe}:no_active_supported_observation")

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
