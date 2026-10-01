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
