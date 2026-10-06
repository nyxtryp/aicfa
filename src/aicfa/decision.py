"""Evidence-gated final decision layer.

This layer converts a READY setup into an analytical action only when an
explicit directional observation is present and consistent. It never infers
direction from an unlabeled concept and never executes an order.
"""

from dataclasses import dataclass
from enum import Enum

from aicfa.setup_analysis import SetupAssessment, SetupCandidate, SetupDecision
from aicfa.market_evidence import MarketObservation
from aicfa.visual_evidence import VisualObservation


class DecisionAction(str, Enum):
    LONG = "long"
    SHORT = "short"
    WAIT = "wait"
    NO_TRADE = "no_trade"


@dataclass(frozen=True)
class DecisionCandidate:
    """One final analytical decision tied to a setup and explicit direction."""

    scenario: str
    action: DecisionAction
    supporting_concepts: tuple[str, ...]
    entry_condition: tuple[str, ...]
    invalidation: tuple[str, ...]
    targets: tuple[str, ...]
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class DecisionAssessment:
    """Final decision gate preserving ambiguity and insufficient evidence."""

    action: DecisionAction
    candidates: tuple[DecisionCandidate, ...]
    missing_context: tuple[str, ...]
    conflicts: tuple[str, ...]
    reasons: tuple[str, ...]


def _directional_observations(
    observations: tuple,
) -> tuple[VisualObservation, ...]:
    return tuple(
        item
        for item in observations
        if item.state == "observed"
        and item.confidence >= 0.5
        and item.direction in {"long", "short"}
    )


def decide(
    setup_assessment: SetupAssessment,
    *,
    observations: tuple[VisualObservation, ...] = (),
    current_price: float | None = None,
) -> DecisionAssessment:
    """Gate setup candidates into LONG/SHORT/WAIT/NO_TRADE.

    Direction is never guessed from a concept name. It must come from an
    explicit directional visual observation. Conflicting directional evidence
    produces WAIT. A READY setup without directional evidence remains WAIT.
    """

    if setup_assessment.decision is SetupDecision.WAIT:
        return DecisionAssessment(
            action=DecisionAction.WAIT,
            candidates=(),
            missing_context=setup_assessment.missing_context,
            conflicts=setup_assessment.conflicts,
            reasons=setup_assessment.reasons or ("material evidence conflict requires WAIT",),
        )

    if setup_assessment.decision is not SetupDecision.READY:
        return DecisionAssessment(
            action=DecisionAction.WAIT,
            candidates=(),
            missing_context=setup_assessment.missing_context,
            conflicts=setup_assessment.conflicts,
            reasons=setup_assessment.reasons or ("setup evidence is not ready for a final decision",),
        )

    directional = _directional_observations(observations)
    if not directional:
        return DecisionAssessment(
            action=DecisionAction.WAIT,
            candidates=(),
            missing_context=setup_assessment.missing_context + (
                "explicit directional evidence is required before LONG or SHORT",
            ),
            conflicts=setup_assessment.conflicts,
            reasons=("setup is structurally ready but direction is not established by evidence",),
        )

    candidate_directions = {candidate.direction for candidate in setup_assessment.candidates}
    if candidate_directions == {None}:
        sides = {item.direction for item in directional}
        if len(sides) > 1:
            return DecisionAssessment(
                action=DecisionAction.WAIT,
                candidates=(),
                missing_context=setup_assessment.missing_context,
                conflicts=setup_assessment.conflicts + ("directional evidence conflicts between LONG and SHORT",),
                reasons=("directional evidence is contradictory",),
            )
        side = next(iter(sides))
    elif len(candidate_directions) == 1 and None not in candidate_directions:
        side = next(iter(candidate_directions))
    else:
        return DecisionAssessment(
            action=DecisionAction.WAIT,
            candidates=(),
            missing_context=setup_assessment.missing_context,
            conflicts=setup_assessment.conflicts + ("setup candidates do not share one resolved MTF direction",),
            reasons=("setup direction is not uniquely resolved",),
        )

    matching = tuple(item for item in directional if item.direction == side)
    if not matching:
        return DecisionAssessment(
            action=DecisionAction.WAIT,
            candidates=(),
            missing_context=setup_assessment.missing_context,
            conflicts=setup_assessment.conflicts + (
                f"no explicit directional evidence supports resolved {side} setup direction",
            ),
            reasons=("resolved MTF setup direction lacks matching explicit evidence",),
        )

    # A structural candidate is not a trade decision. Final LONG/SHORT is
    # blocked until the selected zone has actually reacted and volume provides
    # confirming evidence. This prevents BOS/OB/FVG alone from becoming a live
    # trade signal.
    observed_concepts = {
        item.concept_id
        for item in observations
        if item.state == "observed" and item.confidence >= 0.5
    }
    required_confirmation = ("price_action.rejection", "volume.evidence")
    missing_confirmation = tuple(
        concept for concept in required_confirmation
        if concept not in observed_concepts
    )
    if missing_confirmation:
        labels = {
            "price_action.rejection": "confirmed zone reaction",
            "volume.evidence": "confirming volume evidence",
        }
        return DecisionAssessment(
            action=DecisionAction.WAIT,
            candidates=(),
            missing_context=setup_assessment.missing_context + tuple(
                labels[concept] for concept in missing_confirmation
            ),
            conflicts=setup_assessment.conflicts,
            reasons=(
                "structural setup exists, but final entry confirmation is incomplete: "
                + ", ".join(labels[concept] for concept in missing_confirmation),
            ),
        )

    # A confirmed reaction is not an invitation to chase price after it has
    # already left the actionable zone. Final LONG/SHORT remains actionable
    # only while price is inside the zone or close enough for a retest.
    if current_price is not None:
        for candidate in setup_assessment.candidates:
            if len(candidate.entry_zone) < 2:
                continue
            entry_low = min(level.value for level in candidate.entry_zone)
            entry_high = max(level.value for level in candidate.entry_zone)
            first_target = candidate.target_levels[0].value if candidate.target_levels else None
            tolerance = abs(float(current_price)) * 0.0075
            if side == "long":
                if first_target is not None and current_price >= first_target:
                    return DecisionAssessment(
                        action=DecisionAction.WAIT, candidates=(),
                        missing_context=setup_assessment.missing_context + ("the first long target has already been reached",),
                        conflicts=setup_assessment.conflicts,
                        reasons=("confirmed setup is no longer actionable at the current price; target already reached",),
                    )
                if current_price > entry_high + tolerance:
                    return DecisionAssessment(
                        action=DecisionAction.WAIT, candidates=(),
                        missing_context=setup_assessment.missing_context + ("price is above the actionable long entry zone",),
                        conflicts=setup_assessment.conflicts,
                        reasons=("price has already left the long entry zone; wait for a retest instead of chasing",),
                    )
                if current_price < entry_low - tolerance:
                    return DecisionAssessment(
                        action=DecisionAction.WAIT, candidates=(),
                        missing_context=setup_assessment.missing_context + ("price is below the actionable long entry zone",),
                        conflicts=setup_assessment.conflicts,
                        reasons=("current price is outside the long entry geometry",),
                    )
            else:
                if first_target is not None and current_price <= first_target:
                    return DecisionAssessment(
                        action=DecisionAction.WAIT, candidates=(),
                        missing_context=setup_assessment.missing_context + ("the first short target has already been reached",),
                        conflicts=setup_assessment.conflicts,
                        reasons=("confirmed setup is no longer actionable at the current price; target already reached",),
                    )
                if current_price < entry_low - tolerance:
                    return DecisionAssessment(
                        action=DecisionAction.WAIT, candidates=(),
                        missing_context=setup_assessment.missing_context + ("price is below the actionable short entry zone",),
                        conflicts=setup_assessment.conflicts,
                        reasons=("price has already left the short entry zone; wait for a retest instead of chasing",),
                    )
                if current_price > entry_high + tolerance:
                    return DecisionAssessment(
                        action=DecisionAction.WAIT, candidates=(),
                        missing_context=setup_assessment.missing_context + ("price is above the actionable short entry zone",),
                        conflicts=setup_assessment.conflicts,
                        reasons=("current price is outside the short entry geometry",),
                    )
    action = DecisionAction.LONG if side == "long" else DecisionAction.SHORT
    candidates = tuple(
        DecisionCandidate(
            scenario=candidate.scenario,
            action=action,
            supporting_concepts=candidate.supporting_concepts,
            entry_condition=candidate.entry_condition,
            invalidation=candidate.invalidation,
            targets=candidate.targets,
            rationale=candidate.rationale + (
                f"direction explicitly observed as {side}",
            ),
        )
        for candidate in setup_assessment.candidates
    )

    if not candidates:
        return DecisionAssessment(
            action=DecisionAction.NO_TRADE,
            candidates=(),
            missing_context=setup_assessment.missing_context,
            conflicts=setup_assessment.conflicts,
            reasons=("no actionable setup candidate remains",),
        )

    return DecisionAssessment(
        action=action,
        candidates=candidates,
        missing_context=setup_assessment.missing_context,
        conflicts=setup_assessment.conflicts,
        reasons=("direction and setup structure are both supported by current evidence",),
    )
