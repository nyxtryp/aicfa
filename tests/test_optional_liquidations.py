import pandas as pd

from aicfa.derivatives_evidence import append_derivatives_evidence, derivatives_completeness
from aicfa.evidence_reasoning import EvidenceDecision, assess_market_evidence
from aicfa.market_evidence import MarketEvidence, MarketObservation
from aicfa.scenario_reasoning import assess_scenarios


def _base_evidence():
    return MarketEvidence(
        asset="BTC/USDT",
        timeframes=("15m", "5m", "1m"),
        observations=(
            MarketObservation(
                concept_id="market_structure.bos",
                timeframe="15m",
                state="observed",
                confidence=1.0,
                evidence=("bos_up=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="displacement",
                timeframe="15m",
                state="observed",
                confidence=1.0,
                evidence=("displacement_up=1",),
                direction="long",
            ),
            MarketObservation(
                concept_id="microstructure.order_flow",
                timeframe="1m",
                state="observed",
                confidence=1.0,
                evidence=("taker_imbalance=0.5",),
                direction="long",
            ),
        ),
    )


def _derivatives_without_liquidations():
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2026-10-02T00:00:00Z", "2026-10-02T00:01:00Z"]
            ),
            "funding_rate": [0.0001, 0.0002],
            "open_interest": [1000.0, 1020.0],
            "mark_price": [100.0, 101.0],
            "open_interest_delta": [None, 20.0],
            "mark_price_delta": [None, 1.0],
        }
    )


def test_missing_liquidations_do_not_block_core_derivatives_evidence():
    frame = _derivatives_without_liquidations()
    complete, missing = derivatives_completeness(frame)
    assert complete
    assert missing == ()

    evidence = append_derivatives_evidence(_base_evidence(), frame, timeframe="15m")
    assessment = assess_market_evidence(evidence)

    assert assessment.decision is EvidenceDecision.PROCEED
    assert "derivatives.price_oi" in assessment.supported_concepts
    assert "derivatives:liquidation_volume:unavailable" in evidence.optional_missing_context
    assert "derivatives:liquidation_volume:unavailable" not in evidence.missing_context

    scenarios = assess_scenarios(assessment)
    assert scenarios.hypotheses


def test_liquidations_participate_when_available():
    frame = _derivatives_without_liquidations().copy()
    frame["liquidation_volume"] = [10.0, 50.0]
    frame["long_liquidation_volume"] = [8.0, 40.0]
    frame["short_liquidation_volume"] = [2.0, 10.0]

    evidence = append_derivatives_evidence(_base_evidence(), frame, timeframe="15m")
    assessment = assess_market_evidence(evidence)

    assert assessment.decision is EvidenceDecision.PROCEED
    liquidation = [
        item
        for item in assessment.observations
        if item.concept_id == "derivatives.liquidations"
    ]
    assert liquidation
    assert liquidation[0].direction == "short"

    scenarios = assess_scenarios(assessment)
    reversal = [
        item for item in scenarios.hypotheses if item.scenario == "reversal"
    ]
    assert reversal
    assert "derivatives.liquidations" in reversal[0].supporting_concepts
