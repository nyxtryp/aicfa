import pytest

from aicfa.visual_evidence import (
    VisualEvidence,
    VisualEvidenceSet,
    VisualObservation,
    observation,
)


def _obs(concept_id="market_structure.bos", state="observed"):
    return observation(
        concept_id,
        state=state,
        confidence=0.9,
        evidence=("decisive close beyond visible swing",),
    )


def test_visual_observation_is_immutable_and_validates_confidence():
    item = _obs()
    assert isinstance(item, VisualObservation)
    with pytest.raises(Exception):
        item.confidence = 0.5
    with pytest.raises(ValueError):
        _obs(state="unknown")
    with pytest.raises(ValueError):
        observation("market_structure.bos", state="observed", confidence=1.1, evidence=("x",))


def test_visual_observation_requires_visible_evidence():
    with pytest.raises(ValueError):
        observation("market_structure.bos", state="observed", confidence=0.5, evidence=())


def test_visual_evidence_is_explicitly_screenshot_sourced():
    evidence = VisualEvidence(
        asset="BTC/USDT",
        timeframe="1h",
        observations=(_obs(),),
        visible_context=("visible swing structure", "recent candles"),
        missing_context=("higher timeframe",),
        conflicts=("lower-timeframe reversal vs higher-timeframe continuation",),
    )
    assert evidence.source == "user_screenshot"
    assert evidence.missing_context
    assert evidence.conflicts


def test_visual_evidence_rejects_duplicate_concepts():
    with pytest.raises(ValueError):
        VisualEvidence(
            asset="BTC/USDT",
            timeframe="15m",
            observations=(_obs(), _obs("market_structure.bos")),
        )


def test_visual_evidence_set_supports_multi_timeframe_analysis():
    evidence = VisualEvidenceSet(
        items=(
            VisualEvidence("BTC/USDT", "4h", (_obs("market_structure.range"),)),
            VisualEvidence("BTC/USDT", "1h", (_obs("market_structure.bos"),)),
            VisualEvidence("BTC/USDT", "15m", (_obs("liquidity.sweep"),)),
        )
    )
    assert evidence.assets == ("BTC/USDT",)
    assert evidence.timeframes == ("4h", "1h", "15m")
    assert len(evidence.observations_for("market_structure.bos")) == 1


def test_visual_evidence_set_rejects_duplicate_asset_timeframe():
    item = VisualEvidence("BTC/USDT", "1h", (_obs(),))
    with pytest.raises(ValueError):
        VisualEvidenceSet(items=(item, item))


def test_screenshot_evidence_is_not_live_provider_state():
    evidence = VisualEvidence(
        asset="BTC/USDT",
        timeframe="5m",
        observations=(_obs(),),
    )
    assert evidence.source != "live_provider"
    assert not hasattr(evidence, "ohlcv")
