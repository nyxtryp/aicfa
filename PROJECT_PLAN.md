## 2026-10-01 — Repair MarketEvidence timeframe column mapping

### Finding
Focused verification of the first MarketEvidence repair produced:
`2 failed, 6 passed`.

The failures exposed a mapping bug in the adapter: it read base-timeframe columns for every requested timeframe, causing the same 1m observations to be emitted repeatedly, and it did not resolve the existing `mtf_<timeframe>_...` columns used by the integrated feature frame.

### Forward fix
- `1b0b71a2fa465adb23187d5c88bd8747efecde11` — make MarketEvidence resolve columns by timeframe.
- Base `1m` uses canonical columns.
- Higher timeframes use the existing `mtf_<timeframe>_<column>` state columns.
- Lifecycle columns use the corresponding timeframe-prefixed state when present.
- No analytical rules or causal boundaries were changed.

### Verification
The repair is committed to Git but has not yet been deployed/verified on FrostDeploy.

### Exact next step
Deploy current `main` and rerun:
1. `tests/test_market_evidence_adapter.py`
2. the three adaptive FindSetup tests
3. full pytest
4. live BTC FindSetup smoke without explicit `limit`.


## 2026-10-01 — MarketEvidence base-timeframe repair

### Finding
FrostDeploy verification of `1b0b71a` still had 2 failures:
- base 1m FVG was missing;
- independent 4h analysis was missing.

Root cause: the adapter's column resolver assumed every non-1m timeframe required `mtf_<timeframe>_...`. That is correct when reading a combined multi-timeframe frame, but incorrect for `build_market_evidence_from_frames()`, where each independent frame contains its own canonical/base columns.

### Forward fix
- `91c7216f6a98881ecf567c6ac93d13af54601619`
- Column resolution is now relative to `base_timeframe`.
- The base timeframe reads canonical columns.
- Other requested timeframes read `mtf_<timeframe>_...`.
- Lifecycle state follows the same rule.
- No rollback and no change to analytical concepts or causal policy.

### Verification
Not yet deployed/verified.

### Exact next step
Deploy current `main` and rerun the focused MarketEvidence + adaptive FindSetup tests. If green, continue to mandatory full pytest and live BTC FindSetup smoke.


## MarketEvidence follow-up — bb00dd0f60e7af67ddc5a9635b42c0bb463bca47
- Finding: build_market_evidence() used a single emitted flag, so once BOS/displacement/etc. emitted, later FVG/Order Block concepts were skipped even when independently active.
- Fix: track emitted_concepts and suppress only a concept already emitted by its lifecycle path; independent supported concepts can now coexist.
- Status: code committed; deployment/verification pending.
- Exact next step: deploy current main, then rerun the focused MarketEvidence + adaptive FindSetup tests. If green, run full pytest.


## MarketEvidence verification — 2026-10-01
- Focused verification: 8 passed, 9217 warnings, 15.97s.
- Full suite verification: 305 passed, 18145 warnings, 47.09s.
- Result: MarketEvidence repair and adaptive FindSetup regression coverage are GREEN on the deployed current release.
- Performance optimization remains backlog; analytical development continues forward.
- Exact next step: proceed to the next analytical roadmap item after MarketEvidence repair.

## 2026-10-01 — Order Flow / Microstructure v1 contract

### Finding
Repository inspection confirmed that AICFA already defines semantic data kinds for `TRADES` and `ORDER_BOOK`, but the analytical core had no dedicated Order Flow / Microstructure implementation. The existing live market-data router is OHLCV-only, so this stage must not invent exchange transport or pretend that trade/order-book data are already available.

External microstructure references support separating signed executed flow from resting-book imbalance; these are distinct observables and must remain distinct in AICFA.

### Forward implementation
- `54a908959d69ddf2ad66d7da3c6f2fcfc9bee189` — add `src/aicfa/microstructure.py`.
- Trade-flow contract accepts venue-provided aggressor side `+1/-1` and computes buy volume, sell volume, signed volume, normalized imbalance, and trade counts.
- L1 book contract accepts timestamped bid/ask prices and sizes and computes latest spread, spread in basis points, and bid/ask depth imbalance.
- Inputs must be causally ordered by timestamp.
- No future-price trade-side inference.
- No LONG/SHORT/WAIT/NO TRADE output.
- No exchange-specific fetching.
- `07d40c188fe5db5800cae4f6d53d73d054f2bac2` — add focused causal/validation tests.

### Verification
- Focused server verification: `8 passed, 2 warnings in 0.49s` on FrostDeploy release `2026-10-01T09-31-36-84315af`.
- Full suite: `313 passed, 18146 warnings in 51.60s` on the same release.
- Result: Order Flow / Microstructure v1 primitives are GREEN on deployed main.

### Discovered limitation
The existing Binance/Bybit adapters and centralized fallback router still expose only OHLCV transport. The repository already contains `order_flow.py` and `order_book.py` analytical feature layers, but they are not yet fed by live TRADES / ORDER_BOOK transport.

### Exact next step
Extend the existing Binance/Bybit adapters and centralized fallback router with causal `TRADES` / `ORDER_BOOK` transport, add provider/fallback tests, then deploy and verify before wiring these data kinds into the request-scoped knowledge/data-requirement flow.


## 2026-10-01 — Existing-router TRADES / ORDER_BOOK transport

### Finding
Repository inspection confirmed the live scanner already uses a centralized Binance-primary / Bybit-fallback market-data architecture. No second router is required. `MarketCapability.TRADES` and `MarketCapability.ORDER_BOOK` were already declared in the source registry, but the actual provider adapters exposed only OHLCV.

### Forward implementation
- `3e9201fcf37d11d7c293b853886ae98c9efb0517` — extend the provider contract with `fetch_trades()` and `fetch_order_book()`.
- `1dbd615f4caf77399daa7cdfc9b765d52e8ad167` — add centralized fallback routing for both data kinds, preserving provider provenance and failure attempts.
- `9df27e785642eb0f1124a9aa5afa3bba3018294c` — add Binance public recent-trade and order-book transport.
- `fc6224bf5ca763dbf2396488bdf4c38859242baf` — correct Binance public endpoint path handling.
- `6df0a4b335b1304bdc105bc83d7cf90507db4d03` — add Bybit public recent-trade and order-book transport.
- `1c98530da11f7356d3e654280aa84f79633e858f` — add centralized-router fallback/capability tests.
- `6648e4fb3a7bfd92af77d7d92b48405b994ef964` — add Binance transport tests for signed public trades and L1 order book.
- `7ba1ae137309cff53a36496b7f85b3d49e322257` — add Bybit transport tests for signed public trades and timestamped L1 order book.
- Trade side is normalized to AICFA's causal `+1` buy / `-1` sell contract using venue-provided aggressor information.
- Order-book transport currently normalizes the best bid/ask only; Binance uses local observation time as the conservative availability timestamp because the REST response lacks a public source timestamp, while Bybit uses its returned source timestamp.
- No fabricated data, no cross-exchange merging, and no trading decision is produced.

### Verification
Not yet deployed or server-verified. The next verification must run focused provider/router transport tests first, then the full suite.

### Exact next step
Deploy current `main` and run:
1. `PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_binance_market_data.py tests/test_bybit_market_data.py tests/test_market_data_microstructure_transport.py`
2. full `PYTHONPATH=src .venv/bin/python -m pytest -q`
3. if green, run a live BTC Spot transport smoke for Binance trades/order book and controlled Binance failure -> Bybit fallback.
4. then wire `TRADES` / `ORDER_BOOK` into the request-scoped knowledge/data-requirement flow and feed the existing order-flow/microstructure analytical layers.


## 2026-10-01 — TRADES / ORDER_BOOK transport full-suite verification

- FrostDeploy release: `2026-10-01T09-39-56-cd003e5`.
- Focused transport verification: `30 passed, 1 warning in 0.57s`.
- Full regression verification: `321 passed, 18146 warnings in 51.08s`.
- Result: existing Binance-primary / Bybit-fallback TRADES + ORDER_BOOK transport is GREEN at the full-suite level; warning is the known pytest cache permission warning.
- Exact next step: live BTC/USDT Spot transport smoke for Binance trades + L1 order book, then controlled Binance failure with Bybit fallback for both data kinds. Verify provider provenance, non-empty real rows, causal schema, and no cross-exchange merging before wiring TRADES / ORDER_BOOK into request-scoped knowledge/data requirements.


## 2026-10-01 — Live BTC Spot TRADES / ORDER_BOOK transport smoke GREEN

- FrostDeploy release: `2026-10-01T09-39-56-cd003e5`.
- Binance primary returned real BTCUSDT Spot trades and L1 order book rows.
- Binance trades preserved venue aggressor side as AICFA `+1/-1`; order book returned bid/ask with observation timestamp.
- Controlled Binance failure `CONTROLLED_TEST_BINANCE_FAILURE` caused the existing router to fall back to Bybit for both TRADES and ORDER_BOOK.
- Fallback results were non-empty and provenance recorded the failed Binance attempt; no cross-exchange merging/fabrication occurred.
- Result: live transport smoke GREEN.
- Exact next step: wire `TRADES` / `ORDER_BOOK` into the existing request-scoped Knowledge/Data Requirement flow and feed the existing order-flow/microstructure analytical layers. Do not create a second market-data router.


## 2026-10-01 — Knowledge/Data Requirements + FindSetup microstructure integration

### Forward implementation
- `09bf47eff1f14952ce405f2bcede039a0d11c504` — add explicit knowledge concepts `microstructure.order_flow` and `microstructure.order_book` with observable evidence and non-signal semantics.
- `d3b98dfe757f299c15cce706c526152bcf7e9f6d` — map those concepts to distinct `TRADES` / `ORDER_BOOK` data kinds and include both concepts in the default setup requirement plan.
- `398d4397dd5ecb6ea1510369d205c0ca3852a18e` — expose TRADES / ORDER_BOOK through the existing shared snapshot wrapper without creating a second router.
- `99a5a7e5224d38ad5a88ff77c94829fa4fdbf0d5` — feed live trade and L1 book transport into `FindSetup` and the existing `order_flow.py` / `order_book.py` analytical layers.
- `b0af21d18745e25e2d603afd69abeadfe64b644a` — preserve the provider contract for injected test providers while using source-aware transport when available.
- `0b2bf1f44ce8f52c1c3b7b5e5995f5e649b1f7c9` — add FindSetup microstructure integration coverage.
- `25faf3a99e335ac33eccc0a347c8afd1fe7eb5de` — add knowledge/data-requirement coverage for distinct microstructure data kinds.

### Causal rules
- Signed trade flow uses venue-provided aggressor side only.
- Trade-flow intervals are restricted to completed one-minute intervals relative to the request `now_ms`.
- L1 order-book analysis uses the source observation timestamp; it is not backfilled into earlier candles.
- Microstructure remains descriptive evidence; it does not create a decision by itself.

### Verification
Not yet deployed or server-verified.

### Exact next step
Deploy current `main` and run focused:
1. `tests/test_data_requirements.py`
2. `tests/test_find_setup.py`
3. `tests/test_market_data_microstructure_transport.py`
4. then full pytest.
If green, run live BTC FindSetup smoke without explicit `limit` and inspect that TRADES / ORDER_BOOK are actually populated in the result before advancing to the next analytical integration block.
