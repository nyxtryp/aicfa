from aicfa.evidence_reasoning import EvidenceDecision, assess_visual_evidence
from aicfa.scenario_reasoning import assess_scenarios
from aicfa.visual_evidence import VisualEvidence, VisualEvidenceSet, observation


def _obs(concept_id, confidence=0.9):
    return observation(
        concept_id,
        state="observed",
        confidence=confidence,
        evidence=("visible chart evidence",),
    )


def _assessment(*observations, conflicts=()):
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
    return assess_visual_evidence(evidence)


def test_continuation_hypothesis_uses_structure_and_displacement():
    assessment = _assessment(
        _obs("market_structure.bos"),
        _obs("displacement"),
    )
    result = assess_scenarios(assessment)
    names = {item.scenario for item in result.hypotheses}
    assert "continuation" in names
    hypothesis = next(item for item in result.hypotheses if item.scenario == "continuation")
    assert "market_structure.bos" in hypothesis.supporting_concepts
    assert hypothesis.confirmations
    assert hypothesis.invalidations


def test_reversal_hypothesis_preserves_sweep_and_choch():
    assessment = _assessment(
        _obs("liquidity.sweep"),
        _obs("market_structure.choch"),
    )
    result = assess_scenarios(assessment)
    names = {item.scenario for item in result.hypotheses}
    assert "reversal" in names


def test_multiple_plausible_scenarios_are_preserved():
    assessment = _assessment(
        _obs("market_structure.bos"),
        _obs("liquidity.sweep"),
        _obs("price_action.rejection"),
    )
    result = assess_scenarios(assessment)
    names = {item.scenario for item in result.hypotheses}
    assert "continuation" in names
    assert "reversal" in names
    assert "breakout_failure" in names


def test_insufficient_evidence_does_not_create_scenarios():
    assessment = _assessment(_obs("market_structure.bos", confidence=0.4))
    result = assess_scenarios(assessment)
    assert assessment.decision is EvidenceDecision.NEED_MORE_EVIDENCE
    assert result.hypotheses == ()
    assert result.decision is EvidenceDecision.NEED_MORE_EVIDENCE


def test_contradiction_propagates_to_scenario_wait():
    assessment = _assessment(
        _obs("market_structure.bos"),
        conflicts=("higher timeframe structure conflicts with local continuation",),
    )
    result = assess_scenarios(assessment)
    assert assessment.decision is EvidenceDecision.WAIT
    assert result.decision is EvidenceDecision.WAIT
    assert result.hypotheses == ()


def test_scenario_engine_has_no_trade_execution_fields():
    assessment = _assessment(_obs("market_structure.bos"))
    result = assess_scenarios(assessment)
    assert not hasattr(result, "entry")
    assert not hasattr(result, "stop")
    assert not hasattr(result, "direction")
