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
