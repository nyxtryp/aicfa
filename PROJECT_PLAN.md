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
