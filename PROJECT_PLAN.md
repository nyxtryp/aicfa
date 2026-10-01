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

