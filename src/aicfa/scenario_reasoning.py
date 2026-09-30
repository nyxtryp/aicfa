from dataclasses import dataclass

from aicfa.evidence_reasoning import EvidenceDecision, EvidenceAssessment
from aicfa.market_evidence import MarketObservation
from aicfa.visual_evidence import VisualObservation


@dataclass(frozen=True)
class ScenarioHypothesis:
    """A supported market scenario hypothesis, not a trade signal."""

    scenario: str
    supporting_concepts: tuple[str, ...]
    confirmations: tuple[str, ...]
    invalidations: tuple[str, ...]
    rationale: tuple[str, ...]


@dataclass(frozen=True)
class ScenarioAssessment:
    """Scenario interpretation preserving multiple plausible hypotheses."""

    decision: EvidenceDecision
    hypotheses: tuple[ScenarioHypothesis, ...]
    unsupported_scenarios: tuple[str, ...]
    reasons: tuple[str, ...]


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


_SCENARIO_RULES = {
    "continuation": {
        "support": {"market_structure.bos", "displacement", "order_block.bullish", "order_block.bearish"},
        "confirm": ("follow-through displacement", "structure remains intact"),
        "invalidate": ("decisive structural failure", "acceptance against the active leg"),
    },
    "reversal": {
        "support": {"market_structure.choch", "liquidity.sweep", "price_action.rejection", "wyckoff.spring"},
        "confirm": ("structural follow-through", "rejection of the prior state"),
        "invalidate": ("acceptance in the prior direction", "failed structural transition"),
    },
    "range": {
        "support": {"market_structure.range", "wyckoff.trading_range", "price_action.compression"},
        "confirm": ("repeated reactions at range boundaries", "lack of sustained expansion"),
        "invalidate": ("sustained acceptance outside the range", "structural expansion"),
    },
    "breakout_failure": {
        "support": {"market_structure.bos", "liquidity.sweep", "price_action.rejection"},
        "confirm": ("failed acceptance beyond the level", "return through the broken area"),
        "invalidate": ("sustained acceptance beyond the breakout level",),
    },
}


def _observed_concepts(observations: tuple) -> set[str]:
    return {
        item.concept_id
        for item in observations
        if item.state == "observed" and item.confidence >= 0.5
    }


def assess_scenarios(
    assessment: EvidenceAssessment,
    *,
    observations: tuple[VisualObservation, ...] | None = None,
) -> ScenarioAssessment:
    """Build plausible scenario hypotheses from sufficiently supported evidence.

    The engine deliberately preserves multiple scenarios. It does not choose
    a direction, create an entry, or turn one concept into a trade signal.
    """

    if assessment.decision is not EvidenceDecision.PROCEED:
        return ScenarioAssessment(
            decision=assessment.decision,
            hypotheses=(),
            unsupported_scenarios=tuple(_SCENARIO_RULES),
            reasons=assessment.reasons or ("evidence is not sufficient for scenario reasoning",),
        )

    concepts = _observed_concepts(observations or assessment.observations)
    hypotheses: list[ScenarioHypothesis] = []
    unsupported: list[str] = []

    for name, rule in _SCENARIO_RULES.items():
        matched = tuple(sorted(concepts & rule["support"]))
        if not matched:
            unsupported.append(name)
            continue

        rationale = tuple(
            f"{concept} is supported by the current evidence"
            for concept in matched
        )
        hypotheses.append(
            ScenarioHypothesis(
                scenario=name,
                supporting_concepts=matched,
                confirmations=rule["confirm"],
                invalidations=rule["invalidate"],
                rationale=rationale,
            )
        )

    reasons = []
    if hypotheses:
        reasons.append("one or more scenario hypotheses are supported by current evidence")
    else:
        reasons.append("no defined scenario has sufficient supporting concepts")

    return ScenarioAssessment(
        decision=EvidenceDecision.PROCEED if hypotheses else EvidenceDecision.NEED_MORE_EVIDENCE,
        hypotheses=tuple(hypotheses),
        unsupported_scenarios=tuple(unsupported),
        reasons=tuple(reasons),
    )
