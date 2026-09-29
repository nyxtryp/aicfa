# AICFA — Causal Wyckoff Representation

## Purpose

This layer converts observable price behaviour into deterministic,
Wyckoff-inspired events and state context. It is a **descriptive market-state
layer**, not a trade-signal generator.

It deliberately does not claim that OHLCV data can prove the hidden intent of
large participants or identify a textbook Accumulation/Distribution schematic
with certainty.

## Source contract

Required:

- `timestamp` — availability time of the completed candle;
- `open`;
- `high`;
- `low`;
- `close`.

Optional:

- `volume`.

The layer is asset-agnostic and timeframe-agnostic. The same definitions can
be applied to BTC/USDT, ETH/USDT, SOL/USDT and other supported digital assets
and to supported timeframes. If volume is unavailable, volume-derived fields
are omitted; values are never invented.

## Causal range

Trading-range boundaries use only prior candles:

```text
range_high(T) = max(high[T-N : T-1])
range_low(T)  = min(low[T-N : T-1])
```

Therefore a candle cannot use its own high/low to define the level that it
then breaks.

Future observations cannot rewrite earlier Wyckoff features.

## Observable events

### Trading Range

`wyckoff_in_range` describes whether the current close remains inside the
prior observed range.

### Spring candidate

A spring candidate is:

- current low penetrates the prior lower boundary;
- current close reclaims the prior lower boundary.

This is an observable price event. It is not proof of a complete Wyckoff
Spring schematic.

### Upthrust candidate

An upthrust candidate is:

- current high penetrates the prior upper boundary;
- current close falls back below the prior upper boundary.

Again, this is an observable candidate, not proof of participant intent.

### Sign of Strength / Sign of Weakness

These are descriptive range escapes where the close finishes beyond the prior
boundary and the candle body occupies at least half of its range.

### Accumulation / Distribution proxies

The layer exposes `wyckoff_accumulation_proxy` and
`wyckoff_distribution_proxy` only as explicit proxies derived from
observable spring/upthrust context and range position.

They must not be interpreted as ground-truth labels. Historical statistical
evaluation is required before predictive use.

## State

`wyckoff_state` provides a compact descriptive context:

- `neutral`;
- `trading_range`;
- `breakout_up`;
- `breakout_down`;
- `spring_candidate`;
- `upthrust_candidate`;
- `sign_of_strength`;
- `sign_of_weakness`.

State precedence is deterministic. It is context, not a LONG/SHORT decision.

## Volume context

When volume is present, the layer adds causal relative-volume and volume
expansion features based on strictly prior volume observations.

Volume absence is a normal data-availability condition.

## Relationship to the rest of AICFA

Wyckoff complements, rather than replaces:

- SMC;
- market structure;
- liquidity;
- Price Action;
- volume/volatility;
- CVD/taker flow;
- derivatives;
- optional order-book/microstructure data.

Order Book is **not required** for Wyckoff or for the core AICFA market
representation. If it is unavailable, the Wyckoff layer remains fully usable.

No Wyckoff feature is a standalone trading signal.
