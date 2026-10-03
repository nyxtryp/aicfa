## 2026-10-03 — TASK 9 — RR ↔ OUTCOME ANALYSIS GREEN / FULL REGRESSION VERIFIED

- Added causal RR ↔ outcome analysis in production commit `3118e99fee3381d01598544e60f80edbfb614e72` — `feat: add RR outcome analysis`.
- RR is derived directly from structural Entry/SL/TP geometry; it is not used as a setup-validity filter.
- Analysis preserves the observed outcome for every setup: TP, SL, TIMEOUT, or AMBIGUOUS.
- Aggregate `mean_rr` is calculated only across resolved TP/SL outcomes; unresolved TIMEOUT/AMBIGUOUS outcomes remain visible and are excluded from that resolved aggregate.
- Mismatched setup/evaluation counts are rejected explicitly.
- Added fold-local RR ↔ outcome analysis in production commit `6a35228f43b328801c7a5b86fc0ed725b4fac913` — `feat: analyze RR outcomes across folds`.
- Fold analysis keeps chronological validation boundaries separate; observations from one fold are not mixed into another.
- Added two fold-analysis contract tests in `431946f8dca0ea6f63e0a9eca3c68f6d72f0e67e` — `test: define RR analysis across chronological folds`.
- Server focused validation after fold analysis: `tests/test_evaluation.py` = **19 passed in 0.50s**.
- Server full regression after the fold-analysis layer: **421 passed in 81.74s (0:01:21)**.
- Result: **0 failed, 0 skipped**.
- Regression increased from 419 to 421 tests after the two fold-analysis contract tests.
- No hit-rate, profitability, confidence, predictive-performance, or trading-performance claim is made from this analysis.

### Current Task 9 status

- Conservative single-setup evaluator: GREEN.
- Batch evaluation/statistics: GREEN.
- Causal label purging: GREEN.
- Chronological purged validation folds: GREEN.
- RR ↔ outcome analysis: GREEN.
- RR ↔ outcome analysis across chronological folds: GREEN.
- Fold outcome statistics by chronological folds: GREEN.
- Full regression: **GREEN — 423/423**.
- Task 9 remains ACTIVE.

### 2026-10-03 — FOLD OUTCOME STATISTICS GREEN / FULL REGRESSION VERIFIED

- Added fold-local outcome statistics in production commit `d0b29625fa5abfcd3f1bf8d0d9654567a5c6a110` — `feat: add fold outcome statistics`.
- Added contract coverage in test commit `21e2e7e8c2a2a82df0c5de0c51a1543989713a1e` — `test: define fold outcome statistics contract`.
- Corrected test construction to use the real `BatchEvaluation` contract, including required `results`, in commits `afb3968a1efb64497c922fcf1954990b8089aad7`, `bc9b2c9a056d5b740432e35c6789d6676d890562`, and `781fb414ee590efd8502984044c4a0197430db7a`.
- Fold statistics preserve each fold independently: TP/SL/TIMEOUT/AMBIGUOUS counts, resolved count, TP rate among resolved outcomes, and mean gross return among resolved outcomes.
- No cross-fold pooling or cross-fold average is created.
- Focused server validation: `tests/test_evaluation.py` = **21 passed in 0.54s**.
- Full server regression: **423 passed in 79.60s (0:01:19)**.
- Result: **0 failed, 0 skipped**.
- No performance, confidence, hit-rate, profitability, or predictive-performance claim is made from these statistics.

### Next exact action

Continue Task 9 from the existing chronological purged-fold foundation with the next evaluation/statistics layer defined by the project plan, preserving strict causal boundaries and avoiding fixed RR filters, confidence scores, arbitrary thresholds, or unsupported performance claims.


### 2026-10-03 — SETUP OUTCOME JOURNAL GREEN / FULL REGRESSION VERIFIED

- Added historical per-setup outcome journal in production commit `6190b3817e46eb9fb4ed4cf6b28d61e5613f1e0a` — `feat: add historical setup outcome journal`.
- Added contract coverage in test commit `9507961cff3652a6a8fa5df1ef8191cdbc4402ef` — `test: define setup outcome journal contract`.
- Each journal record preserves setup timestamp, direction, Entry/SL/TP, derived RR, causal outcome, outcome offset, exit price, and gross return.
- TP, SL, TIMEOUT, and AMBIGUOUS remain explicit; unresolved outcomes do not receive fabricated exit prices or returns.
- The journal pairs already-defined setups with already-computed causal evaluations; it does not create or modify Entry/SL/TP.
- Focused server validation: `tests/test_evaluation.py` = **26 passed**.
- Full regression after this layer: **426 passed in 82.05s (0:01:22)**.
- Result: **0 failed, 0 skipped**.
- Task 9 remains ACTIVE.

### Next exact action

Continue Task 9 from the verified historical setup journal and chronological evaluation foundation with the next evaluation/statistics layer defined by the project plan, preserving strict causal boundaries and avoiding fixed RR filters, confidence scores, arbitrary thresholds, or unsupported performance claims.


### 2026-10-03 — DIRECTIONAL OUTCOME STATISTICS FOCUSED GREEN

- Added directional historical setup outcome statistics in production commit `0a0c1232773942cef9dffddb614be957020f86b9` — `feat: add directional setup outcome statistics`.
- Added contract coverage in test commit `459d9d9b3f7e843540d2950827003e937adaaea1` — `test: define directional setup outcome statistics contract`.
- Statistics keep Long/Short outcomes separated; TP/SL/TIMEOUT/AMBIGUOUS remain visible and resolved metrics exclude unresolved outcomes.
- Server focused validation: `tests/test_evaluation.py` = **28 passed in 0.58s**.
- Full regression is not yet rerun after this layer.
- Task 9 remains ACTIVE.

### Next exact action

Run the full regression after directional outcome statistics, then continue Task 9 from the verified journal/evaluation foundation.


### 2026-10-03 — AICFA PRODUCT DIRECTION: THREE CORE HORIZONS + AUTONOMOUS MARKET SCANNER

- Product direction is now fixed around **three main trading horizons** in the primary AICFA system:
  - **Intraday** — 5m–1h, minutes to hours.
  - **Swing** — 1h–1d, hours to days.
  - **Position** — 4h–1w, days to weeks.
- **Scalping is explicitly separated from the primary AICFA system.** It will be implemented later as a dedicated website window with its own faster/microstructure logic and approximately minute-level updates. Scalping must not distort or replace the causal architecture of the three primary horizons.
- The three horizons are contexts of the shared Setup Engine, not three independent engines.
- The primary system must not remain request-driven ("analyze BTC when the user asks"). The target product behavior is an **autonomous market scanner**:
  1. Maintain a configured list of supported coins/markets.
  2. Continuously obtain the required market data for those markets.
  3. Analyze each market across Intraday, Swing, and Position contexts.
  4. Search automatically for currently formed setup candidates.
  5. Emit only setups that satisfy the existing structural/causal contracts.
  6. Produce a concrete **LONG / SHORT** setup when a valid directional setup exists, including Entry, SL, TP1/TP2 and RR where structurally available.
  7. Produce WAIT / NO TRADE when no valid directional setup exists; no forced signal.
  8. Surface results in a dedicated, visually clear **website setup window/dashboard**. Telegram is not part of the primary delivery path.
- The scanner must work across multiple assets, not BTC-only. BTC is one market in the configured universe, not a special-case engine.
- The future website setup window should support at minimum:
  - live/new setup feed;
  - coin/market;
  - horizon (Intraday / Swing / Position);
  - LONG / SHORT direction;
  - Entry;
  - SL;
  - TP1 / TP2;
  - RR;
  - setup timestamp / freshness;
  - setup status / lifecycle;
  - enough structural explanation to show why the setup exists.
- The autonomous scanner must reuse the existing AICFA architecture: confirmed swing → causal BOS/CHoCH/MSS → liquidity → OB/FVG lifecycle → zone reaction → volume evidence → structural Entry/SL/TP → conservative evaluation. Do not introduce a parallel generic indicator scanner.
- Fixed counts of setups per horizon are **not** a requirement. The system should discover whatever valid setup families are currently present rather than manufacture a target number of signals.
- The existing four-way classification is retained only as historical/product context; the primary production system is now explicitly three-horizon, with Scalping separated.
- A dedicated **coin universe/list configuration** must be designed before autonomous scanning is implemented. It should allow the user to define which coins/markets AICFA monitors, rather than hardcoding BTC or a fixed small set.
- Before implementing the autonomous scanner, perform a complete repository audit of `src/aicfa` and tests to identify all existing capabilities for:
  - market data and market context;
  - MTF preparation;
  - setup analysis;
  - candidate generation;
  - Entry/SL/TP/RR;
  - historical evaluation;
  - mode iteration;
  - multi-setup aggregation;
  - deduplication/lifecycle;
  - any existing orchestration layer.
- Do not create a duplicate orchestration/scanner if an existing component can be extended.
- Planned implementation sequence after the audit:
  1. Finish/record the current Task 9 regression state.
  2. Audit the complete existing setup/orchestration architecture.
  3. Define the three-horizon autonomous analysis contract.
  4. Define configurable monitored coin/market universe.
  5. Build/extend one shared multi-market orchestration layer.
  6. Make the scanner discover all valid current setups across the three horizons.
  7. Add causal deduplication, setup lifecycle/freshness and conflict handling where required.
  8. Expose scanner results through the website setup window.
  9. Add persistent/historical setup records so displayed setups can be evaluated after completion.
  10. Validate the complete flow on multiple markets, not BTC alone.
- Quality principle: AICFA should prefer **no signal** over a fabricated or weakly justified LONG/SHORT. No arbitrary confidence score, fixed RR filter, or unsupported profitability claim should be introduced merely to make the scanner produce more signals.
- Scalping remains a later, separate product surface and implementation task.

### 2026-10-03 — DIRECTIONAL STATISTICS FULL REGRESSION VERIFIED

- After directional outcome statistics commit `0a0c1232773942cef9dffddb614be957020f86b9`, server full regression completed successfully: **428 passed in 82.05s (0:01:22)**.
- Result: **0 failed, 0 skipped**.
- Task 9 remains ACTIVE.


### 2026-10-03 — EXPLAINABLE SETUP CONTRACT FIXED

- AICFA setup output is now planned as an **explainable trade scenario**, not a bare LONG/SHORT signal.
- Every displayed setup should carry structured evidence from the actual analysis pipeline:
  - market and timeframe context;
  - horizon: Intraday / Swing / Position;
  - direction: LONG / SHORT;
  - Entry;
  - structural SL;
  - TP1 / TP2 where structurally available;
  - RR derived from Entry/SL/TP;
  - structure evidence (HH/HL/LH/LL, BOS/CHoCH/MSS);
  - liquidity evidence and sweeps;
  - OB/FVG evidence and lifecycle;
  - zone reaction / confirmation;
  - volume evidence where available;
  - explicit invalidation condition;
  - setup timestamp, freshness and lifecycle status.
- The website should present this as a clear **trade description/card** so the user can see not only what AICFA found, but why the setup exists and what would invalidate it.
- The explanation must be generated from real structured evidence produced by AICFA. Do not add an LLM-written explanation layer that invents reasons not present in the underlying analysis.
- A valid setup remains a causal structural result. The description is a presentation of evidence, not an additional signal filter.
- Planned build direction is now explicit: **analyze the existing code → extend the existing architecture → build the autonomous multi-market scanner → expose explainable setups on the website**.
- No implementation should begin by creating a parallel generic signal/indicator scanner.
- Next implementation step remains the complete repository audit of src/aicfa and tests, followed by the smallest architectural extension needed for autonomous multi-market discovery.
