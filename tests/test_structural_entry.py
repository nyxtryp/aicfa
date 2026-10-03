import pandas as pd

from aicfa.evidence_reasoning import assess_market_evidence
from aicfa.market_evidence import MarketEvidence, MarketObservation
from aicfa.scenario_reasoning import assess_scenarios
from aicfa.setup_analysis import SetupDecision, analyze_setups


TFS = ("1d", "4h", "1h", "15m")


def _frames():
    frames = {}
    for tf in TFS:
        frames[tf] = pd.DataFrame([{
            "timestamp": 1000,
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "smc_structure_direction": 1,
            "fvg_bullish": int(tf == "4h"),
            "fvg_bullish_low": 101.0 if tf == "4h" else float("nan"),
            "fvg_bullish_high": 103.0 if tf == "4h" else float("nan"),
            "smc_sweep_low_level": 99.0 if tf == "4h" else float("nan"),
            "active_buy_liquidity_price": 106.0 if tf == "4h" else float("nan"),
        }])
    return frames


def _pipeline(frames):
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
    return analyze_setups(
        assessment,
        scenarios,
        observations=evidence.observations,
        analyses=frames,
        timeframes=TFS,
    )


def test_structural_entry_does_not_reject_setup_for_rr_below_two():
    result = _pipeline(_frames())

    assert result.decision is SetupDecision.READY
    assert result.candidates
    candidate = result.candidates[0]
    assert candidate.entry_zone
    assert candidate.invalidation_level is not None
    assert candidate.target_levels
    assert candidate.target_levels[0].value == 106.0


def test_structural_levels_never_come_from_execution_timeframe():
    frames = _frames()
    frames["1m"] = pd.DataFrame([{
        "timestamp": 1000,
        "open": 100.0,
        "high": 999.0,
        "low": 1.0,
        "close": 105.0,
        "smc_structure_direction": -1,
        "fvg_bullish": 1,
        "fvg_bullish_low": 102.0,
        "fvg_bullish_high": 104.0,
        "smc_sweep_low_level": 1.0,
        "active_buy_liquidity_price": 999.0,
    }])

    result = _pipeline(frames)

    assert result.candidates
    candidate = result.candidates[0]
    assert all(level.timeframe != "1m" for level in candidate.entry_zone)
    assert candidate.invalidation_level is not None
    assert candidate.invalidation_level.timeframe != "1m"
    assert all(level.timeframe != "1m" for level in candidate.target_levels)
