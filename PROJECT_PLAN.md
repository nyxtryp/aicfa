## Continuity checkpoint — 2026-10-03 — TASK 6 PERFORMANCE BASELINE + REWORK

### Server baseline before the new optimization
- User ran full regression on the current Task 6 implementation:
- `tests/test_features.py`: **10 passed in 70.14s**.
- Full suite: **384 passed in 105.05s (1:45)**.
- This is GREEN functionally, but materially slower than the pre-Task-6 baseline (~45–50s full suite).
- Therefore Task 6 is **not accepted as performance-final** yet.

### Diagnosis
- The remaining cost was the per-candle scan of all accumulated zones. NumPy vectorization reduced Python-level work but did not change the underlying O(n × total_zones) lifecycle search.
- The implementation has now been reworked to use:
  - logarithmic price buckets for local zone lifecycle queries;
  - sorted active support/resistance indexes for nearest-level lookup;
  - heaps for retested-zone break detection;
  - explicit handling for very wide zones so the index remains causal/correct.

### New commits
- `fb9010cb9fa9f1b2b9b2223fb06b6b7e8796cfd3` — `perf: index zone lifecycle by price buckets`
- `010c2c8bdcd8c8db982d2e5a9fadc733d8b95b8b` — `fix: key zone break heaps by zone boundaries`

### Verification
- New optimization has **not yet been server-tested**.
- Do not treat the new implementation as GREEN until focused + integration tests pass.

### Next step
Run only the focused zone contract first, then the 10,080-row feature integration. If both pass, run the full regression again and compare against the 384/105.05s baseline.

## Continuity checkpoint — 2026-10-03 — TASK 6 INTEGRATION GREEN

### Verification
- Server integration test after zone lifecycle performance fix:
- `tests/test_features.py`: **10 passed in 70.14s**.
- This confirms the unified `zone_*` feature layer integrates successfully through the full feature pipeline on the current MTF test coverage.
- Performance is improved from the previous hang/non-completion, but the 10,080-row integration path still takes about 70 seconds and should be treated as a performance observation, not as a reason to claim the task fully GREEN yet.

### Current status
- Focused zone contract: **5 passed in 0.49s**.
- Feature integration: **10 passed in 70.14s**.
- Full regression: **not run yet**.
- Task 6: **implementation/integration GREEN; final regression pending**.

### Next step
Run the full server regression. If it remains GREEN, finalize Task 6 documentation/status and move to Task 7 — Volume Evidence.

## Continuity checkpoint — 2026-10-03 — TASK 6 ZONE REACTION PERFORMANCE FIX

### What changed
- Audited the active Task 6 plan and current zone-reaction implementation.
- Confirmed the focused zone contract is already GREEN: **5 passed in 0.49s** on the server.
- Found the integration bottleneck in `zone_reaction.py`: the lifecycle rebuilt/scanned Python zone lists on every candle, which remained effectively O(n × zones) Python work on the 10,080-row MTF integration path.
- Reworked lifecycle storage/evaluation to NumPy-backed fixed arrays, removing the per-candle Python active-zone list construction and per-zone lifecycle loop while preserving causal creation and state-transition precedence.
- Commit: `dea1d542574d9c00ce72a24cefed40ec4087934b` — `perf: remove Python zone lifecycle scans`

### Verification status
- Server focused `tests/test_zone_reaction.py`: **5 passed in 0.49s**.
- Server `tests/test_features.py`: **pending after performance fix**.
- Full regression: **not run yet**.

### Next step
Run the server integration test `tests/test_features.py`. If GREEN, run the full regression, then finalize Task 6 documentation and move to the next planned task.

### Task 6 — Zone Reaction + Support/Resistance — test contract started

- Re-read the repository documentation before continuing, including README, AICFA_TZ and the current docs for Price Action, Evidence/Scenario/Setup/Decision, Market State, Live Market Data, Knowledge Base, Labels, CVD, Wyckoff and visual evidence boundaries.
- Confirmed current Price Action already exposes causal prior support/resistance levels and breakout retests, but there is no dedicated unified zone lifecycle for S/R + OB/FVG/liquidity.
- Defined the missing causal lifecycle contract: `level/zone → distance → touch → reaction → retest/break → confirmation/cancellation`.
- Added focused contract tests before production changes:
  - `7ab1352462580458ae3d2d540ad3cd33ae44c047` — test: define causal zone reaction lifecycle contract
- **Server verification pending** — no production implementation has been changed yet.
# AICFA PROJECT PLAN / CONTINUITY

## Continuity checkpoint — 2026-10-03 — TASK 5 FVG / IMBALANCE LIFECYCLE

### What was done
- Task 4 — Order Block Lifecycle is GREEN.
- Server full regression before Task 5: 377 passed in 44.89s.
- Audited current FVG implementation and unified SMC integration before changing code.
- Confirmed features.py already propagates FVG fields and passes FVG data into unified SMC.
- Task 5 implementation committed:
- 76257aa — feat: add causal FVG lifecycle depth
- 82d6dde — test: cover FVG lifecycle states and concurrent zones
- b3f7a9cc6bbf8aaa7f6c8602bd942e7f0e3a51dd — fix: preserve strongest active FVG lifecycle state
- FVG lifecycle distinguishes UNTOUCHED, TOUCHED, PARTIAL, FILLED, INVALIDATED.
- Added causal penetration ratio 0..1.
- Added FVG creation provenance fields.
- Multiple simultaneously active bullish/bearish FVG zones are tracked independently instead of a newer zone overwriting an older active zone.
- Existing binary fields are retained for compatibility.
- Added causal regression coverage for creation, touch/partial/fill, invalidation, concurrent active zones and causal provenance.
- Fixed concurrent-zone aggregation so a newer UNTOUCHED FVG does not erase the lifecycle state of an older reacted active FVG.

### Verification status
- Server focused FVG regression: **9 passed in 0.52s**.
- The focused failure was caused by lifecycle aggregation when a new active FVG appeared while an older FVG had already been touched; production logic was corrected in b3f7a9cc6bbf8aaa7f6c8602bd942e7f0e3a51dd.
- Full server regression after the FVG aggregation fix: **379 passed in 47.04s**.
- Task 5 — FVG / Imbalance Lifecycle is **GREEN**.

### Current task
Task 6 — Zone Reaction + Support/Resistance

1. Audit the current zone-reaction and support/resistance implementation.
2. Define the missing causal lifecycle: level/zone → distance → touch → reaction → retest/break → confirmation/cancellation.
3. Add focused tests before changing production logic.

## Authoritative SMC integration sequence
1. Confirmed Swing — GREEN.
2. Causal BOS / CHoCH / MSS — GREEN.
3. Liquidity Lifecycle — GREEN.
4. Order Block Lifecycle — GREEN.
5. FVG / Imbalance Lifecycle — GREEN.
6. Zone Reaction + Support/Resistance — NEXT.
7. Volume Evidence.
8. Structural Entry / SL / TP.
9. Conservative Backtest / Evaluation.

## Product UX requirement
End-user UX remains asset-only: user enters an asset such as BTC; AICFA internally evaluates all relevant setup variants/horizons and returns the available setup scenarios. User does not select the trading mode.

## Core architecture rules
- AICFA is a specialized crypto-analysis system, not a wrapper around another AI.
- Core analysis is chart/market-data native.
- SMC includes market structure, liquidity, BOS/CHoCH/MSS, HH/HL/LH/LL, FVG/imbalance, Order Blocks, premium/discount, displacement, Wyckoff and related price-action evidence.
- Optional derivatives/microstructure feeds remain auxiliary evidence and do not independently manufacture setups.
- No fabricated missing data.
- All structural/lifecycle logic must remain causal; no future leakage.
- Do not import external fixed strategy, scoring, timeframe hierarchy, killzones, fixed RR or trade labels.
- Every meaningful implementation/test/deploy step must be recorded here with commit SHA, actual server result, status and next step.
