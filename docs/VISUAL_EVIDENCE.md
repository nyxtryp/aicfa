# AICFA Visual Evidence Contract

AICFA treats a user-supplied chart screenshot as **inference-time evidence**. It is not a training dataset and is never represented as live provider data.

## Runtime path

```
USER REQUEST
    ↓
AICFA determines required evidence
    ↓
user screenshot(s)
    ↓
vision reads visible chart information
    ↓
VisualEvidence
    ↓
Knowledge Base + analytical rules
    ↓
scenario / setup analysis / WAIT
```

## Contract

`VisualObservation` records what the vision layer can support from the visible chart:

- `concept_id` — stable Knowledge Base concept;
- `state` — `observed`, `possible`, or `not_visible`;
- `confidence` — bounded 0..1 assessment of the visual interpretation;
- `evidence` — concrete visible observations supporting the interpretation;
- optional notes and price-location context.

`VisualEvidence` adds:

- asset;
- timeframe;
- screenshot provenance;
- optional capture timestamp;
- visible context;
- explicitly missing context;
- explicitly conflicting observations.

`VisualEvidenceSet` groups evidence across timeframes for one analysis request.

## Important boundaries

### No manual labeling

The user does not label BOS, FVG, liquidity, OB, or other concepts. The future vision layer reads the chart and produces structured observations.

### No fabricated history

Only information visible in the supplied image may be represented as screenshot evidence. If the visible history is insufficient, AICFA must request another screenshot, timeframe, or relevant context.

### No live-data contamination

Screenshot observations cannot silently become OHLCV, WebSocket, REST, or other live-provider observations. Live and screenshot evidence are separate input paths into the same analytical brain.

### No signal generation

This contract describes evidence. It does not produce LONG/SHORT decisions. Scenario and risk logic must consider context, relationships, invalidations, contradictions and evidence quality before an actionable setup can be described.

### Multi-timeframe reasoning

AICFA may request and correlate several screenshots, for example:

- 4H — broader context;
- 1H — structural state;
- 15M — setup zone;
- 5M — entry confirmation.

The exact set depends on the user's request and what evidence is missing.