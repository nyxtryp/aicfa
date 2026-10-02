## 2026-10-02 — MTF TRADING-MODE ARCHITECTURE: AUTHORITATIVE DESIGN CHECKPOINT

### User-confirmed target architecture

AICFA must not treat the universal seven-timeframe chain as the default trading model. The analytical engine must be mode-aware and stateless: every FindSetup call reads fresh market data, while the selected trading horizon determines which timeframes have authority.

Required mode/timeframe hierarchy:

- **Scalping:** 15m → 5m → 1m
- **Intraday:** 1D → 4H → 1H → 15m
- **Swing:** 1W → 1D → 4H → 1H
- **Position:** 1M → 1W → 1D → 4H

Interpretation is hierarchical, not merely a list of candles:
- the highest timeframe establishes the broader directional/context bias;
- the next timeframe(s) establish structure and setup geometry;
- lower timeframe(s) refine/confirm;
- the final timeframe is the execution/entry layer;
- a lower timeframe must not invalidate or override a setup whose analytical horizon is higher unless the relevant authoritative structural timeframe actually changes;
- **1m belongs only to Scalping**. It must not participate in Intraday, Swing, or Position setup decisions.

### Exact repository finding

Inspection of src/aicfa/data_requirements.py, src/aicfa/analysis_depth.py, src/aicfa/setup_analysis.py, and src/aicfa/find_setup.py confirmed why ordinary FindSetup currently processes all seven TFs.

`default_setup_requirements()` has no trading mode/horizon. It merges knowledge concepts into semantic timeframe roles. `DataRequirementPlan.required_timeframes` then maps roles globally:

- EXECUTION → 1m
- LOWER_CONFIRMATION → 5m, 15m
- HIGHER_STRUCTURE → 1h, 4h
- BROADER_CONTEXT → 1d, 1w

Therefore the default result is always: 1m → 5m → 15m → 1h → 4h → 1d → 1w.

`analysis_depth.py` is not the source of the seven-timeframe selection. It only resolves minimum/adaptive historical depth for whichever timeframes the requirement plan has already selected. Its current largest explicit feature dependency is 60 rows.

`FindSetupRequest` currently contains only asset and market_type. There is no strategy/mode/horizon field. `find_setup()` therefore calls `default_setup_requirements(symbol)` with no mode and fetches every timeframe returned by that universal plan.

`setup_analysis.py` is explicitly written around a single seven-timeframe context: SETUP_TIMEFRAMES = 1m, 5m, 15m, 1h, 4h, 1d, 1w; higher structure = 1w, 1d, 4h, 1h; confirmation = 15m, 5m; execution = 1m.

This architecture is not sufficient for the four required trading modes.

### Critical analytical problem identified

The current implementation can mix incompatible horizons inside one candidate. A real captured BTC LONG contained a 4h entry zone, 1w higher-timeframe direction, 15m + 5m confirmation, source_timeframes containing all seven TFs, and targets sourced from 5m/15m.

That is exactly the kind of mixed-horizon setup that the new mode-aware architecture must prevent.

The previous idea of solving LONG → WAIT through persistent `SetupLifecycle` is explicitly **not** the current solution. AICFA remains stateless. The correct fix is analytical timeframe authority/horizon selection, not memory that keeps an old LONG alive.

### Required future setup output

AICFA must explain the complete setup, not only return LONG/SHORT. The result should identify at minimum:
- trading mode;
- setup/scenario type;
- directional bias;
- role/result for every participating timeframe;
- setup/structure timeframe;
- entry timeframe;
- Entry zone;
- Invalidation;
- TP1/TP2 where available;
- RR;
- confirmation;
- rationale/evidence;
- explicit invalidation conditions.

Example Intraday conceptual flow: 1D context/bias → 4H setup structure/zone → 1H refinement/confirmation → 15m entry trigger.

### Architectural implementation direction

Do **not** solve this by merely filtering the existing seven-TF output after analysis.

The mode must enter the requirement/analysis pipeline before data collection:

FindSetupRequest(mode) → mode-specific requirement profile → required TFs → analysis_depth → feature/evidence analysis → scenario reasoning → mode-aware setup analysis → structured setup explanation.

The implementation must reuse the existing knowledge/SMC/evidence layers rather than redesigning them.

`analysis_depth` should remain responsible for historical context depth, not trading-mode selection.

`setup_analysis` must become horizon-aware so that only selected mode timeframes are processed, roles are explicit, low TF evidence cannot override a higher-horizon structural premise, Entry/Invalidation/Targets are sourced from appropriate role layers, confirmation is mode-specific, and 1m is unavailable outside Scalping.

### Current state

- This is an architecture/design checkpoint only.
- No production code was changed in this step.
- No RR threshold was changed.
- No SetupLifecycle integration was performed.
- No model-training work was started.
- Existing deterministic SMC/evidence/order-flow/CVD/L1/Absorption layers remain intact.
- `PROJECT_PLAN.md` remains the single source of truth.

### NEXT UNFINISHED

1. Implement the explicit trading-mode contract in the request/requirements layer.
2. Define mode-specific timeframe roles for the four exact hierarchies above.
3. Make `default_setup_requirements()` (or an equivalent explicit mode profile) return only the required TFs for the selected mode.
4. Pass only those TFs into `analysis_depth` and FindSetup collection.
5. Make Setup Analysis consume mode-specific role mappings rather than the universal seven-TF constants.
6. Add regression tests for exact TF selection: Scalping = 15m, 5m, 1m; Intraday = 1d, 4h, 1h, 15m; Swing = 1w, 1d, 4h, 1h; Position = 1m excluded and 1m must never be fetched/used.
7. Add tests proving a lower timeframe cannot override a higher-horizon setup merely because its direction changes.
8. Produce the full structured setup explanation with mode, scenario, timeframe roles, Entry, Invalidation, TP1/TP2, RR, confirmation, rationale, and invalidation conditions.
9. Run focused tests, then full pytest, then live BTC FindSetup smoke for each mode.
10. Only after this MTF mode architecture is GREEN continue to the next unfinished AICFA block.

### Continuity checkpoint

If the chat is restarted, resume from this section. The active task is **mode-aware MTF analytical architecture**, not SetupLifecycle integration and not model training. Do not revert to the universal seven-timeframe FindSetup design.



## 2026-10-02 — MTF MODE CONTRACT IMPLEMENTED: CODE CHECKPOINT

Implemented the first production-code block of the authoritative MTF mode architecture.

### Completed in code
- Added explicit `TradingMode`: scalping, intraday, swing, position.
- Added authoritative mode profiles:
  - Scalping: 15m → 5m → 1m
  - Intraday: 1d → 4h → 1h → 15m
  - Swing: 1w → 1d → 4h → 1h
  - Position: 1M → 1w → 1d → 4h
- `FindSetupRequest` now carries a normalized trading mode; default is Intraday.
- `default_setup_requirements(..., mode=...)` now returns only the selected mode's required timeframes.
- FindSetup passes only the selected mode timeframes into adaptive analysis depth, data collection, feature analysis, evidence construction, and Setup Analysis.
- Setup Analysis now receives the mode profile and derives context, structure, refinement and execution roles from that profile.
- Direction authority now comes from the mode's structure timeframe; only the designated refinement timeframe may veto it. The final execution timeframe cannot override the higher-horizon direction.
- Entry/invalidation/target discovery is restricted to the selected mode's timeframe set. The execution timeframe cannot manufacture structural setup zones, invalidation, or targets.
- FindSetup result now exposes the selected mode.
- Added calendar-month completion/cursor semantics for 1M.
- Enabled 1M transport in Binance and mapped 1M to Bybit's monthly interval.
- Added/updated regression tests for exact mode timeframe selection, Position exclusion of 1m, monthly candle semantics, and higher-horizon direction authority.

### External transport note
Binance's documented kline interval vocabulary includes `1M` as one-month candles; the previous AICFA restriction was an internal limitation, not a requirement of the exchange API.

### Commits
- `4924fe85ea00bc6ca33917ae86d6046dddf5a272` — trading mode profiles
- `46ff46c85678580debf0c16708d80b8e461a89c1` — FindSetup mode contract
- `da90544f9545e17b502bfd1a4f50012f300feffa` — mode context in Setup Analysis
- `bda625a7ea9ef68928b5518c2772497e608c22d5` — selected-mode context pipeline
- `ce47e54b2664cd6c095d60519736470bd6be59dd` — mode-restricted setup levels
- `1b7b0d5fb40d97c9a93b667f1466d2cbcb2efbcc` — calendar-month market data semantics
- `fb33de276b0ebe09f547f5fb41ce0a815152dc55` — Binance 1M transport
- `a4f4cb7beb0ef7de6cb23092dc449f40f7477cc1` — Bybit 1M transport
- `cf9971298a665781b0e86e40b620154b20298321` — FindSetup mode regression tests
- `582e9172f19b9440873b05b4e0984c51cd49a659` — requirement profile tests
- `129b5080fa1c0c6c738a55f33e8b48b98c788780` — monthly market-data tests
- `a240566af8a5974f5063b79c34230bae91c9ec43` — higher-horizon authority test

### Verification status
The code and tests have been committed to `main`, but the full pytest suite has **not yet been executed on the AICFA server in this checkpoint**. Do not call this block GREEN until server-side focused tests and full regression pass.

### NEXT UNFINISHED
1. Run focused tests on the server and fix any regressions.
2. Run full pytest.
3. Fix any remaining seven-TF assumptions uncovered by tests.
4. Run live BTC FindSetup smoke for all four modes and inspect the actual returned timeframe set/roles.
5. Complete the structured setup explanation: mode, scenario, per-TF role/result, setup TF, entry TF, Entry, Invalidation, TP1/TP2, RR, confirmation, rationale, invalidation conditions.
6. Only after MTF mode architecture is GREEN continue to the next AICFA block.


### 2026-10-02 — Focused-test fixes after first mode-contract run
The first server focused run exposed 7 regressions caused by the initial mode migration:
- two FindSetup expansion tests still asserted the old universal 7-TF/1m contract;
- legacy Setup Analysis tests accessed mode-only context fields when running without a frame map;
- the new higher-horizon test was missing its pandas import;
- MultiTimeframeContext contained a duplicate `structure_timeframe` declaration.

Fixes committed:
- preserve legacy Setup Analysis behavior when `analyses is None`;
- remove duplicate context field;
- update expansion assertions to the explicit default Intraday contract;
- add missing pandas test import.

Fix commits:
- `931fcbd307d37283ceded598f251c17171e12d12`
- `5bbcb2274dde0fd3e971523e62e8a4b7b53db6b3`
- `cfd5470d058dd24db006a1ef723e37727052fbc9`

**NEXT:** rerun the same focused test command. Do not proceed to full regression until it is clean.


### 2026-10-02 — Focused suite result: one remaining test-import regression

Server-side focused suite result:
- **40 passed**
- **1 failed**
- **10,768 warnings**
- remaining failure: `tests/test_setup_analysis.py::test_lower_refinement_conflict_cannot_become_a_new_direction`
- failure: `NameError: name 'pd' is not defined`

The higher-horizon test itself reached the expected code path; the remaining failure was only the missing pandas test import.

Fix committed:
- `d75e6cf4aaae80b361f3b4b5150967bc94800fdd` — restore `import pandas as pd` in `tests/test_setup_analysis.py`.

**NEXT:** rerun the same focused suite. If it is clean, proceed to the full `pytest -q` regression. Do not mark MTF mode architecture GREEN until full regression and the four-mode BTC smoke are also clean.


### 2026-10-02 — Focused MTF suite GREEN

Server-side focused suite completed successfully:
- **41 passed**
- **10,767 warnings**
- no test failures.

The remaining pandas import regression was fixed in:
- `d75e6cf4aaae80b361f3b4b5150967bc94800fdd`

The plan update for that fix is:
- `3768e0e3d00b6c96925956b2e1c460eed2e66ff5`

The remaining warnings include the known pytest cache permission warning in FrostDeploy release directories. This does not affect the test result.

**Status:** focused mode-aware MTF tests are GREEN.

**NEXT:** run the full repository regression `pytest -q`. Do not mark the complete MTF architecture GREEN until full regression passes and the four-mode live BTC FindSetup smoke verifies the actual timeframe/role contract.


### 2026-10-02 — Full regression: 5 legacy MTF/monthly-contract test assumptions

Server full regression:
- **356 passed**
- **5 failed**
- **15,881 warnings**

Failures were identified as test-contract mismatches introduced by the new mode architecture, not five independent production regressions:
1. Binance test still expected `1M` to be rejected, while the mode architecture explicitly enabled monthly transport.
2. Bybit test still expected `1M` to be rejected, while `1M -> M` was explicitly enabled.
3. Setup-engine confirmation test still treated 15m as the confirmation layer; for Intraday the authoritative refinement layer is 1H and execution is 15m.
4. Setup-engine scenario-zone fixture still used the old seven-TF fixture.
5. Setup-engine target fixture likewise relied on the old seven-TF fixture.

Test contracts were migrated to the authoritative Intraday profile:
- `1d -> 4h -> 1h -> 15m`
- 1H is the refinement/confirmation timeframe.
- 15m is execution.
- monthly Binance/Bybit transport is tested as supported behavior.

Fix commits:
- `953776566502834b56a5c44e51152ace3f9093cb`
- `35ff1f9c9a567ed865afd1fdc074a2f2f01c347f`
- `a27f1b61f92629bf1b3b0efeafbdf05ad7ce1c1c`

**NEXT:** rerun the full `pytest -q`. If clean, proceed to the four-mode live BTC FindSetup smoke. Do not weaken production mode authority to satisfy the obsolete seven-TF tests.


### 2026-10-02 — Full regression: remaining stale execution-timeframe test arguments

Server full regression result:
- **349 passed**
- **12 failed**
- **15,881 warnings**
- all 12 failures were `TypeError` because migrated Intraday tests still passed the removed `structure_1m` keyword to `_frames()`.

Root cause:
- authoritative Intraday hierarchy is `1d -> 4h -> 1h -> 15m`;
- `_frames()` had already been migrated to those four timeframes, but several old calls still used `structure_1m`;
- this is a test-fixture migration issue, not a production mode-authority failure.

Fixes:
- `tests/test_setup_engine_mtf.py` migrated all remaining `structure_1m` calls to the explicit Intraday contract and renamed the affected test wording away from the obsolete 1m assumption.
- `tests/test_decision.py` migrated its MTF fixture call to the Intraday contract.
- The helper default now keeps 1H refinement direction coherent by default; the dedicated conflict test explicitly sets 1H bearish against 4H bullish.

Commits:
- `38bddaf7edf4d4badb5a94c15c01b73cd1c97dec` — MTF test fixture migration
- `97f35411a976c4959d86c6d4c8b5658129546c6d` — decision test migration

No production trading logic was changed.

**NEXT:** rerun the full `pytest -q`. If clean, proceed to four-mode live BTC FindSetup smoke. Do not mark MTF architecture GREEN before that smoke passes.


### 2026-10-02 — Full regression: 3 remaining MTF fixture-role mismatches

Server full regression result:
- **358 passed**
- **3 failed**
- **15,881 warnings**

The remaining failures were confined to `tests/test_setup_engine_mtf.py` and came from fixtures still modeling the old seven-TF role semantics:
1. confirmation conflict placed the bearish direction on 15m, while Intraday confirmation/refinement is 1H and 15m is execution;
2. scenario-specific OB geometry was placed on 15m execution, although execution must not manufacture setup zones;
3. active buy-side liquidity used for target selection was placed on 15m execution, although execution must not manufacture structural targets.

Fix committed:
- `461984a3775b03210c995a634748dfd369e6f714` — migrate these fixtures to the authoritative Intraday roles.
- conflict test: 4H bullish + 1H bearish + 15m execution bullish;
- scenario-zone OB: 1H refinement;
- active target liquidity: 1H refinement.

No production trading logic was changed.

**NEXT:** rerun the full `pytest -q`. If clean, proceed to four-mode live BTC FindSetup smoke. Do not mark MTF architecture GREEN before that smoke passes.


### 2026-10-02 — Full regression: duplicate MTF target fixture remained stale

Server full regression after the previous fixture migration:
- **360 passed**
- **1 failed**
- **15,881 warnings**

The only remaining failure was:
- `tests/test_setup_engine_mtf.py::test_setup_engine_prioritizes_active_liquidity_over_nearer_structural_extreme`
- `IndexError: tuple index out of range`

Root cause was confirmed by inspecting the committed test file: the test name existed twice. The earlier definition had already been migrated to place active buy-side liquidity on the 1H refinement timeframe, but the later duplicate definition (the one Python actually executes) still placed it on 15m execution. The later definition therefore produced no eligible target under the new rule that execution timeframe cannot manufacture structural targets.

Fix committed:
- `c9b52623cfb07b42cbcc3175f44b69fcc5755e8b` — move the active-liquidity/previous-high fixture in the executed duplicate test from 15m to 1H.

No production trading logic changed.

**NEXT:** rerun the full `pytest -q`. If clean, proceed to the four-mode live BTC FindSetup smoke. Do not mark MTF architecture GREEN before that smoke passes.