"""Structured setup analysis over evidence and scenario hypotheses.

This layer turns sufficiently supported scenario hypotheses into explicit,
conditional setup candidates. It never fabricates numeric prices and never
places or executes orders.
"""

from dataclasses import dataclass
from enum import Enum

from aicfa.evidence_reasoning import EvidenceDecision, EvidenceAssessment
from aicfa.knowledge_base import get_knowledge
from aicfa.scenario_reasoning import ScenarioAssessment, ScenarioHypothesis
from aicfa.market_evidence import MarketObservation
from aicfa.visual_evidence import VisualObservation


class SetupDecision(str, Enum):
    READY = "ready"
    NEED_MORE_EVIDENCE = "need_more_evidence"
    WAIT = "wait"


@dataclass(frozen=True)
class SetupCandidate:
    """A conditional setup candidate grounded in observed evidence."""

    scenario: str
    supporting_concepts: tuple[str, ...]
    zone_concepts: tuple[str, ...]
    zone_locations: tuple[str, ...]
    entry_condition: tuple[str, ...]
    invalidation: tuple[str, ...]
    targets: tuple[str, ...]
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class SetupAssessment:
    """Setup analysis result preserving uncertainty and multiple candidates."""

    decision: SetupDecision
    candidates: tuple[SetupCandidate, ...]
    missing_context: tuple[str, ...]
    conflicts: tuple[str, ...]
    reasons: tuple[str, ...]


_ZONE_CONCEPTS = {
    "imbalance.fvg",
    "order_block.bullish",
    "order_block.bearish",
    "liquidity.sweep",
    "price_action.rejection",
    "premium_discount.dealing_range",
}

_MIN_SUPPORTING_CONCEPTS = 2


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _observed(observations: tuple) -> tuple[VisualObservation, ...]:
    return tuple(
        item
        for item in observations
        if item.state == "observed" and item.confidence >= 0.5
    )


def _zone_data(observations: tuple[VisualObservation, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    concepts: list[str] = []
    locations: list[str] = []
    for item in _observed(observations):
        if item.concept_id not in _ZONE_CONCEPTS:
            continue
        concepts.append(item.concept_id)
        if item.price_location:
            locations.append(f"{item.concept_id}: {item.price_location}")
    return _unique(concepts), _unique(locations)


def _knowledge_requirements(concepts: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    confirmations: list[str] = []
    invalidations: list[str] = []
    for concept in concepts:
        try:
            entry = get_knowledge(concept)
        except KeyError:
            continue
        confirmations.extend(entry.confirmations)
        invalidations.extend(entry.invalidations)
    return _unique(confirmations), _unique(invalidations)


def _targets(hypothesis: ScenarioHypothesis) -> tuple[str, ...]:
    if hypothesis.scenario == "range":
        return ("opposing visible range boundary or opposing liquidity, if present in evidence",)
    if hypothesis.scenario == "breakout_failure":
        return ("opposing visible liquidity or structural extreme",)
    if hypothesis.scenario == "reversal":
        return ("next visible opposing liquidity or structural extreme",)
    return ("next visible opposing liquidity or structural objective",)


def analyze_setups(
    evidence_assessment: EvidenceAssessment,
    scenario_assessment: ScenarioAssessment,
    *,
    observations: tuple[VisualObservation, ...] | None = None,
) -> SetupAssessment:
    """Build conditional setups without inventing unseen market information.

    A candidate is READY when evidence is contradiction-free, the scenario is
    supported by at least two observed concepts, and a contextual zone is
    visible. The entry remains conditional on explicit confirmation; numeric
    prices are included only when the visual evidence supplied them.
    """

    if evidence_assessment.decision is EvidenceDecision.WAIT:
        return SetupAssessment(
            decision=SetupDecision.WAIT,
            candidates=(),
            missing_context=evidence_assessment.missing_context,
            conflicts=evidence_assessment.conflicts,
            reasons=evidence_assessment.reasons or ("evidence contains material contradictions",),
        )

    if evidence_assessment.decision is not EvidenceDecision.PROCEED:
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=evidence_assessment.missing_context,
            conflicts=evidence_assessment.conflicts,
            reasons=evidence_assessment.reasons or ("evidence is not sufficient for setup analysis",),
        )

    if scenario_assessment.decision is EvidenceDecision.WAIT:
        return SetupAssessment(
            decision=SetupDecision.WAIT,
            candidates=(),
            missing_context=evidence_assessment.missing_context,
            conflicts=evidence_assessment.conflicts,
            reasons=scenario_assessment.reasons or ("scenario reasoning requires WAIT",),
        )

    if scenario_assessment.decision is not EvidenceDecision.PROCEED:
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=evidence_assessment.missing_context,
            conflicts=evidence_assessment.conflicts,
            reasons=scenario_assessment.reasons or ("no sufficiently supported scenario exists",),
        )

    evidence_observations = observations or evidence_assessment.observations
    zones, locations = _zone_data(evidence_observations)
    candidates: list[SetupCandidate] = []
    missing: list[str] = []

    for hypothesis in scenario_assessment.hypotheses:
        if len(hypothesis.supporting_concepts) < _MIN_SUPPORTING_CONCEPTS:
            missing.append(
                f"{hypothesis.scenario}: at least two independent supporting concepts are required"
            )
            continue
        if not zones:
            missing.append(
                f"{hypothesis.scenario}: no contextual setup zone is visible"
            )
            continue

        confirmations, invalidations = _knowledge_requirements(
            hypothesis.supporting_concepts
        )
        entry_conditions = _unique(
            list(hypothesis.confirmations) + list(confirmations)
        )
        invalidation_conditions = _unique(
            list(hypothesis.invalidations) + list(invalidations)
        )

        rationale = _unique(
            list(hypothesis.rationale)
            + [f"contextual zone observed: {concept}" for concept in zones]
        )

        candidates.append(
            SetupCandidate(
                scenario=hypothesis.scenario,
                supporting_concepts=hypothesis.supporting_concepts,
                zone_concepts=zones,
                zone_locations=locations,
                entry_condition=entry_conditions,
                invalidation=invalidation_conditions,
                targets=_targets(hypothesis),
                rationale=rationale,
            )
        )

    if not candidates:
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=_unique(missing),
            conflicts=evidence_assessment.conflicts,
            reasons=("setup conditions are not sufficiently specified",),
        )

    return SetupAssessment(
        decision=SetupDecision.READY,
        candidates=tuple(candidates),
        missing_context=_unique(missing),
        conflicts=evidence_assessment.conflicts,
        reasons=("one or more conditional setups are sufficiently specified by current evidence",),
    )
