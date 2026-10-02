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
