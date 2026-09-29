"""Chart-vision inference boundary for user-supplied screenshots.

This module defines the contract between an actual vision implementation and
AICFA's analytical evidence pipeline. It does not perform image recognition
itself and never invents observations from missing chart information.
"""

from dataclasses import dataclass
from typing import Protocol

from aicfa.knowledge_base import get_knowledge
from aicfa.visual_evidence import VisualEvidence, VisualEvidenceSet, VisualObservation


@dataclass(frozen=True)
class ChartVisionRequest:
    """One screenshot supplied for inference."""

    image: bytes
    asset: str
    timeframe: str
    captured_at_ms: int | None = None

    def __post_init__(self) -> None:
        if not self.image:
            raise ValueError("image must not be empty")
        if not self.asset.strip():
            raise ValueError("asset must not be empty")
        if not self.timeframe.strip():
            raise ValueError("timeframe must not be empty")
        if self.captured_at_ms is not None and self.captured_at_ms < 0:
            raise ValueError("captured_at_ms must be non-negative")


@dataclass(frozen=True)
class ChartVisionOutput:
    """Raw structured output expected from a vision implementation."""

    observations: tuple[VisualObservation, ...]
    visible_context: tuple[str, ...] = ()
    missing_context: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


class ChartVisionAnalyzer(Protocol):
    """Adapter contract for the actual chart-vision implementation."""

    def analyze(self, request: ChartVisionRequest) -> ChartVisionOutput:
        """Read one screenshot and return only visually supported evidence."""


def validate_vision_output(output: ChartVisionOutput) -> ChartVisionOutput:
    """Validate vision output before it enters the analytical evidence graph.

    Concept IDs must exist in the canonical Knowledge Base. This prevents a
    vision provider from silently introducing unsupported concepts. The
    validator does not upgrade confidence, infer direction, or fill missing
    context.
    """

    seen: set[str] = set()
    for item in output.observations:
        if item.concept_id in seen:
            raise ValueError(
                f"duplicate concept observation: {item.concept_id}"
            )
        seen.add(item.concept_id)
        try:
            get_knowledge(item.concept_id)
        except KeyError as exc:
            raise ValueError(
                f"vision output references unknown Knowledge Base concept: "
                f"{item.concept_id}"
            ) from exc
    return output


def to_visual_evidence(
    request: ChartVisionRequest,
    output: ChartVisionOutput,
) -> VisualEvidence:
    """Convert validated vision output into the canonical screenshot contract."""

    validate_vision_output(output)
    return VisualEvidence(
        asset=request.asset,
        timeframe=request.timeframe,
        observations=output.observations,
        visible_context=output.visible_context,
        missing_context=output.missing_context,
        conflicts=output.conflicts,
        captured_at_ms=request.captured_at_ms,
        source="user_screenshot",
    )


def build_evidence_set(
    requests_and_outputs: tuple[
        tuple[ChartVisionRequest, ChartVisionOutput], ...
    ],
) -> VisualEvidenceSet:
    """Convert several vision results into one multi-timeframe evidence set."""

    return VisualEvidenceSet(
        items=tuple(
            to_visual_evidence(request, output)
            for request, output in requests_and_outputs
        )
    )
