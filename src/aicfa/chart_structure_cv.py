"""Deterministic, CPU-only chart structure extraction for AICFA.

This module intentionally stops at pixel-derived market structure. It does not
invent prices, infer trading direction, or emit trade decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import cv2
import numpy as np


@dataclass(frozen=True)
class SwingPoint:
    kind: str  # "high" or "low"
    x: int
    y: int
    label: str  # H/L/HH/HL/LH/LL


@dataclass(frozen=True)
class ChartStructure:
    width: int
    height: int
    trace: tuple[tuple[int, int, int], ...]  # x, high_y, low_y
    swings: tuple[SwingPoint, ...]


@dataclass(frozen=True)
class ChartStructureConfig:
    top_fraction: float = 0.04
    bottom_fraction: float = 0.82
    min_saturation: int = 80
    min_value: int = 70
    min_span_px: int = 2
    smoothing_radius: int = 3
    swing_radius: int = 4
    confirmation_fraction: float = 0.025

    def __post_init__(self) -> None:
        if not 0 <= self.top_fraction < self.bottom_fraction <= 1:
            raise ValueError("invalid chart vertical bounds")
        if self.min_saturation < 0 or self.min_value < 0:
            raise ValueError("color thresholds must be non-negative")
        if self.min_span_px < 1:
            raise ValueError("min_span_px must be positive")
        if self.smoothing_radius < 0 or self.swing_radius < 1:
            raise ValueError("smoothing/swing radius invalid")
        if not 0 < self.confirmation_fraction < 1:
            raise ValueError("confirmation_fraction must be between 0 and 1")


def _decode(image: bytes) -> np.ndarray:
    if not image:
        raise ValueError("image must not be empty")
    array = np.frombuffer(image, dtype=np.uint8)
    decoded = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if decoded is None:
        raise ValueError("image could not be decoded")
    return decoded


def _saturated_chart_mask(image: np.ndarray, cfg: ChartStructureConfig) -> np.ndarray:
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    # TradingView-style bullish/bearish candles are intentionally detected by
    # saturation/value rather than hard-coded RGB colors. This keeps the first
    # stage independent of a single chart theme.
    mask = ((saturation >= cfg.min_saturation) & (value >= cfg.min_value)).astype(
        np.uint8
    ) * 255

    height = image.shape[0]
    top = int(height * cfg.top_fraction)
    bottom = int(height * cfg.bottom_fraction)
    bounded = np.zeros_like(mask)
    bounded[top:bottom, :] = mask[top:bottom]

    # Remove isolated UI pixels while preserving narrow candle wicks.
    kernel = np.ones((2, 2), dtype=np.uint8)
    return cv2.morphologyEx(bounded, cv2.MORPH_OPEN, kernel)


def _column_trace(mask: np.ndarray, cfg: ChartStructureConfig) -> list[tuple[int, int, int]]:
    height, width = mask.shape
    raw: list[tuple[int, int, int]] = []

    for x in range(width):
        ys = np.flatnonzero(mask[:, x] > 0)
        if ys.size == 0:
            continue
        high_y = int(ys.min())
        low_y = int(ys.max())
        if low_y - high_y >= cfg.min_span_px:
            raw.append((x, high_y, low_y))

    if not raw:
        return []

    # Keep the largest contiguous run; chart candles form the dominant run,
    # while isolated UI text/markers form short fragments.
    runs: list[list[tuple[int, int, int]]] = [[raw[0]]]
    for point in raw[1:]:
        if point[0] - runs[-1][-1][0] <= 3:
            runs[-1].append(point)
        else:
            runs.append([point])
    trace = max(runs, key=len)
    if len(trace) < max(8, mask.shape[1] // 20):
        return []

    xs = np.array([p[0] for p in trace], dtype=np.int32)
    highs = np.array([p[1] for p in trace], dtype=np.float32)
    lows = np.array([p[2] for p in trace], dtype=np.float32)

    # Fill small gaps so swing detection works on the price path rather than
    # on individual candle-color fragments.
    full_x = np.arange(int(xs[0]), int(xs[-1]) + 1)
    high_full = np.interp(full_x, xs, highs)
    low_full = np.interp(full_x, xs, lows)

    radius = cfg.smoothing_radius
    if radius:
        window = radius * 2 + 1
        high_full = cv2.blur(high_full.reshape(1, -1), (window, 1)).ravel()
        low_full = cv2.blur(low_full.reshape(1, -1), (window, 1)).ravel()

    return [
        (int(x), int(round(h)), int(round(l)))
        for x, h, l in zip(full_x, high_full, low_full)
    ]


def _local_extrema(values: np.ndarray, radius: int, *, high: bool) -> list[int]:
    indices: list[int] = []
    for i in range(radius, len(values) - radius):
        window = values[i - radius : i + radius + 1]
        center = values[i]
        if high:
            if center == window.min() and center < window[radius + 1 :].min(initial=np.inf):
                indices.append(i)
        else:
            if center == window.max() and center > window[radius + 1 :].max(initial=-np.inf):
                indices.append(i)
    return indices


def _confirmed(
    trace: list[tuple[int, int, int]],
    index: int,
    kind: str,
    threshold: int,
) -> bool:
    if kind == "high":
        pivot = trace[index][1]
        return any(trace[j][2] - pivot >= threshold for j in range(index + 1, len(trace)))
    pivot = trace[index][2]
    return any(pivot - trace[j][1] >= threshold for j in range(index + 1, len(trace)))


def _label_swings(
    trace: list[tuple[int, int, int]],
    candidates: Iterable[tuple[int, str]],
    confirmation_threshold: int,
) -> tuple[SwingPoint, ...]:
    previous_high: int | None = None
    previous_low: int | None = None
    swings: list[SwingPoint] = []

    for index, kind in sorted(candidates, key=lambda item: item[0]):
        if not _confirmed(trace, index, kind, confirmation_threshold):
            continue

        x, high_y, low_y = trace[index]
        if kind == "high":
            value = high_y
            if previous_high is None:
                label = "H"
            elif value < previous_high:
                label = "HH"
            elif value > previous_high:
                label = "LH"
            else:
                label = "EH"
            previous_high = value
            y = high_y
        else:
            value = low_y
            if previous_low is None:
                label = "L"
            elif value > previous_low:
                label = "HL"
            elif value < previous_low:
                label = "LL"
            else:
                label = "EL"
            previous_low = value
            y = low_y

        swings.append(SwingPoint(kind=kind, x=x, y=y, label=label))

    return tuple(swings)


def analyze_chart(
    image: bytes,
    *,
    config: ChartStructureConfig | None = None,
) -> ChartStructure:
    """Extract a normalized visual market-structure representation."""

    cfg = config or ChartStructureConfig()
    decoded = _decode(image)
    mask = _saturated_chart_mask(decoded, cfg)
    trace = _column_trace(mask, cfg)
    if not trace:
        return ChartStructure(
            width=decoded.shape[1],
            height=decoded.shape[0],
            trace=(),
            swings=(),
        )

    highs = np.array([p[1] for p in trace], dtype=np.float32)
    lows = np.array([p[2] for p in trace], dtype=np.float32)
    high_indices = _local_extrema(highs, cfg.swing_radius, high=True)
    low_indices = _local_extrema(lows, cfg.swing_radius, high=False)

    candidates = [(i, "high") for i in high_indices]
    candidates.extend((i, "low") for i in low_indices)

    threshold = max(2, int(round(decoded.shape[0] * cfg.confirmation_fraction)))
    swings = _label_swings(trace, candidates, threshold)

    return ChartStructure(
        width=decoded.shape[1],
        height=decoded.shape[0],
        trace=tuple(trace),
        swings=swings,
    )
