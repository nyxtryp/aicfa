# AICFA — Project Control Plan

The Scenario Engine implementation is the next analytical layer after verified MTF integration.

## 2026-09-29 — Scenario Engine implementation

Implementation commits:
- `9c435ab89d54aa1efe89a94e58875474e3544099` — Add causal Scenario Engine.
- `82e07614983505649dffe2e2a5c391371be4398b` — Add Scenario Engine tests.
- `232035f8dc39694c1d186aa4d3d0d84c813e36e2` — Integrate Scenario Engine into `build_features()`.

Implemented:
- causal scenario hypotheses derived only from the verified SMC market-state representation;
- expansion up/down events requiring matching displacement and structural BOS;
- continuation up/down events using established structure plus directional displacement;
- reversal up/down events from causal structure shifts or explicit liquidity sweep/reclaim plus displacement;
- failed-breakout events from liquidity sweep/reclaim observations;
- range context when structural state is ready without a current break/displacement event;
- independent scenario flags are retained so overlapping hypotheses are not collapsed into a confirmation-count score;
- a compact `scenario_event` taxonomy is emitted only when exactly one scenario family is active;
- `scenario_direction` records scenario-event direction only and is not a trade verdict;
- descriptive current-close entry reference; actual risk sizing and final entry/SL/TP construction remain deferred to Risk/Decision layers.

Design constraints preserved:
- no generic scenario score;
- no confirmation counting;
- no future data;
- scenarios remain measurable hypotheses to evaluate against historical outcomes;
- the engine does not replace the later Risk Engine or Decision Engine.

Tests cover:
- scenario namespace and required fields;
- absence of scenario score/signal fields;
- mechanical failed-breakout detection;
- matching displacement+BOS requirement for expansion;
- future-change invariance;
- invalid state validation.

Server verification: **pending**.

Known limitation:
- current scenario rules are the first mechanical hypothesis layer, not the final trading policy;
- MTF context is already present in the feature frame, but scenario-specific HTF alignment rules are intentionally not hard-coded yet;
- invalidation reference is currently reserved for the later Risk/Decision layer rather than inventing SL/TP policy prematurely.

**Next concrete action:** run the full FrostDeploy pytest suite against this Scenario Engine implementation. If green, record the verification and proceed to the next planned analytical refinement/dataset stage without jumping to ML.
