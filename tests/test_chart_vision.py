import pytest

from aicfa.chart_vision import (
    ChartVisionOutput,
    ChartVisionRequest,
    build_evidence_set,
    to_visual_evidence,
    validate_vision_output,
)
from aicfa.visual_evidence import observation


def _request(timeframe="1h"):
    return ChartVisionRequest(
        image=b"fake-image-bytes",
        asset="BTC/USDT",
        timeframe=timeframe,
    )


def _output(concept_id="market_structure.bos", direction=None):
    return ChartVisionOutput(
        observations=(
            observation(
                concept_id,
                state="observed",
                confidence=0.9,
                evidence=("visible decisive close beyond the swing",),
                direction=direction,
            ),
        )
    )


def test_chart_vision_request_requires_image_and_context():
    with pytest.raises(ValueError):
        ChartVisionRequest(image=b"", asset="BTC/USDT", timeframe="1h")
    with pytest.raises(ValueError):
        ChartVisionRequest(image=b"x", asset="", timeframe="1h")
    with pytest.raises(ValueError):
        ChartVisionRequest(image=b"x", asset="BTC/USDT", timeframe="")


def test_vision_output_accepts_known_kb_concept():
    output = _output()
    assert validate_vision_output(output) is output


def test_vision_output_rejects_unknown_kb_concept():
    output = _output("not_a_real_concept")
    with pytest.raises(ValueError, match="unknown Knowledge Base concept"):
        validate_vision_output(output)


def test_vision_output_rejects_duplicate_concept_observations():
    item = observation(
        "market_structure.bos",
        state="observed",
        confidence=0.9,
        evidence=("visible structure",),
    )
    output = ChartVisionOutput(observations=(item, item))
    with pytest.raises(ValueError, match="duplicate concept"):
        validate_vision_output(output)


def test_to_visual_evidence_preserves_explicit_direction_and_screenshot_source():
    evidence = to_visual_evidence(_request(), _output(direction="long"))
    assert evidence.source == "user_screenshot"
    assert evidence.observations[0].direction == "long"
    assert evidence.observations[0].confidence == 0.9


def test_vision_does_not_infer_direction():
    evidence = to_visual_evidence(_request(), _output())
    assert evidence.observations[0].direction is None


def test_build_evidence_set_preserves_multi_timeframe_inputs():
    evidence = build_evidence_set(
        (
            (_request("4h"), _output("premium_discount.dealing_range")),
            (_request("1h"), _output("market_structure.bos")),
            (_request("15m"), _output("liquidity.sweep")),
        )
    )
    assert evidence.assets == ("BTC/USDT",)
    assert evidence.timeframes == ("4h", "1h", "15m")


def test_missing_context_and_conflicts_are_preserved():
    output = ChartVisionOutput(
        observations=(
            observation(
                "market_structure.bos",
                state="possible",
                confidence=0.4,
                evidence=("structure is partially obscured",),
            ),
        ),
        missing_context=("higher timeframe",),
        conflicts=("visible rejection conflicts with continuation",),
    )
    evidence = to_visual_evidence(_request(), output)
    assert evidence.missing_context == ("higher timeframe",)
    assert evidence.conflicts == ("visible rejection conflicts with continuation",)
    assert evidence.observations[0].state == "possible"
