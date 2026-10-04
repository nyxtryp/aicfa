import pandas as pd

from aicfa.derivatives_evidence import append_derivatives_evidence
from aicfa.evidence_reasoning import EvidenceDecision, assess_market_evidence
from aicfa.market_evidence import MarketEvidence, MarketObservation


def _base_evidence():
    return MarketEvidence(
        asset="BTC/USDT",
        observations=(
            MarketObservation(
                concept_id="market_structure.bos",
                timeframe="1h",
                state="observed",
                confidence=1.0,
                evidence=("confirmed structural break",),
                direction="long",
            ),
        ),
        timeframes=("1h",),
    )


def test_missing_derivatives_are_optional_context_and_do_not_gate_structure():
    result = append_derivatives_evidence(
        _base_evidence(),
        pd.DataFrame(),
        timeframe="1h",
    )

    assert len(result.observations) == 1
    assert result.missing_context == ()
    assert "derivatives: no observations" in result.optional_missing_context

    assessment = assess_market_evidence(result)
    assert assessment.decision is EvidenceDecision.PROCEED


def test_partial_derivatives_are_optional_context_and_do_not_gate_structure():
    derivatives = pd.DataFrame(
        {
            "timestamp": [1000],
            "funding_rate": [0.001],
            "open_interest": [123.0],
            "mark_price": [None],
        }
    )
    result = append_derivatives_evidence(
        _base_evidence(),
        derivatives,
        timeframe="1h",
    )

    assert len(result.observations) == 1
    assert result.missing_context == ()
    assert "derivatives:mark_price:unavailable" in result.optional_missing_context
    assert "derivatives:evidence:partial" in result.optional_missing_context

    assessment = assess_market_evidence(result)
    assert assessment.decision is EvidenceDecision.PROCEED
