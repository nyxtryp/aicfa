# AICFA Evidence Reasoning Layer

The evidence reasoning layer sits between visual/live evidence and downstream scenario/setup analysis.

Its first responsibility is **not to predict direction**. It determines whether the evidence is sufficiently complete and coherent for the next analytical step.

## Decision states

- **PROCEED** — supplied evidence is sufficiently supported for downstream reasoning.
- **NEED_MORE_EVIDENCE** — required timeframe/context is missing or important observations remain uncertain.
- **WAIT** — material evidence is contradictory and should not be silently resolved.

## What it does

1. Collects observations from one or many timeframes.
2. Separates observed concepts from uncertain/possible concepts.
3. Checks explicitly required timeframes and concepts.
4. Preserves missing context.
5. Preserves material contradictions.
6. Resolves concept relationships through the Knowledge Base.
7. Prevents an evidence assessment from becoming a LONG/SHORT signal.

## Dynamic multi-timeframe behavior

The reasoning layer accepts any timeframe set supplied by the evidence. There is no four-timeframe limit.

Example available grid: `1M → 1W → 1D → 4H → 1H → 15M → 5M → 1m`.

A downstream request may require only a subset. The required set is determined by the analysis request and currently available evidence.

The important rule is that AICFA should request **only the additional evidence needed to resolve the current analytical uncertainty**, rather than demanding every timeframe.

## Next layer

After evidence is sufficient, downstream reasoning can evaluate Knowledge Base relationships and scenario families. Setup logic must still apply confirmations, invalidation, evidence quality and contradictory-evidence rules before presenting an actionable analysis.