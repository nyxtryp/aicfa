# AICFA Setup Detection

The Setup Detection layer converts already-observed market-state features into explicit setup candidates.

It is not a trade-signal generator and does not assign a confidence score, probability, indicator-count score, or guaranteed outcome.

## Candidate families

The first deterministic families are:

- liquidity reversal — liquidity sweep/reclaim combined with structure shift, Price Action rejection, or Wyckoff Spring/Upthrust context;
- structure continuation — directional structure + displacement + BOS;
- breakout retest — causal Price Action retest aligned with structure direction;
- failed breakout — causal failed-breakout event;
- Wyckoff Spring / Upthrust;
- expansion — Scenario Engine expansion events.

Each family has explicit up/down candidate fields. If both directions are present on the same timestamp, AICFA marks the candidate as conflicted rather than forcing a direction.

## Context vs candidate

FVG, Order Block, Premium/Discount, absorption, CVD, taker flow and derivatives fields are exposed as context when available. They are deliberately not converted into an additive confirmation score.

This prevents a rule such as “five indicators agree, therefore trade” from being treated as a scientific validation.

## Causality

All inputs are already causal Feature Engine observations. The setup layer does not inspect future candles and does not generate future outcome labels.

setup_reference_price and setup_invalidation_price use already-observed levels only. They are contextual boundaries, not profit targets.

## Missing data

Unavailable optional sources are represented as zero/unavailable context rather than fabricated values. Setup families requiring unavailable source features simply do not trigger.

## Next stage

Historical setup candidates must later be converted into separate outcome labels and evaluated chronologically. Only after statistical validation should scoring/probability and decision logic be introduced.
