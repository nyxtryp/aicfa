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


_DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434/api/chat"


def _vision_prompt(request: ChartVisionRequest) -> str:
    return f"""You are the visual evidence reader for AICFA.

Read ONLY what is visibly supported by this {request.asset} chart screenshot.
The timeframe supplied by the application is {request.timeframe}.

Return JSON only with this exact top-level shape:
{{
  "observations": [
    {{
      "concept_id": "canonical AICFA Knowledge Base concept id",
      "state": "observed|possible|not_visible",
      "confidence": 0.0,
      "evidence": ["short visible facts"],
      "notes": "optional",
      "price_location": "optional visible location",
      "direction": "long|short|null"
    }}
  ],
  "visible_context": ["visible chart facts"],
  "missing_context": ["information not visible but needed"],
  "conflicts": ["visually conflicting evidence"]
}}

Rules:
- Never invent candles, levels, history, indicators, or context outside the image.
- Use only concept IDs that exist in the AICFA Knowledge Base.
- Use observed only when the image directly supports the concept.
- Use possible when evidence is partial or ambiguous.
- Use not_visible only when the concept cannot be established from the image.
- Direction must be null unless the visible evidence explicitly supports long or short.
- Confidence is confidence in visible evidence, not a trade probability.
- If evidence is insufficient, preserve uncertainty and populate missing_context.
- Do not give a trade recommendation, price target, order, or execution instruction.
"""


class OllamaChartVisionAnalyzer:
    """Self-hosted Ollama multimodal adapter for the ChartVision boundary.

    It is opt-in: constructing this class is required before any provider
    request is made. No Ollama Python dependency or paid API is required.
    """

    def __init__(
        self,
        model: str,
        *,
        endpoint: str = _DEFAULT_OLLAMA_ENDPOINT,
        timeout_seconds: float = 120.0,
    ) -> None:
        if not model.strip():
            raise ValueError("model must not be empty")
        if not endpoint.strip():
            raise ValueError("endpoint must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.model = model
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds

    def analyze(self, request: ChartVisionRequest) -> ChartVisionOutput:
        import base64
        import json
        from urllib import request as urllib_request

        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [{
                "role": "user",
                "content": _vision_prompt(request),
                "images": [base64.b64encode(request.image).decode("ascii")],
            }],
        }
        http_request = urllib_request.Request(
            self.endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(
                http_request, timeout=self.timeout_seconds
            ) as response:
                raw = response.read().decode("utf-8")
        except Exception as exc:
            raise RuntimeError(
                f"chart vision provider request failed: {exc}"
            ) from exc

        try:
            provider_response = json.loads(raw)
            content = provider_response["message"]["content"]
            parsed = json.loads(content)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(
                "chart vision provider returned invalid structured JSON"
            ) from exc

        output = _parse_vision_output(parsed)
        return validate_vision_output(output)


def _parse_vision_output(data: object) -> ChartVisionOutput:
    if not isinstance(data, dict):
        raise ValueError("vision output must be a JSON object")

    observations_data = data.get("observations", [])
    if not isinstance(observations_data, list):
        raise ValueError("vision observations must be a list")

    observations: list[VisualObservation] = []
    for item in observations_data:
        if not isinstance(item, dict):
            raise ValueError("each vision observation must be an object")
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list) or not all(
            isinstance(value, str) for value in evidence
        ):
            raise ValueError("observation evidence must be a list of strings")
        observations.append(
            VisualObservation(
                concept_id=item.get("concept_id", ""),
                state=item.get("state", ""),
                confidence=item.get("confidence", -1.0),
                evidence=tuple(evidence),
                notes=item.get("notes", ""),
                price_location=item.get("price_location"),
                direction=item.get("direction"),
            )
        )

    def strings(name: str) -> tuple[str, ...]:
        value = data.get(name, [])
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValueError(f"vision {name} must be a list of strings")
        return tuple(value)

    return ChartVisionOutput(
        observations=tuple(observations),
        visible_context=strings("visible_context"),
        missing_context=strings("missing_context"),
        conflicts=strings("conflicts"),
    )
