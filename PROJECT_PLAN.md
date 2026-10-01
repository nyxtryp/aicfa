## 2026-10-01 — Next analytical block: CVD + Absorption integration

### Current state
- Trade-level Order Flow / Microstructure v1 is **live-verified GREEN**.
- The repository already contains causal standalone implementations:
  - `src/aicfa/cvd.py` + `tests/test_cvd.py`
  - `src/aicfa/absorption.py` + `tests/test_absorption.py`
- These modules are not yet wired into the main `build_features()` / FindSetup analytical chain.

### Forward implementation
Integrate the existing CVD and Absorption layers into the established architecture without redesigning Order Flow:
1. Feed trade-level Order Flow into causal CVD.
2. Feed synchronized OHLC + trade flow + L1/order-book level observations into causal Absorption candidates.
3. Expose their descriptive state through the feature engine / unified market state as appropriate.
4. Preserve strict no-future-data semantics and keep these layers descriptive; they must not directly emit LONG/SHORT/WAIT.
5. Add focused integration and future-leakage tests.
6. Run focused tests, then full pytest.
7. After regression is GREEN, run a live BTC FindSetup smoke and verify CVD/Absorption population before advancing.

### Important architecture rule
Order Flow remains **trade/event-level**, not candle/clock aggregated. CVD is a cumulative transformation of that trade-level flow. Absorption is a synchronized causal market-state candidate using only data available at each observation timestamp.

### Chat-resume checkpoint
If the chat is lost, resume from this exact section: **CVD + Absorption integration is the next implementation task. Do not restart or redesign completed Order Flow/Microstructure work.**



## 2026-10-01 — CVD integration checkpoint

### Completed in this step
- Added causal trade-level CVD primitive: `build_trade_cvd()` in `src/aicfa/cvd.py`.
- It consumes individual venue-provided trades, preserves multiple trades sharing one millisecond timestamp, and cumulatively tracks signed taker volume.
- Exposed `cvd_analysis` through `FindSetupResult`; the current FindSetup request uses the same request-scoped trade set as Order Flow.
- Added focused tests for same-timestamp trade preservation, future-change causality, invalid side rejection, and FindSetup CVD population.
- Commits:
  - `28f58022aed3a817c914ea48d3c2229d3aa7ddad` — trade-level CVD primitive
  - `ec7933d7c2cb278b93aeef44813c4d55d70443dd` — FindSetup CVD exposure
  - `051814ba1ebf763e2c2bca5c87ebe3188003978c` — CVD/FindSetup tests

### Important integration finding
- Absorption is **not yet wired into live FindSetup**, and it must not be faked from the current one-snapshot L1 transport.
- `build_absorption()` requires a timestamped sequence of book levels so persistence and replenishment can be measured causally.
- Current Binance/Bybit FindSetup order-book transport returns the current L1 snapshot; `limit=1` is book depth, not historical snapshots.
- Therefore the next implementation block is to add a real historical/timestamped L1 snapshot transport contract first, then integrate Absorption against that data.
- Do not claim Absorption population until that transport exists and passes causal tests.

### CURRENT STATE
- Order Flow / Microstructure v1: **LIVE GREEN**
- Trade-level CVD: **implemented + integration tests added; verification pending**
- Absorption: **standalone GREEN, live integration blocked by missing historical L1 snapshot sequence**
- Full pytest after the CVD changes: **not yet run**
- Live BTC FindSetup after the CVD changes: **not yet run**

### NEXT UNFINISHED
1. Run focused CVD + FindSetup tests.
2. Run full pytest.
3. If GREEN, add historical/timestamped L1 snapshot transport without inventing data.
4. Integrate causal Absorption.
5. Add Absorption integration/future-leakage tests.
6. Run full pytest and live BTC FindSetup smoke; verify both CVD and Absorption population.
7. Then advance the plan to the next unfinished analytical block.

## 2026-10-01 — Causal L1 observation transport started

### Verified before this step
- Full repository regression after trade-level CVD integration: **328 passed, 20194 warnings, 52.41s** on the deployed server.
- This closes the previous CVD verification checkpoint: CVD + FindSetup integration is GREEN.
- Order Flow / Microstructure v1 remains LIVE GREEN.
- Absorption remains standalone and must not be populated from a single current L1 snapshot.

### Work completed in this step
- Inspected the live market-data contract, Binance adapter, Bybit adapter, router, FindSetup orchestration, and existing order-book level/Absorption contracts.
- Confirmed the architectural constraint: Binance/Bybit REST depth endpoints provide current snapshots; they do not provide a historical sequence that can be queried by past timestamp.
- Added a provider contract for collecting a **causal sequence of real-time L1 observations**: `fetch_order_book_history(..., snapshots, interval_seconds)`.
- Added Binance implementation using repeated real public depth snapshots with injected sleep/clock control.
- Added Bybit implementation using repeated public order-book snapshots and the venue-provided source timestamp.
- Added router-level fallback and provider provenance for L1 history.
- Added adapter and router regression tests covering multiple real observations, ordering, interval behavior, and fallback.
- Commits:
  - `becda64311c8715a62d401bd326d581d34a178e4` — define causal L1 history transport contract
  - `f4ac1c3705d8a33a6fe3b6a5a9a8caa6aea4e66c` — collect timestamped Binance L1 history
  - `91506abb400342a47f81c21f15400c06b50faa52` — collect timestamped Bybit L1 history
  - `a1b865acf2c52638cda28bbe93c5586ac2f1cbcc` — route causal L1 history with provider provenance
  - `da010850c154856e3c6262f2eee9ae31ca7eef67` — Binance L1 history test
  - `2c275f85e9b026ebd1f539a2f0134ddb91dba817` — Bybit L1 history test
  - `9ad6c4da1bb5bac9851fd22af0d2a5010be12f2d` — routed L1 history fallback test

### Important limitation
- This is **real-time observation history collected during the request**, not a fabricated historical order-book dataset and not a historical REST lookup.
- Binance Spot depth currently has no venue timestamp in the adapter response, so its observation timestamp remains the local observation time.
- This transport is deliberately the first minimal step. It does not yet make Absorption live-ready by itself.

### CURRENT STATE
- Full pytest before this transport change: **328 passed**.
- New L1-history transport/tests: **implemented; server verification pending**.
- CVD: **LIVE integration GREEN**.
- Absorption: **standalone GREEN; live integration still blocked until L1 history is verified and synchronized with causal trade flow/price observations**.

### NEXT UNFINISHED
1. Run focused transport tests on server.
2. Run full pytest after the transport changes.
3. If GREEN, build the synchronized causal observation frame for Absorption from real timestamped L1 history, trade-level event flow, and available completed OHLC/price observations.
4. Add Absorption integration and future-leakage tests.
5. Run full pytest and live BTC FindSetup smoke.
6. Only after real Absorption population is verified, mark Absorption live GREEN and advance `PROJECT_PLAN.md` to the next unfinished analytical block.

### Project-plan rule
`PROJECT_PLAN.md` is a **living project journal**. Every meaningful implementation, test result, server verification, architectural finding, commit, regression, and change of the next unfinished task must be recorded here. Historical checkpoints remain historical; the CURRENT STATE and NEXT UNFINISHED sections must reflect the actual repository state at the latest completed step.

## 2026-10-01 — L1 history transport focused verification GREEN

### Verification result
- Server focused transport regression: **33 passed, 1 warning, 0 failed, 0.50s**.
- Covered Binance L1 history, Bybit L1 history, and router fallback/provenance.
- The only warning is the existing pytest cache permission warning in the FrostDeploy release directory; it does not affect test execution.

### CURRENT STATE
- Full suite immediately before L1 transport changes: **328 passed**.
- CVD integration: GREEN.
- Causal L1 history transport: **focused tests GREEN (33 passed)**.
- Absorption: standalone GREEN; live integration not yet claimed.

### NEXT UNFINISHED
1. Run the complete pytest suite after the L1 transport changes.
2. If GREEN, integrate the synchronized causal L1 history into the FindSetup microstructure path.
3. Build and test the causal Absorption integration without fabricating historical book data.
4. Run full pytest and live BTC FindSetup smoke with CVD + Absorption provenance/population.
5. Update this journal again with the exact results and next unfinished analytical block.

## 2026-10-01 — FindSetup causal L1/Absorption integration implemented

### Work completed
- Exposed causal L1 history through SharedSnapshotMarketDataProvider.
- Extended FindSetupResult with order_book_history, order_book_history_provider, and absorption_analysis.
- FindSetup now requests 8 real L1 observations at 1-second intervals through the existing routed provider.
- The final microstructure observation timestamp is the causal minimum of the latest available trade timestamp and latest L1 observation timestamp, preventing later trades from being used against an earlier book state.
- L1 bid/ask snapshots are converted into causal long-format levels for build_absorption().
- Price observations for Absorption are derived from real L1 bid/ask mid-prices: each observation uses the previous/current mid as open/close and their extrema as high/low. No synthetic market history is introduced.
- Absorption remains descriptive only; it does not modify the decision chain or emit LONG/SHORT/WAIT.
- Added FindSetup integration coverage for L1 history transport, provider provenance, and populated causal Absorption analysis.
- Commits:
  - 95582784a50c42805e6fa6333928640af4cb852d — expose causal L1 history through shared provider
  - 85a071d376374352992ac8a1c8b5c40ca257b72e — integrate causal L1 history into FindSetup absorption
  - dbcd67a610978eb30b7c6b509d5c9c4dda1175e7 — exercise populated causal absorption state

### CURRENT STATE
- CVD integration: GREEN from the previous full-suite checkpoint.
- Causal L1 history transport: focused regression GREEN — 33 passed.
- FindSetup Absorption integration: implemented; server verification pending.
- No claim yet that live Absorption is GREEN.

### NEXT UNFINISHED
1. Run focused FindSetup/Absorption integration tests on the deployed server.
2. If GREEN, run the complete pytest suite after the integration.
3. Run live BTC Spot FindSetup smoke and verify real L1 history, provider provenance, CVD, and Absorption population.
4. Inspect live Absorption output for causal timestamps and ensure no future observations are consumed.
5. Record exact results and only then mark Absorption live GREEN.


## 2026-10-01 — FindSetup Absorption integration regression repaired

### Regression found
- Focused server run after the test-fixture fix produced **9 passed, 10 failed, 16390 warnings**.
- All 10 failures shared the same root cause: build_trade_order_flow() performed a causal merge but returned only feature columns, dropping the resulting timestamp.
- New causal Absorption validation correctly requires that timestamp and therefore raised `ValueError: missing required flow columns: ['timestamp']`.
- This was a production-code integration bug, not a test-fixture workaround.

### Repair
- Updated build_trade_order_flow() to preserve the source-availability timestamp alongside its calculated trade-flow features.
- This keeps Absorption's causal contract intact and does not relax any validation.
- Commit: 6354c30684d43ca225ee9819a801a8d4152da243 — fix: preserve timestamps in trade order flow.

### NEXT UNFINISHED
1. Re-run focused tests/test_find_setup.py tests/test_absorption.py on the deployed server.
2. If GREEN, run the complete pytest suite after this repair.
3. Run live BTC Spot FindSetup smoke and verify real L1 history, provenance, CVD, and Absorption population.
4. Inspect causal timestamps before marking Absorption live GREEN.


## 2026-10-01 — Absorption L1 regression diagnosed and repaired

### Regression found
- Focused FindSetup/Absorption verification: **18 passed, 1 failed** after the timestamp repair.
- The remaining integration failure was an empty Absorption result, not a causal timestamp failure.
- Root cause: FindSetup intentionally collects L1 (best bid/best ask) observations. The previous liquidity-multiple calculation compared a candidate level with the same-snapshot median of that side. With only one L1 level, that median equals the candidate itself, making the multiple exactly 1 and preventing the configured 1.5 threshold from ever qualifying.

### Repair
- `build_absorption()` now keeps the original same-snapshot cross-level calculation when multiple levels exist.
- For true L1 input, it causally falls back to the historical median size of the same displayed level within the observation window.
- The FindSetup L1 fixture now models actual replenishment/growth strongly enough to exercise that contract.
- Commits:
  - b3d94216209bcac670d74824d4d3009ca40e4cd5 — fix: support causal liquidity multiple for L1 absorption
  - 505f8ff54552f333cdd35ef408c99fb9249fa46d — test: strengthen L1 replenishment fixture

### NEXT UNFINISHED
1. Re-run focused `tests/test_find_setup.py tests/test_absorption.py` on the deployed server.
2. If GREEN, run the complete pytest suite after these Absorption changes.
3. Run live BTC Spot FindSetup smoke and verify real L1 history, provenance, CVD, and Absorption population.
4. Inspect causal timestamps before marking Absorption live GREEN.

## 2026-10-01 — CVD + Absorption live checkpoint GREEN

### Verification completed
- Focused FindSetup/Absorption regression after the L1 fixture repair: **19 passed, 16399 warnings, 0 failed**.
- Complete repository regression: **332 passed, 21228 warnings, 0 failed**.
- Live BTC Spot FindSetup smoke exposed and repaired a real production-path type bug: Binance L1 adapter fields arrive as strings while the FindSetup Absorption mid-price calculation expected numeric values.
- Commit: `9ddced38e3292685b83952bc4ccad6ea0da2fece` — `fix: normalize live L1 numeric fields before absorption`.
- Final live BTC Spot diagnostic is GREEN: Binance provides trades, current order book, and L1 history; 60 trades; 8 L1 observations; populated Order Flow, CVD, and Absorption.
- Live decision was `WAIT` with reason `material evidence is contradictory`.
- Absorption remained descriptive and did not qualify as absorption in the observed request despite aggressive buy imbalance.
- Causal timestamp alignment was verified: Order Flow uses the common causal observation timestamp rather than pairing later trades with an earlier book state.

### Architectural constraint preserved
- L1 history is collected only during the user's FindSetup request.
- There is no continuous/background collector.
- The current transport collects 8 real observations at approximately 1-second intervals. It is an interim request-scoped observation burst, not fabricated historical data.

### CURRENT STATE
- Market Evidence: GREEN
- Order Flow / Microstructure v1: LIVE GREEN
- Trade-level CVD: LIVE GREEN
- Causal L1 history transport: GREEN
- Absorption: **LIVE GREEN**
- FindSetup microstructure integration: **LIVE GREEN**
- Full regression: **332 passed**
- No new analytical block should redesign the completed Order Flow/CVD/Absorption work.

### NEXT UNFINISHED — Displacement Engine
The next analytical block is **Displacement**.

Goals:
1. Implement a causal displacement primitive over completed OHLCV data.
2. Detect abnormal directional price expansion relative to a causal baseline.
3. Measure body/range expansion, directional efficiency, and relative volume without future leakage.
4. Keep displacement descriptive; it must not directly emit LONG/SHORT/WAIT.
5. Add focused tests for bullish/bearish displacement, weak/non-displacement candles, threshold validation, and future-change causality.
6. Integrate displacement into the existing analytical chain only after the standalone contract is GREEN.
7. Run focused tests, then full pytest, then verify the live BTC FindSetup path.

## 2026-10-01 — PROJECT PLAN RECONCILIATION / CURRENT SOURCE OF TRUTH

This section supersedes the stale reconciliation that incorrectly introduced a separate interface knowledge document and incorrectly treated it as the next project block.

### Permanent project-document rule
- `PROJECT_PLAN.md` is the **single authoritative project journal and continuity document for all of AICFA**.
- All meaningful architecture decisions, implementation steps, tests, server/deployment verification, regressions, fixes, completed stages, current state, and NEXT UNFINISHED work belong here.
- A chat restart must be recoverable from this document without requiring the user to re-explain the project history.
- Do not create parallel project diaries or knowledge packs for this purpose.
- Historical sections remain historical, but the latest CURRENT STATE and NEXT UNFINISHED sections must describe the actual repository state.
- Before starting a new implementation block, reconcile this plan against the actual `main` branch and current test state.

### Closed / removed branch
The temporary `docs/AICFA_INTERFACE_KNOWLEDGE.md` document was an unnecessary parallel project document and is being removed. It is not part of the AICFA architecture or roadmap.

The local-model/interface-model research branch is **closed**. Do not reopen local model selection, SmolLM3, Shirdel, FinSenti-Llama, or related model-search work unless the user explicitly reopens that subject.

### Actual analytical state
The repository already contains the completed deterministic analytical chain through:
- Market Structure
- Liquidity
- Displacement
- FVG
- Order Blocks
- Premium / Discount
- Unified SMC
- Multi-Timeframe
- Volume / Volatility
- Derivatives
- Canonical Market State
- Setup Events
- Knowledge Base / Data Requirements
- Market Evidence
- Evidence Reasoning
- Scenario Reasoning
- Setup Detection
- Setup Analysis
- Decision Layer
- universal asset resolution
- seven-timeframe FindSetup orchestration
- trade-level Order Flow / Microstructure
- trade-level CVD
- causal L1 history transport
- causal Absorption

### Learning/data pipeline already completed
The repository also already contains a substantial leakage-safe learning-data foundation:
- causal future-outcome label engine;
- task-specific training datasets;
- chronological/leak-safe dataset construction;
- label end intervals / barrier timing needed for purged validation;
- configurable label/volatility/barrier parameters;
- direction/task selection.

Therefore the next learning block is **not** to invent the dataset pipeline from scratch. The next substantive unfinished block is the first AICFA-owned model training/evaluation layer built on the existing causal dataset foundation.

### Current regression gate
A current server test run has been reported with these failures:
- `tests/test_order_flow.py::test_trade_order_flow_uses_event_window_without_clock_intervals`
- `tests/test_find_setup.py::test_find_setup_fetches_exactly_seven_causal_timeframes`
- additional `tests/test_find_setup.py` failure(s) were reported but the third test name was truncated in the chat output.

These failures must be reconciled against the actual repository `main` state and deployed release before changing correct code. Do not assume they are caused by stale deployment, and do not weaken tests merely to obtain GREEN.

### NEXT UNFINISHED
1. Verify the actual `main` HEAD and deployed release SHA.
2. Inspect the current failing Order Flow and FindSetup tests together with their production code.
3. Repair only genuine regressions while preserving the established causal contracts.
4. Run focused tests.
5. Run the complete pytest suite.
6. Record the exact GREEN result here.
7. Only after the regression gate is GREEN, begin the **first AICFA-owned model training/evaluation** stage using the existing leak-safe training datasets.
8. Keep the deterministic analytical core authoritative; the learning model must initially be evaluated against it and must not silently override its decision contract.

### Continuity rule
When resuming AICFA after a chat reset, start from this document, verify the repository state, then continue from **NEXT UNFINISHED**. Do not restart completed analytical blocks and do not resurrect closed branches.


## 2026-10-01 — CURRENT SOURCE OF TRUTH: SETUP ENGINE

This section supersedes all earlier "NEXT UNFINISHED" sections below it.

### Product direction
AICFA's immediate purpose is to analyze the **current market/chart** and produce a structured trading setup when conditions align. Historical data is not the current product goal and must not become a detour into model training.

The live analytical path is:

```
CURRENT MARKET / CHART
→ multi-timeframe market state
→ Market Structure / SMC
→ Liquidity
→ BOS / CHoCH / MSS
→ FVG
→ Order Blocks
→ Displacement
→ Premium / Discount
→ Price Action / Wyckoff
→ Volume / Volatility
→ Derivatives
→ Order Flow
→ CVD
→ Absorption
→ Scenario
→ SETUP ENGINE
→ Entry / Invalidation / Targets / Required Confirmation
→ LONG / SHORT / WAIT / NO TRADE
```

### Already completed
The deterministic analytical core already contains the completed blocks listed in the reconciliation above, including Displacement, FVG, Order Blocks, Unified SMC, Setup Detection, Setup Events, CVD, L1 history and Absorption.

The current deployed regression gate is **332 passed, 21228 warnings, 0 failed**. The previously reported Order Flow / FindSetup failures are no longer current and must not be resurrected as unfinished work.

### Current gap
There are already separate layers named:
- `setup_detection.py`
- `setup_events.py`
- `setup_analysis.py`
- `decision.py`

However, the request path still treats them primarily as separate descriptive/reasoning stages. The next implementation must make them function as one coherent **SETUP ENGINE** over the current multi-timeframe market state.

The engine must:
1. identify the active setup family from the current state;
2. resolve direction from actual current evidence rather than guessing;
3. combine SMC/price-action/microstructure confluence;
4. identify the relevant entry condition;
5. identify a concrete invalidation reference when the available market data supports one;
6. identify visible target/liquidity objectives when available;
7. explicitly state missing confirmation/context instead of inventing prices;
8. preserve WAIT / NO TRADE when evidence conflicts or the setup is incomplete;
9. remain deterministic and causal;
10. not execute orders.

### Important distinction
Historical labels and the existing leak-safe dataset foundation remain valid project infrastructure. They are **not** the next implementation block and must not replace the current setup-engine work.

Model training is deferred until the deterministic setup engine is sufficiently complete to define exactly what AICFA is trying to learn.

### NEXT UNFINISHED
1. Unify current setup detection, scenario reasoning, setup analysis and decision into the coherent SETUP ENGINE.
2. Make the engine consume the actual current **seven-timeframe** state (`1m`, `5m`, `15m`, `1h`, `4h`, `1d`, `1w`) as one hierarchical context. `1m` is execution/microstructure context only; it must never be the sole source of market direction or setup levels.
3. Add explicit structured setup output: family, direction, entry condition, invalidation, targets, confirmation requirements and rationale, with levels derived from the appropriate timeframe(s), never by defaulting to the 1m close.
4. Add focused causal/conflict/no-invention tests.
5. Run the focused tests and complete pytest.
6. Run a live BTC FindSetup smoke and inspect the resulting setup object.
7. Record the exact GREEN result here before advancing to the next analytical block.

### Continuity rule
After a chat reset, start from this section. Do not jump to model training, do not redo completed analytical layers, and do not reopen closed local-model research.


## 2026-10-01 — SETUP ENGINE correction: seven-timeframe context is mandatory

The first implementation attempt incorrectly passed the `1m` analysis as the market context for setup levels/direction. This was rejected because AICFA's setup must be derived from the complete seven-timeframe hierarchy, not from the execution timeframe.

### Correction
- Reverted the incorrect 1m-only setup-level implementation.
- `find_setup.py` no longer passes a 1m-specific analysis object into `analyze_setups()`.
- Removed the invalid test that treated the 1m close as the setup entry price.
- No setup direction, entry, invalidation, or target may be inferred solely from 1m.
- The future SETUP ENGINE implementation must consume the complete seven-timeframe current state and resolve each piece from the timeframe where that evidence actually exists.

### Current implementation checkpoint
- Reversion commits: `56ab85d0a1ab9496d54eb19c567f3c9bf1adb4f2`, `4c1944067f361dc5c70b187a81f36d359e96e5e3`, `69ead87d751696d9fa79df1eb8e75bb03bef4ff0`.
- Next code work remains the genuine multi-timeframe SETUP ENGINE, not a 1m shortcut.

## 2026-10-01 — SETUP ENGINE implementation: seven-timeframe current state

Implemented the first genuine multi-timeframe SETUP ENGINE pass.

### Implementation
- src/aicfa/setup_analysis.py now defines an explicit MultiTimeframeContext.
- The live setup path requires the complete seven-timeframe state: 1w → 1d → 4h → 1h → 15m → 5m → 1m.
- Higher-timeframe structure (1w/1d/4h/1h) establishes setup direction.
- 15m/5m are confirmation timeframes.
- 1m is execution/microstructure context only and cannot establish setup direction.
- A lower-timeframe confirmation conflict with higher-timeframe structure produces WAIT.
- Setup candidates now expose structured direction, entry zone levels, invalidation level, target levels, confirmation timeframes and source timeframes.
- Numeric levels are read from the timeframe where the relevant FVG/OB/liquidity evidence exists. The engine does not use the 1m close as an automatic entry.
- The engine explicitly requires all seven timeframes in the live path.
- The old visual analyze_setups API remains compatible when no analyses mapping is supplied; the actual FindSetup production path always supplies all seven analyses.

### FindSetup integration
- find_setup.py now passes the complete analyses mapping and canonical seven-timeframe list into analyze_setups().
- The production request path therefore cannot silently fall back to a 1m-only setup context.

### Tests added
- tests/test_setup_engine_mtf.py
  - higher-timeframe direction beats contradictory 1m direction;
  - 15m conflict with higher structure forces WAIT;
  - entry/invalidation/target levels come from the relevant 4h context rather than 1m;
  - missing one of the seven required timeframes blocks setup readiness.

### Commits
- e2fe456f10958713c16d6804eaeb34c8e2a6aa5b — genuine seven-timeframe SETUP ENGINE implementation.
- 89422483df6e785209e7aea179554ffceec193bc — pass complete seven-timeframe state from FindSetup.
- 9411dea4b63f40a58ba2e2af27b01662f326f0f6 — seven-timeframe SETUP ENGINE tests.

### Verification status
- Tests have not yet been run after these commits.
- Previous green checkpoint remains historical: 332 passed, 21228 warnings, 0 failed.
- Next action is focused SETUP ENGINE tests, then full pytest, then live BTC FindSetup smoke.

## 2026-10-01 — SETUP ENGINE focused-test regression and correction

The first focused verification of the seven-timeframe SETUP ENGINE produced **5 failures, 21 passed, 16396 warnings in 31.71s**.

Failures:
- `tests/test_setup_engine_mtf.py::test_setup_engine_levels_come_from_relevant_timeframe_not_1m` — target/level selection returned `1w` where the test requires the relevant supporting `4h` timeframe.
- Four `tests/test_setup_analysis.py` failures because `VisualObservation` did not preserve its parent chart timeframe, while the new setup-analysis path now needs observation-level timeframe provenance.

This was a real implementation regression, not a test-only workaround.

### Corrections committed
- `4ff0409193f5074e029b9299f5d13e3c46f6bc6e` — setup zone/level selection now prefers timeframes that supplied the observed setup evidence instead of blindly starting at 1w.
- `b472e1cb8700bd15a3fc37e984486a568c5d5247` — `VisualObservation` now preserves optional timeframe provenance.
- `1c615dfc51721ed1cf656d03a79fa871d7f11bdc` — visual evidence assessment propagates the parent chart timeframe into each observation.
- `697c352fb9d147bb981b5776acc0999a5e28e820` — target-level selection now receives supporting setup timeframes and prefers those timeframes.

### Architectural rule preserved
The correction does **not** weaken the seven-timeframe requirement. It only fixes provenance and source-timeframe selection:
- higher TF structure still determines direction;
- 15m/5m remain confirmation;
- 1m remains execution/microstructure only;
- entry/invalidation/targets must come from the timeframe where the relevant evidence exists;
- no fabricated numeric levels and no automatic 1m-close entry.

### Verification
The correction commits are not yet verified by pytest. The next action remains the focused SETUP ENGINE test command, followed by full pytest if green.


## 2026-10-01 — SETUP ENGINE second focused-test regression

Focused verification after the previous correction: **25 passed, 1 failed, 16396 warnings in 30.23s**.

Remaining failure:
- `test_setup_engine_levels_come_from_relevant_timeframe_not_1m` still returned a `1w` target instead of the supporting `4h` target.

Root cause: the target selector passed `source_tfs` into the helper's **concept filter** parameter rather than into an explicit preferred-timeframe parameter. Therefore the intended 4h priority was not actually applied.

Correction:
- `22582e5dd7e0fed699419f6ef51b92e2edad54d3` — separated explicit preferred timeframes from concept-based evidence discovery in the source-timeframe ordering helper. Target selection now receives `source_tfs` as an actual timeframe priority.

Verification after this correction is pending. The single remaining failure is specifically source-timeframe selection; the other 25 focused tests are green.


## 2026-10-01 — SETUP ENGINE full regression GREEN

### Verification completed
- Focused SETUP ENGINE regression after commit `22582e5dd7e0fed699419f6ef51b92e2edad54d3`: **26 passed, 0 failed, 16395 warnings** in 30.72s.
- Complete repository regression after the SETUP ENGINE changes: **336 passed, 0 failed, 21228 warnings** in 55.66s.
- The remaining focused failure from the previous checkpoint is resolved: setup levels/targets now honor the relevant supporting timeframe instead of incorrectly falling back to 1w.
- The existing `PytestCacheWarning` about permissions in the immutable FrostDeploy release directory remains non-fatal and does not affect test execution.

### GREEN checkpoint
The deterministic repository regression gate is GREEN at **336 passed**. The seven-timeframe SETUP ENGINE implementation is therefore regression-verified against the full test suite.

### NEXT UNFINISHED
1. Run the live BTC FindSetup smoke against the deployed current release.
2. Inspect the returned setup object and verify the seven-timeframe context is actually populated in production.
3. Verify direction, setup family, entry condition/zone, invalidation, targets, confirmation requirements and source timeframes; no 1m-only inference and no fabricated numeric levels.
4. Record the exact live output and any production-path regression here.
5. Only after the live setup object is verified GREEN, advance to the next analytical block.


## 2026-10-01 — SETUP ENGINE: MTF conflict semantics corrected

### Live smoke finding
- Live BTC Spot FindSetup returned all seven required timeframes:
  1m, 5m, 15m, 1h, 4h, 1d, 1w.
- The result was WAIT with material evidence is contradictory.
- The raw observations showed that long and short directions coexisted across the seven timeframes and also inside different evidence types.
- This exposed an overly broad conflict rule in Market Evidence: any coexistence of LONG and SHORT observations was being treated as a global contradiction.
- That rule is incompatible with hierarchical MTF reasoning because opposite directions across timeframes are expected market context and must be resolved by the SETUP ENGINE hierarchy rather than rejected upstream.

### Correction
- Market Evidence conflict detection now distinguishes:
  - same-timeframe opposing structural signals (BOS, CHoCH, Displacement) — material conflict;
  - opposite structural directions on different timeframes — preserved as MTF context, not a global evidence conflict;
  - opposing contextual zones such as bullish/bearish FVG or OB — not automatically a structural contradiction.
- The SETUP ENGINE remains responsible for resolving higher-timeframe structure against 15m/5m confirmation.
- No direction is inferred from the count of LONG/SHORT observations.
- No 1m-only direction or level inference is introduced.

### Commits
- 0c41b2b72c178b782ff56492d81e6f41e087e981 — classify MTF evidence conflicts by timeframe.
- 66a5572532ab00b8af1742f47ca33c6f9d4e9840 — add regression coverage for hierarchical MTF conflict semantics.

### NEXT UNFINISHED
1. Run focused Market Evidence + SETUP ENGINE tests on the deployed release.
2. Run the complete pytest suite.
3. Run live BTC FindSetup again.
4. Inspect whether the corrected hierarchy produces a real setup candidate when the current market state supports one, or correctly returns WAIT/NEED_MORE_EVIDENCE when it does not.
5. Verify family, direction, entry zone/condition, invalidation, targets, confirmation timeframes and source timeframes.
6. Record the exact production result before advancing the SETUP ENGINE block.


## 2026-10-01 — SETUP ENGINE: scenario-specific zones and live target gap

### Completed since previous checkpoint
- Corrected Market Evidence so directional event opposition is not manufactured into a global conflict.
- Commits:
  - `68dbd11d9fb6b64ae7ca646acb9a2a8c56882568` — preserve per-timeframe conflicts in MTF evidence.
  - `19641d8151f48fa2318b1a3dbf58215c890c5965` — align MTF conflict expectations.
  - `2f1c282a507bd5777cb8c4ee448a5b2a67a8075c` — do not infer evidence conflicts from event opposition.
  - `0f5133be8d76d78b8ba3dd02c9fad618071042b0` — align evidence-conflict tests with event semantics.
- Focused conflict regression: **11 passed, 1 warning**.
- Full regression after conflict correction: **338 passed, 21228 warnings, 0 failed**.
- Corrected setup geometry so entry zones, invalidation and targets respect the relevant timeframe and actionable side of current price.
- Commits:
  - `c7638b4` — enforce coherent MTF setup levels.
  - `d9d3f97` — respect resolved MTF direction in decision gate.
  - `46354e6` — preserve legacy decision direction gating.
  - `3b12ce6` — enforce setup level geometry tests.
  - `be632a2` — preserve hierarchical MTF direction tests.
  - `d2c033b8162522f0886be6ffd161b252045d57ed` — keep setup targets at zone timeframe scale.
  - `501067ca40d29b3a576224b58fb8f106be68af89` — prevent lower-timeframe setup targets.
- Added scenario-specific entry-zone concept priority:
  - continuation: directional Order Block, then FVG;
  - reversal: FVG, then directional Order Block;
  - breakout failure: directional Order Block, then FVG.
- Commits:
  - `b3ffee36a5bfe53ddfed73e8eaeef28779de7372` — make setup zones scenario-specific.
  - `a708a62e0147b2891edde1eedfa0d90ca397d984` — scenario-specific zone tests.
  - `1d5d6aded0dd494d15685e8fee06f0417d4cccab` — honor scenario zone priority.
- Focused SETUP ENGINE tests: **14 passed, 1 warning, 0 failed**.
- Complete repository regression: **341 passed, 21228 warnings, 0 failed**.

### Live BTC verification
The live BTC Spot FindSetup path now reaches the scenario/setup layers with all seven timeframes and populated evidence:
- seven TF: `1m, 5m, 15m, 1h, 4h, 1d, 1w`;
- Market Evidence: PROCEED, no global conflict, no missing context;
- scenarios: continuation, reversal and breakout-failure have supporting evidence;
- Order Flow, CVD and Absorption are populated from the live request-scoped data.

The current live result is nevertheless:
`WAIT — setup conditions are not sufficiently specified`.

The immediate reason is explicit and valid:
- continuation: no geometrically valid target is available;
- reversal: no geometrically valid target is available;
- breakout_failure: no geometrically valid target is available.

This is **not** a test failure. It is the live setup engine refusing to invent a target when the currently available target levels do not satisfy its causal MTF geometry.

### Architectural issue now isolated
The next task is **target/level construction**, not another broad rewrite:
1. inspect the actual live seven-timeframe target/zone geometry;
2. determine which legitimate liquidity/structure objectives can serve as targets for each scenario;
3. make target construction scenario-aware where the market evidence supports it;
4. preserve WAIT when no valid objective exists;
5. add focused tests;
6. run full pytest;
7. run live BTC FindSetup again.

Do not relax causality, do not use 1m as the sole source of setup levels, and do not manufacture targets merely to produce LONG/SHORT.

### CURRENT STATE
- Seven-timeframe SETUP ENGINE: implemented and regression GREEN.
- Scenario-specific entry zones: implemented and regression GREEN.
- CVD / Absorption / Order Flow: live integrated and GREEN.
- Full regression: **341 passed, 21228 warnings, 0 failed**.
- Live BTC: reaches scenario reasoning but currently returns honest WAIT because no geometrically valid target is available.

### NEXT UNFINISHED
**Target/level construction for the SETUP ENGINE** — inspect real live level geometry, define valid scenario-aware target selection, test it, then re-run full regression and live BTC smoke.


## 2026-10-01 — SETUP ENGINE target geometry inspection: first live diagnostic

The requested live seven-timeframe level dump returned only `close` for every timeframe:
- 1w: close 84055.59
- 1d: close 84037.96
- 4h: close 84037.96
- 1h: close 84037.97
- 15m: close 84037.96
- 5m: close 84037.96
- 1m: close 84037.96

None of the requested target/zone columns were present in the returned frames:
`previous_high`, `previous_low`, active liquidity prices, liquidity breakout levels, FVG bounds, or Order Block bounds.

### Finding
This means the current live target problem cannot yet be solved by choosing a better target among those columns: the FindSetup frames used by this diagnostic are not exposing those level columns at all. Before changing target-selection logic, the production feature/level population path must be inspected to determine where the relevant causal levels actually live and why they are absent from `r.frames`.

### NEXT UNFINISHED
Inspect the live frame columns and the feature builders that populate previous highs/lows, liquidity, FVG and Order Block levels. Do not invent fallback target prices and do not relax target geometry until the source-level data contract is understood.


## 2026-10-01 — Correction: live level diagnostic inspected the wrong object

The previous diagnostic conclusion that the level columns were absent from AICFA was **incorrect**.

### Root cause of the diagnostic mistake
- `FindSetupResult.frames` intentionally contains the raw OHLCV frames returned by the market-data provider.
- The analytical level columns are added by `build_features()` and stored in `FindSetupResult.analysis` / the internal `analyses` mapping.
- `find_setup.py` passes the full `analyses` mapping into `analyze_setups()`.
- Therefore the absence of FVG/OB/liquidity columns in `r.frames` is expected and is **not** evidence of a production data-loss bug.

### Code verification
`src/aicfa/features.py` explicitly propagates:
- liquidity: `previous_high/low`, active liquidity prices, breakout levels;
- FVG: bullish/bearish bounds and lifecycle;
- Order Blocks: bullish/bearish bounds and lifecycle.

`src/aicfa/setup_analysis.py` reads those analytical columns from `context.latest_rows`, which is built from the `analyses` mapping.

### Consequence
The live `WAIT` caused by missing geometrically valid targets remains the real issue to investigate. The next diagnostic must inspect `r.analysis` or the actual setup candidate source rows, not `r.frames`.

No production code was changed for the incorrect diagnostic. This correction is recorded to preserve the mistake rather than rewrite history.

### NEXT UNFINISHED
Inspect the actual analytical level values from `r.analysis` / seven-timeframe `analyses` and determine why target selection finds no valid objective above/below current price for the live scenarios. Then implement only the target rule supported by the actual causal level data.


## 2026-10-01 — SETUP ENGINE: causal target fallback added

### Investigation
- Inspected the real Git implementation instead of changing target logic blindly.
- Confirmed `build_features()` already propagates liquidity, FVG, Order Block and causal rolling-range features into analytical frames.
- Confirmed `_target_levels()` only accepted three objective families:
  - active liquidity;
  - liquidity breakout;
  - confirmed previous swing high/low.
- This can legitimately produce no target even when the current analytical state has a valid causal range extreme above/below price, because confirmed swing/liquidity events may not exist on the required timeframe at the latest row.

### Change
- Added `internal_previous_high/low` as additional causal target candidates.
- Added `rolling_high_60 / rolling_low_60` as the final causal fallback.
- No fabricated prices, future data, or 1m-only target logic was introduced.
- Existing target timeframe restriction remains: target must come from the entry timeframe or a higher timeframe.
- Added regression test proving a 4h causal rolling high can serve as a target when liquidity/swing target columns are unavailable.

### Commits
- `7cba3c9422e88dca8a1fe1043921a6d7e245db42` — test: allow causal rolling extreme target fallback
- `31b052e08dd39018ab888fca2e8a94e17b042738` — fix: add causal rolling extremes as target fallback

### NEXT UNFINISHED
Run focused SETUP ENGINE tests, then full regression, then repeat live BTC FindSetup smoke. The live smoke must verify that the target is an actual causal analytical level, remains at entry-TF or higher, and is not derived solely from 1m.


## 2026-10-01 — SETUP ENGINE focused regression after target fallback

- Server result: **8 passed, 0 failed, 1 warning in 0.55s**.
- The warning is the known non-fatal `PytestCacheWarning` caused by release-directory permissions.
- Target fallback regression is green.
- No code change is required for the warning.

### NEXT UNFINISHED
Run the full AICFA regression, then perform the live BTC FindSetup smoke and inspect the resulting target level.


## 2026-10-01 — Full regression after target fallback

- Server result: **342 passed, 0 failed, 21228 warnings in 56.39s**.
- This is the new full green checkpoint.
- The warnings remain non-fatal; the known `PytestCacheWarning` is due release-directory permissions.
- Target fallback implementation is fully covered by the regression suite.

### NEXT UNFINISHED
Run the live BTC FindSetup smoke and inspect whether the current seven-timeframe market state now produces a geometrically valid causal target without relying on 1m.


## 2026-10-01 — SETUP ENGINE: MTF target construction correction

The previous target selector was too dependent on the entry timeframe and selected the first valid objective in timeframe/source order rather than treating targets as multi-timeframe market objectives.

### Correction implemented
- _target_levels() now evaluates all allowed setup-objective timeframes from the entry timeframe upward.
- It collects every causal target candidate that is geometrically beyond current price.
- It selects the nearest valid objective in the trade direction.
- Source priority is used only as a tie-breaker.
- The execution timeframe cannot become the target source when the entry zone is higher-timeframe.
- No future data, fabricated prices, or 1m-only direction logic was introduced.

### Commits
- 986d78fcb676c87b5da8ed115de397273cf91425 — fix: build setup targets from MTF objectives
- 52fe4ed787e916b97ccaed0d22765cd3721798dc — test: validate MTF target selection

### Verification
Server pytest verification is pending.

### NEXT UNFINISHED
Run focused SETUP ENGINE tests, then full pytest. If green, run live BTC FindSetup smoke and inspect the actual selected entry zone, invalidation and MTF target.


## 2026-10-01 — SETUP ENGINE: target hierarchy grounded in market-delivery methodology

The prior target implementation was treated as an implementation experiment and is superseded by a stricter target hierarchy.

### Methodology constraints checked against external references
- SMC/ICT setup logic treats structure, liquidity, displacement and PD arrays as a connected framework; an isolated OB/FVG is not sufficient by itself. citeturn0search5turn0search8
- Profit targets are described as the next draw on liquidity / significant opposing liquidity or higher-timeframe objective, rather than an arbitrary nearby price column. citeturn2search0turn2search10
- Higher-timeframe structure supplies the directional anchor while lower timeframes provide confirmation/execution; 1m must not determine the setup by itself. citeturn2search9turn1search0
- Binance provides public klines, trades, depth and realtime WebSocket market data required for AICFA to construct current-market state itself. citeturn0search0turn0search1turn0search2

### Implementation
- Target selection is now hierarchical: active liquidity → liquidity breakout objective → confirmed structural extreme → causal range extreme.
- The first target is the nearest valid objective within the highest available objective class, not the nearest arbitrary level across all classes.
- A second distinct target may be returned beyond Target 1 when a causal objective exists.
- Targets remain constrained to the setup timeframe and higher; execution-only lower timeframes cannot manufacture the setup target.
- Direction, entry and invalidation remain MTF/hierarchical; 1m remains execution context only.

### Commits
- de5ac103767d2cb8ad7acf08951f761a6b8320a6 — fix: prioritize true draw on liquidity targets
- 8418084ffd0562df50fe3d4f59fa2efdbca08202 — test: validate draw on liquidity target hierarchy

### 80% objective
80% is a **measured acceptance target, not a hard-coded claim**. We cannot honestly declare an 80% win rate before running a causal, out-of-sample evaluation with fixed entry/SL/TP rules and costs. Backtesting literature specifically warns about data mining, multiple testing and overfitting. citeturn3search12turn3search14

The product goal is therefore: **only emit setups when the full confluence passes the defined gates, then measure realized setup outcomes and iterate against a fixed evaluation protocol.** No artificial confidence percentage will be used to make a weak setup look like an 80% setup.

### NEXT UNFINISHED
Run focused SETUP ENGINE tests, then full regression. If green, run live BTC FindSetup and inspect the actual MTF setup: scenario, entry zone, invalidation, Target 1, Target 2 and confirmation requirements. After that, build the causal setup outcome evaluator needed to measure the real hit rate.


## 2026-10-01 — SETUP ENGINE: live smoke exposed forbidden 1m setup levels

### Live BTC verification
The corrected live FindSetup smoke reached a READY setup, but exposed a remaining architectural violation:
- direction was resolved from higher-timeframe structure: 1w=long;
- all seven required timeframes were present;
- target levels came from 5m, not 1m;
- however the selected entry zone was still an active bullish FVG on **1m**;
- invalidation was also derived from a **1m previous low**;
- continuation, reversal and breakout_failure candidates all reused the same 1m entry/invalidation/targets, so the scenario distinction was not yet reflected in actual geometry.

### Correction
Commit:
- bd508400e8b3eec75a437bf4af3e4a86d2187f8a — `fix: keep setup zones above execution timeframe`

`_zone_levels()` now explicitly excludes the execution timeframe (`1m`) from setup-zone construction.

Architectural rule reinforced:
- 1m = execution/microstructure confirmation only;
- setup Entry zone and setup Invalidation cannot be manufactured from 1m;
- setup direction is still determined hierarchically from higher-timeframe structure;
- setup targets may use relevant MTF objectives but never 1m-only objectives.

### Verification
The code correction has been committed to `main`. A new live BTC smoke is required to verify that Entry/Invalidation now come from an appropriate higher setup timeframe and that scenario-specific geometry is not collapsing into one identical 1m-derived setup.

### NEXT UNFINISHED
Run live BTC FindSetup smoke against the new release and inspect:
1. actual setup entry timeframe/source;
2. invalidation timeframe/source;
3. target timeframes/sources;
4. whether continuation/reversal/breakout_failure remain meaningfully distinct.
Do not advance to outcome evaluation until this live setup geometry is GREEN.


## 2026-10-01 — SETUP ENGINE: structural geometry gates verified

### Regression verification
After enforcing structural setup geometry and scenario-specific evidence in the MTF SETUP ENGINE:
- focused SETUP ENGINE tests: **10 passed, 1 warning**;
- full regression: **344 passed, 0 failed, 21228 warnings**;
- the remaining full-suite failure was a legacy scenario-preservation test; the scenario-specific evidence gate was correctly scoped to the real MTF engine, while legacy/non-numeric analysis continues to preserve upstream scenario hypotheses.

### Relevant commits
- a43bdd0de6b138a32e54895e569caa0579a1c0ab — test: keep scenario zone fixture geometrically valid
- dde7003d92426eaed35fab332b41a045b361fb39 — test: keep both scenario fixtures above RR threshold
- 53aa3d2962314e32d3dd7a2779768a4800fa064b — fix: preserve legacy scenario hypotheses

### Current checkpoint
The complete test suite is green. The known pytest cache permission warnings remain non-fatal and are not part of the functional failure count.

### NEXT UNFINISHED
Run live BTC FindSetup smoke against the current release and inspect the actual MTF setup geometry:
1. entry timeframe/source;
2. invalidation timeframe/source and whether structural risk is sane;
3. Target 1/Target 2 timeframes/sources and draw-on-liquidity logic;
4. continuation/reversal/breakout_failure geometry and whether unsupported scenarios are omitted;
5. final LONG/SHORT/WAIT/NO TRADE decision.
Do not advance to outcome evaluation until this live geometry checkpoint is GREEN.


## 2026-10-02 — SETUP ENGINE: duplicate actionable geometry gate verified

### Implementation and regression history
- Added actionable-geometry deduplication so the real MTF SETUP ENGINE does not emit multiple setup objects when different scenario hypotheses resolve to the exact same trade geometry.
- Geometry identity is based on direction plus Entry zone, Invalidation and ordered Target levels with their value/timeframe/source provenance.
- This does **not** rank scenarios. Distinct geometry remains distinct; only duplicate actionable trade geometry is collapsed.
- Legacy/non-numeric setup analysis is intentionally excluded from this deduplication so its multiple plausible scenario hypotheses remain preserved.
- Commits:
  - `81828cae30016fddbf4c203ad2c5cced375bcee5` — fix: collapse duplicate actionable setup geometry
  - `817224946bba9c0e91460d619a2de9afb2ba44fc` — test: collapse duplicate actionable scenario geometry
  - `e43742e9535785063e08749065e2c9c8ee1b632c` — fix: scope setup geometry dedupe to MTF engine
  - `8993238318d6a11ec3957f0442e4710fe4d9e823` — fix: remove duplicate setup assessment return

### Regression found and repaired
- The first dedupe implementation was applied too broadly and caused the legacy test `test_multiple_plausible_setups_are_preserved` to fail because distinct legacy scenario hypotheses were collapsed.
- The correction scoped deduplication only to the real numeric MTF engine.
- A deployment syntax error was then exposed: a duplicated tail of the final `SetupAssessment` return caused `IndentationError` during test collection. This was a patching mistake, not an architectural issue, and was removed in commit `8993238318d6a11ec3957f0442e4710fe4d9e823`.

### Verification
- Focused server regression after repair: **18 passed, 0 failed, 1 warning in 0.59s**.
- Covered `tests/test_setup_analysis.py` and `tests/test_setup_engine_mtf.py`.
- The only warning is the existing non-fatal FrostDeploy pytest cache permission warning.
- Full repository regression after commit `8993238` is **not yet run**.

### CURRENT STATE
- MTF SETUP ENGINE duplicate-geometry gate: **focused GREEN**.
- Legacy scenario preservation: **focused GREEN**.
- Full repository regression: **pending** after the latest fix.
- Live BTC setup geometry: not yet re-verified after the latest dedupe/fix sequence.

### NEXT UNFINISHED
1. Run the complete pytest suite after commit `8993238`.
2. If GREEN, run the live BTC FindSetup smoke and inspect one coherent actionable setup: Entry zone, Invalidation, ordered Target 1/Target 2, confirmation and source timeframes, with duplicate scenario geometry collapsed.
3. Only after live setup geometry is GREEN, build the causal setup outcome evaluator to measure the actual realized setup hit rate against the project’s ~80% product objective.


## 2026-10-02 — SETUP ENGINE: full regression GREEN after geometry dedupe

### Verification
- Complete server regression after the duplicate actionable-geometry fix: **345 passed, 0 failed, 21228 warnings, 54.01s**.
- This is the new full green checkpoint after commit `8993238318d6a11ec3957f0442e4710fe4d9e823`.
- The warnings remain non-fatal and are the known FrostDeploy pytest cache permission warning.

### CURRENT STATE
- MTF SETUP ENGINE: regression GREEN.
- Legacy scenario preservation: GREEN.
- Duplicate actionable scenario geometry: deduplication implemented and GREEN.
- Full repository regression: **345 passed**.
- Live BTC setup geometry still needs re-verification after the final dedupe sequence.

### NEXT UNFINISHED
Run the live BTC FindSetup smoke and inspect the actual coherent actionable setup geometry: Entry zone, Invalidation, ordered Target 1/Target 2, confirmation and source timeframes, and duplicate scenario handling. Do not advance to the outcome evaluator until this live geometry checkpoint is GREEN.


## 2026-10-02 — SETUP ENGINE: live BTC geometry GREEN

### Verification
Live BTC Spot FindSetup smoke against the current release produced one coherent actionable setup:

- Decision: `LONG`
- Reason: `direction and setup structure are both supported by current evidence`
- All seven required timeframes present: `1m, 5m, 15m, 1h, 4h, 1d, 1w`
- Candidate count: **1**
- Scenario: `continuation`
- Direction: `long`
- Entry zone: **15m active bullish FVG**, 84412.01–84432.90
- Invalidation: **5m sell-side liquidity**, 84101.62
- Target 1: **4h previous high**, 85649.95
- Target 2: **1d previous high**, 87395.67
- Confirmation: `15m, 5m`
- Source timeframes: all seven required timeframes
- No conflicts.
- Unsupported breakout-failure scenario is explicitly reported as incomplete.
- Reversal is not emitted separately because it resolves to the exact same actionable geometry as continuation.

### Geometry gate
This closes the live geometry checkpoint:
- Entry is above the 1m execution timeframe.
- Invalidation is above the 1m execution timeframe and comes from a structural/liquidity level.
- Targets are ordered and come from 4h/1d causal objectives.
- Target 1 and Target 2 form one ordered target ladder for the same directional thesis.
- Duplicate scenario geometry is collapsed rather than emitted as multiple identical trades.
- 1m remains execution/microstructure context and does not determine the setup geometry.

### CURRENT STATE
- MTF SETUP ENGINE: **regression GREEN**
- Legacy scenario preservation: **GREEN**
- Duplicate actionable geometry handling: **GREEN**
- Full repository regression: **345 passed, 0 failed**
- Live BTC setup geometry: **GREEN**
- Current product path now reaches a coherent live actionable setup with Entry / Invalidation / Target 1 / Target 2 / Confirmation.

### NEXT UNFINISHED
**Build the causal setup outcome evaluator.**

The evaluator must measure realized outcomes of emitted setups against the fixed Entry/Invalidation/Target rules and the project product objective of approximately 80% profitable realized setups over a sufficiently large forward/out-of-sample sample. Do not hard-code 80%, do not turn it into a confidence score, and do not alter setup rules merely to improve a retrospective metric.

## MASTER ROADMAP — FROM START TO CURRENT STATE

### 1. С чего начали
AICFA задуман как собственная специализированная AI-система для анализа крипторынка и цифровых активов, а не оболочка над чужой AI-моделью.
Исходная цель: система получает текущий рынок/график сама, анализирует его и при наличии условий формирует торговый setup.
Обязательные режимы: Scalping, Intraday, Swing, Position.
Главный аналитический фундамент: Smart Money Concepts — Market Structure, Liquidity, BOS/CHoCH/MSS, HH/HL/LH, FVG, Order Blocks, Displacement, Premium/Discount и связанные подтверждения.
На первом этапе рабочий актив — BTC; позже планируется расширение на top-100.

### 2. Что построили по дороге
Постепенно собрана собственная детерминированная аналитическая цепочка:
- market-data adapters и универсальное разрешение актива;
- OHLCV и семь обязательных таймфреймов;
- Market Structure;
- Liquidity;
- Displacement;
- FVG;
- Order Blocks;
- Premium / Discount;
- Unified SMC;
- Multi-Timeframe analysis;
- Volume / Volatility;
- Derivatives;
- Canonical Market State;
- Setup Events;
- Market Evidence и Evidence Reasoning;
- Scenario Reasoning;
- Setup Detection;
- Setup Analysis;
- Decision Layer;
- trade-level Order Flow / Microstructure;
- trade-level CVD;
- causal L1 observation history;
- causal Absorption;
- единый MTF SETUP ENGINE.

Параллельно построен leakage-safe фундамент для будущей оценки/данных, но обучение модели не является текущей целью проекта.

### 3. Ключевые архитектурные решения
- AICFA сама строит аналитический вывод из рыночных данных; биржа не выдаёт ей готовый сигнал.
- Основная MTF-цепочка: `1w → 1d → 4h → 1h → 15m → 5m → 1m`.
- 1m — только execution/microstructure context.
- 1m никогда не является единственным источником направления, Entry, Invalidation или Target.
- Один actionable setup = одно направление/тезис + одна Entry zone + один Invalidation + упорядоченный Target ladder + Confirmation.
- Разные цели внутри одного тезиса могут быть TP1/TP2; это не означает два разных setup.
- Если разные гипотезы дают абсолютно одинаковую торговую геометрию, в реальном MTF engine они схлопываются в один actionable setup.
- Если доказательств недостаточно или геометрия невалидна, система должна честно выдавать WAIT/NO TRADE.
- Никаких будущих данных, искусственных исторических order-book данных или подгонки правил ради красивого результата.
- Цель ~80% прибыльных реализованных setup — продуктовая acceptance target, а не hard-coded confidence и не заявленный результат.

### 4. Где дошли сейчас
Текущий путь уже проходит от реального рыночного ввода до actionable setup:
`market data → 7 TF → аналитические слои → evidence/scenario reasoning → SETUP ENGINE → LONG/SHORT/WAIT → Entry / Invalidation / TP1 / TP2 / Confirmation`.

Последний проверенный live BTC setup:
- LONG;
- continuation;
- Entry: 15m bullish FVG 84412.01–84432.90;
- Invalidation: 5m sell-side liquidity 84101.62;
- TP1: 4h previous high 85649.95;
- TP2: 1d previous high 87395.67;
- Confirmation: 15m + 5m;
- все 7 TF присутствуют;
- 1m не используется для setup geometry;
- duplicate reversal geometry не эмитируется отдельно;
- breakout_failure не выдумывается при неполном evidence.

Текущий regression checkpoint: **345 passed, 0 failed**.
Live BTC setup geometry: **GREEN**.

### 5. К чему идём
Теперь AICFA должна перейти от «мы умеем сформировать setup» к «мы умеем причинно измерять, что произошло с каждым сформированным setup после его появления».

Следующий блок:
**Causal Setup Outcome Evaluator.**

Он должен:
1. фиксировать emitted setup как неизменяемый snapshot;
2. фиксировать Entry zone, Invalidation, TP1/TP2, direction, confirmation и provenance;
3. после появления будущих market observations определять, что произошло первым и по каким правилам;
4. корректно обрабатывать достижение Entry, SL, TP1, TP2, отсутствие активации и неоднозначные случаи;
5. не использовать данные, которые были недоступны на момент setup;
6. работать на forward/out-of-sample данных;
7. считать фактические outcome-метрики по большой выборке;
8. отдельно учитывать комиссии/slippage, когда будет определён execution protocol;
9. не менять setup rules задним числом ради улучшения метрики.

Только после появления этого evaluator можно объективно проверять, насколько AICFA приближается к продуктовой цели ~80% прибыльных реализованных setup.

### 6. Что НЕ делаем сейчас
- Не уходим в обучение модели ради обучения.
- Не возвращаемся к поиску локальной LLM.
- Не делаем 1m главным аналитическим timeframe.
- Не строим сигналы из чужого готового AI.
- Не добавляем искусственные уровни/данные ради LONG/SHORT.
- Не пересобираем уже GREEN Order Flow/CVD/Absorption без конкретной регрессии.

### CURRENT SOURCE OF TRUTH
С этого момента этот master roadmap фиксирует непрерывную линию проекта: **идея → аналитические блоки → MTF SETUP ENGINE → live GREEN setup → causal outcome evaluation → последующая проверка/улучшение качества**.

### NEXT UNFINISHED
**Build the AICFA chart visualization output layer.**

The causal setup outcome evaluator remains a later validation block and is deliberately deferred while the product output is made directly visible on the market chart.


## 2026-10-02 — PRODUCT DIRECTION: VISUAL SETUP OUTPUT ON AICFA CHART

### Decision
The product direction is clarified: AICFA does not need a separate screenshot-reading workflow as the immediate interface. The existing AICFA market-analysis path already constructs the setup from real market data. The next product layer is to make that exact analytical result visible as a high-quality chart with the setup drawn on it.

### What AICFA already does
The current live analytical path reaches a coherent actionable setup from current market data:
- 7-timeframe market context: 1w → 1d → 4h → 1h → 15m → 5m → 1m;
- Market Structure / SMC;
- Liquidity;
- BOS / CHoCH / MSS-related structural events;
- FVG;
- Order Blocks;
- Displacement;
- Premium / Discount;
- Volume / Volatility;
- Derivatives;
- Order Flow;
- CVD;
- causal L1 history;
- Absorption;
- scenario reasoning;
- Setup Engine;
- Decision Layer.

The current output already contains the core trade geometry: direction, Entry zone, Invalidation, ordered Target 1 / Target 2 and confirmation, with source timeframe/provenance.

### New product goal
AICFA should produce two equivalent representations of the same setup:
1. a precise textual setup;
2. a professional chart visualization of that exact setup.

The chart is not a second analysis engine. It is a visualization of the already-computed AICFA analytical state and setup geometry. The renderer must not invent or modify Entry, Invalidation, Targets, BOS, FVG, OB or other analytical facts.

### Required chart quality
The visualization must be a real trading-style chart, not a generic decorative graph. It should contain the relevant market data and clearly visualize, where available and causally supported:
- candlesticks / price action;
- timeframe and asset;
- current price;
- Market Structure labels and levels;
- BOS / CHoCH / MSS events where produced by the analytical layers;
- HH / HL / LH / LL structure where available;
- liquidity levels / sweeps;
- FVG zones;
- Order Blocks;
- displacement events;
- Premium / Discount context where applicable;
- Volume / relevant market activity information;
- the final Entry zone;
- Invalidation / SL;
- ordered Target 1 / Target 2 and their provenance;
- setup direction and scenario;
- confirmation requirements.

Only information actually produced by AICFA's analytical layers should be drawn. Missing evidence must remain missing; the renderer must never fabricate annotations just to make the chart look complete.

### Rendering architecture
The intended flow is:
current market data → AICFA analytical layers → MTF SETUP ENGINE → textual setup + chart renderer → final visual setup

The renderer should be deterministic and GPU-free. It can use the same OHLCV/feature/event objects already used by AICFA and draw the resulting setup programmatically.

### Explicit non-goal
We are not changing the product into screenshot ingestion/vision analysis at this stage. A user-uploaded screenshot is a possible future interface concept, but it is not the current implementation target and must not replace the deterministic AICFA analytical core.

### Validation requirements
The chart output must be validated against the exact textual setup:
- Entry coordinates must match the Setup Engine exactly;
- Invalidation must match exactly;
- Target 1 / Target 2 must match exactly and remain ordered;
- source timeframe/provenance must be preserved;
- 1m must not become a setup-geometry source merely because the chart is rendered on 1m data;
- annotations must respect causal availability and not display future-derived structure;
- WAIT / NO TRADE must render as such without drawing a fictional trade setup;
- the chart renderer must have regression tests for geometry and causal annotation behavior.

### Relationship to outcome evaluation
The causal setup outcome evaluator remains required for later measurement of realized setup quality and the product's approximately 80% profitability objective. It is deferred, not cancelled. The immediate next implementation is the chart visualization layer because it makes the already-existing AICFA reasoning and setup directly inspectable by a human.

### NEXT UNFINISHED
Build the AICFA chart visualization output layer.


## 2026-10-02 — CHART VISUALIZATION: implementation started

### Reconciliation before code
- Re-read the current `PROJECT_PLAN.md` and confirmed it remains the single source of truth.
- Confirmed `main` HEAD is `3ce75fe1fec658e5778dd00dd65ef6b67a731d39`, the checkpoint that defines chart visualization as the current product direction.
- Confirmed the repository already reaches the live GREEN MTF SETUP ENGINE checkpoint and that chart rendering must visualize existing analytical state rather than recalculate trading logic.
- Confirmed `requirements.txt` currently has no plotting library. The first implementation step is therefore to add a CPU-only deterministic renderer dependency and a dedicated visualization contract.

### Implementation contract being fixed before coding
The chart layer will be split into:
1. a deterministic visualization model that converts existing AICFA OHLCV/features/setup state into render-ready primitives;
2. a renderer that only draws those primitives and never changes Entry, Invalidation, Targets, provenance, or analytical decisions.

The first renderer output will be a high-quality PNG suitable for human inspection and regression testing. SVG/export extensions remain possible after the first GREEN renderer.

The primary chart timeframe will be selected from the actionable setup Entry zone timeframe, while higher/lower timeframe levels are projected with explicit source-timeframe labels. The 1m timeframe remains execution/microstructure context and can never manufacture setup geometry.

The first implementation must support, where the source data actually contains them:
- candles and volume;
- current price;
- HH/HL/LH/LL and structure direction;
- BOS/CHoCH/MSS events;
- liquidity levels and sweeps;
- FVG zones;
- Order Blocks;
- displacement;
- Premium/Discount context;
- Entry zone;
- Invalidation;
- ordered TP1/TP2 with provenance;
- direction, scenario, confirmation and source timeframes.

No annotation is fabricated when its causal source is absent.

### Immediate action
Implement the visualization model + renderer, then add focused geometry/causality tests, run them on the server, run the full regression, execute a real BTC smoke, inspect the produced chart, and update this journal after each meaningful checkpoint.

### NEXT UNFINISHED
Build the deterministic AICFA chart visualization model and first PNG renderer.


## 2026-10-02 — CHART VISUALIZATION: first implementation checkpoint

### Code completed
- Added `src/aicfa/chart_visualization.py`.
- Added a typed `ChartModel` contract containing candles, current price, setup geometry, provenance, analytical events, structure labels, zones, direction, scenario, confirmation and status.
- Added deterministic CPU-only PNG rendering with matplotlib.
- The renderer consumes the existing `SetupAssessment` geometry verbatim; it does not recalculate Entry, Invalidation or Targets.
- Primary chart timeframe is the setup Entry timeframe; the 1m layer cannot become setup geometry.
- Added initial rendering of candles, volume, current price, setup levels, FVG/OB zones, BOS/CHoCH/MSS, liquidity sweeps, displacement and HH/HL/LH/LL labels when those columns are present.
- WAIT/NO TRADE produces no fictional trade levels.
- Added focused tests for geometry/provenance, 1m exclusion, WAIT behavior, PNG generation and future-feature causality.
- Added `matplotlib>=3.9,<4` as the CPU rendering dependency.

### Commits
- `69fbd18b48f0aa4b25ddd9924e944ef8e95ddba6` — docs: record chart visualization implementation start
- `8969ec8dd23b1e27e53ce476003ec6a04bcd3212` — feat: add deterministic AICFA chart model and renderer
- `305433dfe4fd1d70c3722e46ece2214949883d5c` — test: cover chart geometry and causal rendering
- `df2a3e4734151e06fc178ecb69d69961afb9b826` — build: add CPU chart rendering dependency

### Verification state
- Code has been written and committed to `main`.
- Server/FrostDeploy verification is **pending**.
- Full regression is **pending** after the new visualization dependency/module.
- A real BTC chart smoke and visual inspection are still required.
- This first implementation is intentionally the visualization foundation, not yet the final integrated product output path.

### NEXT UNFINISHED
Run the chart visualization focused tests and full regression on the deployed/current server release, then perform a real BTC rendering smoke and inspect the produced chart before advancing the renderer.
