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


def test_entry_condition_requires_structural_confirmation_at_zone():
    result = _pipeline(_frames())

    assert result.candidates
    condition = result.candidates[0].entry_condition
    assert any("reaction/confirmation" in item for item in condition)
    assert any("displacement" in item.lower() for item in condition)



def test_target_contract_requires_objective_beyond_entry():
    result = _pipeline(_frames())
    assert result.candidates
    candidate = result.candidates[0]
    entry_high = max(level.value for level in candidate.entry_zone)
    assert candidate.target_levels
    assert all(level.value > entry_high for level in candidate.target_levels)


def test_target_contract_allows_liquidity_as_draw_not_invalidation():
    result = _pipeline(_frames())
    candidate = result.candidates[0]
    assert candidate.target_levels
    assert candidate.target_levels[0].source == "active buy-side liquidity"
    assert candidate.invalidation_level is not None
    assert candidate.invalidation_level.source != "active buy-side liquidity"


def test_target_contract_excludes_execution_timeframe():
    frames = _frames()
    frames["1m"] = pd.DataFrame([{
        "timestamp": 1000,
        "open": 100.0,
        "high": 110.0,
        "low": 90.0,
        "close": 105.0,
        "smc_structure_direction": 1,
        "active_buy_liquidity_price": 999.0,
        "previous_high": 998.0,
        "rolling_high_60": 997.0,
    }])
    result = _pipeline(frames)
    assert result.candidates
    assert all(level.timeframe != "1m" for level in result.candidates[0].target_levels)


def test_target_contract_does_not_create_arbitrary_tp_when_no_objective_exists():
    frames = _frames()
    for frame in frames.values():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "liquidity_breakout_high"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")
    result = _pipeline(frames)
    assert result.decision is SetupDecision.NEED_MORE_EVIDENCE
    assert result.candidates == ()


def test_target_contract_keeps_distinct_targets_in_causal_price_order():
    frames = _frames()
    for frame in frames.values():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")
    frames["4h"].loc[0, "active_buy_liquidity_price"] = 120.0
    frames["4h"].loc[0, "previous_high"] = 125.0
    result = _pipeline(frames)
    assert result.candidates
    targets = result.candidates[0].target_levels
    assert len(targets) == 2
    assert targets[0].value < targets[1].value


def test_target_contract_uses_only_current_rows_not_future_rows():
    frames = _frames()
    for frame in frames.values():
        frame.loc[0, "timestamp"] = 1000
        frame.loc[0, "active_buy_liquidity_price"] = 150.0
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")

        frame.loc[1] = frame.loc[0]
        frame.loc[1, "timestamp"] = 2000
        frame.loc[1, "active_buy_liquidity_price"] = float("nan")

    result = _pipeline(frames)
    assert result.candidates
    assert result.candidates[0].target_levels == ()
