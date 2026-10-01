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
