from aicfa.decision import DecisionAction, decide
from aicfa.evidence_reasoning import assess_visual_evidence
from aicfa.scenario_reasoning import assess_scenarios
from aicfa.setup_analysis import SetupDecision, analyze_setups
from aicfa.visual_evidence import VisualEvidence, VisualEvidenceSet, observation


def _obs(concept_id, *, direction=None):
    return observation(
        concept_id,
        state="observed",
        confidence=0.9,
        evidence=("visible chart evidence",),
        direction=direction,
    )


def _setup(*observations):
    evidence = VisualEvidenceSet(
        items=(
            VisualEvidence(
                asset="BTC/USDT",
                timeframe="1h",
                observations=tuple(observations),
            ),
        )
    )
    assessment = assess_visual_evidence(evidence)
    scenarios = assess_scenarios(assessment)
    setup = analyze_setups(assessment, scenarios, observations=assessment.observations)
    return assessment, setup


def test_ready_setup_without_direction_waits():
    _, setup = _setup(
        _obs("market_structure.bos"),
        _obs("displacement"),
        _obs("imbalance.fvg"),
    )
    assert setup.decision is SetupDecision.READY

    result = decide(setup, observations=())
    assert result.action is DecisionAction.WAIT
    assert result.candidates == ()
    assert any("directional evidence" in item for item in result.missing_context)


def test_explicit_long_direction_produces_long_decision():
    _, setup = _setup(
        _obs("market_structure.bos", direction="long"),
        _obs("displacement", direction="long"),
        _obs("imbalance.fvg", direction="long"),
    )
    result = decide(setup, observations=(
        _obs("market_structure.bos", direction="long"),
        _obs("displacement", direction="long"),
    ))
    assert result.action is DecisionAction.LONG
    assert result.candidates
    assert all(item.action is DecisionAction.LONG for item in result.candidates)


def test_explicit_short_direction_produces_short_decision():
    _, setup = _setup(
        _obs("market_structure.bos", direction="short"),
        _obs("displacement", direction="short"),
        _obs("imbalance.fvg", direction="short"),
    )
    result = decide(setup, observations=(
        _obs("market_structure.bos", direction="short"),
        _obs("displacement", direction="short"),
    ))
    assert result.action is DecisionAction.SHORT
    assert result.candidates
    assert all(item.action is DecisionAction.SHORT for item in result.candidates)


def test_conflicting_directional_evidence_waits():
    _, setup = _setup(
        _obs("market_structure.bos", direction="long"),
        _obs("displacement", direction="short"),
        _obs("imbalance.fvg"),
    )
    result = decide(setup, observations=(
        _obs("market_structure.bos", direction="long"),
        _obs("displacement", direction="short"),
    ))
    assert result.action is DecisionAction.WAIT
    assert result.candidates == ()
    assert result.conflicts


def test_concept_names_do_not_imply_direction():
    _, setup = _setup(
        _obs("market_structure.bos"),
        _obs("displacement"),
        _obs("imbalance.fvg"),
    )
    result = decide(setup, observations=(
        _obs("market_structure.bos"),
        _obs("displacement"),
        _obs("imbalance.fvg"),
    ))
    assert result.action is DecisionAction.WAIT
    assert result.candidates == ()


def test_decision_has_no_execution_fields():
    _, setup = _setup(
        _obs("market_structure.bos", direction="long"),
        _obs("displacement", direction="long"),
        _obs("imbalance.fvg", direction="long"),
    )
    result = decide(setup, observations=(
        _obs("market_structure.bos", direction="long"),
        _obs("displacement", direction="long"),
    ))
    assert not hasattr(result, "order")
    assert not hasattr(result, "quantity")
    assert not hasattr(result, "leverage")


def test_mtf_resolved_direction_ignores_opposite_lower_timeframe_evidence():
    from tests.test_setup_engine_mtf import _frames, _pipeline

    setup = _pipeline(_frames(structure_4h=1, structure_15m=1, structure_1h=1))
    result = decide(
        setup,
        observations=(
            _obs("market_structure.bos", direction="long"),
            _obs("displacement", direction="short"),
        ),
    )

    assert result.action is DecisionAction.LONG
    assert result.candidates
