from dataclasses import dataclass
from enum import Enum

from aicfa.knowledge_base import get_knowledge
from aicfa.market_evidence import MarketEvidence, MarketObservation
from aicfa.visual_evidence import VisualEvidenceSet, VisualObservation


class EvidenceDecision(str, Enum):
    PROCEED = "proceed"
    NEED_MORE_EVIDENCE = "need_more_evidence"
    WAIT = "wait"


@dataclass(frozen=True)
class EvidenceAssessment:
    """Deterministic evidence assessment before scenario/setup reasoning."""

    decision: EvidenceDecision
    observations: tuple
    supported_concepts: tuple[str, ...]
    possible_concepts: tuple[str, ...]
    missing_context: tuple[str, ...]
    conflicts: tuple[str, ...]
    reasons: tuple[str, ...]


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _assess_observations(
    observations: tuple,
    *,
    available_timeframes: tuple[str, ...],
    missing_context: tuple[str, ...] = (),
    conflicts: tuple[str, ...] = (),
    required_concepts: tuple[str, ...] = (),
    required_timeframes: tuple[str, ...] = (),
) -> EvidenceAssessment:
    supported = [
        item.concept_id
        for item in observations
        if item.state == "observed" and item.confidence >= 0.5
    ]
    possible = [
        item.concept_id
        for item in observations
        if item.state == "possible" or (item.state == "observed" and item.confidence < 0.5)
    ]

    missing = list(missing_context)
    missing.extend(
        f"required timeframe: {timeframe}"
        for timeframe in required_timeframes
        if timeframe not in set(available_timeframes)
    )

    observed_concepts = set(supported)
    missing.extend(
        f"required concept: {concept_id}"
        for concept_id in required_concepts
        if concept_id not in observed_concepts
    )

    reasons: list[str] = []
    if possible:
        reasons.append("some evidence interpretations remain uncertain")
    if missing:
        reasons.append("required context is missing")
    if conflicts:
        reasons.append("material evidence is contradictory")

    if conflicts:
        decision = EvidenceDecision.WAIT
    elif missing or possible:
        decision = EvidenceDecision.NEED_MORE_EVIDENCE
    else:
        decision = EvidenceDecision.PROCEED

    return EvidenceAssessment(
        decision=decision,
        observations=observations,
        supported_concepts=_unique(supported),
        possible_concepts=_unique(possible),
        missing_context=_unique(missing),
        conflicts=_unique(conflicts),
        reasons=_unique(reasons),
    )


def assess_visual_evidence(
    evidence: VisualEvidenceSet,
    *,
    required_concepts: tuple[str, ...] = (),
    required_timeframes: tuple[str, ...] = (),
) -> EvidenceAssessment:
    """Assess screenshot evidence without predicting direction."""

    observations = tuple(
        observation
        for item in evidence.items
        for observation in item.observations
    )
    return _assess_observations(
        observations,
        available_timeframes=evidence.timeframes,
        missing_context=tuple(
            context
            for item in evidence.items
            for context in item.missing_context
        ),
        conflicts=tuple(
            conflict
            for item in evidence.items
            for conflict in item.conflicts
        ),
        required_concepts=required_concepts,
        required_timeframes=required_timeframes,
    )


def assess_market_evidence(
    evidence: MarketEvidence,
    *,
    required_concepts: tuple[str, ...] = (),
    required_timeframes: tuple[str, ...] = (),
) -> EvidenceAssessment:
    """Assess deterministic market evidence without treating it as visual data."""

    return _assess_observations(
        evidence.observations,
        available_timeframes=evidence.timeframes,
        missing_context=evidence.missing_context,
        conflicts=evidence.conflicts,
        required_concepts=required_concepts,
        required_timeframes=required_timeframes,
    )


def related_concepts(concept_id: str) -> tuple[str, ...]:
    """Return Knowledge Base relationships for one observed concept."""

    return get_knowledge(concept_id).relationships


def explain_observation(concept_id: str) -> tuple[str, tuple[str, ...]]:
    """Expose the definition and causal links used by downstream reasoning."""

    entry = get_knowledge(concept_id)
    return entry.definition, entry.relationships
