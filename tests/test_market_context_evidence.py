import pandas as pd

from aicfa.evidence_reasoning import EvidenceDecision, assess_market_evidence
from aicfa.market_context_evidence import append_market_context_evidence
from aicfa.market_evidence import MarketEvidence
from aicfa.scenario_reasoning import assess_scenarios


def _base_evidence():
    return MarketEvidence(
        asset="BTCUSDT",
        observations=(),
        timeframes=("1m",),
    )


def test_market_context_layers_become_causal_evidence():
    ts = pd.Timestamp("2026-10-02T00:00:00Z")
    trades = pd.DataFrame(
        {
            "timestamp": [ts],
            "volume": [10.0],
            "side": [1],
        }
    )
    flow = pd.DataFrame(
        {
            "timestamp": [ts],
            "taker_net_volume": [8.0],
            "taker_imbalance": [0.8],
        }
    )
    cvd = pd.DataFrame(
        {
            "timestamp": [ts],
            "cvd": [8.0],
            "cvd_delta": [8.0],
        }
    )
    book = pd.DataFrame(
        {
            "timestamp": [ts],
            "bid_ask_imbalance": [0.4],
            "spread": [1.0],
        }
    )
    absorption = pd.DataFrame(
        {
            "timestamp": [ts],
            "absorption": [True],
            "absorption_side": ["buy"],
        }
    )
    analysis = pd.DataFrame(
        {
            "timestamp": [ts],
            "structural_premium_discount": [-0.4],
            "wyckoff_state": ["spring_candidate"],
        }
    )
    derivatives = pd.DataFrame(
        {
            "timestamp": [ts],
            "liquidation_volume": [1000.0],
            "long_liquidation_volume": [800.0],
            "short_liquidation_volume": [200.0],
        }
    )

    evidence = append_market_context_evidence(
        _base_evidence(),
        timeframe="1m",
        trades=trades,
        order_flow=flow,
        cvd=cvd,
        order_book=book,
        absorption=absorption,
        analysis=analysis,
        derivatives=derivatives,
    )

    concepts = {item.concept_id for item in evidence.observations}
    assert {
        "microstructure.trades",
        "microstructure.order_flow",
        "microstructure.cvd",
        "microstructure.order_book",
        "microstructure.absorption",
        "premium_discount.dealing_range",
        "wyckoff.state",
        "derivatives.liquidations",
    } <= concepts
    assert not evidence.missing_context

    assessment = assess_market_evidence(evidence)
    assert assessment.decision is EvidenceDecision.PROCEED

    scenarios = assess_scenarios(assessment)
    names = {item.scenario for item in scenarios.hypotheses}
    assert "continuation" in names
    assert "reversal" in names
    assert "range" in names


def test_missing_context_is_explicit_instead_of_fabricated():
    evidence = append_market_context_evidence(
        _base_evidence(),
        timeframe="1m",
        trades=pd.DataFrame(),
        order_flow=pd.DataFrame(),
        cvd=pd.DataFrame(),
        order_book=pd.DataFrame(),
        absorption=pd.DataFrame(),
        analysis=pd.DataFrame(),
        derivatives=pd.DataFrame(),
    )

    assert "microstructure:trades:unavailable" in evidence.missing_context
    assert "microstructure:order_flow:unavailable" in evidence.missing_context
    assert "microstructure:cvd:unavailable" in evidence.missing_context
    assert "microstructure:order_book:unavailable" in evidence.missing_context
    assert "microstructure:absorption:unavailable" in evidence.missing_context
    assert "derivatives:liquidations:unavailable" in evidence.missing_context
