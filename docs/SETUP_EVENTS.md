# AICFA — Setup Event Engine

## Purpose

`build_setup_events()` converts the canonical Market State into a causal lifecycle of setup events.

It is an event layer, not a probability model, score, ranking, trade signal or execution engine.

## Lifecycle

```text
created
   ↓
strengthened / updated
   ↓
invalidated
   ↓
expired
```

A new setup replacing an existing setup can produce an invalidation of the previous identity and a creation of the new identity on the same observation.

## Identity

A live setup identity consists of:

- descriptive setup family;
- resolved direction.

Conflicted setups have no directional identity and therefore do not generate directional events.

## Causality

Only the current canonical state and prior observations are used. Future observations cannot rewrite earlier event rows.

`setup_event_outcome` is intentionally empty in the live event layer. Historical outcomes are a separate future-label/validation pipeline and must never leak into current scanner state.

## Event types

- `created` — a non-conflicted directional setup identity appears when no prior active identity exists;
- `strengthened` — the same setup identity remains active and the descriptive state changes;
- `invalidated` — a previous setup identity disappears or is replaced;
- `expired` — an invalidation occurs while the current state has no active setup.

This layer deliberately does not claim that an event will lead to a profitable trade.
