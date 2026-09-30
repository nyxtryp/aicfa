from aicfa.decision import DecisionAction, decide
from aicfa.evidence_reasoning import EvidenceDecision, assess_market_evidence
from aicfa.market_evidence import MarketEvidence, MarketObservation
from aicfa.scenario_reasoning import assess_scenarios
from aicfa.setup_analysis import SetupDecision, analyze_setups


def _obs(concept_id: str, timeframe: str = "1h", direction: str | None = None):
    return MarketObservation(
        concept_id=concept_id,
        timeframe=timeframe,
        state="observed",
        confidence=0.9,
        evidence=(f"deterministic {concept_id} evidence",),
        direction=direction,
    )


def test_market_evidence_reaches_authoritative_decision_layer():
    evidence = MarketEvidence(
        asset="BTC/USDT",
        timeframes=("4h", "1h", "15m", "5m"),
        observations=(
            _obs("market_structure.bos", "4h", "long"),
            _obs("displacement", "1h", "long"),
            _obs("order_block.bullish", "1h", "long"),
            _obs("imbalance.fvg", "15m", "long"),
        ),
    )

    assessed = assess_market_evidence(evidence)
    assert assessed.decision is EvidenceDecision.PROCEED

    scenarios = assess_scenarios(assessed)
    assert scenarios.hypotheses

    setups = analyze_setups(assessed, scenarios)
    assert setups.decision is SetupDecision.READY

    decision = decide(setups, observations=assessed.observations)
    assert decision.action is DecisionAction.LONG


def test_market_evidence_without_explicit_direction_cannot_create_trade_direction():
    evidence = MarketEvidence(
        asset="BTC/USDT",
        timeframes=("4h", "1h", "15m"),
        observations=(
            _obs("market_structure.bos", "4h"),
            _obs("displacement", "1h"),
            _obs("imbalance.fvg", "15m"),
        ),
    )

    assessed = assess_market_evidence(evidence)
    scenarios = assess_scenarios(assessed)
    setups = analyze_setups(assessed, scenarios)
    decision = decide(setups, observations=assessed.observations)

    assert decision.action is DecisionAction.WAIT
