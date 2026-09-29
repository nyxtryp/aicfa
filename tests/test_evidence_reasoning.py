import pytest

from aicfa.evidence_reasoning import (
    EvidenceDecision,
    assess_visual_evidence,
    explain_observation,
    related_concepts,
)
from aicfa.visual_evidence import VisualEvidence, VisualEvidenceSet, observation


def _evidence(*items):
    return VisualEvidenceSet(items=tuple(items))


def _item(timeframe, *observations, missing=(), conflicts=()):
    return VisualEvidence(
        asset="BTC/USDT",
        timeframe=timeframe,
        observations=tuple(observations),
        missing_context=missing,
        conflicts=conflicts,
    )


def _obs(concept_id, state="observed", confidence=0.9):
    return observation(
        concept_id,
        state=state,
        confidence=confidence,
        evidence=("visible chart evidence",),
    )


def test_complete_evidence_can_proceed():
    result = assess_visual_evidence(
        _evidence(_item("1h", _obs("market_structure.bos"))),
        required_concepts=("market_structure.bos",),
        required_timeframes=("1h",),
    )
    assert result.decision is EvidenceDecision.PROCEED
    assert result.supported_concepts == ("market_structure.bos",)


def test_missing_timeframe_requires_more_evidence():
    result = assess_visual_evidence(
        _evidence(_item("1h", _obs("market_structure.bos"))),
        required_timeframes=("4h", "1h"),
    )
    assert result.decision is EvidenceDecision.NEED_MORE_EVIDENCE
    assert "required timeframe: 4h" in result.missing_context


def test_uncertain_observation_requires_more_evidence():
    result = assess_visual_evidence(
        _evidence(_item("15m", _obs("liquidity.sweep", confidence=0.4))),
    )
    assert result.decision is EvidenceDecision.NEED_MORE_EVIDENCE
    assert result.possible_concepts == ("liquidity.sweep",)


def test_material_conflict_favors_wait():
    result = assess_visual_evidence(
        _evidence(
            _item(
                "1h",
                _obs("market_structure.bos"),
                conflicts=("apparent continuation conflicts with visible reversal structure",),
            )
        )
    )
    assert result.decision is EvidenceDecision.WAIT
    assert result.conflicts


def test_relationships_come_from_knowledge_base():
    relationships = related_concepts("liquidity.sweep")
    assert "market_structure.bos" in relationships
    definition, linked = explain_observation("liquidity.sweep")
    assert "liquidity" in definition.lower()
    assert linked == relationships


def test_reasoner_does_not_create_trade_signal_fields():
    result = assess_visual_evidence(
        _evidence(_item("1h", _obs("market_structure.bos"))),
    )
    assert not hasattr(result, "direction")
    assert not hasattr(result, "entry")
    assert not hasattr(result, "stop")
