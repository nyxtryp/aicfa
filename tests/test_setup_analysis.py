import pandas as pd
from aicfa.evidence_reasoning import EvidenceDecision, assess_visual_evidence
from aicfa.scenario_reasoning import assess_scenarios
from aicfa.setup_analysis import SetupDecision, analyze_setups
from aicfa.visual_evidence import VisualEvidence, VisualEvidenceSet, observation


def _obs(concept_id, confidence=0.9, price_location=None):
    return observation(
        concept_id,
        state="observed",
        confidence=confidence,
        evidence=("visible chart evidence",),
        price_location=price_location,
    )


def _pipeline(*observations, conflicts=()):
    evidence = VisualEvidenceSet(
        items=(
            VisualEvidence(
                asset="BTC/USDT",
                timeframe="1h",
                observations=tuple(observations),
                conflicts=tuple(conflicts),
            ),
        )
    )
    assessment = assess_visual_evidence(evidence)
    scenarios = assess_scenarios(assessment)
    setups = analyze_setups(assessment, scenarios)
    return assessment, scenarios, setups


def test_continuation_setup_contains_zone_entry_invalidation_and_targets():
    evidence, scenarios, result = _pipeline(
        _obs("market_structure.bos"),
        _obs("displacement"),
        _obs("imbalance.fvg", price_location="visible FVG zone"),
    )
    assert evidence.decision is EvidenceDecision.PROCEED
    assert scenarios.decision is EvidenceDecision.PROCEED
    assert result.decision is SetupDecision.READY
    candidate = next(item for item in result.candidates if item.scenario == "continuation")
    assert "imbalance.fvg" in candidate.zone_concepts
    assert candidate.zone_locations == ("imbalance.fvg: visible FVG zone",)
    assert candidate.entry_condition
    assert candidate.invalidation
    assert candidate.targets


def test_setup_does_not_fabricate_numeric_levels():
    _, _, result = _pipeline(
        _obs("market_structure.bos"),
        _obs("displacement"),
        _obs("imbalance.fvg"),
    )
    candidate = next(item for item in result.candidates if item.scenario == "continuation")
    assert candidate.zone_locations == ()
    assert all("price" not in item.lower() for item in candidate.targets)


def test_insufficient_scenario_support_requires_more_evidence():
    _, _, result = _pipeline(
        _obs("market_structure.bos"),
        _obs("imbalance.fvg"),
    )
    assert result.decision is SetupDecision.NEED_MORE_EVIDENCE
    assert result.candidates == ()


def test_missing_contextual_zone_requires_more_evidence():
    _, _, result = _pipeline(
        _obs("market_structure.bos"),
        _obs("displacement"),
    )
    assert result.decision is SetupDecision.NEED_MORE_EVIDENCE
    assert any("contextual setup zone" in item for item in result.missing_context)


def test_contradictory_evidence_forces_wait():
    evidence, scenarios, result = _pipeline(
        _obs("market_structure.bos"),
        _obs("displacement"),
        _obs("imbalance.fvg"),
        conflicts=("higher timeframe structure conflicts with continuation",),
    )
    assert evidence.decision is EvidenceDecision.WAIT
    assert scenarios.decision is EvidenceDecision.WAIT
    assert result.decision is SetupDecision.WAIT
    assert result.candidates == ()


def test_multiple_plausible_setups_are_preserved():
    _, scenarios, result = _pipeline(
        _obs("market_structure.bos"),
        _obs("displacement"),
        _obs("liquidity.sweep"),
        _obs("price_action.rejection"),
        _obs("imbalance.fvg"),
    )
    names = {item.scenario for item in scenarios.hypotheses}
    candidate_names = {item.scenario for item in result.candidates}
    assert "continuation" in names
    assert "reversal" in names
    assert "breakout_failure" in names
    assert {"continuation", "reversal", "breakout_failure"} <= candidate_names


def test_setup_has_no_execution_fields():
    _, _, result = _pipeline(
        _obs("market_structure.bos"),
        _obs("displacement"),
        _obs("imbalance.fvg"),
    )
    assert not hasattr(result, "order")
    assert not hasattr(result, "quantity")
    assert not hasattr(result, "leverage")




def test_lower_refinement_conflict_cannot_become_a_new_direction():
    from aicfa.setup_analysis import build_multi_timeframe_context, _resolve_direction

    def frame(direction):
        return pd.DataFrame({
            "timestamp": [1],
            "smc_structure_direction": [direction],
        })

    analyses = {
        "1d": frame(1),
        "4h": frame(1),
        "1h": frame(-1),
        "15m": frame(-1),
    }
    context = build_multi_timeframe_context(
        (),
        analyses,
        timeframes=("1d", "4h", "1h", "15m"),
        mode="intraday",
    )
    direction, conflict = _resolve_direction(context)
    assert direction is None
    assert conflict == "lower confirmation conflicts with higher-timeframe structure"
