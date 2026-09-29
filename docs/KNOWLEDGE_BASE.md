# AICFA Knowledge Base v1

The Knowledge Base is the durable analytical knowledge layer of AICFA.

It is not a candle database, screenshot training dataset, trade-signal list, visual parser, or live-data provider. It interprets evidence supplied by those input paths.

## Knowledge entry contract

Every concept has:

- stable identifier;
- domain;
- definition;
- observable evidence;
- relationships to other concepts;
- confirmations;
- invalidations;
- counterexamples;
- setup relevance.

The distinction is deliberate: a concept describes market behavior; it does not automatically become a LONG or SHORT signal.

## Initial knowledge domains

1. Market Structure: BOS, CHoCH.
2. Liquidity: sweeps and liquidity context.
3. Imbalance: FVG.
4. Order Blocks.
5. Premium / Discount.
6. Price Action.
7. Wyckoff.
8. Derivatives: price/OI relationship.
9. Risk: invalidation.

The registry is intentionally small in v1. It establishes the schema that later concepts can follow without mixing knowledge with market history.

## Runtime boundary

A future visual layer will convert a user screenshot into structured evidence. The user does not label BOS, FVG, liquidity or other concepts manually. AICFA maps what is actually visible to this knowledge registry.

If the screenshot is insufficient, AICFA requests additional timeframe(s) or chart history. It never invents unseen candles.

Live REST/WebSocket data can feed the same analytical brain when a user asks for current evidence, but live transport is not part of the Knowledge Base.

## Historical data boundary

Historical candles are optional supporting evidence for future validation or specialized models. They are not required to instantiate or query the Knowledge Base.

User screenshots are runtime evidence, not a prerequisite training dataset.

## Design rule

Knowledge is not a signal. Setup logic must evaluate context, relationships, confirmations, invalidations, contradictory evidence, timeframe context and evidence quality. When evidence is insufficient or contradictory, the correct outcome is WAIT.
