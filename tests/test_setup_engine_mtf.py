import pandas as pd

from aicfa.evidence_reasoning import assess_market_evidence
from aicfa.market_evidence import MarketEvidence, MarketObservation
from aicfa.scenario_reasoning import assess_scenarios
from aicfa.setup_analysis import SetupDecision, analyze_setups


TFS = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")


def _frames(*, structure_4h=1, structure_15m=1, structure_1m=-1):
    frames = {}
    for tf in TFS:
        direction = 0
        if tf == "4h":
            direction = structure_4h
        elif tf == "15m":
            direction = structure_15m
        elif tf == "1m":
            direction = structure_1m
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
    )


def test_setup_engine_uses_higher_timeframe_direction_not_1m():
    result = _pipeline(_frames(structure_4h=1, structure_15m=1, structure_1m=-1))

    assert result.decision is SetupDecision.READY
    assert result.candidates
    assert {candidate.direction for candidate in result.candidates} == {"long"}


def test_setup_engine_waits_when_confirmation_conflicts_with_higher_structure():
    result = _pipeline(_frames(structure_4h=1, structure_15m=-1, structure_1m=-1))

    assert result.decision is SetupDecision.WAIT
    assert result.candidates == ()
    assert "lower confirmation conflicts with higher-timeframe structure" in result.conflicts


def test_setup_engine_levels_come_from_relevant_timeframe_not_1m():
    result = _pipeline(_frames(structure_4h=1, structure_15m=1, structure_1m=-1))

    candidate = result.candidates[0]
    assert candidate.direction == "long"
    assert candidate.entry_zone
    assert all(level.timeframe == "4h" for level in candidate.entry_zone)
    assert candidate.invalidation_level is not None
    assert candidate.invalidation_level.timeframe == "4h"
    assert candidate.target_levels
    assert candidate.target_levels[0].timeframe == "4h"


def test_setup_engine_requires_all_seven_timeframes():
    frames = _frames()
    frames.pop("1w")

    result = _pipeline(frames)

    assert result.decision is SetupDecision.NEED_MORE_EVIDENCE
    assert "required timeframe: 1w" in result.missing_context


def test_setup_engine_requires_directionally_coherent_levels():
    result = _pipeline(_frames(structure_4h=1, structure_15m=1, structure_1m=-1))

    candidate = result.candidates[0]
    entry_low = min(level.value for level in candidate.entry_zone)
    entry_high = max(level.value for level in candidate.entry_zone)

    assert candidate.invalidation_level is not None
    assert candidate.target_levels
    assert candidate.invalidation_level.value < entry_low
    assert candidate.target_levels[0].value > entry_high
