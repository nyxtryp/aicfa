# AICFA — Canonical Market State

## Purpose

`build_market_state()` converts already-built causal features, scenarios and setup candidates into a stable machine-readable representation of the current market state.

It is a representation layer, not a trading signal, score, probability model or decision engine.

## Flow

```text
Raw Market Data
  ↓
Feature Engine
  ↓
Scenario / Setup Detection
  ↓
Canonical Market State
  ↓
Setup Event Engine
  ↓
Future Label / Validation
  ↓
Risk / Decision
```

## Core state

The canonical state preserves:

- market-structure direction;
- scenario activity, direction and event family;
- setup activity and direction;
- setup conflict state;
- primary setup family when there is exactly one non-conflicted family;
- SMC readiness;
- premium/discount context;
- volatility and volume regimes;
- Wyckoff state;
- descriptive Price Action context.

A conflicted setup remains neutral. The state layer never resolves opposing candidates by preference.

## Optional context availability

The state exposes explicit availability flags for:

- CVD;
- taker flow;
- absorption;
- order book.

Unavailable sources remain unavailable. A zero numeric value is not interpreted as proof that a source existed and measured zero.

`market_state_context_availability_mask` is a bitmask describing source availability. It is not a confidence score.

## State changes

`market_state_changed` marks a change in the canonical descriptive state compared with the immediately preceding observation.

This is intended as a deterministic input for the future Setup Event Engine:

```text
state unchanged
  → no duplicate state event

state changed
  → evaluate event lifecycle
```

The flag itself does not classify an event as created, strengthened, invalidated or expired. Those lifecycle semantics belong to the later Setup Event Engine.

## Causality

All fields use only the already available row and past observations represented in the supplied feature/state frame. Future rows cannot rewrite earlier state.

The state layer does not generate future outcome labels. Historical outcome labels remain a separate pipeline.
