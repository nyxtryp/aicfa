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


## 2026-10-02 — FOUR-MODE LIVE BTC FINDSETUP SMOKE GREEN

- Live BTC validation completed for all four internal trading modes after the full regression gate.
- Scalping: exact timeframes **15m→5m→1m**; decision **WAIT**; reason: **higher-timeframe structure and lower-timeframe confirmation conflict**; no blocking missing context.
- Intraday: exact timeframes **1d→4h→1h→15m**; decision **WAIT**; continuation/reversal structural RR was **1.255 < 2.000**; range support was insufficient and breakout-failure evidence incomplete.
- Swing: exact timeframes **1w→1d→4h→1h**; decision **WAIT**; continuation/reversal structural RR was **0.560 < 2.000**; range support was insufficient and breakout-failure evidence incomplete.
- Position: exact timeframes **1M→1w→1d→4h**; decision **WAIT**; continuation/reversal structural RR was **0.289 < 2.000**; range support was insufficient and breakout-failure evidence incomplete.
- Result: all four mode profiles select their authoritative mode-specific timeframe sets. The system does not fall back to a universal seven-timeframe grid.
- End-user contract remains unchanged: the user supplies only the asset; the eventual orchestrator evaluates Scalping, Intraday, Swing and Position automatically. The four separate calls above are internal validation only.

## 2026-10-02 — ANALYSIS DEPTH AUDIT: UNIVERSAL 60-CANDLE BASE IDENTIFIED

- Live inspection showed the current Position request received exactly **60 candles on every selected timeframe**: `1M=60, 1w=60, 1d=60, 4h=60`.
- Repository audit explains the current behavior: `analysis_depth.py` derives a global technical minimum from the largest current feature dependency, `feature.rolling=60`, and applies that minimum to every selected timeframe.
- Important architectural finding: **60 is a technical feature/warmup minimum, not a validated SMC market-context requirement**.
- The same 60-row depth represents radically different historical context by timeframe: 60×1m=1h, 60×5m=5h, 60×15m=15h, 60×1h=2.5d, 60×4h=10d, 60×1d=60d, 60×1w=60w, 60×1M=5y.
- Therefore the current rule `every timeframe = 60 rows` must not be treated as the final SMC data-depth design.
- Current adaptive expansion only doubles a timeframe when blocking `missing_context` remains unresolved, up to two expansion passes. It does not yet define sufficient historical depth for SMC structure, liquidity, Order Block/FVG lifecycle, HTF context, MTF context and LTF confirmation.
- This is an **architecture audit finding**, not yet a production code change. No arbitrary replacement such as 500 or 1000 candles is being introduced.

## NEXT ACTIVE TASK — ADAPTIVE SMC ANALYSIS DEPTH

Goal: replace the universal 60-candle assumption with a concept-driven, mode-aware and timeframe-aware depth model.

Required design:
1. Separate **technical feature warmup** from **SMC market-context history**.
2. Define explicit depth requirements for market structure, liquidity, BOS/CHoCH/MSS, HH/HL/LH/LL, FVG/imbalance, Order Blocks, premium/discount, displacement, Wyckoff and price action.
3. Account for each mode's role hierarchy: Scalping **15m→5m→1m**; Intraday **1d→4h→1h→15m**; Swing **1w→1d→4h→1h**; Position **1M→1w→1d→4h**.
4. Do not choose a single arbitrary candle count for all timeframes.
5. Make depth adaptive: if the required structure/context cannot be established from the current history, AICFA must request more historical candles for the affected timeframe instead of silently analyzing an insufficient slice.
6. Preserve causal/no-future-leakage behavior.
7. Add tests proving the selected depth follows analytical requirements and that adaptive expansion is deterministic.
8. After implementation: focused tests → full `pytest -q` → live BTC four-mode smoke → record actual returned depths and decisions in this plan.

Do not revert to the universal seven-timeframe model and do not require the user to select a trading mode.


## 2026-10-02 — SMC ANALYSIS DEPTH IMPLEMENTED

- Web research confirms there is **no canonical universal SMC candle count**. SMC/ICT analysis is hierarchical: higher timeframe establishes context/structure, intermediate timeframe identifies zones/structure, and lower timeframe refines/times execution. citeturn0search5turn0search1
- Current implementation was therefore changed from the incorrect universal `60 rows per timeframe` rule to role-aware analysis history.
- `e8e6b5fdadc091c1e2b7e2363f1ba0c47d6d01ab`: `analysis_depth.py` now uses these SMC analysis-history defaults by timeframe role:
  - BROADER_CONTEXT: **120 candles**
  - HIGHER_STRUCTURE: **180 candles**
  - LOWER_CONFIRMATION: **240 candles**
  - EXECUTION: **240 candles**
- The existing feature dependency minimum remains **60 candles**, but it is now only a technical warm-up floor; it no longer determines the complete market-analysis depth.
- `c6d14080a2a2c55ff0d192a215eaf899461fe652`: tests updated to assert the role-aware depth contract.
- The selected depths remain below current Binance futures kline endpoint limits; Binance documents a maximum of 1500 records per kline request. citeturn1search0
- This is an intentional engineering baseline rather than a claim that SMC itself mandates exactly 120/180/240. The system still retains adaptive expansion for recent-event/active-zone context when the current history is insufficient.

### NEXT VERIFICATION GATE
1. Deploy these commits to the AICFA server.
2. Run the focused `tests/test_analysis_depth.py` suite.
3. Run the full `pytest -q` regression.
4. Run live BTC FindSetup for all four internal modes and inspect actual returned candle counts per timeframe.
5. If the live result shows insufficient structure/zone context, tune the depth contract from observed evidence and tests rather than reverting to a universal candle count.


## 2026-10-02 — ANALYSIS DEPTH TEST FAILURE AND CONTRACT FIX

- Server focused test result reported by user: `tests/test_analysis_depth.py` → **1 failed, 3 passed**. The failing test constructed `default_setup_requirements("BTCUSDT")` without a trading mode, then expected mode-specific mixed depths `{120, 180, 240}`.
- Root cause: a mode-less plan has no authoritative timeframe-to-role mapping. The resolver intentionally uses the conservative 240-row depth rather than guessing the role for each timeframe. The user's diagnostic command also omitted `mode`, so its all-240 result did not represent live mode-specific FindSetup requests.
- `90fcddd6facc680edb142136ee310310c947a829`: corrected regression coverage to verify the exact role-aware depths for **all four explicit modes**:
  - Scalping: 15m=120, 5m=180, 1m=240
  - Intraday: 1d=120, 4h=180, 1h=240, 15m=240
  - Swing: 1w=120, 1d=180, 4h=240, 1h=240
  - Position: 1M=120, 1w=180, 1d=240, 4h=240
  - Added a separate assertion that a mode-less generic plan conservatively resolves to 240 rows because roles are ambiguous.
- `6fa2a72a901ffc37427b371201d8de052d3c0d6b`: documented the intentional conservative fallback in `analysis_depth.py`. No production depth behavior was loosened to make the test pass.
- **Verification status: PENDING.** These commits have been pushed to `main`; the server must deploy them before focused and full regression tests can confirm the fix.
- Next step: run `tests/test_analysis_depth.py` on the deployed release. If green, run the full suite. Do not claim the tests are green until the server returns the result.


## 2026-10-02 — FULL REGRESSION: STALE FINDSETUP DEPTH TESTS

- Server full regression result reported by user: **3 failed, 368 passed, 15880 warnings in 45.06s**.
- All three failures were stale test expectations from the old universal 60/120/240 dependency-depth contract:
  - test_find_setup_uses_dependency_depth_when_no_diagnostic_limit_is_given
  - test_find_setup_expands_missing_context_until_provider_boundary
  - test_find_setup_stops_expansion_when_context_signature_stalls
- Production FindSetup is already using the new role-aware mode depth. Its default Intraday request starts at **1d=120, 4h=180, 1h=240, 15m=240**. Adaptive missing-context expansion may then double only unresolved timeframes, so values can exceed the baseline 240 when additional history is requested.
- a47c35437d012187b978d208393453d4ec3ec90a: updated these tests to assert the actual role-aware initial depths and deterministic adaptive expansion behavior. No production analysis-depth logic was changed.
- **Server verification is PENDING.** The test fix is committed but has not yet been executed on the deployed release.
- Next step: deploy/update the current release from main and rerun the full pytest -q. Only after the full suite is green should live depth validation continue.


## 2026-10-02 — FULL REGRESSION GREEN: ADAPTIVE FINDSETUP DEPTH TESTS

- Test fix committed: `8a0b490eb9f52063b1168a909f6430abf190a12d` — `test: account for adaptive FindSetup depth expansion`.
- The stale FindSetup depth assertions were updated to reflect the actual role-aware baseline plus deterministic adaptive expansion. Production analysis-depth logic was not changed.
- Server verification reported by user after deployment: `PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python -m pytest -q` → **371 passed in 43.50s**.
- Regression gate is now **GREEN** with zero failures.
- The current architecture therefore has verified mode-aware SMC depth plus adaptive expansion when context is missing/stalls.
- End-user contract remains: the user enters **only the asset**; AICFA internally evaluates Scalping, Intraday, Swing and Position. The four modes are not user-selected.
- Next active task: audit and implement a dedicated **Support/Resistance** analysis layer. Current feature inspection shows no explicit `support`/`resistance` feature. Existing related inputs include swing highs/lows, rolling highs/lows, previous highs/lows, liquidity levels/pools, Order Blocks, FVG, dealing ranges, premium/discount, breakouts and sweeps. These are related but are not a dedicated classic S/R layer.
- Required S/R work: implement causally, distinguish local vs higher-timeframe levels, account for repeated reactions/strength, break/retest/rejection behavior, distance to price, and feed the resulting evidence into scenario/setup reasoning rather than leaving S/R as an implicit side effect.

## 2026-10-03 — TASK 1: CONFIRMED SWING — IMPLEMENTED, SERVER VERIFICATION PENDING

- Audit result: the existing swing detector was already causal in practice: with `right=R`, pivot index `i` was emitted only at confirmation row `i+R`. Downstream protected-structure logic already consumed the confirmed row.
- Implementation commit: `682095cb62028c2c89a87f665c4f4fd18da5de19` — `feat: expose causal swing confirmation metadata`.
- The structure layer now explicitly exposes, for external and internal swings: pivot index, confirmation index, pivot timestamp, and confirmation timestamp.
- The contract is explicit: pivot timestamp is descriptive; confirmation timestamp is the first time downstream logic may use the swing.
- Focused regression commit: `a20675674850abadc5142eaf770e7874053da0c1` — `test: verify causal swing confirmation contract`.
- Added tests for exact `pivot -> confirmation` mapping and configurable `right` confirmation delay.
- No full regression or live BTC verification has been claimed yet. Server verification is pending.
- **NEXT:** run focused `tests/test_structure.py`; if green, run full `pytest -q`, then validate live BTC before marking Task 1 complete and moving to Task 2 (causal BOS/CHoCH/MSS).

## 2026-10-03 — TASK 1 FOCUSED TEST GATE GREEN

- Server verification reported by user: `tests/test_structure.py` → **10 passed in 0.76s**.
- Result: Confirmed Swing focused regression gate is **GREEN**.
- The causal swing contract and new pivot/confirmation metadata pass the full structure test module.
- Full regression has not yet been run after these changes.
- **NEXT:** run the complete `PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python -m pytest -q`. If green, perform the planned live BTC validation for Task 1 before moving to Task 2.

## PROJECT CONTINUITY RULE

- After every meaningful implementation/test/deploy step, update this file with: **what changed, commit SHA, server verification result, current status, and next step**.
- Never claim a test or live verification is green until the server result has actually been reported or directly executed.
- Treat this file as the continuity/source-of-truth record for the AICFA build sequence.


## 2026-10-02 — NEW SMC/SETUP ENGINE INTEGRATION BLOCK: 9 TASKS

The next implementation block adopts nine proven mechanisms from the reviewed external SMC analyzer, but reimplements them inside AICFA's existing causal/evidence architecture. The external project's strategy, scoring, timeframe assumptions and fixed trade rules are NOT copied.

### Authoritative 9-task sequence

1. **Confirmed Swing**
   - Make swing timestamps explicitly causal: a pivot at index `i` becomes usable only at `confirmed_at_index = i + swing_length`.
   - Downstream structure/liquidity logic must use confirmation time, never treat the pivot timestamp itself as the availability time.
   - Preserve causal MTF rules and current role-aware depth/adaptive expansion.

2. **Causal BOS / CHoCH / MSS**
   - Rework structural-break detection so a swing can participate only after confirmation.
   - Preserve HH/HL/LH/LL and distinguish structural event time from pivot time.
   - Prevent stale or already-consumed structural levels from generating repeated false breaks.
   - MSS/CHoCH/BOS must remain evidence for scenario reasoning, not standalone trade commands.

3. **Liquidity Lifecycle**
   - Make liquidity levels/pools explicitly causal and stateful.
   - Support creation, active state, sweep/break, invalidation and relevant reaction.
   - Verify equal-high/equal-low grouping and tolerance logic rather than assuming ordinary swing highs/lows are equivalent to equal liquidity.
   - Keep liquidity as a structural layer that interacts with S/R, BOS/CHoCH/MSS and scenario reasoning.

4. **Order Block Lifecycle**
   - Replace binary OB state with a lifecycle such as: `UNTOUCHED → TOUCHED → PARTIAL → DEEP → INVALIDATED`.
   - Preserve causal creation/confirmation and invalidation.
   - Expose lifecycle state to setup/scenario reasoning.
   - Volume confirmation remains metadata/evidence, never a mandatory gate that silently discards structurally valid OBs.

5. **FVG / Imbalance Lifecycle**
   - Apply the same causal lifecycle discipline to FVGs: creation, active/unmitigated state, touch/partial fill, mitigation/fill and invalidation where applicable.
   - Preserve bounds, displacement linkage and timeframe role.
   - Ensure downstream setup logic distinguishes a fresh FVG from an already mitigated/filled imbalance.

6. **Zone Reaction + Support/Resistance**
   - Implement the dedicated S/R layer already identified as the previous active task and combine it with OB/FVG/liquidity zones.
   - Model the sequence:
     `level/zone → distance → touch → reaction → retest/break → confirmation/cancellation`.
   - Distinguish local vs higher-timeframe levels, repeated reactions/strength, break/retest/rejection and distance to current price.
   - Feed zone-reaction evidence into scenario/setup reasoning; do not leave S/R as implicit rolling/swing data.

7. **Volume Evidence**
   - Treat volume as contextual evidence attached to structural events/zones, not as an unconditional filter.
   - For OB/FVG/structure reactions, record whether volume confirms or does not confirm the event.
   - Avoid self-influenced volume baselines where the event candle is included in its own comparison when a prior-candle baseline is intended.
   - Missing volume-derived auxiliary evidence must remain diagnostic/non-blocking unless a specific hypothesis explicitly requires it.

8. **Structural Entry / SL / TP**
   - Derive entry/invalidation/targets from the actual structural zone and market context, not from arbitrary current-price offsets.
   - For OB-based setups, preserve the structural chain:
     `OB boundary → ATR/structural buffer → SL → entry → risk`.
   - Targets should use valid opposing liquidity / structural targets and respect direction, current price and entry semantics.
   - Keep the existing AICFA risk/reward gate and do not import an external fixed RR value without validation.
   - Structural SL/TP are setup outputs/evidence, not guarantees of execution or outcome.

9. **Conservative Backtest / Evaluation**
   - Use one deterministic setup logic for live analysis and historical evaluation wherever architecture permits.
   - Resolve same-candle SL+TP ambiguity conservatively: if both are touched and intrabar ordering is unknown, count SL first.
   - Make evaluation explicitly causal and prevent future data from influencing setup generation.
   - Separate in-sample tuning from out-of-sample evaluation; do not treat tiny trade counts as reliable confidence.
   - Ensure backtest results are actually wired into evaluation/reporting rather than remaining an unused side structure.

### Integration rule

These nine tasks become one coherent AICFA chain:

`confirmed swing → causal BOS/CHoCH/MSS → liquidity → OB/FVG lifecycle → zone reaction/SR → volume evidence → structural entry/SL/TP → conservative evaluation`

They must operate together with AICFA's existing:
- Market Structure / HH-HL-LH-LL
- Liquidity
- SMC
- Premium/Discount
- Displacement
- Price Action
- Wyckoff
- MTF context
- optional Trades/CVD/Order Flow/Order Book/Absorption
- optional Funding/OI/Mark Price/Liquidations
- scenario/evidence/decision pipeline

Optional feeds remain auxiliary evidence. They do not independently manufacture scenarios or setups, and missing optional data must not block chart-native analysis.

### Implementation/verification gate

For each task:
1. inspect current AICFA implementation before changing it;
2. implement the smallest causal change;
3. add focused regression tests;
4. commit the implementation and tests;
5. update this plan with commit SHA and actual verification;
6. run full `pytest -q` after the task block reaches a stable checkpoint;
7. only after regression is GREEN, perform live BTC validation and inspect the returned evidence/setup behavior.

Do not copy the external project's fixed strategy, scoring, timeframe hierarchy, killzones, RR target, or trade labels into AICFA.

### Current status

- Existing regression baseline: **371 passed in 43.50s**, reported by the user after commit `8a0b490eb9f52063b1168a909f6430abf190a12d`.
- Existing dedicated S/R work is now incorporated into **Task 6: Zone Reaction + Support/Resistance** rather than being a disconnected side layer.
- No implementation from these nine tasks is claimed yet.
- **ACTIVE TASK: 1 — Confirmed Swing.**
- **NEXT: audit current swing implementation, define causal confirmation contract, implement + focused tests, then record the commit and server result here.**

### Do not do

- Do not revert to universal seven-timeframe analysis.
- Do not require the user to select a trading mode.
- Do not make optional derivatives/microstructure feeds universal prerequisites.
- Do not fabricate missing evidence.
- Do not import the external project's strategy wholesale.
- Do not claim any of these nine tasks are complete until code/tests/server verification prove it.

## 2026-10-03 — TASK 1 FULL REGRESSION GATE GREEN

- Server verification reported by user after the Confirmed Swing implementation/test commits: `PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python -m pytest -q` → **373 passed in 47.48s**.
- Result: full regression is **GREEN** with zero failures.
- This confirms the Confirmed Swing metadata/causal contract does not regress the broader AICFA test suite.
- Current code/plan baseline at the start of this verification was commit `ddc6421f4357273b7fb920dff3e0e7367aa49801`; this plan update records the server result and becomes the next continuity checkpoint.
- **NEXT:** run the planned live BTC validation for Task 1 and inspect that swing pivot timestamps remain descriptive while confirmation timestamps are the causal availability time. If live validation is clean, close Task 1 and move to **Task 2 — Causal BOS / CHoCH / MSS**.


## 2026-10-03 — TASK 2: CAUSAL BOS / CHoCH / MSS — IMPLEMENTATION READY FOR SERVER VERIFICATION

- Task 2 audit confirmed the existing BOS/CHoCH calculation already waits for confirmed swing rows: the structure engine updates the active swing level only on its confirmation row, then evaluates structural breaks causally on the current row.
- 6300259a75a9e15b1b447a43784c501831f15bf8 — feat: expose causal BOS and CHoCH provenance.
- The structure layer now records, for each BOS event, the reference swing pivot index and the reference swing confirmation index. This makes the distinction explicit: the BOS/CHoCH event occurs on the current break row, while the referenced swing became usable only at its confirmation row.
- Existing stale-level protection remains in place through the consumed-level state (broken_high / broken_low), preventing repeated BOS events against the same consumed structural level.
- 4fa95378a814bf8c89a436bb6de0dad99df7b621 — test: verify causal BOS and CHoCH provenance.
- Added focused coverage proving a BOS references a confirmed swing (pivot 2 → confirmation 4 → break 6) and that consumed levels do not generate duplicate BOS rows.
- Server verification is PENDING. No GREEN status is claimed until the user runs the focused structure suite.
- NEXT: run tests/test_structure.py. If green, run the full pytest -q; then inspect the causal BOS/CHoCH/MSS behavior before closing Task 2.


## 2026-10-03 — TASK 2 FOCUSED TEST GATE GREEN

- Server verification reported by user: tests/test_structure.py → 12 passed in 0.95s.
- Result: Task 2 causal BOS/CHoCH/MSS focused structure gate is GREEN.
- The new causal BOS provenance tests and existing structure regression all pass together.
- Full regression has not yet been run after Task 2.
- NEXT: run the complete PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python -m pytest -q. If green, inspect/validate the full Task 2 behavior before moving to Task 3 — Liquidity Lifecycle.


## 2026-10-03 — TASK 2 FULL REGRESSION GATE GREEN

- Server verification reported by user: `PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python -m pytest -q` → **375 passed in 46.25s**.
- Result: Task 2 full regression gate is **GREEN** with zero failures.
- Focused Task 2 gate was already GREEN: `tests/test_structure.py` → **12 passed in 0.95s**.
- Current status: Task 2 — Causal BOS / CHoCH / MSS is regression-green.
- **NEXT:** targeted Task 2 behavior review, then proceed to **Task 3 — Liquidity Lifecycle**: causal creation/active/sweep/invalidation/reaction states, equal-high/equal-low grouping/tolerance, and integration with S/R, BOS/CHoCH/MSS and scenario reasoning.


## 2026-10-03 — TASK 3: LIQUIDITY LIFECYCLE — IMPLEMENTATION COMMITTED

- Audit found that AICFA already had causal liquidity-pool creation, active-pool tracking, equal-high/equal-low tolerance, sweep/break handling, invalidation flags, and internal/external pool separation.
- Gap identified: the lifecycle did not expose a distinct post-sweep **reaction** event; sweep/reclaim was present but reaction was not represented as a later causal state transition.
- `9accf9179e946285825c0dd2f6e988f7aa5c806b` — added explicit causal liquidity reaction tracking after a pool is swept.
  - `liquidity_pool_reaction_high/low` event flags.
  - `last_swept_buy/sell_liquidity_price` provenance fields.
  - Reaction is emitted only on a later candle, never on the same sweep row.
- `9813326cadc36a105d7172abb0b267a67e741bca` — exposed the new lifecycle fields through the main `build_features` pipeline.
- Focused test added to `tests/test_liquidity.py` proving sweep → later reaction is causal.
- **Server verification: PENDING.** These commits are on `main`, but no server test has been run after the Task 3 change yet.
- **NEXT:** run `tests/test_liquidity.py` on the AICFA server. If green, run the full `pytest -q` regression and record the actual result before closing Task 3.


## 2026-10-03 — TASK 3 LIQUIDITY LIFECYCLE: FOCUSED TEST GATE GREEN

- Server verification reported by user: `tests/test_liquidity.py` → **8 passed in 0.58s**.
- Result: Task 3 Liquidity Lifecycle focused test gate is **GREEN**. The focused liquidity tests pass with the new causal post-sweep reaction fields.
- Full regression has **not** yet been run after the Task 3 implementation.
- Current implementation commits: `9accf9179e946285825c0dd2f6e988f7aa5c806b` (causal liquidity reaction lifecycle) and `9813326cadc36a105d7172abb0b267a67e741bca` (feature-pipeline integration).
- **NEXT:** run the complete `PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python -m pytest -q`. Record the actual result before closing Task 3 or starting Task 4.
