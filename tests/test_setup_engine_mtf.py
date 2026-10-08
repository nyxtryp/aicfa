import pandas as pd

from aicfa.evidence_reasoning import assess_market_evidence
from aicfa.market_evidence import MarketEvidence, MarketObservation
from aicfa.scenario_reasoning import assess_scenarios
from aicfa.setup_analysis import SetupDecision, analyze_setups


TFS = ("1d", "4h", "1h", "15m")


def _frames(*, structure_4h=1, structure_15m=1, structure_1h=1):
    frames = {}
    for tf in TFS:
        direction = 0
        if tf == "4h":
            direction = structure_4h
        elif tf == "15m":
            direction = structure_15m
        elif tf == "1h":
            direction = structure_1h
        frame = pd.DataFrame(
            [{
                "timestamp": 1000,
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 105.0,
                "smc_structure_direction": direction,
                "fvg_bullish": int(tf == "4h"),
                "fvg_bullish_low": 101.0 if tf == "4h" else float("nan"),
                "fvg_bullish_high": 103.0 if tf == "4h" else float("nan"),
                "smc_sweep_low_level": 99.0 if tf == "4h" else 80.0,
                "active_buy_liquidity_price": 120.0 if tf == "4h" else 130.0,
            }]
        )
        frames[tf] = frame
    return frames


def _evidence():
    observations = (
        MarketObservation(
            concept_id="market_structure.bos",
            timeframe="4h",
            state="observed",
            confidence=1.0,
            evidence=("bos_up=1",),
            direction="long",
        ),
        MarketObservation(
            concept_id="displacement",
            timeframe="4h",
            state="observed",
            confidence=1.0,
            evidence=("displacement_up=1",),
            direction="long",
        ),
        MarketObservation(
            concept_id="imbalance.fvg",
            timeframe="4h",
            state="observed",
            confidence=1.0,
            evidence=("fvg_bullish=1",),
            direction="long",
        ),
    )
    return MarketEvidence(
        asset="BTC/USDT",
        observations=observations,
        timeframes=TFS,
    )


def _pipeline(frames):
    evidence = _evidence()
    assessment = assess_market_evidence(evidence)
    scenarios = assess_scenarios(assessment)
    return analyze_setups(
        assessment,
        scenarios,
        observations=evidence.observations,
        analyses=frames,
        timeframes=TFS,
        mode="swing",
    )


def test_setup_engine_uses_higher_timeframe_direction_not_execution_tf():
    result = _pipeline(_frames(structure_4h=1, structure_15m=1, structure_1h=1))

    assert result.decision is SetupDecision.READY
    assert result.candidates
    assert {candidate.direction for candidate in result.candidates} == {"long"}


def test_setup_engine_waits_when_confirmation_conflicts_with_higher_structure():
    result = _pipeline(_frames(structure_4h=1, structure_15m=1, structure_1h=-1))

    assert result.decision is SetupDecision.WAIT
    assert result.candidates == ()
    assert "lower confirmation conflicts with higher-timeframe structure" in result.conflicts


def test_setup_engine_levels_come_from_relevant_timeframe_not_1m():
    result = _pipeline(_frames(structure_4h=1, structure_15m=1, structure_1h=1))

    candidate = result.candidates[0]
    assert candidate.direction == "long"
    assert candidate.entry_zone
    assert all(level.timeframe == "4h" for level in candidate.entry_zone)
    assert candidate.invalidation_level is not None
    assert candidate.invalidation_level.timeframe == "4h"
    assert candidate.target_levels
    assert candidate.target_levels[0].timeframe != "1m"


def test_setup_engine_requires_all_mode_timeframes():
    frames = _frames()
    frames.pop("1d")

    result = _pipeline(frames)

    assert result.decision is SetupDecision.NEED_MORE_EVIDENCE
    assert "required timeframe: 1d" in result.missing_context


def test_setup_engine_requires_directionally_coherent_levels():
    result = _pipeline(_frames(structure_4h=1, structure_15m=1, structure_1h=1))

    candidate = result.candidates[0]
    entry_low = min(level.value for level in candidate.entry_zone)
    entry_high = max(level.value for level in candidate.entry_zone)

    assert candidate.invalidation_level is not None
    assert candidate.target_levels
    assert candidate.invalidation_level.value < entry_low
    assert candidate.target_levels[0].value > entry_high


def test_setup_engine_does_not_use_execution_target_than_entry_zone():
    result = _pipeline(_frames(structure_4h=1, structure_15m=1, structure_1h=1))
    candidate = result.candidates[0]

    assert candidate.entry_zone
    entry_tf = candidate.entry_zone[0].timeframe
    allowed = TFS[TFS.index(entry_tf):]
    assert candidate.target_levels
    assert candidate.target_levels[0].timeframe in allowed


def test_setup_engine_can_use_causal_rolling_extreme_as_target_fallback():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1h=1)
    for tf, frame in frames.items():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "liquidity_breakout_high"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = 125.0 if tf == "4h" else float("nan")

    result = _pipeline(frames)
    assert result.candidates
    candidate = result.candidates[0]
    assert candidate.target_levels
    assert candidate.target_levels[0].timeframe == "4h"
    assert candidate.target_levels[0].value == 125.0
    assert candidate.target_levels[0].source == "causal rolling high"


def test_setup_engine_collapses_duplicate_actionable_scenario_geometry():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1h=1)
    evidence = MarketEvidence(
        asset="BTC/USDT",
        observations=(
            MarketObservation(
                concept_id="market_structure.bos",
                timeframe="4h",
                state="observed",
                confidence=1.0,
                evidence=("bos_up=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="displacement",
                timeframe="4h",
                state="observed",
                confidence=1.0,
                evidence=("displacement_up=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="market_structure.choch",
                timeframe="1h",
                state="observed",
                confidence=1.0,
                evidence=("choch_up=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="liquidity.sweep",
                timeframe="1h",
                state="observed",
                confidence=1.0,
                evidence=("sweep_low=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="imbalance.fvg",
                timeframe="4h",
                state="observed",
                confidence=1.0,
                evidence=("fvg_bullish=1",),
                direction="long",
            ),
        ),
        timeframes=TFS,
    )
    assessment = assess_market_evidence(evidence)
    scenarios = assess_scenarios(assessment)
    result = analyze_setups(
        assessment,
        scenarios,
        observations=evidence.observations,
        analyses=frames,
        timeframes=TFS,
        mode="swing",
    )

    assert len(result.candidates) == 1
    assert result.candidates[0].scenario == "continuation"
    assert any(
        "reversal: same actionable geometry as continuation" in item
        for item in result.missing_context
    )


def test_setup_engine_uses_scenario_specific_zone_family():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1h=1)
    for tf, frame in frames.items():
        frame.loc[0, "order_block_bullish_low"] = 101.0 if tf == "4h" else float("nan")
        frame.loc[0, "order_block_bullish_high"] = 103.0 if tf == "4h" else float("nan")
        frame.loc[0, "fvg_bullish_low"] = 96.0 if tf == "4h" else float("nan")
        frame.loc[0, "fvg_bullish_high"] = 99.0 if tf == "4h" else float("nan")
    frames["4h"].loc[0, "smc_sweep_low_level"] = 90.0
    frames["4h"].loc[0, "active_buy_liquidity_price"] = 130.0

    evidence = MarketEvidence(
        asset="BTC/USDT",
        observations=(
            MarketObservation(
                concept_id="market_structure.bos",
                timeframe="4h",
                state="observed",
                confidence=1.0,
                evidence=("bos_up=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="displacement",
                timeframe="4h",
                state="observed",
                confidence=1.0,
                evidence=("displacement_up=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="order_block.bullish",
                timeframe="15m",
                state="observed",
                confidence=1.0,
                evidence=("order_block_bullish=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="market_structure.choch",
                timeframe="15m",
                state="observed",
                confidence=1.0,
                evidence=("choch_up=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="liquidity.sweep",
                timeframe="15m",
                state="observed",
                confidence=1.0,
                evidence=("sweep_low=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="imbalance.fvg",
                timeframe="4h",
                state="observed",
                confidence=1.0,
                evidence=("fvg_bullish=1",),
                direction="long",
            ),
        ),
        timeframes=TFS,
    )
    assessment = assess_market_evidence(evidence)
    scenarios = assess_scenarios(assessment)
    result = analyze_setups(
        assessment,
        scenarios,
        observations=evidence.observations,
        analyses=frames,
        timeframes=TFS,
        mode="swing",
    )

    by_scenario = {candidate.scenario: candidate for candidate in result.candidates}
    assert by_scenario["continuation"].entry_zone[0].source.startswith("active bullish OB")
    assert by_scenario["reversal"].entry_zone[0].source.startswith("active bullish FVG")


def test_setup_engine_prioritizes_active_liquidity_over_nearer_structural_extreme():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1h=1)
    for tf, frame in frames.items():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")
    frames["4h"].loc[0, "active_buy_liquidity_price"] = 108.0
    frames["4h"].loc[0, "previous_high"] = 106.0

    result = _pipeline(frames)
    candidate = result.candidates[0]
    assert candidate.target_levels[0].value == 108.0
    assert candidate.target_levels[0].source == "active buy-side liquidity"


def test_setup_engine_can_return_second_distinct_target_after_primary_draw():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1h=1)
    for tf, frame in frames.items():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")
    frames["4h"].loc[0, "active_buy_liquidity_price"] = 120.0
    frames["4h"].loc[0, "previous_high"] = 125.0

    result = _pipeline(frames)
    targets = result.candidates[0].target_levels
    assert len(targets) == 2
    assert targets[0].value == 120.0
    assert targets[1].value == 125.0


def test_setup_engine_prioritizes_active_liquidity_over_nearer_structural_extreme():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1h=1)
    for tf, frame in frames.items():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")
    frames["1h"].loc[0, "active_buy_liquidity_price"] = 108.0
    frames["1h"].loc[0, "previous_high"] = 106.0
    result = _pipeline(frames)
    candidate = result.candidates[0]
    assert candidate.target_levels[0].value == 108.0
    assert candidate.target_levels[0].source == "active buy-side liquidity"


def test_setup_engine_can_return_second_distinct_target_after_primary_draw():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1h=1)
    for tf, frame in frames.items():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")
    frames["4h"].loc[0, "active_buy_liquidity_price"] = 120.0
    frames["4h"].loc[0, "previous_high"] = 125.0
    result = _pipeline(frames)
    targets = result.candidates[0].target_levels
    assert len(targets) == 2
    assert targets[0].value == 120.0
    assert targets[1].value == 125.0


def test_setup_engine_exposes_derived_rr_without_fixed_minimum_gate():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1h=1)
    # Keep this fixture's target geometry deterministic across all TFs.
    for frame in frames.values():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "liquidity_breakout_high"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")
    frames["4h"].loc[0, "active_buy_liquidity_price"] = 106.0
    frames["4h"].loc[0, "smc_sweep_low_level"] = 99.0

    result = _pipeline(frames)

    assert result.decision is SetupDecision.READY
    assert result.candidates
    candidate = result.candidates[0]
    assert candidate.invalidation_level.value == 99.0
    assert candidate.target_levels[0].value == 106.0
    assert candidate.target_levels[0].value > max(level.value for level in candidate.entry_zone)
