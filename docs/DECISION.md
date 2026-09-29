# AICFA Decision Layer

The Decision Layer is the gate after Setup Analysis.

## Actions

- LONG — a READY setup has explicit, consistent long directional evidence.
- SHORT — a READY setup has explicit, consistent short directional evidence.
- WAIT — evidence is incomplete, contradictory, or direction is not established.
- NO_TRADE — no actionable setup candidate remains after the gate.

## Direction rule

AICFA never infers direction from an unlabeled concept name.

Visual observations may carry an explicit directional interpretation:

- `long`
- `short`
- no direction

Direction is inference-time evidence produced by the future vision layer. It is not a user-supplied manual market label and is not training data.

If both LONG and SHORT directional observations are present at sufficient confidence, the Decision Layer returns WAIT rather than choosing a side.

A READY setup without directional evidence also returns WAIT. Structural readiness alone is not enough to manufacture a LONG or SHORT decision.

## Decision candidate

A decision candidate preserves:

- scenario;
- action;
- supporting concepts;
- conditional entry requirements;
- invalidation conditions;
- visible target objectives;
- rationale.

Numeric prices are not fabricated.

## Safety boundary

The Decision Layer does not:

- place orders;
- calculate order quantity;
- select leverage;
- execute trades;
- continuously scan markets;
- override contradictory evidence.

The path is:

`Visual Evidence → Evidence Reasoning → Scenario Reasoning → Setup Analysis → Decision`

The final decision remains evidence-gated and may legitimately be WAIT.
