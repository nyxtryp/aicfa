import cv2
import numpy as np

from aicfa.chart_structure_cv import ChartStructureConfig, analyze_chart


def _synthetic_chart() -> bytes:
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    image[:] = (18, 20, 24)

    closes = [
        170, 165, 155, 145, 135, 128, 120, 112,
        118, 128, 140, 132, 120, 108, 98, 90,
        96, 105, 116, 128, 138, 130, 118, 108,
        112, 120, 132, 145, 138, 128, 118, 126,
        138, 150, 162, 155, 145, 135, 142, 152,
    ]

    previous = closes[0] + 4
    for i, close in enumerate(closes):
        x = 12 + i * 7
        open_price = previous
        high = min(open_price, close) - 7
        low = max(open_price, close) + 7
        color = (60, 210, 90) if close < open_price else (70, 70, 225)
        cv2.line(image, (x, high), (x, low), color, 2)
        cv2.rectangle(
            image,
            (x - 2, min(open_price, close)),
            (x + 2, max(open_price, close)),
            color,
            -1,
        )
        previous = close

    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def test_native_chart_structure_extracts_price_trace_and_swings():
    result = analyze_chart(
        _synthetic_chart(),
        config=ChartStructureConfig(
            top_fraction=0.02,
            bottom_fraction=0.90,
            swing_radius=3,
            confirmation_fraction=0.02,
        ),
    )

    assert result.width == 320
    assert result.height == 240
    assert len(result.trace) > 100
    assert result.swings
    assert {item.kind for item in result.swings} == {"high", "low"}
    assert all(item.label in {"H", "L", "HH", "HL", "LH", "LL", "EH", "EL"} for item in result.swings)


def test_native_chart_structure_is_deterministic():
    image = _synthetic_chart()
    first = analyze_chart(image)
    second = analyze_chart(image)

    assert first == second
