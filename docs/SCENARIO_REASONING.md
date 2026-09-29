# AICFA Scenario Reasoning

Scenario Reasoning is the first layer that combines supported observations into market-behavior hypotheses.

## Supported hypothesis families

- continuation
- reversal
- range
- breakout failure

These are hypotheses, not automatic trade directions.

## Rules

1. Scenario reasoning runs only after the Evidence Reasoning layer says evidence is sufficient.
2. Multiple plausible scenarios are preserved instead of silently selecting one.
3. Each hypothesis carries supporting concepts, confirmation requirements and invalidation conditions.
4. Contradictory evidence propagates `WAIT` rather than being overridden.
5. A single concept does not create a scenario or trade signal.
6. Scenario Reasoning does not produce entry, stop or execution instructions.

## Multi-timeframe behavior

Observations may come from any supported timeframe. The engine does not require a fixed four-timeframe chain. Evidence selection remains dynamic and is determined by the user's analytical request and unresolved uncertainty.

## Next step

The next layer can combine scenario hypotheses with the richer Knowledge Base confirmation/invalidation semantics and evidence quality to form a structured setup analysis, including explicit entry conditions, invalidation and targets only when the evidence is sufficient.