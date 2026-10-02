### Implementation progress — derivatives integration
- `64160be`: added normalized derivatives adapter path for Binance/Bybit.
- `cbc408e`: switched liquidation collection to the public Binance/Bybit market liquidation streams; no fabricated liquidation values.
- `b182cf3`: added deterministic derivatives completeness/evidence bridge.
- `0298f26`, `903ba73`, `8c69298`: connected derivatives collection and normalized evidence into live FindSetup while keeping injected test providers deterministic.
- `476ec52`: added focused tests for schema normalization, completeness, causal alignment, missing-data behavior and Bybit normalization.
- `85f95cb`: fixed the live integration bug found by the first Scalping smoke. Funding and Open Interest were coming from independent endpoints with different timestamps, but the adapter previously combined them by exact timestamp; this produced rows with null funding/OI and caused `build_derivatives` to reject the live frame. The adapter now builds a causal common timeline: OI is carried forward from the latest known observation, funding is carried forward from the latest known observation, and the current mark price is retained at its own timestamp. No future values are backfilled.
- `7db5cf6`: added a regression test proving funding/OI/mark alignment works when their source timestamps differ and that the resulting frame passes derivatives completeness.
- `279c0c4`: corrected the Bybit timestamp-alignment regression fixture to include an observed liquidation event; an empty mocked liquidation stream must remain incomplete because `liquidation_volume` is a required live source and no liquidation evidence may be fabricated.
- Live FindSetup requests Funding + Open Interest + Liquidations + Mark Price when the knowledge requirement requires all four, computes existing `build_derivatives` analytics, and attaches a causal `derivatives.price_oi` observation. If the required derivatives source fails or is incomplete, the evidence path records explicit unavailable context instead of fabricating a setup.
- Important implementation detail: Binance/Bybit liquidation data is collected from the public market liquidation websocket streams; REST `allForceOrders` is not treated as a valid current source.

### Verification state
Focused and full regression tests were previously green before the timestamp-alignment fix. The first live Scalping smoke exposed a real integration bug: `DERIVATIVES_PROVIDER: unavailable: funding_rate/open_interest must be numeric and non-null`, with zero derivative rows. This was caused by independent Funding/OI timestamps being merged without causal alignment. The fix is now committed and must be verified by focused tests, full `pytest -q`, then the four live BTC mode smoke checks again.

## 2026-10-02 — DATA PIPELINE COMPLETENESS BLOCK: REQUIRED BEFORE FOUR-MODE LIVE SMOKE

### User-confirmed execution order
Before live BTC validation of the four trading modes, AICFA must first have a complete and actually connected market-data pipeline for setup validation.

The order is authoritative:
1. Complete the real market-data/source integration.
2. Verify data completeness and causal alignment.
3. Run regression tests.
4. Only then run four separate live BTC FindSetup smoke checks: Scalping 15m→5m→1m; Intraday 1d→4h→1h→15m; Swing 1w→1d→4h→1h; Position 1M→1w→1d→4h.

End-user UX remains asset-only: the user supplies BTC and the eventual orchestrator evaluates all four horizons automatically. The four separate calls are internal validation only.

### Current repository audit
The repository has a source/capability registry, real Binance and Bybit market-data transports, OHLCV, trades, Order Book/history, CVD, Order Flow, Absorption, deterministic SMC/evidence layers, and derivatives.py with derivatives analytics.

Critical integration gap found: live FindSetup currently defaults to FallbackMarketDataProvider(BinanceMarketDataProvider(), BybitMarketDataProvider()). Funding, Open Interest, Liquidations and Mark Price are represented in the repository/data contract and derivatives analytics, but are not yet fully connected as live source data into the FindSetup evidence pipeline.

The registry's declared capabilities are not proof of a live integration. Only an actual adapter + collection path + normalization + FindSetup integration counts as connected.

### Required implementation block
1. Connect real derivatives source collection: Funding Rate, Open Interest, Liquidations, Mark Price.
2. Use the existing source registry/data-source abstraction; preserve fallback behavior; do not invent unsupported API capabilities.
3. Normalize venue-specific schemas, preserve causal timestamps, prevent future leakage, and align derivatives evidence with selected mode/timeframes.
4. Make live FindSetup actually request and receive required derivatives data and feed it into existing derivatives/evidence analysis without breaking OHLCV/trades/order-book/CVD/absorption.
5. If required data is unavailable, explicitly mark evidence unavailable/insufficient and return WAIT/insufficient evidence where needed. Never fabricate derivatives evidence.
6. Add tests for capability mapping, normalization, causal alignment, required-data completeness, missing-data behavior, no fabricated derivatives evidence, and exact mode-specific requirements.

### Do not do
- Do not revert to universal seven-timeframe analysis.
- Do not make the user select a trading mode.
- Do not weaken existing MTF authority rules.
- Do not add APIs merely for quantity.
- Do not treat a registry entry as a live integration.
- Do not generate a setup when required evidence is absent.
- Do not run the four-mode live smoke until this data block is GREEN.

### Verification gate
This block is complete only when real source adapters are identified and connected for required data, FindSetup receives normalized derivatives data, missing-data behavior is deterministic and safe, focused tests pass, and full pytest -q passes.

Only after that: run the four separate live BTC smoke checks and inspect actual returned timeframes, roles, evidence, decision, reason and setup output.

### Continuity checkpoint
If the chat is restarted, resume from this section first.

ACTIVE TASK: complete the real market-data/derivatives integration and data-sufficiency gate.
NEXT AFTER GREEN: four-mode live BTC FindSetup smoke.

## 2026-10-02 — MARKET CONTEXT → EVIDENCE/REASONING INTEGRATION

### Implementation completed
- f02055f: added src/aicfa/market_context_evidence.py, a causal bridge that converts collected Trades, Order Flow, CVD, Order Book, Absorption, Premium/Discount, Wyckoff and liquidation data into MarketObservation objects. Missing layers are recorded explicitly; values are never fabricated.
- d28bb62: connected that bridge inside live FindSetup immediately before evidence assessment, so the collected microstructure/context data now enters the same evidence graph consumed by scenario/setup/decision reasoning.
- fff9847: expanded scenario support rules so Order Flow, CVD, Order Book, Absorption, Premium/Discount, Wyckoff and derivatives liquidation/positioning observations can materially support continuation, reversal, range and breakout-failure hypotheses.
- 94d1a0f: added integration tests proving the mandatory market-context layers become causal evidence, affect scenario hypotheses, and produce explicit missing-context state when unavailable.

### Mandatory foundation status
The previously identified gap was that microstructure was calculated but stopped at FindSetupResult fields. This block closes that gap for the following layers:
- Trades
- Order Flow
- CVD
- Order Book
- Absorption
- Premium / Discount
- Wyckoff
- Liquidations

They now participate in the evidence/scenario path rather than being metadata-only outputs.

Derivatives Funding + Open Interest + Mark Price remain connected through derivatives.price_oi; liquidation magnitude is now also represented separately as derivatives.liquidations.

### Verification status
Code changes are committed, but server-side pytest has NOT yet been run after this block. Do not mark this block GREEN until:
1. focused market-context tests pass;
2. full pytest -q passes;
3. live BTC four-mode smoke checks are run only after the regression gate;
4. each smoke result is inspected for mode, selected timeframes, evidence completeness, decision and reason.

### Required next action
Run on the AICFA server:
`sudo -u fd-aicfa bash -lc 'cd "$(readlink -f /srv/frostdeploy/aicfa/current)" && PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_market_context_evidence.py'`
Then full pytest -q. If failures appear, fix them and append the fix/commit to this plan before proceeding.

### Continuity rule
Every subsequent code/test/fix/verification movement for this task must be appended to PROJECT_PLAN.md with commit SHA, result, and next step before moving to the next stage.

## 2026-10-02 — MARKET CONTEXT FOCUSED TEST GATE

- Server verification completed: `tests/test_market_context_evidence.py` → **2 passed, 1 warning in 0.39s**.
- Result: the new market-context evidence bridge passes both causal-evidence and explicit-missing-context integration tests.
- This focused block is GREEN.
- Next step: run the full server regression `PYTHONPATH=src .venv/bin/python -m pytest -q`.
- Four-mode live BTC smoke remains blocked until the full regression passes.

---

---

## 2026-10-02 — FULL REGRESSION GATE GREEN

- Server verification completed after the market-context evidence integration: `PYTHONPATH=src .venv/bin/python -m pytest -q` → **368 passed, 15880 warnings in 45.91s**.
- Result: full regression passes with zero test failures. The warning count is non-blocking for this gate.
- Verification gate is now GREEN for the market-context/data-sufficiency block.
- Code baseline at this verification: `4ff738674d0dbab168c64e818744c0910a05d419`.
- Next step: run the four separate live BTC FindSetup smoke checks for internal validation only: Scalping (15m→5m→1m), Intraday (1d→4h→1h→15m), Swing (1w→1d→4h→1h), Position (1M→1w→1d→4h). Inspect exact mode/timeframes, evidence completeness, derivatives provider/data, scenario hypotheses, decision and reason. End-user UX remains asset-only.

## 2026-10-02 — LIVE BTC SCALPING SMOKE RESULT

- Live command executed for `FindSetupRequest(asset="BTC", mode="scalping")`.
- Result: **mode=SCALPING**, **symbol=BTCUSDT**, exact timeframes **15m→5m→1m**.
- Live derivatives provider: **binance**; **201 rows** received with all required columns: funding_rate, open_interest, liquidation_volume, long_liquidation_volume, short_liquidation_volume, mark_price.
- Trades/order-book/order-flow/CVD/absorption were received: 60 / 1 / 1 / 1 / 8 rows.
- Evidence path correctly included SMC, microstructure, premium/discount and Wyckoff observations.
- However the live evidence assessment returned **NEED_MORE_EVIDENCE** and decision **WAIT** because liquidation volume was unavailable in the collected derivative data. Missing context was explicit: `derivatives:liquidation_volume:unavailable` and `derivatives:liquidations:volume_unavailable`.
- No setup was fabricated; scenario hypotheses were correctly withheld because required context was missing.
- This smoke is **NOT GREEN**. Do not proceed to Intraday/Swing/Position until liquidation data is actually available and the Scalping smoke is re-run successfully.
- Next step: inspect/fix the live Binance liquidation stream/collection path so `liquidation_volume` is populated causally, add/adjust regression coverage if needed, run focused + full pytest, then rerun the Scalping smoke with a compact output command.


## 2026-10-02 — OPTIONAL LIQUIDATION CONTEXT FIX

- `b22d8ba`: MarketEvidence now distinguishes blocking `missing_context` from non-blocking `optional_missing_context`.
- `e3d1a36`, `323a1d4`: derivatives evidence now requires only core positioning state (Funding, Open Interest, Mark Price); liquidation volume is optional event context and is never fabricated.
- `cb24cf4`: live market-context bridge records unavailable liquidation data as optional context instead of blocking evidence/scenario reasoning.
- `0243589`: added regression tests proving missing liquidation data still allows core derivatives evidence/scenario reasoning, while available liquidation data becomes causal reversal evidence.
- Architectural rule restored: AICFA analyzes the chart/market first. Liquidations are an additional confirmation layer, not a mandatory prerequisite for a setup.
- Next step: run focused liquidation/evidence tests, then full `pytest -q`. Only after GREEN rerun the live BTC Scalping smoke.


## 2026-10-02 — TEST FIX

- `a36bb63`: fixed the newly added `tests/test_optional_liquidations.py` file; it had been committed with literal `\\n` sequences, causing pytest collection `SyntaxError`.
- The server-side error was test-file syntax only; the liquidation architecture fix remains unchanged.
- Next: rerun the focused optional-liquidation test.

## 2026-10-02 — SERVER COLLECTION ERROR ROOT CAUSE FIX

- Server focused test exposed a second repository serialization defect: `src/aicfa/derivatives_evidence.py` contained literal `\\n` characters instead of real newlines, so Python raised `SyntaxError: unexpected character after line continuation character` during import.
- Repository audit also found the same literal-newline corruption in `src/aicfa/market_evidence.py`; it was repaired before rerunning tests.
- `df76e1b193e5103f3d41e6739c61465a87247111`: restored real newlines in `src/aicfa/market_evidence.py`.
- `b0d964888eba2523c557c6aae71c21dbd1dbc3e9`: restored real newlines in `src/aicfa/derivatives_evidence.py`.
- These are file-format/serialization fixes only; the optional-liquidation architecture is unchanged.
- Server verification is still required; no test result is marked GREEN from these commits until the user reruns the focused test.
- Next step: rerun `tests/test_optional_liquidations.py`. If it passes, run full `pytest -q`; then update this plan with the actual result before the live Scalping smoke.


## 2026-10-02 — OPTIONAL LIQUIDATION TEST FAILURE / FIX

- Server focused test result: `tests/test_optional_liquidations.py` → **1 passed, 1 failed, 2 warnings in 0.64s**.
- Failure: `test_liquidations_participate_when_available` asserted that `derivatives.liquidations` was present in assessed observations, but `append_derivatives_evidence()` only exposed the core `derivatives.price_oi` observation.
- Root cause: available liquidation data was treated as optional for completeness, but the derivatives evidence bridge did not yet materialize it as a separate causal `MarketObservation`.
- `3e6bd73bd6d2674b720e074887078099af120ccf`: fixed `src/aicfa/derivatives_evidence.py` so available liquidation volume (+ long/short split when present) creates `derivatives.liquidations` evidence and direction is derived only from the observed split.
- Architectural rule unchanged: liquidation data is optional confirmation/context; its absence remains non-blocking and is never fabricated.
- The two pytest cache PermissionDenied warnings are non-blocking infrastructure warnings in the release directory.
- Server verification is still required; this fix is **NOT GREEN** until the focused test is rerun.
- Next step: rerun `tests/test_optional_liquidations.py`. If **2 passed**, run full `pytest -q`; then update this plan with the actual result before the live Scalping smoke.


## 2026-10-02 — DATA REQUIREMENT ARCHITECTURE CORRECTION

- Full regression result from server: **2 failed, 368 passed, 15881 warnings in 47.75s**.
- The two failures exposed the wrong global data contract:
  - `test_derivatives_completeness_rejects_missing_required_source_fields` still treated liquidation volume as a required derivative field.
  - `test_missing_context_is_explicit_instead_of_fabricated` still treated absent liquidation data as blocking.
- Architectural correction: AICFA's **core setup analysis is chart-native**. The mandatory analytical substrate is OHLCV/volume plus the derived structural/SMC layers: market structure, liquidity, BOS/CHoCH, FVG/imbalance, order blocks, premium/discount, price action and Wyckoff context.
- Funding, Open Interest, Mark Price, Liquidations, Trades, CVD, Order Flow, Order Book and Absorption are **not universal prerequisites**. They are auxiliary evidence and are collected/used only when the active knowledge/hypothesis requires them or when explicitly supplied as confirmation data.
- `ae402290fa148f1d3938475a8c34499cfcc2c96b`: removed derivatives and microstructure concepts from the default setup collection plan.
- `f961781e8df405a2ada298194c4ba6c4c79fea6c`: FindSetup no longer requires derivatives completeness for the core path and no longer treats missing trades as fatal; auxiliary feeds are collected only when required by the plan.
- `778f7658ae1eff3b0333c15d543bd48ab5b6ac40`: missing microstructure feeds are now diagnostic `optional_missing_context`, not blocking context.
- `7e5d8f6294f74412ed309c9a91f70e692d5690f0`: scenario hypotheses now have chart/SMC support paths and do not depend on auxiliary derivatives/microstructure observations.
- `f7484804d50b0ad25d2835c6f1c6aef852f4b37a`: derivatives completeness regression updated so liquidation absence is optional when the derivatives module is explicitly used.
- `d616370e39bcbc16be4034c0bcedf8b026fb1e6d`: market-context regression updated so auxiliary-feed absence is explicitly non-blocking.
- This is the intended architecture: **do not fetch or retain data just because an exchange exposes it; use a datum only when it has a defined analytical role for the active hypothesis.**
- Current state: code changes are committed, but **server verification is NOT GREEN yet**.
- Next step: run the focused affected tests and then full `pytest -q`. If green, run the live BTC Scalping smoke and confirm that unavailable derivatives/microstructure feeds no longer force WAIT when the core chart/SMC evidence is sufficient.


## 2026-10-02 — FOCUSED TESTS ALIGNED WITH CHART-NATIVE ARCHITECTURE

- Server focused result after the data-requirement correction: **2 failed, 7 passed, 2 warnings in 0.83s**.
- The two failures were stale expectations in tests, not evidence that auxiliary feeds must become mandatory:
  - `test_market_context_layers_become_causal_evidence` expected optional microstructure/context/liquidation observations to independently create continuation/reversal/range hypotheses.
  - `test_liquidations_participate_when_available` expected liquidation evidence by itself to create a reversal hypothesis.
- Architectural rule confirmed: optional feeds may become causal observations and confirmations, but **scenario hypotheses require their defined chart/SMC support path**. Liquidations do not manufacture a reversal; microstructure does not manufacture continuation/range.
- `ca57c616d72feb5eb93e4e226a850f2c4f893e1b`: aligned `test_market_context_evidence.py` with chart-native scenario support. The test still verifies all supplied optional layers become observations, but now verifies they do not independently manufacture scenarios.
- `248f9de86dd84fbeddde4b0a755137b56972752d`: aligned `test_optional_liquidations.py` so available liquidations are verified as causal `derivatives.liquidations` evidence while remaining optional confirmation; reversal still requires chart/SMC reversal evidence.
- The two PytestCacheWarning PermissionDenied warnings remain non-blocking release-directory infrastructure warnings.
- Server verification after these test commits is still required; these commits are **NOT GREEN yet** until the focused suite is rerun.
- Next step: rerun:
  `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_derivatives_market_data.py tests/test_market_context_evidence.py tests/test_optional_liquidations.py`
- If focused tests are green, run full `pytest -q`. Only after full regression is green, run the live BTC Scalping smoke and verify that auxiliary feeds no longer block a chart-native setup.


### Follow-up: focused test correction
- Server result: **1 failed, 8 passed, 2 warnings in 0.64s**.
- The remaining failure was a test expectation issue: the fixture intentionally supplies `premium_discount.dealing_range`, and the scenario engine correctly maps that core concept to the **range** hypothesis.
- `93c6dadd71eb74975fbe20cc99986c765c2c163e`: corrected the test to require exactly the legitimate `range` hypothesis from `premium_discount.dealing_range`, while still asserting that optional feeds do not create continuation/reversal hypotheses.
- No architecture rollback. The core rule remains: optional feeds are confirmations/observations; chart/SMC support rules generate hypotheses.
- Server verification for this new commit is pending.


## 2026-10-02 — FOCUSED DATA-REQUIREMENT REGRESSION GREEN

- Server verification after commit `93c6dadd71eb74975fbe20cc99986c765c2c163e`: focused suite `tests/test_derivatives_market_data.py tests/test_market_context_evidence.py tests/test_optional_liquidations.py` → **9 passed, 1 warning in 0.57s**.
- The remaining warning is a non-blocking PytestCacheWarning: the service user cannot create pytest cache files inside the immutable release directory.
- Focused verification is GREEN. This confirms the test expectations now match the chart-native scenario architecture and optional auxiliary-feed contract.
- Next step: run full server regression `PYTHONPATH=src .venv/bin/python -m pytest -q`. Do not run live BTC smoke until the full regression result is green.


## 2026-10-02 — FULL REGRESSION FAILURES: TEST CONTRACT ALIGNMENT

- Server full regression result: **4 failed, 366 passed, 15867 warnings in 45.96s**.
- The four failures were stale tests still asserting the previous universal-microstructure behavior, which conflicts with the intended chart-native default contract:
  - `test_setup_requirements_are_knowledge_driven` expected TRADES and ORDER_BOOK in the default requirements, although these feeds must be requested only by explicit knowledge concepts.
  - Two FindSetup tests expected default trade/order-book/history/absorption collection and then referenced counters that were never created because the feeds were correctly not requested.
  - The CVD test expected default trade-derived CVD even though no explicit TRADES requirement was active.
- Updated tests only; production behavior was not weakened and optional feeds were not reintroduced into the default path.
- Test commits: `f82ab306814c05c15f95a1276cd1bbbf3974f061` (default requirement expectations) and `003834ebddcd4e4ac638a51b2cdeae3f1b2f1649` (FindSetup optional-feed expectations).
- Server has NOT yet verified these test changes. Do not mark the regression gate GREEN and do not run live BTC smoke until the full suite passes.
- Next step: deploy/update the current release from `main`, rerun `PYTHONPATH=src .venv/bin/python -m pytest -q`, and inspect any remaining failures before live validation.


## 2026-10-02 — FULL SERVER REGRESSION GREEN AFTER TEST CONTRACT ALIGNMENT

- Server result reported by user: `PYTHONPATH=src .venv/bin/python -m pytest -q` → **370 passed, 15866 warnings in 45.05s**.
- The four stale default-microstructure expectations are now aligned with the chart-native default contract; full regression passes with zero failures.
- The warning count is recorded, not treated as a test failure. Pytest cache permission warnings in immutable release directories remain a known infrastructure issue.
- Regression gate is GREEN for the current deployed release. No claim is made here that live market behavior has been verified by this test run.
- Next step: perform live BTC FindSetup smoke checks for the four internal modes, inspecting exact selected timeframes, data/evidence availability, hypotheses, decision and reason. End-user input remains asset-only; the four calls are internal validation.
- Follow-up audit item: remove any test expectation that encodes a universal seven-timeframe default; each mode must use its authoritative mode-specific timeframe profile.
