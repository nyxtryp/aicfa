"""Immutable explainable trade-description contract for AICFA.

This module only projects already-produced setup geometry and evidence into a
website-facing structure. It never creates Entry/SL/TP, direction, confidence,
or reasons that are absent from the underlying setup candidate.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TYPE_CHECKING

from .data_requirements import TradingMode, normalize_trading_mode
from .setup_analysis import SetupCandidate, SetupLevel, _risk_reward_value

if TYPE_CHECKING:
    from .find_setup import FindSetupResult


@dataclass(frozen=True)
class TradeDescription:
    """One explainable live setup projected from an existing SetupCandidate."""

    asset: str
    market_type: str
    horizon: TradingMode
    direction: str
    scenario: str
    entry_zone: tuple[SetupLevel, ...]
    stop_loss: SetupLevel | None
    targets: tuple[SetupLevel, ...]
    rr: float | None
    structure_evidence: tuple[str, ...]
    liquidity_evidence: tuple[str, ...]
    zone_evidence: tuple[str, ...]
    zone_locations: tuple[str, ...]
    reaction_evidence: tuple[str, ...]
    volume_evidence: tuple[str, ...]
    entry_conditions: tuple[str, ...]
    invalidation: tuple[str, ...]
    rationale: tuple[str, ...]
    source_timeframes: tuple[str, ...]
    confirmation_timeframes: tuple[str, ...]
    timestamp: object
    freshness_ms: int | None
    lifecycle_status: str = "new"

    @property
    def entry(self) -> tuple[SetupLevel, ...]:
        """Website-friendly alias preserving the complete entry zone."""
        return self.entry_zone

    @property
    def tp1(self) -> SetupLevel | None:
        return self.targets[0] if self.targets else None

    @property
    def tp2(self) -> SetupLevel | None:
        return self.targets[1] if len(self.targets) > 1 else None


def _latest_timestamp(result: FindSetupResult) -> object:
    frame = result.analysis
    if frame is None or frame.empty or "timestamp" not in frame.columns:
        return None
    return frame["timestamp"].iloc[-1]


def _concepts(candidate: SetupCandidate, prefix: str) -> tuple[str, ...]:
    return tuple(
        concept for concept in candidate.supporting_concepts
        if concept.startswith(prefix)
    )


def _volume_evidence(candidate: SetupCandidate) -> tuple[str, ...]:
    return tuple(
        concept for concept in candidate.supporting_concepts
        if concept.startswith("volume")
    )


def _structure_evidence(candidate: SetupCandidate) -> tuple[str, ...]:
    return tuple(
        concept for concept in candidate.supporting_concepts
        if concept.startswith("market_structure.")
        or concept == "displacement"
    )


def _liquidity_evidence(candidate: SetupCandidate) -> tuple[str, ...]:
    return tuple(
        concept for concept in candidate.supporting_concepts
        if concept.startswith("liquidity.")
    )


def _reaction_evidence(candidate: SetupCandidate) -> tuple[str, ...]:
    return tuple(
        concept for concept in candidate.supporting_concepts
        if concept == "price_action.rejection"
        or "reaction" in concept
    )


def build_trade_description(
    result: FindSetupResult,
    candidate: SetupCandidate,
    *,
    now_ms: int | None = None,
    lifecycle_status: str = "new",
) -> TradeDescription:
    """Project one existing candidate into the explainable display contract.

    Missing geometry remains missing. In particular, an entry zone is not
    collapsed to a fabricated midpoint and absent SL/TP levels stay None.
    """
    if candidate.direction not in {"long", "short"}:
        raise ValueError("trade description requires an explicit LONG or SHORT direction")
    if lifecycle_status not in {"new", "active", "invalidated", "completed", "expired"}:
        raise ValueError("unsupported lifecycle status")

    timestamp = _latest_timestamp(result)
    freshness_ms = None
    if now_ms is not None and timestamp is not None:
        try:
            timestamp_ms = int(timestamp.timestamp() * 1000)
        except AttributeError:
            timestamp_ms = int(timestamp)
        freshness_ms = max(0, int(now_ms) - timestamp_ms)

    return TradeDescription(
        asset=result.symbol,
        market_type=result.request.market_type,
        horizon=normalize_trading_mode(result.mode),
        direction=candidate.direction,
        scenario=candidate.scenario,
        entry_zone=candidate.entry_zone,
        stop_loss=candidate.invalidation_level,
        targets=candidate.target_levels,
        rr=_risk_reward_value(
            candidate.direction,
            candidate.entry_zone,
            candidate.invalidation_level,
            candidate.target_levels,
        ),
        structure_evidence=_structure_evidence(candidate),
        liquidity_evidence=_liquidity_evidence(candidate),
        zone_evidence=candidate.zone_concepts,
        zone_locations=candidate.zone_locations,
        reaction_evidence=_reaction_evidence(candidate),
        volume_evidence=_volume_evidence(candidate),
        entry_conditions=candidate.entry_condition,
        invalidation=candidate.invalidation,
        rationale=candidate.rationale,
        source_timeframes=candidate.source_timeframes,
        confirmation_timeframes=candidate.confirmation_timeframes,
        timestamp=timestamp,
        freshness_ms=freshness_ms,
        lifecycle_status=lifecycle_status,
    )


def build_trade_descriptions(
    result: FindSetupResult,
    *,
    now_ms: int | None = None,
    lifecycle_status: str = "new",
) -> tuple[TradeDescription, ...]:
    """Project every current candidate without ranking or dropping candidates."""
    return tuple(
        build_trade_description(
            result,
            candidate,
            now_ms=now_ms,
            lifecycle_status=lifecycle_status,
        )
        for candidate in result.setup_assessment.candidates
    )
