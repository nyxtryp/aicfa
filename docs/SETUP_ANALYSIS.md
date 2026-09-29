# AICFA Setup Analysis

Setup Analysis is the layer after Evidence Reasoning and Scenario Reasoning.

Its purpose is to turn sufficiently supported market hypotheses into explicit,
conditional setup candidates without inventing information that is not visible
in the supplied evidence.

## Decision states

- READY — at least one setup candidate is sufficiently specified by the available evidence.
- NEED_MORE_EVIDENCE — the scenario or setup context is incomplete.
- WAIT — material evidence conflicts prevent a valid setup from being formed.

## Candidate contents

Each setup candidate contains:

- scenario hypothesis;
- supporting concepts;
- contextual setup-zone concepts;
- optional price-location descriptions taken directly from visual evidence;
- conditional entry requirements;
- invalidation conditions;
- target objectives expressed as visible structural/liquidity conditions;
- rationale.

Numeric prices are never invented. A price location appears only when the upstream visual evidence actually supplies one.

## Formation requirements

A setup candidate requires:

1. Evidence Reasoning must return PROCEED.
2. Scenario Reasoning must return PROCEED.
3. The scenario must have at least two observed supporting concepts.
4. A contextual setup zone must be visible.

The entry remains conditional on confirmation. A READY setup therefore means
the setup structure is sufficiently defined; it does not mean an order should
be placed immediately.

## Knowledge Base integration

For supporting concepts known to the Knowledge Base, Setup Analysis carries
their confirmation and invalidation requirements into the candidate. Unknown
concepts are not given fabricated semantics.

The scenario's own confirmation and invalidation requirements are preserved as well.

## Multiple scenarios

Setup Analysis does not silently choose one hypothesis. If continuation,
reversal or breakout-failure hypotheses are simultaneously supported by the
same evidence, separate candidates are preserved.

## Safety boundary

This layer does not contain:

- order placement;
- quantity;
- leverage;
- execution;
- fabricated historical context;
- autonomous market scanning.

The output is analytical setup structure for the next decision/risk layers.

## Evidence path

user screenshot / live evidence
→ VisualEvidence
→ EvidenceReasoning
→ ScenarioReasoning
→ SetupAnalysis
→ later confirmation / risk / decision layers.

Screenshot evidence remains inference-time evidence, not training data.