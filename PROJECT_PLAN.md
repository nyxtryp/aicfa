## 2026-10-03 — TASK 7 VOLUME EVIDENCE — FOCUSED CONTRACT GREEN

- Production implementation commit: `89aa9bc23eace629cb842d4bd9772c88d919cca4` — `feat: add causal volume evidence layer`.
- Focused contract tests commit: `367abf502d9a8f160d9835bc864e6c05c4343d8d` — `test: define causal volume evidence contract`.
- Server validation: `tests/test_volume_evidence.py` = **7 passed in 0.52s**.
- Contract covers relative volume, z-score, expansion/dry-up, BOS/breakout evidence, liquidity sweep/rejection, displacement, future-leakage protection, no artificial `volume_evidence_score`, and negative-volume validation.
- Volume Evidence remains an observation/evidence layer; it does not manufacture BUY/SELL signals or directional scores.
- Task 7 is **focused-contract GREEN**; integration into `features.py` and `unified_smc.py` is still pending.

### Next exact action
Integrate `build_volume_evidence()` into the feature pipeline and unified SMC propagation without changing existing causal semantics. Add integration coverage first, then run the focused + integration tests before the full regression.

## 2026-10-03 — TASK 6 FINAL REGRESSION GREEN / HANDOFF

- Server full regression after the latest Zone Reaction/index optimizations: **384 passed in 79.11s (1:19)**.
- Result: **0 failed, 0 skipped** in the current automated test suite.
- Previously verified focused Zone Reaction contract: **5 passed in 0.48s**.
- Previously verified higher-timeframe integration: **1 passed in 13.75s**.
- Task 6 — Zone Reaction + Support/Resistance is now **functionally GREEN and regression-verified**.
- The current full-suite runtime is materially improved versus the recent 105.05s Task 6 baseline, but remains above the older ~45–50s pre-Task-6 baseline. This is recorded as performance debt; do not make further blind Zone Reaction changes now.
- The bad `cProfile -m pytest` diagnostic attempt is not part of validation and must not be repeated. The current acceptance is based on the real full pytest regression above.

### Current project direction

The authoritative SMC sequence remains:
1. Confirmed Swing — GREEN.
2. Causal BOS / CHoCH / MSS — GREEN.
3. Liquidity Lifecycle — GREEN.
4. Order Block Lifecycle — GREEN.
5. FVG / Imbalance Lifecycle — GREEN.
6. Zone Reaction + Support/Resistance — **GREEN / accepted**.
7. **Volume Evidence — NEXT**.
8. Structural Entry / SL / TP.
9. Conservative Backtest / Evaluation.

### Next exact action

Start **Task 7 — Volume Evidence**:
1. Audit the existing volume/volatility/CVD evidence implementation and current feature/unified-SMC propagation.
2. Define the causal Volume Evidence contract before changing production logic.
3. Add focused regression tests first.
4. Implement only after the contract is covered.
5. Run focused tests, then full regression.
6. Update this file with every commit and actual server result/runtime.

Do not move to Structural Entry / SL / TP until Task 7 is functionally integrated and regression-green.

## 2026-10-03 — TASK 6 third-pass zone index fix — VERIFIED

- Server focused validation after commit `3214766ab725ab6dce890315299d7f2a11ddb590`: `tests/test_zone_reaction.py` = **5 passed in 0.48s**.
- Server higher-timeframe integration after the same fix: `tests/test_features.py::test_feature_integration_exposes_required_higher_timeframes` = **1 passed in 13.75s**.
- This materially improves the previous **67.71s** regression and the earlier **25.88s / 24.21s** measurements.
- Root cause/fix is validated: incrementally maintaining already-built zone bucket indexes avoids repeated large index rebuilds as zones are created.
- Full `tests/test_features.py` and full-suite regression have **not** yet been rerun after this optimization.
- Task 6 remains open pending profiling and final regression acceptance.

### Current project direction
AICFA is being built as an independent, data-native crypto-analysis system. The SMC sequence is: Confirmed Swing → causal BOS/CHoCH/MSS → Liquidity Lifecycle → Order Block Lifecycle → FVG/Imbalance Lifecycle → Zone Reaction + Support/Resistance → Volume Evidence → Structural Entry/SL/TP → Conservative Backtest/Evaluation.

End-user UX remains asset-only: user supplies an asset such as BTC; AICFA internally orchestrates relevant horizons/setup variants. Core logic must remain causal, avoid fabricated missing data/future leakage, and not depend on order-book input.

### What remains
1. Finish Task 6: profile the current **13.75s** integration path, target the actual bottleneck, then run focused + integration + full regression.
2. Task 7 — Volume Evidence.
3. Task 8 — Structural Entry / SL / TP.
4. Task 9 — Conservative Backtest / Evaluation.
5. Stabilize FindSetup so asset input is enough and AICFA internally selects necessary horizons/setup variants.
6. Later: scanner/alerts and broader asset coverage; no live-trading dependency.

### Exact next action
Profile the complete 10,080-row `build_features()` path on the server. Do not make another blind Zone Reaction change. After profiling, optimize only the measured bottleneck, then run:
- `tests/test_zone_reaction.py`
- `tests/test_features.py::test_feature_integration_exposes_required_higher_timeframes`
- full `pytest -q` only after the targeted change remains green.

## 2026-10-03 — TASK 6 third-pass zone index fix

- Server validation of the previous `_active_level()` optimization: `tests/test_zone_reaction.py` = **5 passed in 0.53s**.
- The higher-timeframe integration then completed, but regressed to **1 passed in 67.71s**.
- Root cause found in the new lazy indexes: every newly created zone invalidated the already-built sorted bucket indexes. On a long history, `_active_level()` therefore rebuilt large historical bucket lists repeatedly, turning the optimization into a repeated sort/rebuild path.
- Fixed `src/aicfa/zone_reaction.py` to maintain existing normal/wide candidate and midpoint indexes incrementally with `bisect.insort` when a new zone enters an already-indexed bucket, instead of invalidating and rebuilding the whole bucket.
- Commit: `3214766ab725ab6dce890315299d7f2a11ddb590` — `perf: keep zone bucket indexes incrementally sorted`.
- No lifecycle/causality rules were intentionally changed.
- **Server validation pending.**

### Next exact action

Run `tests/test_zone_reaction.py`. If green, run the single higher-timeframe integration test again and compare against **67.71s**. Do not run the full suite until this regression is resolved.

## 2026-10-03 — TASK 6 active-level second-pass optimization (server test pending)

- Latest server verification before this code change: `tests/test_zone_reaction.py` = **5 passed in 0.44s**.
- Higher-timeframe integration after the previous candidate-lookup optimization: `tests/test_features.py::test_feature_integration_exposes_required_higher_timeframes` = **1 passed in 25.88s** (previously 24.21s), so that optimization did not improve the full integration runtime.
- GitHub inspection identified the remaining avoidable cost in `_active_level()`: even after bucket selection, it materialized every zone from each selected bucket and ran NumPy over the whole bucket population on every candle.
- Implemented a lazy midpoint-sorted bucket index for normal and wide zones. Nearest-level lookup now performs an exact binary-search/expansion around the candle price and stops once remaining midpoints cannot beat the current best distance. Lifecycle semantics and the selected occupied-bucket strategy are unchanged.
- Commit: `f915d20b5b9e7bafbaedb2a93020d84ea55dfacf` — `perf: avoid full bucket scans in active zone lookup`.
- **Server validation pending.**

### Next exact action

Run only `tests/test_zone_reaction.py`. If green, immediately rerun the single higher-timeframe integration test and compare its exact runtime with **25.88s**. Do not run the full suite yet.

## 2026-10-03 — TASK 6 active-level lookup rework (tests pending)

- `faulthandler` diagnostics on the 10,080-row feature integration repeatedly stopped inside `zone_reaction._active_level()`, confirming the runtime bottleneck was the nearest-zone lookup rather than MTF imports.
- Root cause: the previous bucket lookup walked outward radius-by-radius and could traverse thousands of empty price buckets for every candle and for both support/resistance.
- Reworked `src/aicfa/zone_reaction.py` to maintain sorted occupied bucket IDs and inspect only the current occupied bucket plus its nearest occupied neighbors; wide zones remain explicitly checked so the lookup stays exact.
- Commit: `2a24cc1f5481b79d0d78041b70227cd6dd90ffd7` — `perf: use nearest occupied buckets for active zone lookup`.
- No lifecycle thresholds, creation timing, touch/reaction/retest/break state rules were intentionally changed.
- Server validation is pending.

### Next exact action
Run only `tests/test_zone_reaction.py`. If it passes, run the previously hanging `tests/test_features.py::test_feature_integration_exposes_required_higher_timeframes` and record the exact runtime before any full-suite run.

## 2026-10-03 — build_features performance: liquidity active-pool bookkeeping

- User stopped the slow `tests/test_features.py` run after it stalled at `...`; no result was claimed.
- MTF optimization remains validated separately: `tests/test_multi_timeframe.py` = 6 passed in 0.73s.
- GitHub inspection identified a hot path in `src/aicfa/liquidity.py`: every candle rebuilt six filtered active-pool lists from the entire historical pool list, adding substantial Python allocation/work inside the row loop.
- Optimization commit: `5deb10c6359917084b9606ae8501b4f5b1e12037` (`perf: avoid rebuilding liquidity active pool lists`). Active buy/sell and external/internal counts are now maintained incrementally; latest active level lookup is retained semantically with a fallback scan only when the previous latest pool becomes inactive.
- This is a performance-only bookkeeping optimization; pool creation/sweep/break conditions were not intentionally changed.
- Next: run the focused liquidity tests first, then re-run `tests/test_features.py` once.

## 2026-10-03 — MTF focused validation

- Server validation after the targeted MTF optimization: `tests/test_multi_timeframe.py` = **6 passed in 0.73s**.
- This confirms the focused MTF behavior remains green after the lightweight `build_structure()` path was introduced.
- Performance improvement itself is not yet accepted; the integration benchmark is still pending.
- Next exact action: run `tests/test_features.py` once and compare against the previous stalled >4 minute run / prior 57.03s baseline.

## 2026-10-03 — MTF performance diagnosis and targeted optimization

- Confirmed server-side slowdown: `tests/test_features.py` stalled on `test_feature_integration_exposes_required_higher_timeframes`; first three tests passed before the long-running test.
- Measured `build_features()` by source timeframe on the server: 5m (2016 rows) = 16.60s; 15m (672) = 2.52s; 1h (168) = 0.60s; 4h (42) = 0.46s; 1d (7) = 0.39s; 1w (1) = 0.41s.
- Code inspection showed `build_features()` invokes MTF after the full feature pipeline, while `build_multi_timeframe_structure()` unnecessarily called the full `build_structure()` for each HTF frame.
- Targeted optimization committed directly to `main`:
  - `8811b843d8f5505731165ea8ec6949672423cfdf` — added optional lightweight structure flags.
  - `64a457195dedf0187331df9d1f88182547fbbb77` — MTF now requests only external structure needed for its 15 mapped columns, skipping internal structure, protected levels, and pivot/confirmation timestamp generation.
  - `7a4904db7df0e8c7b6adf4ed99a7ba985ef22206` — corrected indentation in the structure optimization block; final code inspected on GitHub.
- Default `build_structure()` behavior remains unchanged because all three new flags default to `True`; only MTF explicitly disables the unnecessary layers.
- Server validation is still required. Do NOT claim performance improvement or test equivalence until the focused MTF/features tests run on the deployed release.
- Next exact action: run the focused MTF test file first, then `tests/test_features.py` if it passes.

## Continuity checkpoint — 2026-10-03 — TASK 6 OPTIMIZATION PASS 2 FOCUSED TEST GREEN

### Server verification
- Code commit: `76ef392bbf66dae8f48a2e4d9731e83208165463`.
- Focused `tests/test_zone_reaction.py`: **5 passed in 0.47s**.
- This validates the focused lifecycle contract after replacing per-candle candidate sets with reusable marker-array deduplication and precomputing candle bucket bounds.
- Feature integration runtime and full regression are still pending for this optimization.

### Next action
Run only `tests/test_features.py` and record the exact runtime. Compare with the previous integration result of **10 passed in 57.03s**. Run the full suite only if the integration remains green and its runtime indicates the change is safe and worthwhile.

---

## Continuity checkpoint — 2026-10-03 — TASK 6 TARGETED OPTIMIZATION PASS 2 (TESTS PENDING)

### Code change
- Commit: `76ef392bbf66dae8f48a2e4d9731e83208165463` — `perf: reuse zone candidate markers and precompute candle buckets`.
- In `src/aicfa/zone_reaction.py`, replaced per-candle candidate `set` creation/updates with a reusable integer marker array and candidate list deduplication.
- Precomputed each candle's low/high logarithmic bucket IDs using NumPy rather than computing two scalar logarithms inside every loop iteration.
- Intended as an implementation-only performance optimization. No zone lifecycle thresholds, state-transition rules, source semantics, or causal timing were intentionally changed.
- **Verification pending.** Do not consider this optimization accepted until the focused zone contract and feature integration pass; measure integration runtime before deciding whether to run the full suite.

### Next action
Run only `tests/test_zone_reaction.py`. If it passes, run `tests/test_features.py` and compare its runtime with the prior 57.03s. If focused tests fail, fix the regression before integration testing.

---

## Continuity checkpoint — 2026-10-03 — TASK 6 FULL REGRESSION GREEN

### Verified server results after latest zone hot-loop fix
- Commit under test: `1881089f2afe40dc5893793f4c6d1a4cacbf789b` — `fix: preserve candle arrays in zone reaction hot loop`.
- `tests/test_zone_reaction.py`: **5 passed in 0.60s**.
- `tests/test_features.py`: **10 passed in 57.03s**.
- Full suite: **384 passed in 84.23s (1:24)**.
- Compared with the previously recorded Task 6 full-suite result of **384 passed in 105.05s**, the latest full suite is **20.82 seconds faster**. The feature integration also improved from **86.00s** to **57.03s**.
- However, this is still slower than the earlier pre-Task-6 full-suite baseline of roughly **45–50s**. Functional regression is GREEN; performance is improved but not fully back to baseline.

### Task 6 status
- Zone Reaction + Support/Resistance focused contract: **GREEN**.
- Feature integration: **GREEN**.
- Full regression: **GREEN — 384/384**.
- Task 6 is functionally integrated. Before marking it fully closed, decide whether to make another targeted performance pass or accept the current measured regression with a recorded follow-up. Do not silently claim baseline performance has been restored.

### Next action
- Recommended next step: profile the remaining Task 6 integration cost and attempt one targeted optimization without changing lifecycle semantics; run focused zone tests and `tests/test_features.py` first, then full suite only if integration improves and remains green.
- If the next optimization does not produce a worthwhile improvement, document the trade-off and close Task 6 with the remaining performance debt explicit, then continue to Task 7 — Volume Evidence.
- Always update this file after every meaningful implementation/test/fix, with commit SHA, exact test results/runtime, current status, and the next action. This plan remains the continuity source of truth across chats.

---

## Continuity checkpoint — 2026-10-03 — TASK 6 FEATURE INTEGRATION VERIFIED; PERFORMANCE STILL UNDER REVIEW

### Server verification
- Focused `tests/test_zone_reaction.py`: **5 passed in 0.60s** after commit `1881089f2afe40dc5893793f4c6d1a4cacbf789b`.
- Feature integration `tests/test_features.py`: **10 passed in 57.03s**.
- The integration path improved from the last recorded **86.00s** to **57.03s** (about 29 seconds faster), but remains slower than the pre-Task-6 full-suite baseline (~45–50 seconds for the entire suite). Do not claim performance is solved.

### Project continuity / working agreement
- Treat this `PROJECT_PLAN.md` as the persistent source of truth across chats: record each meaningful implementation, commit, actual server test result/runtime, bug/fix, current status, next exact action, and the larger project direction.
- Never record a test/deploy as completed until the user reports the actual result or a tool verifies it.
- Keep the plan explicit enough that a new chat can resume without asking the user to retell the project.
- Preserve the asset-only user experience: the user provides an asset (e.g. BTC); AICFA internally orchestrates relevant horizons/setup variants. The long-term goal remains an independent, data-native crypto analysis system, not a thin wrapper around another model.
- Maintain causal/no-future-leakage rules and the SMC roadmap already recorded below. No live trading is being implemented as part of this Task 6 verification.

### Current status
- Task 6 focused contract: **GREEN**.
- Task 6 feature integration: **GREEN functionally**, performance **improved but still under review**.
- Full regression after commit `1881089f`: **not run**.
- Task 6 is **not yet marked fully complete**.

### Next action
1. Run the full regression only now that the feature integration passes:
   ```bash
   sudo -u fd-aicfa bash -lc '
   cd "$(readlink -f /srv/frostdeploy/aicfa/current)" &&
   PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python -m pytest -q
   '
   ```
2. Record the exact pass/fail count and runtime here.
3. If full regression passes, compare its runtime against the 384 passed / 105.05s Task 6 baseline and ~45–50s pre-Task-6 baseline. Decide whether another optimization is needed before closing Task 6.
4. Only after Task 6 is accepted, proceed to Task 7 — Volume Evidence; then Task 8 — Structural Entry / SL / TP; Task 9 — Conservative Backtest / Evaluation.

---

## Continuity checkpoint — 2026-10-03 — TASK 6 NUMPY HOT-LOOP FIX VERIFIED (FOCUSED)

### What changed
- Fixed a variable-shadowing regression introduced by the NumPy hot-loop optimization: per-candle OHLC arrays `highs/lows` were overwritten by candidate-zone arrays.
- Renamed candidate-zone arrays to `zone_highs/zone_lows`, preserving the candle arrays across iterations.
- Removed the remaining scalar pandas write for resistance breaks, writing into the result array consistently.
- Commit: `1881089f2afe40dc5893793f4c6d1a4cacbf789b` — `fix: preserve candle arrays in zone reaction hot loop`.

### Server verification
- `tests/test_zone_reaction.py`: **5 passed in 0.60s**.

### Current status / next step
- Focused zone contract: **GREEN** after the fix.
- Feature integration: **pending**; performance improvement is not yet verified.
- Full regression: **not run**.
- Run only `tests/test_features.py` next and record its runtime before deciding whether a full suite is warranted.

---

## Continuity checkpoint — 2026-10-03 — TASK 6 INTEGRATION STILL TOO SLOW

### Latest server verification
- Focused `tests/test_zone_reaction.py`: **5 passed in 0.45s**.
- Feature integration `tests/test_features.py`: **10 passed in 86.00s (1:26)**.
- Full regression: **384 passed in 105.05s (1:45)**.

### Status
- Functional correctness remains GREEN on the focused zone contract and full regression.
- Performance is **NOT acceptable / not final**. The new indexing work did not reduce the feature integration path; it is now slower than the previous 70.14s result.
- Task 6 therefore remains OPEN. Do not move to Task 7 yet.

### Current optimization target
The next pass must profile/fix the actual hot path in `zone_reaction.py`, especially:
- `_active_level()` outward scanning of sorted levels;
- per-row pandas `.iloc/.at` operations;
- Python `set`/bucket construction and scalar logarithm calls on every candle.

The next implementation should preserve the same causal lifecycle and focused contract while removing avoidable Python/pandas overhead from the 10,080-row integration path.

### Next step
Optimize the zone-reaction hot path first. After the code change, rerun **only** `tests/test_zone_reaction.py` and then `tests/test_features.py`; do not spend another full-suite run until integration runtime is materially improved.

## Continuity checkpoint — 2026-10-03 — TASK 6 FOCUSED ZONE CONTRACT GREEN

### Verification
- Server focused `tests/test_zone_reaction.py`: **5 passed in 0.45s**.
- The latest bucket/index/heap implementation preserves the focused causal lifecycle contract.

### Current status
- Focused zone contract: **GREEN**.
- Feature integration: pending after the latest optimization.
- Full regression: not run yet.
- Task 6 remains open pending integration performance verification.

### Next step
Run `tests/test_features.py` and record the exact runtime. Do not run the full suite until the integration result is known.

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


### 2026-10-03 — Task 6 performance: zone nearest-level index
- `tests/test_liquidity.py`: 8 passed in 0.52s after liquidity active-pool bookkeeping optimization.
- `tests/test_features.py` still stalls at the 4th test (`test_feature_integration_exposes_required_higher_timeframes`), so the long 10,080-row MTF integration path remains the active bottleneck.
- Root cause identified in `zone_reaction.py`: every new zone used Python `bisect.insort` and every broken zone used list removal for sorted support/resistance levels. Those operations are O(n) per mutation and can become quadratic as zones accumulate.
- Replaced sorted level maintenance with the existing spatial bucket index for exact nearest-active lookup; wide zones remain explicitly checked. Zone lifecycle creation/touch/reaction/retest/break rules were not intentionally changed.
- Commit: `392606125317356839f4f2c6cb240e8782f57948` — `perf: remove O(n) sorted zone level maintenance`.
- Next: focused `tests/test_zone_reaction.py`, then rerun `tests/test_features.py`.

- Fix follow-up: focused Zone Reaction test exposed two stale `_remove_level(...)` calls left from the removed sorted level index; added a compatibility no-op shim so lifecycle cleanup no longer references deleted bookkeeping. Commit: `ccd907855bc85c712205c329f197c0ec26643332` — `fix: remove stale sorted zone index cleanup calls`.

### 2026-10-03 — Zone Reaction follow-up: remove stale sorted-index references
- Directly fixed on GitHub `main`: removed the obsolete `_remove_level` shim and the two break-path calls that still passed deleted `support_levels` / `resistance_levels` variables. This was the cause of the `NameError`; no server file edits were made.
- Commit: `07a5a3c93aa12cf8d65445f115ec4401770398c0` — `fix: remove obsolete zone level cleanup references`.
- Validation status: **pending server deploy and focused test**; do not treat Zone Reaction as green until `tests/test_zone_reaction.py` passes.
- Next: deploy this GitHub revision, then run only `tests/test_zone_reaction.py`; after it passes, return to the slow `tests/test_features.py` integration test.

### 2026-10-03 — Zone lifecycle candidate bottleneck: second wide-zone global scan removed

- The hanging 10,080-row integration was re-audited against the deployed code after a4236083.
- Found a second independent O(n) path: the per-candle lifecycle candidate collection still iterated the entire wide_zones list before vectorized filtering. Therefore the previous wide-zone fix only optimized _active_level(); it did not remove the global scan from lifecycle evaluation.
- Replaced that scan with the existing coarse logarithmic wide-zone bucket index, using the candle's coarse bucket range and the existing candidate marker array for deduplication.
- GitHub commit: 40448a16000b2d9dae15e13f2794c0a7c49833ed — perf: remove wide zone scan from candle candidate lookup.
- No zone lifecycle thresholds, creation timing, touch/reaction/retest/break precedence or causal semantics were intentionally changed.
- Server validation is pending deployment.
- Next: deploy 40448a16, run only tests/test_zone_reaction.py; if green, run the single hanging higher-timeframe feature test. If it still stalls, capture a fresh faulthandler stack rather than waiting minutes.

### 2026-10-03 — Zone active-level bottleneck: wide-zone global scan removed
- Faulthandler evidence from the previous deployed revision repeatedly landed inside `_active_level()`, specifically the `wide_zones` loop.
- The prior optimization removed the empty-bucket radius walk but still scanned every wide zone on every candle, so the hot path could remain O(n) per candle.
- Changed `src/aicfa/zone_reaction.py`: wide zones now use a coarser logarithmic bucket index and nearest occupied coarse buckets instead of a global `wide_zones` scan.
- GitHub commit: `a4236083c91ad924bed39937f15b9635ba087cb5` — `perf: index wide zones for active-level lookup`.
- No server validation yet. Next: deploy this revision, run `tests/test_zone_reaction.py`, then the single previously hanging higher-timeframe feature integration test.

- Faulthandler evidence from the previous deployed revision repeatedly landed inside `_active_level()`, specifically the `wide_zones` loop.
- The prior optimization removed the empty-bucket radius walk but still scanned every wide zone on every candle, so the hot path could remain O(n) per candle.
- Changed `src/aicfa/zone_reaction.py`: wide zones now use a coarser logarithmic bucket index and nearest occupied coarse buckets instead of a global `wide_zones` scan.
- GitHub commit: `a4236083c91ad924bed39937f15b9635ba087cb5` — `perf: index wide zones for active-level lookup`.
- No server validation yet. Next: deploy this revision, run `tests/test_zone_reaction.py`, then the single previously hanging higher-timeframe feature integration test.


### 2026-10-03 — Zone active-level Python scan vectorized
- Diagnostic stack confirmed the remaining >5s hotspot was `zone_reaction.py:_active_level()` (stack at line 383).
- Replaced per-zone Python candidate iteration in `_active_level()` with NumPy filtering/distance calculation after collecting only the nearest occupied normal/coarse buckets.
- No zone lifecycle creation/touch/reaction/retest/break rules intentionally changed.
- Commit: `0879620f2e9c1d840551b02e65b046511e1bbb25`
- Server validation: pending deployment.
- Next: deploy this revision, run `tests/test_zone_reaction.py`, then run the isolated 10,080-row `zone_reaction` benchmark. If it is still slow, capture the next stack before changing another path.


### 2026-10-03 — Task 6 zone bottleneck resolved; feature integration verified

- Server focused Zone Reaction contract after active-level vectorization: **5 passed in 0.45s**.
- Isolated 10,080-row `build_zone_reaction()` benchmark: **0.032s**, confirming Zone Reaction itself is no longer the integration bottleneck.
- Previously hanging higher-timeframe feature integration test now completes successfully: `tests/test_features.py::test_feature_integration_exposes_required_higher_timeframes` = **1 passed in 24.21s**.
- Commit under validation: `0879620f2e9c1d840551b02e65b046511e1bbb25` — `perf: vectorize active zone level lookup`.
- This confirms the latest zone-reaction optimization removed the observed hang, while the full 10,080-row feature path still has measurable runtime (~24.21s) that may contain other costs.
- Full `tests/test_features.py` regression and full suite have **not** been rerun after this optimization.

### Next exact action
Profile the complete 10,080-row `build_features()` path to identify the remaining runtime contributors. Do not make another blind zone change; Zone Reaction is currently measured at 0.032s in isolation.

## 2026-10-03 — Zone candidate lookup optimization
- **Commit:** `6de9aa9df7c5de2dba29c82532df1ac7df8d1fc7`
- **Change:** narrowed zone-reaction candle candidates by price within each logarithmic bucket using lazy sorted indexes and binary search; avoids appending/scanning all historical zones from broad buckets.
- **Diagnostic basis:** full `build_zone_reaction` on 10,080 rows previously showed the hot stack at candidate collection (`zone_reaction.py:491`), not the active-level lookup.
- **Validation:** pending on deployed release.
- **Next:** run focused zone-reaction test, then the higher-timeframe feature integration test; if both pass, measure the 10,080-row full zone-reaction runtime once.

## Continuity checkpoint — 2026-10-03 — TASK 7 VOLUME EVIDENCE INTEGRATION GREEN

### Verification
- Production Volume Evidence layer: `89aa9bc23eace629cb842d4bd9772c88d919cca4`.
- Volume Evidence contract + integration tests: `cd7a3892dc4510906e3ff75de830aba6c7f71941`.
- Unified SMC propagation: `75d3640b44f35704c332fe8a095adec78ff37d74`.
- Features integration: `c7b21aa6605db4a6659ba538c4e6bcbfc4cb0f26`.
- Follow-up fix for optional structure event columns: `04f50ed231b73e8a8d72e2c4194b44ddde945121`.
- Server focused Volume Evidence regression: **9 passed in 1.29s**.
- The 9 tests cover causal observations, prior-only baseline, expansion/dry-up, event attachment, displacement, no future rewrite, invalid volume, unified SMC propagation and features exposure.
- No directional volume score or BUY/SELL verdict was introduced.

### Current status
- Task 7 focused contract + integration: **GREEN**.
- Full regression after Task 7 integration: **pending**.
- Task 8 Structural Entry / SL / TP must not start until the Task 7 changes survive the relevant feature/unified tests and full regression.

### Next exact action
Run the feature regression:
`tests/test_features.py`.
After that, run the full suite and record the actual result here before closing Task 7.


## 2026-10-03 — TASK 7 FINAL REGRESSION GREEN / HANDOFF TO TASK 8

### Server verification
- `tests/test_volume_evidence.py`: **9 passed in 1.29s**.
- `tests/test_features.py`: **10 passed in 49.05s**.
- Full regression: **393 passed in 81.69s (1:21)**.
- Result: **0 failed, 0 skipped** in the current automated test suite.

### Task 7 status
- Volume Evidence is fully integrated into `features.py` and `unified_smc.py`.
- Causal evidence includes relative volume, z-score, expansion/dry-up, BOS/breakout, rejection, liquidity sweep and displacement observations.
- No artificial directional volume score or BUY/SELL verdict was introduced.
- Prior-only baseline and no-future-rewrite behavior remain covered by tests.
- **Task 7 — Volume Evidence: GREEN / CLOSED.**

### Next task
**Task 8 — Structural Entry / SL / TP.**

Task 8 must build structural entry conditions from already-established causal evidence (structure, liquidity, OB/FVG, zone reaction, volume evidence), then derive structural stop-loss and take-profit levels without importing a fixed strategy, fixed RR, future information or fabricated data.

### Next exact action
Audit the existing entry/setup/SL/TP implementation and tests before changing production logic. Define the Task 8 causal contract first, then add focused regression tests before implementation.


### 2026-10-03 — TASK 8 STRUCTURAL ENTRY / SL / TP — FIRST CONTRACT FIX
- Added focused regression coverage in `tests/test_structural_entry.py`.
- Structural setup engine no longer rejects an otherwise geometrically valid setup solely because derived RR is below fixed 2.0.
- RR remains derived geometry for later evaluation; it is not a setup-generation gate.
- Execution timeframe `1m` remains excluded from Entry / Invalidation / Target price generation.
- Production implementation commit: `85467a2dcb41818186a0deb00e00244cb220f072`.
- Focused tests must be run on the server before marking this slice GREEN.
- Next Task 8 slice: make invalidation explicitly structural/case-dependent rather than selecting the nearest arbitrary level.


## 2026-10-03 — TASK 8 STRUCTURAL ENTRY / SL — SERVER GREEN

- Structural SL production commit: `d34c6fc9b8484329135bfc558214aa63ab13df29`.
- Structural SL contract verified with MTF: `tests/test_setup_engine_mtf.py` + `tests/test_structural_entry.py` = **14 passed in 0.63s**.
- Structural Entry focused-contract tests commit: `a2dc525180e36a521219c63dfd518844b7851477`.
- Structural Entry production commit: `44b2f5ea3cd7eefad0dee74ca668ea7327ee2e3c`.
- Entry + MTF contract verified: **15 passed in 0.64s**.
- Full regression after Entry + SL: **396 passed in 82.20s (1:22)**.
- Entry now requires causal zone reaction/confirmation; BOS/CHoCH, displacement, sweep rejection and structural context are used as confirmation evidence. Volume Evidence can confirm but cannot manufacture an Entry level.
- 1m remains excluded from structural Entry, Invalidation and Target generation.
- Structural SL uses structural invalidation only: Continuation prefers previous swing then sweep; Reversal / Breakout Failure prefer sweep then previous swing. Active liquidity is treated as a draw/target, not an automatic SL.
- If no valid structural invalidation exists beyond Entry, no fabricated SL is emitted.

### Current Task 8 status
Structural Entry: **GREEN**.
Structural SL: **GREEN**.
Full regression: **GREEN — 396/396**.
Task 8 remains **ACTIVE** because the Target/TP contract is not yet finalized and regression-verified as the final Task 8 slice.

### Next exact action
Define focused tests for the **causal Target/TP contract** before changing production code:
1. target must be a real causal objective beyond Entry;
2. active liquidity may be a target/draw, never an automatic invalidation;
3. target hierarchy must not import fixed RR or arbitrary percentages;
4. 1m cannot create a structural target;
5. multiple distinct targets must remain causally ordered;
6. if no valid structural/liquidity objective exists, no fabricated TP is emitted;
7. no future-looking target data may leak into the current setup.
Run focused tests first, then implement only the missing production behavior, then run focused + MTF + full regression.
