import pytest

from aicfa.market_evidence import MarketEvidence, MarketObservation


def _obs(**kwargs):
    defaults = {
        "concept_id": "market_structure.bos",
        "timeframe": "1h",
        "state": "observed",
        "confidence": 0.9,
        "evidence": ("deterministic market-state evidence",),
        "direction": "long",
    }
    defaults.update(kwargs)
    return MarketObservation(**defaults)


def test_market_observation_accepts_explicit_direction():
    item = _obs()
    assert item.direction == "long"
    assert item.timeframe == "1h"


def test_market_observation_does_not_require_direction():
    item = _obs(direction=None)
    assert item.direction is None


def test_market_observation_rejects_invalid_direction():
    with pytest.raises(ValueError, match="direction"):
        _obs(direction="bullish")


def test_market_evidence_requires_market_data_source():
    evidence = MarketEvidence(
        asset="BTC/USDT",
        observations=(_obs(),),
        timeframes=("1h", "15m"),
    )
    assert evidence.source == "market_data"


def test_market_evidence_rejects_duplicate_concept_timeframe():
    item = _obs()
    with pytest.raises(ValueError, match="duplicate"):
        MarketEvidence(
            asset="BTC/USDT",
            observations=(item, item),
            timeframes=("1h",),
        )
