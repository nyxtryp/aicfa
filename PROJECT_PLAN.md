## 2026-10-03 — TASK 9 — RR ↔ OUTCOME ANALYSIS GREEN / FULL REGRESSION VERIFIED

- Added causal RR ↔ outcome analysis in production commit `3118e99fee3381d01598544e60f80edbfb614e72` — `feat: add RR outcome analysis`.
- RR is derived directly from structural Entry/SL/TP geometry; it is not used as a setup-validity filter.
- Analysis preserves the observed outcome for every setup: TP, SL, TIMEOUT, or AMBIGUOUS.
- Aggregate `mean_rr` is calculated only across resolved TP/SL outcomes; unresolved TIMEOUT/AMBIGUOUS outcomes remain visible and are excluded from that resolved aggregate.
- Mismatched setup/evaluation counts are rejected explicitly.
- Added fold-local RR ↔ outcome analysis in production commit `6a35228f43b328801c7a5b86fc0ed725b4fac913` — `feat: analyze RR outcomes across folds`.
- Fold analysis keeps chronological validation boundaries separate; observations from one fold are not mixed into another.
- Added two fold-analysis contract tests in `431946f8dca0ea6f63e0a9eca3c68f6d72f0e67e` — `test: define RR analysis across chronological folds`.
- Server focused validation after fold analysis: `tests/test_evaluation.py` = **19 passed in 0.50s**.
- Server full regression after the fold-analysis layer: **421 passed in 81.74s (0:01:21)**.
- Result: **0 failed, 0 skipped**.
- Regression increased from 419 to 421 tests after the two fold-analysis contract tests.
- No hit-rate, profitability, confidence, predictive-performance, or trading-performance claim is made from this analysis.

### Current Task 9 status

- Conservative single-setup evaluator: GREEN.
- Batch evaluation/statistics: GREEN.
- Causal label purging: GREEN.
- Chronological purged validation folds: GREEN.
- RR ↔ outcome analysis: GREEN.
- RR ↔ outcome analysis across chronological folds: GREEN.
- Fold outcome statistics by chronological folds: GREEN.
- Full regression: **GREEN — 423/423**.
- Task 9 remains ACTIVE.

### 2026-10-03 — FOLD OUTCOME STATISTICS GREEN / FULL REGRESSION VERIFIED

- Added fold-local outcome statistics in production commit `d0b29625fa5abfcd3f1bf8d0d9654567a5c6a110` — `feat: add fold outcome statistics`.
- Added contract coverage in test commit `21e2e7e8c2a2a82df0c5de0c51a1543989713a1e` — `test: define fold outcome statistics contract`.
- Corrected test construction to use the real `BatchEvaluation` contract, including required `results`, in commits `afb3968a1efb64497c922fcf1954990b8089aad7`, `bc9b2c9a056d5b740432e35c6789d6676d890562`, and `781fb414ee590efd8502984044c4a0197430db7a`.
- Fold statistics preserve each fold independently: TP/SL/TIMEOUT/AMBIGUOUS counts, resolved count, TP rate among resolved outcomes, and mean gross return among resolved outcomes.
- No cross-fold pooling or cross-fold average is created.
- Focused server validation: `tests/test_evaluation.py` = **21 passed in 0.54s**.
- Full server regression: **423 passed in 79.60s (0:01:19)**.
- Result: **0 failed, 0 skipped**.
- No performance, confidence, hit-rate, profitability, or predictive-performance claim is made from these statistics.

### Next exact action

Continue Task 9 from the existing chronological purged-fold foundation with the next evaluation/statistics layer defined by the project plan, preserving strict causal boundaries and avoiding fixed RR filters, confidence scores, arbitrary thresholds, or unsupported performance claims.


### 2026-10-03 — SETUP OUTCOME JOURNAL GREEN / FULL REGRESSION VERIFIED

- Added historical per-setup outcome journal in production commit `6190b3817e46eb9fb4ed4cf6b28d61e5613f1e0a` — `feat: add historical setup outcome journal`.
- Added contract coverage in test commit `9507961cff3652a6a8fa5df1ef8191cdbc4402ef` — `test: define setup outcome journal contract`.
- Each journal record preserves setup timestamp, direction, Entry/SL/TP, derived RR, causal outcome, outcome offset, exit price, and gross return.
- TP, SL, TIMEOUT, and AMBIGUOUS remain explicit; unresolved outcomes do not receive fabricated exit prices or returns.
- The journal pairs already-defined setups with already-computed causal evaluations; it does not create or modify Entry/SL/TP.
- Focused server validation: `tests/test_evaluation.py` = **26 passed**.
- Full regression after this layer: **426 passed in 82.05s (0:01:22)**.
- Result: **0 failed, 0 skipped**.
- Task 9 remains ACTIVE.

### Next exact action

Continue Task 9 from the verified historical setup journal and chronological evaluation foundation with the next evaluation/statistics layer defined by the project plan, preserving strict causal boundaries and avoiding fixed RR filters, confidence scores, arbitrary thresholds, or unsupported performance claims.


### 2026-10-03 — DIRECTIONAL OUTCOME STATISTICS FOCUSED GREEN

- Added directional historical setup outcome statistics in production commit `0a0c1232773942cef9dffddb614be957020f86b9` — `feat: add directional setup outcome statistics`.
- Added contract coverage in test commit `459d9d9b3f7e843540d2950827003e937adaaea1` — `test: define directional setup outcome statistics contract`.
- Statistics keep Long/Short outcomes separated; TP/SL/TIMEOUT/AMBIGUOUS remain visible and resolved metrics exclude unresolved outcomes.
- Server focused validation: `tests/test_evaluation.py` = **28 passed in 0.58s**.
- Full regression is not yet rerun after this layer.
- Task 9 remains ACTIVE.

### Next exact action

Run the full regression after directional outcome statistics, then continue Task 9 from the verified journal/evaluation foundation.


### 2026-10-03 — AICFA PRODUCT DIRECTION: THREE CORE HORIZONS + AUTONOMOUS MARKET SCANNER

- Product direction is now fixed around **three main trading horizons** in the primary AICFA system:
  - **Intraday** — 5m–1h, minutes to hours.
  - **Swing** — 1h–1d, hours to days.
  - **Position** — 4h–1w, days to weeks.
- **Scalping is explicitly separated from the primary AICFA system.** It will be implemented later as a dedicated website window with its own faster/microstructure logic and approximately minute-level updates. Scalping must not distort or replace the causal architecture of the three primary horizons.
- The three horizons are contexts of the shared Setup Engine, not three independent engines.
- The primary system must not remain request-driven ("analyze BTC when the user asks"). The target product behavior is an **autonomous market scanner**:
  1. Maintain a configured list of supported coins/markets.
  2. Continuously obtain the required market data for those markets.
  3. Analyze each market across Intraday, Swing, and Position contexts.
  4. Search automatically for currently formed setup candidates.
  5. Emit only setups that satisfy the existing structural/causal contracts.
  6. Produce a concrete **LONG / SHORT** setup when a valid directional setup exists, including Entry, SL, TP1/TP2 and RR where structurally available.
  7. Produce WAIT / NO TRADE when no valid directional setup exists; no forced signal.
  8. Surface results in a dedicated, visually clear **website setup window/dashboard**. Telegram is not part of the primary delivery path.
- The scanner must work across multiple assets, not BTC-only. BTC is one market in the configured universe, not a special-case engine.
- The future website setup window should support at minimum:
  - live/new setup feed;
  - coin/market;
  - horizon (Intraday / Swing / Position);
  - LONG / SHORT direction;
  - Entry;
  - SL;
  - TP1 / TP2;
  - RR;
  - setup timestamp / freshness;
  - setup status / lifecycle;
  - enough structural explanation to show why the setup exists.
- The autonomous scanner must reuse the existing AICFA architecture: confirmed swing → causal BOS/CHoCH/MSS → liquidity → OB/FVG lifecycle → zone reaction → volume evidence → structural Entry/SL/TP → conservative evaluation. Do not introduce a parallel generic indicator scanner.
- Fixed counts of setups per horizon are **not** a requirement. The system should discover whatever valid setup families are currently present rather than manufacture a target number of signals.
- The existing four-way classification is retained only as historical/product context; the primary production system is now explicitly three-horizon, with Scalping separated.
- A dedicated **coin universe/list configuration** must be designed before autonomous scanning is implemented. It should allow the user to define which coins/markets AICFA monitors, rather than hardcoding BTC or a fixed small set.
- Before implementing the autonomous scanner, perform a complete repository audit of `src/aicfa` and tests to identify all existing capabilities for:
  - market data and market context;
  - MTF preparation;
  - setup analysis;
  - candidate generation;
  - Entry/SL/TP/RR;
  - historical evaluation;
  - mode iteration;
  - multi-setup aggregation;
  - deduplication/lifecycle;
  - any existing orchestration layer.
- Do not create a duplicate orchestration/scanner if an existing component can be extended.
- Planned implementation sequence after the audit:
  1. Finish/record the current Task 9 regression state.
  2. Audit the complete existing setup/orchestration architecture.
  3. Define the three-horizon autonomous analysis contract.
  4. Define configurable monitored coin/market universe.
  5. Build/extend one shared multi-market orchestration layer.
  6. Make the scanner discover all valid current setups across the three horizons.
  7. Add causal deduplication, setup lifecycle/freshness and conflict handling where required.
  8. Expose scanner results through the website setup window.
  9. Add persistent/historical setup records so displayed setups can be evaluated after completion.
  10. Validate the complete flow on multiple markets, not BTC alone.
- Quality principle: AICFA should prefer **no signal** over a fabricated or weakly justified LONG/SHORT. No arbitrary confidence score, fixed RR filter, or unsupported profitability claim should be introduced merely to make the scanner produce more signals.
- Scalping remains a later, separate product surface and implementation task.

### 2026-10-03 — DIRECTIONAL STATISTICS FULL REGRESSION VERIFIED

- After directional outcome statistics commit `0a0c1232773942cef9dffddb614be957020f86b9`, server full regression completed successfully: **428 passed in 82.05s (0:01:22)**.
- Result: **0 failed, 0 skipped**.
- Task 9 remains ACTIVE.


### 2026-10-03 — EXPLAINABLE SETUP CONTRACT FIXED

- AICFA setup output is now planned as an **explainable trade scenario**, not a bare LONG/SHORT signal.
- Every displayed setup should carry structured evidence from the actual analysis pipeline:
  - market and timeframe context;
  - horizon: Intraday / Swing / Position;
  - direction: LONG / SHORT;
  - Entry;
  - structural SL;
  - TP1 / TP2 where structurally available;
  - RR derived from Entry/SL/TP;
  - structure evidence (HH/HL/LH/LL, BOS/CHoCH/MSS);
  - liquidity evidence and sweeps;
  - OB/FVG evidence and lifecycle;
  - zone reaction / confirmation;
  - volume evidence where available;
  - explicit invalidation condition;
  - setup timestamp, freshness and lifecycle status.
- The website should present this as a clear **trade description/card** so the user can see not only what AICFA found, but why the setup exists and what would invalidate it.
- The explanation must be generated from real structured evidence produced by AICFA. Do not add an LLM-written explanation layer that invents reasons not present in the underlying analysis.
- A valid setup remains a causal structural result. The description is a presentation of evidence, not an additional signal filter.
- Planned build direction is now explicit: **analyze the existing code → extend the existing architecture → build the autonomous multi-market scanner → expose explainable setups on the website**.
- No implementation should begin by creating a parallel generic signal/indicator scanner.
- Next implementation step remains the complete repository audit of src/aicfa and tests, followed by the smallest architectural extension needed for autonomous multi-market discovery.

### 2026-10-03 — COMPLETE REPOSITORY AUDIT: AUTONOMOUS THREE-HORIZON SCANNER GAP ANALYSIS

- Audited the repository tree and the existing `src/aicfa` analytical/scanner/orchestration modules plus the corresponding tests, with the current main branch at plan commit `9f083fd4c59689905cd4c091382bbe1bbeb43f9f`.
- Existing analytical core is substantial and should be reused:
  - causal structure / HH-HL-LH-LL / BOS / CHoCH / MSS;
  - liquidity pools, sweeps and lifecycle;
  - FVG and Order Block lifecycle;
  - zone reaction;
  - displacement;
  - volume evidence;
  - MTF causal mapping;
  - market evidence / scenario reasoning;
  - structural Entry / invalidation / target geometry;
  - RR derivation;
  - conservative historical evaluation, chronological purged folds, outcome journal and directional/fold statistics.
- `find_setup.py` is currently the main end-to-end request-driven orchestration path for **one asset and one TradingMode at a time**. It resolves one symbol, fetches that mode's timeframes, builds evidence/scenarios/setup/decision and returns one `FindSetupResult`.
- `market_scanner.py` already contains `CentralMarketScanner`, but it is only a provider-independent polling foundation over an explicitly supplied `list[MarketKey]`; it fetches/builds features per market/timeframe. It does **not** yet run the complete setup-analysis/decision pipeline, iterate the three horizons, aggregate setup candidates, or emit explainable trade objects.
- There is currently **no completed top-level autonomous orchestrator** equivalent to: configured coin universe → one market → Intraday + Swing + Position → shared Setup Engine → all current valid setups → unified multi-market result.
- There is currently **no persistent/user-facing coin-universe configuration layer**. The existing scanner accepts a universe in memory; the required product behavior needs a durable configurable list of monitored markets without hardcoding BTC.
- There is currently **no autonomous continuous scheduling/lifecycle loop** around setup discovery. `scan_once()` is a primitive we can extend rather than duplicate.
- `setup_analysis.py` supports MTF setup analysis for a single `TradingMode` and already deduplicates identical actionable geometry inside one assessment. It does not yet aggregate/deduplicate across Intraday/Swing/Position or across multiple symbols.
- `setup_lifecycle.py` currently keys active state by only `(symbol, market_type)`. That is insufficient for the new product contract because a symbol may legitimately have independent Intraday, Swing and Position setups simultaneously. Lifecycle identity must eventually include the horizon/setup identity and preserve multiple active setups per market where geometry is distinct.
- The current `TradingMode` code still contains **SCALPING** as a production mode, while the new primary product contract is three horizons. More importantly, current profiles are not yet the exact desired product boundaries: Intraday is `1d/4h/1h/15m`, and Position includes `1M/1w/1d/4h`. These must be reconciled with the fixed primary contract (Intraday 5m–1h context, Swing 1h–1d, Position 4h–1w) before autonomous orchestration is built. This is an architectural contract change, not a reason to duplicate the engine.
- The existing market-data layer is suitable as a base for multi-market work: normalized OHLCV, completed-candle filtering, fallback providers, shared short-lived snapshots, symbol resolution, and optional trades/order-book/derivatives collection are already present. The knowledge-driven requirements layer can request auxiliary data without making every scan pay that cost.
- The existing evidence/decision chain correctly preserves WAIT/NO TRADE and does not manufacture direction from concept names. This should remain the gate for autonomous emission.
- Explainability is partially present in `SetupCandidate` / `DecisionCandidate` through supporting concepts, entry conditions, invalidation, targets and rationale. However, there is not yet a dedicated immutable **display/trade-description contract** combining market, horizon, direction, numeric Entry/SL/TP1/TP2, RR, evidence, invalidation, timestamp/freshness and lifecycle status. The website should consume such a structured object rather than generate reasons independently.
- Numeric setup geometry is currently represented as `entry_zone`, `invalidation_level` and `target_levels`, not as a finalized scalar Entry/SL/TP display contract. The conversion to a website-ready trade description must preserve the underlying zone geometry and must not invent prices.
- Historical evaluation is already causal and separate from live setup generation. The missing piece is integration of emitted live setup records with persistent historical outcome records after lifecycle completion.
- Test coverage includes dedicated tests for market scanning, FindSetup, MTF setup engine, setup detection/lifecycle, structural entry, market data routing, data requirements, multi-timeframe structure, decision gating and evaluation. The latest user-run full regression is **428 passed, 0 failed, 0 skipped in 82.05s**.
- Audit conclusion: **do not create a new generic scanner or replace the existing Setup Engine**. Extend the existing `CentralMarketScanner` + `find_setup`/MTF setup pipeline with a new top-level multi-market/multi-horizon orchestration layer, then add the coin universe, setup identity/lifecycle, explainable trade-description contract, and website feed.

### Next exact action after audit

1. Reconcile the code-level TradingMode/timeframe contract to the fixed three primary horizons while keeping Scalping isolated for later.
2. Define the minimal multi-horizon orchestration contract around the existing `find_setup`/Setup Engine; do not implement the website yet.
3. Add tests for: one market → three horizons, multiple markets → independent results, no forced signal, and preservation of distinct concurrent setups.

### 2026-10-03 — PRIMARY THREE-HORIZON ORCHESTRATION: IMPLEMENTED, VERIFICATION PENDING

- Reconciled the primary TradingMode timeframe contract:
  - Intraday: `4h → 1h → 15m → 5m`
  - Swing: `1d → 4h → 1h`
  - Position: `1w → 1d → 4h`
  - Scalping remains isolated at `15m → 5m → 1m` for the later dedicated fast product.
- Added `src/aicfa/market_orchestrator.py` as the first autonomous orchestration layer over the existing `find_setup` pipeline.
- The orchestrator runs one market through the three primary horizons, preserves independent candidates, and explicitly rejects Scalping in the primary scan.
- Added multi-market orchestration so a configured asset list can be scanned independently without making BTC special.
- Added focused contract tests for:
  - one market → all three primary horizons;
  - multiple markets → independent results;
  - WAIT → no forced setup;
  - simultaneous distinct horizon setups remain separate;
  - Scalping isolation.
- Commits:
  - `2d0d4f458af49c5de6f0ab5a037134ee2fc2582d` — primary horizon timeframe contract
  - `f648c03fbd3ddd863c9b73fab1e955216d462398` — FindSetup horizon tests
  - `e759375266a221e99562387123258b47e4864d42` — data-requirement horizon tests
  - `8a8e6e02d448ef70fded068ac3f9abf9a1836346` — primary market orchestrator
  - `820f296389de7cac73501164d0d3965eb896ad1f` — orchestrator tests
- Verification status: **focused tests not yet executed on the production VDS** after these changes.

### Next exact action

Run the focused horizon/orchestrator tests on the VDS. If green, run the full regression. Only after that continue with the configured market universe and the structured explainable TradeDescription contract.



### 2026-10-03 — FULL REGRESSION: THREE-HORIZON CONTRACT RECONCILIATION

- Production VDS full regression after the primary three-horizon orchestration changes: 432 passed, 3 failed, 0 skipped in 92.00s.
- All three failures were traced to the transition from the former timeframe contract to the new primary profiles.
- Analysis-depth expectations were updated to the current Intraday 4h/1h/15m/5m, Swing 1d/4h/1h and Position 1w/1d/4h role mappings.
- The lower-confirmation conflict fixture was corrected so the actual Intraday structure timeframe (1h) conflicts with the lower confirmation timeframe (15m).
- The MTF target test was corrected to enforce the actual contract: targets may come from any relevant non-execution timeframe and must not be manufactured by 1m; dedicated causal target fallback tests remain unchanged.
- No production setup-analysis logic was changed for these failures because the first two were stale fixtures and the third assertion contradicted the existing target-discovery contract.
- Next exact action: run the corrected focused tests, then full regression. If green, proceed to configurable market universe.


### 2026-10-03 — THREE-HORIZON REGRESSION GREEN / CONFIGURABLE MARKET UNIVERSE IMPLEMENTED

- Corrected deployment fixture commit fd021de902b4544556aa82bdb0f5b651f4218f68 reached the VDS.
- Focused tests/test_setup_analysis.py: 8 passed in 0.44s.
- Full VDS regression after the three-horizon reconciliation: 435 passed in 87.73s (0:01:27).
- Result: 0 failed, 0 skipped.
- Added src/aicfa/market_universe.py with immutable MonitoredMarket and MarketUniverse contracts, asset normalization, explicit spot/futures market type, duplicate protection, and JSON loading for a durable configured universe.
- Added config/market_universe.example.json as an empty configuration template. No coin list is hardcoded yet; the actual monitored list will be selected later.
- Connected market_orchestrator.py to the configured universe through scan_universe(...).
- The orchestrator still reuses the existing find_setup / Setup Engine and does not introduce a second signal engine.
- Added contract tests for universe normalization, validation, JSON loading and configured-universe orchestration.
- Commits:
  - f69c22905865d06691f2bac57c11982b16fc1fe3 — configurable market universe
  - 0405f2ccdd39855960cfddef8abc33f256b20156 — market universe contract tests
  - 9c0e24f4c5412cc4e619c9f16d7ba177d1c7a922 — connect orchestrator to market universe
  - 011d5b65c79840f600d07b139a5ff126097c62de — configured-universe orchestration test
  - 6e4f2f0cfe5ffeb2038a5749628b6c34405820b9 — market universe configuration template

### Next exact action

Run focused VDS tests for tests/test_market_universe.py and tests/test_market_orchestrator.py. If green, run the full regression. After that, move to the structured explainable TradeDescription contract. The actual monitored coin list is intentionally deferred until the universe mechanism is verified.


### 2026-10-03 — EXPLAINABLE TRADE DESCRIPTION CONTRACT IMPLEMENTED

- Added `src/aicfa/trade_description.py` with immutable `TradeDescription` and builders over the existing `SetupCandidate` geometry.
- The contract preserves the real entry zone, structural invalidation/SL, TP levels and derived RR without collapsing zones to fabricated scalar prices.
- Structured evidence is separated into market structure, liquidity, zone/OB/FVG, reaction and volume evidence, plus entry conditions, invalidation, rationale and source/confirmation timeframes.
- The description carries asset, market type, Intraday/Swing/Position horizon, LONG/SHORT direction, scenario, setup timestamp, freshness and lifecycle status.
- Missing Entry/SL/TP geometry remains missing; no fallback price, confidence score or synthetic reason is created.
- Added `build_trade_descriptions(...)` to preserve every current setup candidate rather than ranking or silently dropping candidates.
- Added `tests/test_trade_description.py` covering geometry preservation, evidence projection, RR derivation, missing geometry, multiple directions and lifecycle status.
- Implementation commits:
  - `ea507440732b88169b0805f6f2614ea8ce2e7c7d` — explainable trade description contract
  - `0f8198a1a670022b0726425364d10db2ca70d468` — initial contract tests
  - `dd95d0d03949a8e9bba8c3fa31514d3b2d2ba3f9` — corrected RR test expectation

### Next exact action

Run focused VDS validation for `tests/test_trade_description.py`. If green, run the full regression. Then integrate `TradeDescription` into the multi-horizon orchestrator so scanner output exposes structured explainable setups while preserving the existing `FindSetupResult` and candidate pipeline.


### 2026-10-03 — TRADE DESCRIPTION INTEGRATED INTO MULTI-HORIZON ORCHESTRATOR

- Integrated the existing immutable `TradeDescription` contract directly into `market_orchestrator.py`.
- Every emitted `HorizonSetup` now carries both the original `SetupCandidate` and its structured `TradeDescription` projection.
- The orchestrator does not generate new trading logic: it projects the already-approved candidate geometry/evidence from the existing FindSetup pipeline.
- Entry/SL/TP/RR, evidence, horizon, direction, timestamp, freshness and lifecycle status therefore travel with the setup into the multi-market scan result.
- Existing WAIT / NO TRADE behavior is unchanged: descriptions are created only for actual setup candidates; no candidate means no setup description.
- Added orchestrator test coverage confirming descriptions preserve horizon and direction, including simultaneous long/short candidates.
- Production change: `feat: expose trade descriptions from market orchestrator`.
- Test commit: `07b31a5977b544047e2966f5fc3f652a48eaeacd`.

### Next exact action

Run focused VDS validation for `tests/test_market_orchestrator.py` and `tests/test_trade_description.py`. If green, run the full regression. After that, define the setup identity/lifecycle integration so multiple independent Intraday/Swing/Position setups can remain active without overwriting each other.


### 2026-10-03 — MULTIPLE INDEPENDENT SETUP LIFECYCLES IMPLEMENTED

- Corrected the lifecycle contract: a market is **not** limited to one setup, and a horizon is **not** limited to one setup.
- Added `SetupIdentity` in `src/aicfa/setup_lifecycle.py`.
- Identity is based on market, market type, horizon, direction and actionable Entry/SL/TP geometry. Re-observing the same geometry updates the existing lifecycle instead of creating a duplicate.
- The lifecycle now supports multiple independent setups simultaneously for the same market + same horizon, different horizons on the same market, and different markets independently.
- Added `evaluate_all(...)` to evaluate all existing setups independently and activate every distinct new actionable candidate.
- Existing setup geometry remains immutable after activation; a changed analytical candidate does not overwrite the original active setup.
- Added `active_setups(...)` and identity-aware clearing while preserving the existing single-result `evaluate(...)` API for compatibility.
- Removed the previous behavior that refused activation whenever an assessment contained multiple candidates.
- Added tests for two distinct setups active simultaneously on the same BTC/USDT Intraday horizon, the same setup reappearing on the next scan without duplication, and independent Intraday/Swing/Position setups coexisting on the same market.
- Production commit: `e714ba8353779a638781d01f76556aac795749dc` — `feat: support independent concurrent setup lifecycles`.
- Test commit: `df7bfebed945bdd00f4a11b62ace3adc09eeb305` — `test: cover concurrent setup identities and horizons`.
- VDS verification is pending.

### Next exact action

Deploy the two commits to the VDS, run `tests/test_setup_lifecycle.py` first, then `tests/test_market_orchestrator.py tests/test_trade_description.py`, then the full regression. After green verification, connect the orchestrator's HorizonSetup identities to this multi-setup lifecycle so repeated scans update the same setup while distinct geometries remain simultaneously active.


### 2026-10-03 — ORCHESTRATOR CONNECTED TO MULTI-SETUP LIFECYCLE

- Connected `market_orchestrator.py` to the existing multi-setup `SetupLifecycle` through an optional lifecycle state.
- Each emitted `HorizonSetup` can now expose its stable `SetupIdentity` and the corresponding lifecycle result.
- The orchestrator evaluates the latest execution-timeframe close for each primary horizon when lifecycle tracking is enabled.
- Repeated scans of the same setup geometry update the same lifecycle instead of creating duplicates.
- Distinct geometries in the same market/horizon remain independent; Intraday, Swing and Position lifecycles coexist on the same market.
- Lifecycle state is still separate from the deterministic setup-generation pipeline; no new signal logic or forced setup was introduced.
- Added orchestrator regression tests for repeated-scan continuity and independent geometries.
- Production commit: `5d121fbc10b5a575dc3ee16a2e166d2510960c94` — `feat: connect orchestrator scans to setup lifecycle`.
- Test commit: `1b43f3ac3ce863382f8075f2ebbf7c5e88c035cd` — `test: verify orchestrator lifecycle continuity`.

### Next exact action

Deploy the latest commits to the VDS. Run the lifecycle + orchestrator focused tests first. If green, run the full regression. Then move to the autonomous recurring scan/state loop and persistent setup records, without limiting the number of valid concurrent setups.

### 2026-10-03 — LIFECYCLE REGRESSION FIX

- Fixed backward-compatible `SetupLifecycle.evaluate()` to return the existing active setup first when a changed ready candidate creates an additional independent setup.
- This preserves the legacy single-result API while `evaluate_all()` still retains all independent active setups.
- Fixed orchestrator lifecycle test fixtures to expose the required assessment decision and imported `SetupLevel`.
- Regression failures were test/API compatibility issues; no one-setup-per-market restriction was restored.
- Fix commits: `b7ba368ef696fd6b136ffa9a4f0a5b98c53c957c`, `32d8cf93c1e4a0762260582a4497f7b236202d78`.
### 2026-10-03 — AUTONOMOUS RECURRING SCAN/STATE ENGINE ADDED

- Added `src/aicfa/autonomous_scan.py` with `AutonomousScanEngine` and `AutonomousScanState`.
- The engine owns one long-lived `SetupLifecycle` and reuses it across scans, so repeated identical setup geometry keeps the same lifecycle while independent geometries remain separate.
- Each scan runs only against the configured `MarketUniverse`; the monitored market list is not hardcoded to BTC and supports the user's configurable asset/market list.
- The primary autonomous loop remains strictly **Intraday + Swing + Position**. Scalping is not included.
- `scan_once()` provides deterministic single-cycle execution for testing and service integration.
- `run_forever()` provides the recurring loop with configurable interval, stop predicate, and callback; it adds no new signal logic or setup-count limit.
- Current state is intentionally in-process. Durable persistence of active setup records across process/server restarts remains the next state-storage layer.
- Added regression coverage for repeated scans, independent lifecycle identities, configured multi-market scanning, and stoppable recurring execution.
- User server baseline before this step: **451 passed, 0 failed, 0 skipped**.

### Next exact action

Deploy the autonomous scan/state engine and run its focused tests. If green, run the full regression. Then add durable setup-state records so active setups survive process restarts without changing setup identity or lifecycle semantics. Keep the monitored coin list configurable and do not hardcode a fixed asset set.

### 2026-10-03 — PRIMARY AUTONOMOUS SCAN CADENCE FIXED AT 5 MINUTES

- Fixed the primary autonomous scan cadence contract at **5 minutes (300 seconds)** via `MAIN_SCAN_INTERVAL_SECONDS = 300`.
- Each cycle re-evaluates the configured market universe; it does **not** create a new signal merely because five minutes elapsed.
- `SetupLifecycle` remains responsible for recognizing the same setup geometry, a new independent setup, TP1/TP2, invalidation and expiration.
- Scalping remains a separate future approximately minute-level product surface and is not part of this primary cycle.
- Durable persistence is intentionally deferred until the real scan cadence and market-universe runtime are verified.
- The actual monitored coin list is still intentionally not invented; it will be fixed in the single `config/market_universe.json` configuration once the user selects the exact markets.

### Next exact action

1. Select the exact fixed monitored coin/market list.
2. Create the production `config/market_universe.json` from that list.
3. Run the autonomous scanner against the complete list and measure one full 5-minute-cycle execution time on the VDS.
4. Only after runtime is acceptable, proceed to durable setup-state persistence.
