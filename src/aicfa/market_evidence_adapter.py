"""Deterministic bridge from AICFA feature/state columns to MarketEvidence."""
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


def _active(value: object) -> bool:
    try:
        return bool(float(value))
    except (TypeError, ValueError):
        return False


def _columns_for(
    analysis: pd.DataFrame,
    timeframe: str,
    columns: tuple[str | None, str | None],
    *,
    base_timeframe: str,
) -> tuple[str | None, str | None]:
    prefix = "" if timeframe == base_timeframe else f"mtf_{timeframe}_"
    return tuple(
        f"{prefix}{column}" if column is not None else None
        for column in columns
    )


def _lifecycle_column(
    analysis: pd.DataFrame,
    timeframe: str,
    name: str,
    *,
    base_timeframe: str,
) -> str | None:
    candidates = (
        name if timeframe == base_timeframe else f"mtf_{timeframe}_{name}",
        f"mtf_{timeframe}_{name}" if timeframe == base_timeframe else name,
    )
    return next((column for column in candidates if column in analysis.columns), None)


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
    *,
    base_timeframe: str,
) -> MarketObservation | None:
    columns = _columns_for(analysis, timeframe, _DIRECTION_COLUMNS[concept_id], base_timeframe=base_timeframe)
    available = [column for column in columns if column is not None and column in analysis.columns]
    if not available:
        return None

    mask = analysis[available].fillna(0).astype(float).ne(0).any(axis=1)
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


def _latest_active_event(
    analysis: pd.DataFrame,
    timeframe: str,
    *,
    event_concepts: tuple[str, ...],
    lifecycle_name: str,
    base_timeframe: str,
) -> MarketObservation | None:
    lifecycle_column = _lifecycle_column(analysis, timeframe, lifecycle_name, base_timeframe=base_timeframe)
    if lifecycle_column is None:
        return None

    latest = analysis.sort_values("timestamp").iloc[-1]
    if not _active(latest.get(lifecycle_column, 0)):
        return None

    candidates: list[tuple[object, MarketObservation]] = []
    for concept_id in event_concepts:
        columns = _columns_for(analysis, timeframe, _DIRECTION_COLUMNS[concept_id], base_timeframe=base_timeframe)
        available = [column for column in columns if column is not None and column in analysis.columns]
        if not available:
            continue
        mask = analysis[available].fillna(0).astype(float).ne(0).any(axis=1)
        if not mask.any():
            continue
        row = analysis.loc[mask].iloc[-1]
        item = _observation(
            concept_id,
            timeframe,
            row,
            columns,
            notes="currently active lifecycle state",
        )
        if item is not None:
            candidates.append((row["timestamp"], item))

    if not candidates:
        return None

    _, item = max(candidates, key=lambda value: value[0])
    return MarketObservation(
        concept_id=item.concept_id,
        timeframe=item.timeframe,
        state="observed",
        confidence=1.0,
        evidence=item.evidence + (f"{lifecycle_column}=1",),
        direction=item.direction,
        notes=item.notes,
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
        emitted_concepts: set[str] = set()

        fvg_active = _latest_active_event(
            analysis,
            timeframe,
            event_concepts=("imbalance.fvg",),
            lifecycle_name="fvg_active",
            base_timeframe=base_timeframe,
        )
        if fvg_active is not None:
            observations.append(fvg_active)
            emitted = True
            emitted_concepts.add("imbalance.fvg")

        ob_active = _latest_active_event(
            analysis,
            timeframe,
            event_concepts=("order_block.bullish", "order_block.bearish"),
            lifecycle_name="order_block_active",
            base_timeframe=base_timeframe,
        )
        if ob_active is not None:
            observations.append(ob_active)
            emitted = True
            emitted_concepts.update({"order_block.bullish", "order_block.bearish"})

        for concept_id in _DIRECTION_COLUMNS:
            if concept_id in emitted_concepts:
                continue
            item = _latest_event(analysis, concept_id, timeframe, base_timeframe=base_timeframe)
            if item is not None:
                observations.append(item)
                emitted = True

        if not emitted:
            missing.append(f"{timeframe}:no_active_supported_observation")

    directions = {item.direction for item in observations if item.direction in {"long", "short"}}
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

    directions = {item.direction for item in observations if item.direction in {"long", "short"}}
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
