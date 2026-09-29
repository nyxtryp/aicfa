# AICFA — Price Action

## Purpose

Price Action is a deterministic, causal descriptive layer. It formalizes candle
behaviour and price interaction with previously observed levels. It does not
produce LONG/SHORT signals.

## Source contract

Required fields:

- `timestamp` — availability time of the completed candle;
- `open`;
- `high`;
- `low`;
- `close`.

Volume is not required by this layer.

## Features

The layer provides:

- candle body and body/range;
- upper/lower wick proportions;
- close location inside the candle;
- descriptive bullish/bearish rejection;
- prior resistance/support levels;
- breakout and failed-breakout events;
- breakout retests;
- short candle-sequence continuation;
- short candle-sequence reversal;
- range expansion/compression;
- consolidation classification.

Prior support/resistance levels are calculated from candles strictly before the
current row.

## Causality

For event time T, only candles with availability timestamps <= T may affect the
result. Rolling levels exclude the current candle when defining prior levels.
Future candles cannot rewrite earlier Price Action features.

## Interpretation limits

These are measurable descriptions, not universal market truths. A rejection,
breakout, retest, reversal, expansion or consolidation event does not by itself
imply a trade direction or expected return.

The thresholds are explicit parameters and must be evaluated historically before
being treated as predictive.

## Relationship to SMC

Price Action complements SMC, liquidity, structure, volume, derivatives and
microstructure. It does not replace those layers and should not be converted into
a score by simple indicator counting.
