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
        "1h": frame(1),
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


def test_broader_context_conflict_blocks_continuation_direction():
    from aicfa.setup_analysis import build_multi_timeframe_context, _resolve_direction

    def frame(direction):
        return pd.DataFrame({"timestamp": [1], "smc_structure_direction": [direction]})

    analyses = {
        "1w": frame(-1),
        "1d": frame(1),
        "4h": frame(1),
    }
    context = build_multi_timeframe_context(
        (),
        analyses,
        timeframes=("1w", "1d", "4h"),
        mode="position",
    )
    direction, conflict = _resolve_direction(
        context,
        scenario="continuation",
        supporting=("market_structure.bos", "displacement"),
    )
    assert direction is None
    assert conflict == "broader higher-timeframe structure conflicts with setup direction"


def test_reversal_can_change_direction_only_after_choch_and_sweep():
    from aicfa.setup_analysis import build_multi_timeframe_context, _resolve_direction

    def frame(direction):
        return pd.DataFrame({"timestamp": [1], "smc_structure_direction": [direction]})

    analyses = {
        "1w": frame(-1),
        "1d": frame(1),
        "4h": frame(1),
    }
    context = build_multi_timeframe_context(
        (),
        analyses,
        timeframes=("1w", "1d", "4h"),
        mode="position",
    )
    direction, conflict = _resolve_direction(
        context,
        scenario="reversal",
        supporting=("market_structure.choch", "liquidity.sweep"),
    )
    assert direction == "long"
    assert conflict is None


def test_continuation_rejects_opposite_bos_event_on_higher_structure():
    from aicfa.market_evidence import MarketObservation
    from aicfa.setup_analysis import build_multi_timeframe_context, _resolve_direction, _event_direction_conflict

    def frame(direction):
        return pd.DataFrame({"timestamp": [1], "smc_structure_direction": [direction]})

    analyses = {
        "4h": frame(1),
        "1h": frame(1),
        "15m": frame(1),
        "5m": frame(1),
    }
    observations = (
        MarketObservation(
            concept_id="market_structure.bos",
            timeframe="4h",
            state="observed",
            confidence=1.0,
            evidence=("bos_down=1",),
            direction="short",
        ),
    )
    context = build_multi_timeframe_context(
        observations,
        analyses,
        timeframes=("4h", "1h", "15m", "5m"),
        mode="intraday",
    )
    direction, conflict = _resolve_direction(
        context,
        scenario="continuation",
        supporting=("market_structure.bos", "displacement"),
    )
    assert direction == "long"
    assert conflict is None
    assert _event_direction_conflict(
        context,
        scenario="continuation",
        direction="long",
        observations=observations,
    ) is not None


def test_setup_rationale_uses_structural_state_not_event_direction():
    from aicfa.market_evidence import MarketObservation
    from aicfa.evidence_reasoning import EvidenceAssessment, EvidenceDecision
    from aicfa.scenario_reasoning import ScenarioAssessment, ScenarioHypothesis
    from aicfa.setup_analysis import analyze_setups

    def frame(direction):
        return pd.DataFrame({
            "timestamp": [1],
            "smc_structure_direction": [direction],
            "order_block_bullish_low": [90.0],
            "order_block_bullish_high": [95.0],
            "previous_low": [89.0],
            "previous_high": [110.0],
            "active_buy_liquidity_price": [115.0],
        })

    observations = (
        MarketObservation("market_structure.bos", "1h", "observed", 1.0, ("bos_up=1",), direction="long"),
        MarketObservation("displacement", "1h", "observed", 1.0, ("displacement_up=1",), direction="long"),
        MarketObservation("order_block.bullish", "1h", "observed", 1.0, ("order_block_bullish=1",), direction="long"),
    )
    evidence = EvidenceAssessment(
        decision=EvidenceDecision.PROCEED,
        observations=observations,
        missing_context=(),
        conflicts=(),
        reasons=(),
        supported_concepts=tuple(item.concept_id for item in observations),
        possible_concepts=(),
    )
    scenario = ScenarioAssessment(
        decision=EvidenceDecision.PROCEED,
        hypotheses=(ScenarioHypothesis(
            scenario="continuation",
            supporting_concepts=("market_structure.bos", "displacement"),
            confirmations=(),
            invalidations=(),
            rationale=("market_structure.bos is supported by the current evidence",),
        ),),
        unsupported_scenarios=(),
        reasons=(),
    )
    analyses = {
        "4h": frame(1),
        "1h": frame(1),
        "15m": frame(1),
        "5m": frame(1),
    }
    result = analyze_setups(
        evidence,
        scenario,
        observations=observations,
        analyses=analyses,
        timeframes=("4h", "1h", "15m", "5m"),
        mode="intraday",
    )
    assert result.decision is SetupDecision.READY
    rationale = " ".join(result.candidates[0].rationale)
    assert "4h structure=long" in rationale
    assert "1h structure=long" in rationale
    assert "1h structure=short" not in rationale


def test_tp1_prefers_nearest_valid_objective_over_distant_liquidity_pool():
    from aicfa.setup_analysis import MultiTimeframeContext, _target_levels

    def row(**values):
        return pd.Series(values)

    context = MultiTimeframeContext(
        timeframes=("1d", "4h", "1h"),
        mode="swing",
        latest_rows={
            "1d": row(active_sell_liquidity_price=1800.0, previous_low=2200.0, smc_structure_direction=-1),
            "4h": row(active_sell_liquidity_price=1810.0, previous_low=2420.0, smc_structure_direction=-1),
            "1h": row(smc_structure_direction=-1),
        },
        observations=(),
        structure_direction="short",
        structure_timeframe="4h",
        context_timeframe="1d",
        execution_timeframe="1h",
    )
    targets = _target_levels(
        context, "short", current_price=2500.0,
        preferred_timeframes=("4h", "1d"), entry_zone=(),
    )
    assert targets
    assert targets[0].value == 2420.0
    assert targets[0].source == "previous low"


def test_primary_mode_hierarchies_are_independent():
    from aicfa.data_requirements import mode_timeframe_profile

    assert mode_timeframe_profile("intraday").timeframes == ("4h", "1h", "15m", "5m")
    assert mode_timeframe_profile("swing").timeframes == ("1d", "4h", "1h")
    assert mode_timeframe_profile("position").timeframes == ("1w", "1d", "4h")


def test_reversal_accepts_mss_as_structural_transition():
    from aicfa.setup_analysis import build_multi_timeframe_context, _resolve_direction

    def frame(direction):
        return pd.DataFrame({"timestamp": [1], "smc_structure_direction": [direction]})

    analyses = {
        "1w": frame(-1),
        "1d": frame(1),
        "4h": frame(1),
    }
    context = build_multi_timeframe_context(
        (),
        analyses,
        timeframes=("1w", "1d", "4h"),
        mode="position",
    )
    direction, conflict = _resolve_direction(
        context,
        scenario="reversal",
        supporting=("market_structure.mss", "liquidity.sweep"),
    )
    assert direction == "long"
    assert conflict is None


def test_continuation_blocks_counter_direction_bos_but_reversal_does_not():
    from aicfa.market_evidence import MarketObservation
    from aicfa.setup_analysis import build_multi_timeframe_context, _event_direction_conflict

    def frame(direction):
        return pd.DataFrame({"timestamp": [1], "smc_structure_direction": [direction]})

    analyses = {
        "1d": frame(-1),
        "4h": frame(-1),
        "1h": frame(-1),
    }
    observations = (
        MarketObservation("market_structure.bos", "4h", "observed", 1.0, ("bos_up=1",), direction="long"),
        MarketObservation("market_structure.choch", "4h", "observed", 1.0, ("choch_up=1",), direction="long"),
        MarketObservation("liquidity.sweep", "4h", "observed", 1.0, ("sweep_low=1",), direction="long"),
    )
    context = build_multi_timeframe_context(
        observations, analyses, timeframes=("1d", "4h", "1h"), mode="swing"
    )
    assert _event_direction_conflict(
        context, scenario="continuation", direction="short", observations=observations
    ) is not None
    assert _event_direction_conflict(
        context, scenario="reversal", direction="long", observations=observations
    ) is None
