# AICFA Chart Vision Inference Boundary

The chart-vision layer is the bridge between a user-supplied chart screenshot and the existing AICFA analytical brain.

It is an **inference boundary**, not a training-data pipeline.

## Flow

```
USER REQUEST
    ↓
Chart screenshot
    ↓
ChartVisionRequest
    ↓
actual vision implementation
    ↓
ChartVisionOutput
    ↓
validation against Knowledge Base
    ↓
VisualEvidence
    ↓
Evidence Reasoning
    ↓
Scenario Reasoning
    ↓
Setup Analysis
    ↓
Decision
```

## Request contract

`ChartVisionRequest` contains:
- image bytes;
- asset;
- timeframe;
- optional screenshot capture timestamp.

An empty image or missing asset/timeframe is rejected.

## Vision output contract

The actual vision implementation must return `ChartVisionOutput` containing:
- `VisualObservation` records;
- visible context;
- missing context;
- explicit visual conflicts.

The vision implementation is responsible for reading the image. The user does not manually label BOS, FVG, liquidity, order blocks, direction, or other concepts.

## Knowledge Base boundary

`validate_vision_output()` requires every emitted `concept_id` to exist in the canonical Knowledge Base.

The validator does **not**:
- infer direction;
- increase confidence;
- invent unseen history;
- fill missing context;
- convert a possible observation into an observed one;
- create a trade signal.

## Direction

Direction is optional evidence:
- `direction="long"` only when the vision implementation has explicit visual support for a long-side interpretation;
- `direction="short"` only when explicitly supported;
- `None` when direction is not visually established.

The downstream Decision Layer remains responsible for gating LONG/SHORT and will return WAIT when a READY setup lacks explicit directional evidence.

## Uncertainty and missing context

The vision layer must preserve uncertainty. Examples:
- chart area is obscured;
- required swing history is outside the screenshot;
- timeframe is unclear;
- a structure break is only partially visible;
- direction cannot be established from the visible evidence.

In these cases the output must use `possible` / `not_visible`, `missing_context`, or conflicts rather than guessing.

AICFA can then request another screenshot or timeframe before proceeding.

## Multi-timeframe

Multiple requests can be converted into one `VisualEvidenceSet`.

There is no fixed four-timeframe requirement. AICFA requests the timeframes needed by the current analysis.

## Current implementation boundary

This stage defines and validates the interface. It intentionally does not hard-code a particular external vision provider or pretend that image recognition has already been implemented.

The next stage can attach an actual vision implementation to `ChartVisionAnalyzer` without changing the downstream analytical contracts.

## Self-hosted provider adapter

`OllamaChartVisionAnalyzer` is an optional adapter for a self-hosted Ollama multimodal model.

It:
- sends the screenshot as base64 image input;
- supplies the asset/timeframe context and strict evidence-only instructions;
- requests JSON output;
- converts the response into `VisualObservation` records;
- validates every concept against the canonical Knowledge Base before returning it.

The adapter is opt-in and does not require the Ollama Python package or a paid external API. A multimodal vision model must already be installed and served by Ollama.

Example:

    from aicfa.chart_vision import ChartVisionRequest, OllamaChartVisionAnalyzer
    analyzer = OllamaChartVisionAnalyzer("YOUR_VISION_MODEL")
    output = analyzer.analyze(
        ChartVisionRequest(image=chart_bytes, asset="BTC/USDT", timeframe="1h")
    )

The repository does not automatically install, download, or select a vision model. This keeps the production analytical core independent from a specific provider and prevents accidental paid API usage.
