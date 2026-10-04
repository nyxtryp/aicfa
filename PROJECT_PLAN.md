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


### 2026-10-03 — MONITORED MARKET UNIVERSE EXPANDED TO 200

- Audited the user's selected market list as an AICFA autonomous-scanner universe rather than as a simple market-cap ranking.
- The initial user list contained **121 unique assets** with no internal duplicates.
- The previous assistant audit proposed additional markets. A recount corrected the earlier stated total: the combined set is **141 unique assets**, not 139, because `ENS/USDT` and `SSV/USDT` were not present in the user's original 121.
- Expanded the curated universe by **59 additional assets** to reach exactly **200 unique USDT spot markets**.
- The expansion deliberately adds missing exposure across:
  - AI / AI agents / compute;
  - DePIN;
  - L1/L2 and modular infrastructure;
  - DeFi / DEX / derivatives;
  - RWA / institutional DeFi;
  - gaming;
  - interoperability / oracles;
  - additional liquid/high-activity assets.
- Current production configuration was created at `config/market_universe.json` with exactly **200** `spot` markets.
- The universe is still a configured input to the existing AICFA orchestration; it does not create a second signal engine, ranking model, confidence score or forced setup.
- Current market-sector references were checked against current CoinGecko category data. DePIN is currently about $11B, RWA about $79B, L2 about $10.8B, and Gaming about $4.2B; these categories are broad enough that the universe intentionally selects liquid/established representatives rather than attempting to include every token in each sector.
- The 200-market list remains subject to the next required operational check: verify actual availability/liquidity of every configured USDT spot pair through the AICFA market-data provider on the VDS before treating the list as fully production-valid.

### Next exact action

1. Deploy the new `config/market_universe.json` to the VDS.
2. Run focused universe/orchestrator/autonomous-scan tests.
3. Verify all 200 configured markets against the real market-data provider and record any unavailable/illiquid pairs.
4. Run one complete autonomous `scan_once()` over the full 200-market universe and measure wall-clock execution time.
5. Compare the measured runtime with the fixed **300-second / 5-minute** cadence.
6. Only after the full-list runtime and market availability are verified, proceed to durable setup-state persistence.


### 2026-10-03 — AUTONOMOUS SCAN ROTATION CHANGED TO 40 MARKETS PER MINUTE

- Clarified the production scheduling model: the universe contains **200 configured markets**, but the site must **not** run all 200 markets in one five-minute burst.
- Production rotation is now designed as **5 sequential batches × 40 markets**.
- One batch is processed every **60 seconds**.
- After five batches, all 200 markets have been revisited once; therefore each configured market is normally re-evaluated once every **5 minutes / 300 seconds**.
- This keeps the original five-minute market refresh contract while reducing the per-minute workload from 200 markets to 40 markets.
- The existing SetupLifecycle remains long-lived across batches, so a setup can persist while its market waits for the next batch; the next visit can recognize the same setup, a new geometry, TP1/TP2, invalidation or expiration.
- Added AutonomousScanEngine.scan_batch() and run_forever_batches() with defaults of **40 markets per batch** and **60 seconds between batches**.
- The legacy full-universe scan_once() / run_forever() APIs remain available for deterministic tests and full-scan runtime measurement.
- Added regression tests proving 200 markets rotate as 40/40/40/40/40 and the first batch is revisited after the five-batch rotation.
- Production implementation commit: b5f5fe7d3eea9b2755e6ae72c3e3a640363844b0.
- Test commit: 2c52d11d91d078349841dfcdb1e56788c27c48ef.
- Important runtime contract: the 40-market batch must complete within its 60-second slot if the production service is to maintain a strict one-batch-per-minute cadence. We therefore measure real batch wall-clock time on the VDS before enabling the live loop.
- Durable persistence is still deferred.

### Next exact action

1. Deploy the 200-market configuration and rotating-batch code to the VDS.
2. Run focused autonomous/universe/orchestrator tests.
3. Verify all 200 configured USDT spot pairs against the real provider.
4. Measure a real **40-market batch** wall-clock runtime on the VDS.
5. If the batch fits inside 60 seconds, wire the live service to run_forever_batches(interval_seconds=60, batch_size=40).
6. Confirm the five-batch rotation gives each market one evaluation every 5 minutes.
7. Only then proceed to durable setup-state persistence.


### 2026-10-03 — MARKET DATA MULTI-SOURCE ROUTING AUDIT / 200-MARKET AVAILABILITY CHECK

- The initial production-universe availability check against Binance Spot returned **153/200 available** and **47/200 unavailable**. This result is only a Binance Spot availability result; it does **not** reduce or redefine the configured 200-market universe.
- The 47 unavailable Binance Spot pairs are not to be deleted or replaced merely because Binance Spot does not list them. AICFA must support multiple public market-data sources and automatic per-market fallback.
- Repository audit confirmed that this architecture is already partially present and must be extended rather than duplicated:
  - src/aicfa/market_data_router.py contains FallbackMarketDataProvider, which tries providers in order and returns the first successful normalized OHLCV/trades/order-book result while preserving provider-attempt diagnostics.
  - src/aicfa/market_data_router.py also contains SharedSnapshotMarketDataProvider for short-lived shared MTF snapshots.
  - src/aicfa/market_source_registry.py already defines capability-aware source selection and an ordered public-source registry containing Binance, Bybit, Bitget, Kraken, KuCoin, Gate, MEXC, CoinLore and CoinGecko.
  - src/aicfa/bybit_market_data.py is an implemented public Bybit adapter for symbol resolution, OHLCV, trades and order-book data.
  - Binance and Bybit are therefore not separate analytical paths; they are market-data providers underneath the shared AICFA data contract.
- Important architectural requirement is now fixed: **the entire AICFA analytical pipeline must consume provider-agnostic normalized market data**. Provider selection/fallback must happen below the scanner/setup/evidence layers.
- Provider fallback must be automatic per market/request: if the preferred source cannot resolve a market or cannot provide a required dataset, AICFA should try the next compatible source rather than abandoning the market or requiring manual source selection.
- Capability matters: a source that has OHLCV but lacks a required auxiliary capability must not be selected as if it could satisfy the full request. The existing registry already models this distinction.
- The current 153/200 Binance Spot result is therefore recorded as a diagnostic, not as a universe decision.
- No production code was changed in this step. The next implementation step is to audit the actual implemented adapters versus the registry declarations, then define/implement the smallest provider-agnostic fallback path needed by the autonomous 40-markets-per-minute scanner.
- After provider coverage/fallback is verified, re-check the full 200-market universe across the available sources, then measure the real 40-market batch runtime. The fixed production target remains 5 sequential batches of 40, one batch per minute, with each market revisited approximately every 5 minutes.


### 2026-10-03 — GENERIC MULTI-EXCHANGE ADAPTER ADDED

- Added src/aicfa/ccxt_market_data.py in production commit 5a3d76555bb2475153415f6bdede3d81fda58185.
- The adapter implements the existing provider-agnostic MarketDataProvider shape through CCXT instead of creating one transport implementation per exchange.
- It supports public spot/futures symbol resolution, OHLCV, trades, L1 order book and causal order-book history.
- Exchange-specific transport is selected by CCXT exchange id; the same AICFA normalization contract is preserved.
- Current CCXT documentation lists 104 cryptocurrency exchanges plus prediction-market integrations, so the architecture can support many venues through one tested adapter rather than maintaining dozens of duplicate adapters. (Verified against current CCXT documentation.)
- Added tests/test_ccxt_market_data.py in commit bef369cc88c9100e82497d81f18ec5d243932ed2 covering spot/futures resolution and normalized OHLCV/trades/order-book output with a mocked exchange.
- Important: adding the generic adapter does not mean AICFA will query every exchange on every scan. Provider selection remains capability-aware and fallback is per market/request; the next step is to wire the real CCXT venues into the existing source registry/router and validate their actual 200-market coverage.
- The 200-market universe remains unchanged. Binance's earlier 153/200 result remains only a Binance Spot diagnostic.


### 2026-10-03 — CCXT SOURCE FACTORY / CAPABILITY ROUTING

- Added src/aicfa/ccxt_sources.py in commit 5adff66ce8c2414ef613615da3adc36471151ad5.
- Added a broad initial CCXT venue set: Binance, Bybit, OKX, Bitget, Gate, KuCoin, MEXC, Kraken, Coinbase, Bitfinex, BingX, HTX, BitMart, CoinEx, WhiteBIT, Crypto.com, Bitrue, Bitstamp, Gemini and Upbit.
- The factory does not blindly assume every venue supports every data type. It reads the installed CCXT exchange capability flags and builds SourceDescriptor capabilities from the actual adapter metadata. CCXT documents these has flags and recommends checking them before calling unified methods. cite: turn0search0
- Market metadata is intentionally loaded lazily inside each provider and cached by CCXT; this avoids the earlier Binance mistake of downloading exchangeInfo once per market. CCXT explicitly documents loadMarkets caching. cite: turn0search0
- Added tests/test_ccxt_sources.py in commit 6150e4716926c2d6a42c187de1cbe06a1c5d317f for capability detection and deterministic source ordering.
- Next implementation step: connect the constructed sources to the existing fallback router with source-specific symbol resolution, so a symbol resolved on venue A is never accidentally fetched from venue B using the wrong venue symbol format. Then run the 200-market coverage map and measure the 40-market batch.


### 2026-10-03 — VENUE-AWARE FALLBACK ROUTING

- Added src/aicfa/market_aware_router.py in commit edd628657b521c357d6e250681821d6dc569ee6e.
- The router resolves an asset against the provider chain and, when falling back, resolves the symbol again on the next venue before fetching data. This prevents exchange-specific symbols from being reused on the wrong venue.
- Resolution is cached per asset + market type for the life of the router; the cache can be cleared explicitly.
- Added tests/test_market_aware_router.py in commit 9603ee770dc8ddd2986df6b70e8dad3ff6e5ecac proving fallback from one venue to another uses the second venue's own symbol.
- Next: build the production multi-source provider chain from the existing native adapters plus the CCXT sources, then run the 200-market coverage audit. No live 200-market network scan has been claimed yet.


### 2026-10-03 — PRODUCTION MULTI-SOURCE PROVIDER CHAIN

- Added src/aicfa/public_market_data.py in commit f93642c480de4f9d73a351a507440b527bd49f1f.
- Production chain is native-first: Binance + Bybit, followed by the configured CCXT venues excluding duplicate Binance/Bybit integrations.
- Added provider-compatible venue-aware routing in commit f337263175023800770479846fdd8409162149ed. The router now exposes the normal resolve_symbol/fetch_ohlcv provider contract while preserving venue-specific fallback resolution.
- Added tests/test_public_market_data.py in commit 3a8f1caa8ab9a529cc03c65cd816f3121deb93b6.
- Added scripts/check_market_coverage.py in commit 2ec113ce214036a7e7d2c33266f7d1f0427ca66a. This is the VDS-side audit for all configured 200 markets across the production source chain.
- No 200-market multi-source coverage result is claimed yet; the real network audit must be run on the VDS.
- Current external CCXT documentation confirms the unified adapter approach and cached load_markets behavior. cite: turn0search0 turn0search2

### Next exact action

1. Deploy these commits through FrostDeploy.
2. Run focused provider/router tests.
3. Run scripts/check_market_coverage.py on the VDS.
4. Fix any markets still missing across the full source chain.
5. Then measure the real 40-market batch wall-clock runtime.
6. Only after that wire the live service loop and proceed to durable persistence.


### 2026-10-03 — VENUE ROUTER CONTRACT FIX

- Fixed src/aicfa/market_aware_router.py in commit b160e20cf028ce8340fbd9f10610fda964e2f9c6.
- Added the missing resolve_symbol() provider-contract method and populated the venue-symbol cache during resolution.
- This fixes the VDS focused-test failure where MarketAwareFallbackProvider had no resolve_symbol attribute; the fallback path continues to use each venue's own symbol.


### 2026-10-03 — AUTONOMOUS ROTATION REVISED TO 20 MARKETS PER MINUTE SLOT

- The production scheduling model is now **20 configured markets per minute-sized slot**, rather than 40.
- The scheduler does not impose a data-volume deadline or truncate market data to fit the slot.
- The batch is simply the unit of work assigned to a recurring minute-sized slot; provider requests are allowed to complete normally.
- With the current **199-market** universe, the rotation is **20 × 9 + 19 markets**, i.e. 10 batches per full rotation.
- Therefore each market is normally revisited once per approximately **10-minute rotation**, not forced into a five-minute refresh.
- Setup logic is unchanged: Intraday + Swing + Position continue through the existing FindSetup/SMC/evidence pipeline, and SetupLifecycle preserves the identity of repeated setups across rotations.
- Multi-source routing remains independent of the scheduler: Binance availability is not assumed, and fallback/alternative venues remain responsible for obtaining the required data.
- Full multi-source aggregation remains a separate data layer to be completed after the scheduler contract is fixed; it must not reduce the information supplied to analysis merely to satisfy a timing target.

### Next exact action

1. Deploy the 20-market batch scheduler change.
2. Run focused autonomous-scan tests.
3. Run the full regression.
4. Measure a real 20-market batch on the VDS without truncating data or imposing a hard 60-second data deadline.
5. Validate a full 199-market rotation and its effective revisit interval.
6. Then implement/verify full multi-source data aggregation and durable setup-state persistence.


### 2026-10-04 — MARKET UNIVERSE CLEANUP AFTER FULL RESOLUTION TEST

- Full VDS resolution test of the previous **199-market** production universe completed in **549 seconds (9m 09s)**.
- At the user's request, removed these six markets from the production universe: **INJ/USDT, XMR/USDT, EOS/USDT, AEVO/USDT, YGG/USDT, PRIME/USDT**.
- Production `config/market_universe.json` now contains **193 markets**.
- No other market was removed or replaced.
- This is a universe/configuration change only; setup logic, provider routing and market-data collection contracts are unchanged.

### Next exact action

1. Deploy the updated 193-market universe to the VDS.
2. Re-run the full resolution test for all 193 markets.
3. Compare total runtime and identify remaining slow/fallback markets.
4. Then measure actual MTF data acquisition for a 20-market slot without truncation or a hard data deadline.


### 2026-10-04 — TRADFI UNIVERSE INVESTIGATION STARTED (SEPARATE FROM 193 CRYPTO MARKETS)

- The production crypto universe is fixed at **193 markets** and is not being changed during the TradFi investigation.
- Started a separate investigation of real TradFi instruments available natively on **Bybit, OKX, Bitget and MEXC**.
- Required categories: **metals, oil, gas, stocks, indices/ETFs and FX**.
- The investigation must preserve the exchange's **native contract symbol/ID** and explicitly record the instrument type (for example perpetual/swap/future where applicable). Normalized AICFA symbols must not be invented before the venue-native mapping is known.
- Raw full derivatives listings must **not** be dumped to the user. The scan must filter server-side and return only a compact categorized TradFi inventory with exchange, native symbol/ID, category and contract type.
- CFD/other non-perpetual venue products must not be silently mixed with futures/perpetual instruments. Their market type and data requirements must be identified separately before integration into the existing AICFA market model.
- Official venue API metadata is the source of truth for the live inventory. Current official documentation confirms instrument metadata endpoints for Bybit, OKX, Bitget and MEXC. citeturn0search2turn0search0turn0search1turn1search0

### Next exact action

1. Run a **server-side compact TradFi inventory scan** against Bybit, OKX, Bitget and MEXC; do not print the raw market universe.
2. Produce counts and categorized native symbols only.
3. Review the resulting inventory for false positives/false negatives and distinguish perpetuals/futures from other venue products.
4. Build a separate TradFi market mapping/configuration only after the live inventory is verified; keep the existing 193 crypto markets unchanged.
5. Then determine which existing AICFA market-data contracts can support the verified TradFi instruments and what adapter extensions, if any, are required.


### 2026-10-04 — APPROVED 55-ITEM TRADFI TARGET SET / UNIFIED MARKET CONTRACT EXTENDED

- The user approved the compact **55-item TradFi target universe**:
  - 5 metals: Gold, Silver, Copper, Platinum, Palladium.
  - 3 energy: WTI, Brent, Natural Gas.
  - 7 FX: EUR/USD, GBP/USD, USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD.
  - 10 indices: SPX, NDX, DJIA, RUT, DAX 40, FTSE 100, CAC 40, Nikkei 225, Euro Stoxx 50, VIX.
  - 4 ETFs: SPY, QQQ, IWM, GLD.
  - 26 stocks: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AVGO, AMD, MU, SNDK, ARM, TSM, ASML, SMCI, QCOM, ORCL, PLTR, NFLX, COIN, MSTR, JPM, BAC, WMT, XOM, BA.
- **SPX is intentionally a separate index target from SPY**, which is an ETF target.
- **SNDK remains explicitly included**.
- The existing **193 crypto markets remain unchanged** for this phase. The user will clean the crypto universe separately later; no crypto replacement/removal is part of this TradFi step.
- No native venue symbols are assumed from the canonical names. Official venue metadata remains the source of truth. Bybit exposes instrument metadata through its instruments-info endpoint; OKX exposes instrument metadata by instType including SWAP/FUTURES; Bitget exposes contract configuration through its mix contracts endpoint; MEXC exposes live futures contract pairs through its contract-detail endpoint.
- Extended MonitoredMarket to support optional asset_class, category, instrument_type, and verified venue_symbols while preserving the existing crypto JSON contract unchanged.
- This is a **single AICFA market-universe/data-routing contract**, not a separate TradFi scanner or analytical engine.
- No 55-item TradFi production entries or native mappings have been added yet; they must be populated only after live venue verification.

### Next exact action

1. Run the live verification of all 55 approved targets against Bybit, OKX, Bitget and MEXC using the existing AICFA/CCXT market-data architecture.
2. For every positive match, record the venue-native symbol/ID and exact instrument type/contract type; distinguish perpetual/swap/future from other products.
3. Check the actual OHLCV availability needed by Intraday/Swing/Position on confirmed TradFi contracts.
4. Review false positives/duplicates (especially ETF vs index and commodity tokens vs actual TradFi contracts).
5. Add only confirmed TradFi entries to the same MarketUniverse alongside the unchanged 193 crypto markets.
6. Run focused universe/routing tests, then VDS live resolution/MTF verification.


### 2026-10-04 — TRADFI TARGET CONFIG ADDED / LIVE VERIFICATION PENDING

- Added approved target file: `config/tradfi_targets.json`.
- The file contains exactly **55 unique canonical AICFA targets** grouped into metal/energy/FX/index/ETF/stock categories.
- Added tests locking the 55-target contract, including **SPX** and **SNDK**.
- Extended `MonitoredMarket` so verified TradFi entries can later carry:
  - `asset_class=tradfi`;
  - category;
  - exact instrument type;
  - venue-native symbol/ID mappings.
- Existing crypto entries remain backward-compatible and the production `config/market_universe.json` remains at **193 crypto markets**. No TradFi target has been inserted into that production file yet.
- This target file is a canonical approved input list, not a separate TradFi scanner or analytical engine.
- Live native-symbol verification remains the gate before populating production TradFi mappings.

### Next exact action

1. Run the focused market-universe tests on the VDS.
2. Run the live 55-target venue verification against Bybit, OKX, Bitget and MEXC.
3. Store only verified native symbols/IDs and instrument types.
4. Validate OHLCV availability on the confirmed instruments for the three primary horizons.
5. Merge confirmed TradFi markets into the same production MarketUniverse without touching the 193 crypto entries.


### 2026-10-04 — LIVE TRADFI VERIFICATION UTILITY ADDED

- Added `scripts/verify_tradfi_targets.py`.
- It reads the approved 55-target config and queries **Bybit, OKX, Bitget and MEXC through CCXT live market metadata**.
- It reports only compact candidate metadata per target:
  - native `symbol` / `id`;
  - market type;
  - spot/swap/future flags;
  - base/quote/settle;
  - active/state;
  - exchange-specific contract fields when present.
- The utility is **verification only**: it does not modify `config/market_universe.json`, does not create TradFi setups, and does not become a separate scanner.
- Matching intentionally produces candidates for manual review because the same ticker can appear as crypto, ETF, index, RWA or another instrument on different venues. Native exchange metadata remains the final source of truth.

### Immediate verification command

```bash
sudo -u fd-aicfa bash -lc '
cd "$(readlink -f /srv/frostdeploy/aicfa/current)" &&
PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python scripts/verify_tradfi_targets.py
'
```

- Do not add any result to production until the output has been reviewed target-by-target.


### 2026-10-04 — LIVE TRADFI MAPPING INTEGRATED BESIDE 193 CRYPTO

- Reviewed the live Bybit/OKX/Bitget/MEXC verification output for all 55 approved targets.
- Integrated **44 verified TradFi perpetual markets** into the same `config/market_universe.json` beside the unchanged **193 crypto spot markets**.
- TradFi entries use `market_type=futures`, `asset_class=tradfi`, `instrument_type=perpetual`, and verified `venue_symbols`.
- Bitget entries explicitly marked `isRwa=YES` were not used as production mappings.
- FX false positives such as `EUR/USDT`, `GBP/USDT`, `JPY/USDT`, `CHF/USDT`, `AUD/USDT`, `CAD/USDT` were not treated as the corresponding FX pairs. Only verified EUR/USD and GBP/USD perpetual mappings were integrated.
- Existing **SPX/USDT spot crypto entry remains untouched**; the S&P 500 TradFi target is represented separately by the same canonical asset with `market_type=futures`, preserving both markets.
- Added routing support so `MarketAwareFallbackProvider` consumes verified `venue_symbols` before generic symbol resolution, while retaining normal fallback behavior for unmapped venues.
- `scan_universe()` now registers configured venue mappings before running the existing FindSetup/SMC pipeline; no separate TradFi scanner or analytical engine was introduced.
- Added focused regression coverage for native-symbol routing and the 193-crypto + 44-TradFi production-universe contract.
- **11 approved targets remain pending** because no non-RWA verified perpetual mapping was established in the current four-venue output: USD/JPY, USD/CHF, AUD/USD, USD/CAD, NZD/USD, RUT, DAX 40, FTSE 100, CAC 40, Euro Stoxx 50, VIX.

### Next exact action

1. Deploy commits to VDS.
2. Run focused TradFi routing/universe tests.
3. Run live resolution/MTF acquisition on a small representative TradFi set across Bybit/OKX/MEXC.
4. If resolution is clean, run the full 237-market universe validation and measure the new autonomous rotation interval.
5. Investigate the 11 still-pending targets separately; do not fabricate mappings or convert crypto/USDT instruments into FX/index equivalents.


### 2026-10-04 — TRADFI LIVE OHLCV TEST EXPOSED GENERIC-ROUTING BYPASS

- The first VDS live OHLCV check across all 44 integrated TradFi markets returned **42/44 OK**, but exposed a routing defect: several markets were being resolved to Binance tickers even though production `venue_symbols` explicitly mapped them to Bybit/OKX/MEXC.
- Observed examples include **XAG/USDT → Binance XAGUSDT**, **SPX/USDT → Binance SPXUSDT**, and **SNDK/USDT → Binance SNDKUSDT**. The same bypass affected additional TradFi targets.
- This violates the verified native-symbol contract. An explicit `venue_symbols` mapping is now authoritative: AICFA may use only the listed mapped venues for that market and may fall back only between those mapped venues. It must never substitute a generic resolver result from an unmapped venue.
- **EUR/USD** and **GBP/USD** were the two live failures. Their configured Bybit symbols were selected, but Bybit rejected the symbol as invalid during the OHLCV request. The previous generic fallback then triggered long multi-venue resolution attempts. The new authoritative-mapping rule prevents that silent substitution; these FX mappings now require fresh native-symbol verification.
- Added regression coverage proving that an unmapped Binance provider cannot bypass an explicit TradFi mapping and that fallback may move only between explicitly mapped venues.
- No TradFi market was removed or replaced by this fix.
- Next: deploy the routing fix, rerun the complete 44-market OHLCV validation, then inspect any remaining mapped-venue failures before MTF analysis.



### 2026-10-04 — FINAL PRODUCTION UNIVERSE CLEANUP: 117 CRYPTO + 29 TRADFI

- Finalized the production market universe after the user's quality cleanup.
- Removed exactly **76 crypto markets** from the previous 193-market crypto universe; **117 crypto markets remain**.
- Removed the duplicate/weak TradFi entries and the two FX targets explicitly rejected by the user.
- Final TradFi production set is **29 markets**:
  - 4 metals: XAU, XAG, XCU, XPT.
  - 3 energy: WTI, BRENT, NATGAS.
  - 4 index/ETF exposures: DJIA, NIKKEI, SPY, QQQ.
  - 18 stocks: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AVGO, AMD, ARM, TSM, ASML, ORCL, PLTR, NFLX, COIN, JPM, MU.
- Removed TradFi entries: XPD, EUR/USD, GBP/USD, SPX, NDX, IWM, GLD, SNDK, SMCI, QCOM, MSTR, BAC, WMT, XOM, BA.
- The crypto SPX/USDT entry was also removed, eliminating the previous canonical-name collision with the TradFi SPX target.
- Updated config/tradfi_targets.json from the broad 55-target investigation set to the final 29-target production set; FX is now intentionally absent.
- Updated the market-universe contract test from 55 to 29 targets and explicitly locked out removed SPX/SNDK/EUR/USD/GBP/USD targets.
- Resulting production universe: **117 Crypto + 29 TradFi = 146 markets**.
- No setup-analysis, SMC, routing, lifecycle, Entry/SL/TP, or scheduler logic was changed by this cleanup.

### Next exact action

1. Deploy the finalized 146-market configuration through FrostDeploy.
2. Run the focused market-universe/configuration tests on the VDS.
3. Run the full test suite.
4. Run live resolution for all **146 markets** and verify that no removed market remains in the production universe.
5. Measure the real autonomous 20-market slot and the full rotation interval after the universe reduction.
6. Run representative/full TradFi OHLCV verification for the remaining 29 markets, then proceed to MTF acquisition validation.


### 2026-10-04 — FULL REGRESSION FOLLOW-UP: STALE UNIVERSE TEST + MAPPED-ROUTING CACHE FIX

- Full regression reached 468 passed with 2 failures; both were isolated to the recent TradFi routing test file.
- Updated the stale production-universe assertion from the previous 193 Crypto + 44 TradFi universe to the finalized 117 Crypto + 29 TradFi = 146 markets.
- Fixed MarketAwareFallbackProvider.register_market_symbols() so every explicitly mapped native venue symbol is immediately routable after registration; fallback still remains restricted to the explicitly mapped venues.
- No market-analysis, SMC, setup, lifecycle, Entry/SL/TP, or scheduler behavior was changed.
- Next: redeploy these two fixes, run the focused TradFi routing tests, then rerun the full regression.


### 2026-10-04 — LIVE COVERAGE TIMING INSTRUMENTATION

- Updated `scripts/check_market_coverage.py` to measure the real symbol-resolution time for **each configured market**.
- Each market now prints an indexed timing line in the form `[001/146] BTC/USDT -> ... | 0.123s`, including missing markets.
- Added total, average, minimum and maximum resolution timings.
- Output is flushed immediately so the per-market timer is visible while the 146-market run is in progress.
- No market-data, routing, analysis, or scheduler logic was changed.

### 2026-10-04 — FUTURES-ONLY MONITORING + SEQUENTIAL 24/7 QUEUE + 15s MARKET TIMEOUT

- Removed **MKR/USDT, NOT/USDT and DOGS/USDT** from the production monitored universe.
- Changed the remaining crypto monitored markets from **spot to futures**, because AICFA's execution/trading target is futures. TradFi remains futures as before.
- Production universe is now **114 crypto futures + 29 TradFi futures = 143 markets**.
- Autonomous monitoring no longer uses a 20-market/minute batch model. The queue is now **one market at a time in configured order**, then wraps to the first market and repeats continuously 24/7.
- `batch_size=1` is retained only for API compatibility; a multi-market batch is no longer the production scheduling model.
- Coverage resolution now has a **15-second per-market timeout**. If no source resolves the market within 15 seconds, it is logged as TIMEOUT and the queue advances to the next market immediately.
- The 15-second rule is a data-resolution guard; it does not fabricate data or substitute an unmapped venue.

### Next exact action

1. Deploy these changes through FrostDeploy.
2. Run focused universe + autonomous scheduler tests.
3. Run the 143-market live coverage check and record which crypto futures are actually available.
4. Remove only crypto markets that genuinely have no usable futures source after the 15-second rule; do not silently fall back to spot.
5. Validate representative/full futures OHLCV/MTF acquisition before continuing with setup analysis.


### 2026-10-04 — FULL MARKET EVIDENCE ACQUISITION: DERIVATIVES + CAUSAL SMART-MONEY CONTEXT

- Verified that AICFA already contains a dedicated derivatives evidence layer:
  `derivatives_market_data.py` collects real Funding Rate, Open Interest, Mark Price and public liquidation events from Binance/Bybit without fabrication.
- `derivatives.py` causally aligns funding/OI/positioning observations to the OHLCV timeline and derives descriptive OI/price relationships.
- `derivatives_evidence.py` feeds the derivatives state into the same `MarketEvidence → scenario → setup → decision` chain. Liquidations remain optional event context; missing liquidation data never becomes a fabricated zero.
- Updated live `FindSetup` so futures requests automatically collect this existing derivatives layer; spot/non-futures requests do not incur the derivatives collection cost unless explicitly requested.
- Updated the full market-data diagnostic to verify real derivatives sources instead of reporting them as fake `UNSUPPORTED(provider-contract)` placeholders.
- Fixed Binance futures order-book history probing: Binance futures depth requires a supported depth limit; the L1 history collector now requests a valid futures depth size and still records only the best bid/ask.
- CCXT documentation was checked against the current unified public API: funding, open interest and liquidations are contract-specific and exchange-dependent, so unsupported venue capabilities must remain explicitly unavailable rather than fabricated.
- Current architecture therefore uses:
  `OHLCV + trades + order book + causal order-book history + derivatives context` where the market actually supports the source.
- Important timeout clarification: the existing 15-second timeout is a coverage/symbol-resolution guard. It is not yet a hard kill of a full production FindSetup analysis.

### Next exact action

1. Deploy the latest Git changes through FrostDeploy.
2. Run focused derivatives + FindSetup tests.
3. Run the full regression.
4. Run the complete 143-market full-data diagnostic.
5. Inspect actual coverage by source and only then decide whether any additional venue-specific adapters are justified.

### 2026-10-04 — FULL 143-MARKET DATA DIAGNOSTIC: 104 GREEN / 39 FOLLOW-UP ITEMS

- Completed the complete production full-data diagnostic across all **143 monitored futures markets**.
- Scope: OHLCV `1w/1d/4h/1h/15m/5m`, trades, order book, order-book history, funding rate, open interest, mark price and optional public liquidation events.
- Final result: **104/143 fully OK, 34/143 PARTIAL, 5/143 TIMEOUT**.
- Full diagnostic elapsed time: **1349.94s (~22m 30s)**.
- **32 PARTIAL markets** have complete primary market data but derivatives unavailable through the current Binance + Bybit derivatives layer: `PEPE, SHIB, BONK, FLOKI, RAY, XAU, XAG, XCU, XPT, WTI, BRENT, NATGAS, NIKKEI, SPY, QQQ, AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AVGO, AMD, MU, ARM, TSM, ASML, ORCL, PLTR, NFLX, COIN`.
- For those 32, all six OHLCV timeframes, trades, order book and order-book history passed; derivatives failed with the recurring Binance HTTP 400 / Bybit `10001` errors.
- **DJIA** is PARTIAL because `1w` OHLCV is unavailable from the resolved MEXC source; all other required primary market-data categories passed.
- **JPM** is PARTIAL because `1w` OHLCV, trades, order book and order-book history fail on the current Bybit mapping; MEXC also returns no `1w` OHLCV rows. Other OHLCV timeframes pass.
- **5 TIMEOUT markets:** `BABYDOGE, PONKE, MYRO, RDNT, GNS`. Each reached the diagnostic's 30-second per-market full-data timeout.
- The diagnostic confirms the core architecture is broadly functional. The remaining failures are concentrated in derivatives venue coverage, two primary TradFi mappings/data gaps, and five slow/unresolved crypto futures.
- No SMC, setup engine, Entry/SL/TP, RR, lifecycle or decision logic should be changed to solve these failures. Remediation belongs in market routing/acquisition and coverage handling.

### 2026-10-04 — DATA COVERAGE REMEDIATION PLAN FOR THE 39 AFFECTED MARKETS

- **Phase A — Derivatives coverage:** preserve the existing dedicated derivatives architecture (`funding + open interest + mark price + optional liquidation events -> causal alignment -> derivatives evidence -> scenario/setup/decision`). Extend routing so eligible verified futures venues can provide real derivatives data where Binance/Bybit do not. Never fabricate unsupported values.
- Derivatives must remain contextual evidence, not a single-metric kill switch for an otherwise valid structural SMC setup.
- Add tests for native derivatives-symbol routing, mapped-venue fallback, capability detection, and explicit unsupported fields.
- **Phase B — DJIA/JPM:** verify authoritative native mappings first. Repair or replace only the invalid/unusable venue mapping/source. Do not substitute crypto/USDT lookalikes or bypass `venue_symbols` with generic resolution.
- **Phase C — five timeouts:** investigate `BABYDOGE, PONKE, MYRO, RDNT, GNS` individually for stale mappings, slow fallback, unavailable futures contracts, endpoint-specific failures or excessive retries. Keep the 15-second symbol-resolution guard separate from the 30-second full-data diagnostic timeout. Remove a market only if it is genuinely unavailable as a usable futures market.
- **Phase D — final 143-market verification:** run focused tests, full regression, then the complete 143-market diagnostic again. Compare against the baseline **104 OK / 34 PARTIAL / 5 TIMEOUT** and document every remaining exception explicitly.

### Next exact action

1. Start with **Phase A: derivatives routing/capability coverage** for the 32 markets whose primary market data is already healthy.
2. Inspect the current derivatives provider/routing implementation and existing venue mappings before adding any new adapter.
3. Implement the smallest extension that supplies real funding/OI/mark data from eligible mapped futures venues.
4. Add focused regression tests and verify on the VDS.
5. Then fix DJIA/JPM and investigate the five timeout markets.
6. After the 39-market remediation, rerun the complete 143-market diagnostic and record the final before/after coverage.

### 2026-10-04 — PHASE A DERIVATIVES FOLLOW-UP: 29/32 TARGETS GREEN

- After adding the CCXT derivatives fallback chain and capability-aware current funding/OI/mark fallbacks, the targeted 32-market verification completed with **29/32 fully OK** and **3/32 PARTIAL**.
- All 29 GREEN markets had complete OHLCV `1w/1d/4h/1h/15m/5m`, trades, order book, order-book history, funding, open interest and mark price.
- The remaining three — **BONK, XCU and NATGAS** — have complete primary market data and fail only in derivatives acquisition.
- The failure is not an instruction to prefer OKX. The derivatives architecture is a capability-aware fallback chain and must switch between eligible futures venues until one supplies real funding + OI + mark price.
- Web/venue verification identified **Gate** as an additional real futures source for all three targets: Gate lists `BONK_USDT`, `XCU_USDT` and `NG_USDT` perpetual contracts. OKX also lists XCU and NG perpetuals, but the current OKX adapter is unable to obtain a valid mark-price observation for these three cases.
- Added Gate/CCXT as the next derivatives fallback with `defaultType=swap`, preserving the no-fabrication rule.
- Added focused regression coverage for Gate swap routing.
- Do not rerun the full 32-market diagnostic yet. First run the three-market targeted verification for **BONK, XCU, NATGAS**.

### 2026-10-04 — GATE CCXT CONSTRUCTOR FIX

- The first targeted BONK/XCU/NATGAS verification did not reach market checks because the deployed CCXT package rejected `gateio` at provider construction time with `unsupported CCXT exchange: gateio`.
- The Gate fallback itself is intentionally universal and remains part of the common futures derivatives chain; this was a CCXT constructor-surface compatibility issue, not an asset-specific routing problem.
- Updated `CcxtDerivativesProvider` to retain the canonical exchange ID `gateio` while accepting a `gate` constructor alias when the installed CCXT build does not expose `ccxt.gateio`.
- Added regression coverage for the constructor alias and preserved Gate's `defaultType=swap` routing.
- Commits: `7ff15d9` (production fix), `611d9fd` (regression test).

### Next exact action

1. Deploy these commits through FrostDeploy.
2. Run `tests/test_derivatives_market_data.py` on the VDS.
3. Run only the targeted **BONK, XCU, NATGAS** full-data diagnostic.
4. If those three are green, do not add asset-specific rules; proceed with the universal derivatives coverage verification before the final 143-market run.

### 2026-10-04 — UNIVERSAL DERIVATIVE FIELD-LEVEL FALLBACK

- Confirmed the required architecture is broader than whole-provider fallback: a futures asset may expose different derivative fields on different venues.
- Implemented universal field-level aggregation in FallbackDerivativesProvider: funding, open interest and mark price are collected independently across the allowed venue set and combined causally without fabricating missing values.
- Expanded the derivatives CCXT fallback to the configured 19 allowed exchanges.
- Added native futures-symbol routing: authoritative venue_symbols are passed into derivatives acquisition, while CCXT can resolve a futures symbol from loaded markets when no explicit mapping is supplied.
- Providers are no longer rejected merely because one derivative field is unavailable; another venue can supply that field. The final result is accepted only when funding + open interest + mark price are all actually present somewhere in the collected real observations.
- Added focused tests for mixed-source derivative fields and native futures-symbol routing.
- Commits: 5df0b5b (field-level fallback), c51f3c7 (allow partial provider observations), 01c6ef2 (pass native venue symbols), 28568f5 (tests).
- Next: deploy, run the derivatives test suite, then verify only XCU first. After XCU is confirmed, handle BONK timeout separately. Do not rerun 32/143 yet.


### 2026-10-04 — DERIVATIVES FALLBACK BOUNDARY + FIELD PROVENANCE

- Completed the universal derivative field-level fallback implementation.
- The derivatives core is explicitly defined as: funding_rate, open_interest, mark_price.
- Optional liquidation fields remain best-effort context: liquidation_volume, long_liquidation_volume, short_liquidation_volume.
- Each field is independently sourced and causally merged. A market may therefore receive funding, OI, mark price and liquidation context from different real futures venues.
- The fallback now records field-level provenance (for example funding_rate=okx, open_interest=gateio) instead of reporting only a provider list.
- The universal provider chain now uses a bounded per-provider timeout of 3 seconds by default.
- The chain stops immediately once all three mandatory core fields have real observations. Missing optional liquidation data never keeps AICFA waiting on additional slow/unsupported venues.
- No fabricated values were introduced; unavailable fields remain unavailable.
- Added regression coverage proving that an unnecessary provider is not queried after core derivatives coverage is complete.
- Commits: 7defb3a (bounded fallback + field provenance), 8dde57c (early-stop regression test).

### Next exact action

1. Deploy these two commits through FrostDeploy.
2. Run tests/test_derivatives_market_data.py.
3. Run the direct XCU full-data diagnostic.
4. If XCU is green, run BONK and NATGAS targeted diagnostics.
5. Only after those are green, rerun the broader derivatives-affected market set and compare against the 29/32 baseline.


### 2026-10-04 — DERIVATIVES SEMANTIC CORRECTION: CONTEXTUAL EVIDENCE, NOT TRADING CORE

- Corrected the product-level semantics of derivatives data.
- **Price + market structure + SMC remain AICFA's primary decision foundation**: OHLCV, confirmed swings, HH/HL/LH/LL, BOS/CHoCH/MSS, liquidity, OB/FVG, zone reaction, volume, structural Entry/SL/TP.
- Funding Rate, Open Interest, Mark Price and Liquidations are an **additional derivatives evidence/mechanism layer**. They help explain, confirm or contradict what price/structure is doing; they do not replace structural evidence.
- The previous wording "mandatory derivatives core" was incorrect at the product level. The three fields funding_rate, open_interest, mark_price are now treated as a **preferred derivatives evidence coverage target** used only to optimize data acquisition/fallback.
- A structurally valid SMC setup must **not** become NO TRADE solely because funding, OI, mark price or liquidation data is unavailable or partial.
- Missing/partial derivatives data is now recorded in optional_missing_context, not the structural missing_context gate. Therefore derivatives availability cannot independently force NEED_MORE_EVIDENCE.
- derivatives.price_oi evidence is emitted when the actual OI + mark observations needed for that relationship exist; funding enriches the context when available. Missing fields are never fabricated.
- Renamed the market-data fallback terminology from "core fields" to **coverage fields** so the implementation cannot be mistaken for a trading-priority hierarchy.
- Commits: 1ad02eb (contextual derivatives evidence / no setup gate), 16bd9b6 (regression tests for missing/partial derivatives), 69dec28 (derivatives coverage terminology), cd06679 (remove remaining mandatory-core implementation wording).
- No new signal, confidence score, RR filter or asset-specific exception was introduced.

### Next exact action

1. Deploy the semantic correction to the VDS.
2. Run tests/test_derivatives_market_data.py and the new tests/test_derivatives_contextual.py.
3. Run focused FindSetup/decision tests to verify missing derivatives cannot gate a structural setup.
4. Re-run XCU, then BONK/NATGAS targeted diagnostics using the universal field-level fallback.
5. Only after those checks, continue the broader affected-market verification.


### 2026-10-04 — DERIVATIVES FALLBACK HARD TIMEOUT FIX

- Targeted verification of XCU/BONK/NATGAS exposed a real implementation gap: the configured 3-second provider timeout was only passed into individual CCXT/HTTP operations; a provider attempt containing multiple operations could still exceed that boundary and stall the universal fallback.
- Added a hard per-provider attempt timeout around `FallbackDerivativesProvider`, so a slow/blocked venue is abandoned after the configured provider timeout and the next eligible venue is tried.
- A timed-out provider is not allowed to block fallback completion while its underlying network/CCXT call unwinds.
- Kept field-level aggregation unchanged: funding, open interest and mark price remain independently sourced and causally combined; no value is fabricated.
- Hardened Gate/CCXT swap initialization by disabling unnecessary currency fetching, avoiding the unrelated spot-currency request observed during XCU diagnostics.
- Added regression coverage proving a slow provider is bypassed within the hard timeout and Gate keeps swap routing without currency discovery.
- Production commit: `eef91da14458d6c8f6b0e902509508f5a16d0c2b`.
- Test commit: `228bbdafea2af78ff522c7dd8917d065efba4ec3`.

### Next exact action

1. Deploy these two commits through FrostDeploy.
2. Run `tests/test_derivatives_market_data.py` and `tests/test_derivatives_contextual.py`.
3. Run focused FindSetup/decision tests again to confirm no regression.
4. Re-run targeted `XCU BONK NATGAS` full-data diagnostics.
5. If green, continue the broader derivatives-affected market verification.


### 2026-10-04 — DERIVATIVES FALLBACK PARALLEL BATCH FIX


### 2026-10-04 — DERIVATIVES SYMBOL-NORMALIZATION FIX

- Expanded the real-data diagnostic from the three problematic markets to 12 futures markets: XCU, BONK, NATGAS, XAU, WTI, XAG, PEPE, APT, BTC, ETH, LTC, SOL.
- Result: **6/12 fully OK**. PEPE, XAU, XAG, XCU, WTI and NATGAS are green with complete OHLCV/trades/order-book data plus funding/OI/mark. PEPE/XAU/XAG/WTI obtain mark from Bitget; XCU/NATGAS obtain mark from Gate while funding/OI come from OKX.
- The four major liquid crypto tests BTC/ETH/SOL/LTC and APT failed derivatives acquisition because the resolved primary-market symbol was a native-style value such as BTCUSDT and was passed unchanged into the universal fallback. That format is valid for some REST endpoints but is not a valid CCXT unified futures symbol for the CCXT providers, so the fallback could not discover the corresponding BTC/USDT:USDT market.
- BONK remained partial with only mark_price missing; the other fields were also unavailable in this run. The failure is now separated from the generic crypto-symbol issue because BONK already uses a CCXT-style BONK/USDT:USDT primary symbol and still needs provider-level investigation.
- Added canonical symbol normalization at the universal derivatives boundary: native-style BTCUSDT, ETHUSDT, etc. are normalized to BTC/USDT, ETH/USDT, etc. before CCXT/provider fallback. Explicit venue_symbols still take precedence through native_symbol, so authoritative venue-specific mappings are not overwritten.
- Added a focused regression test proving a native-style resolved symbol is normalized before provider attempts.
- Production commit: 2cb9e3b6acc304947f93ae6c447b90a8f46aa4f1.
- Test commit: b1b2e0c9c75829455a3281a81f094fb900a54458.

### Next exact action

1. Deploy the symbol-normalization production/test commits through FrostDeploy.
2. Run tests/test_derivatives_market_data.py and tests/test_derivatives_contextual.py.
3. Run focused FindSetup/decision/MTF tests.
4. Re-run only **BTC ETH SOL LTC APT BONK** first; these are the remaining crypto cases from the 12-market probe.
5. Do not touch the six already-green markets or add asset-specific exceptions unless the new diagnostic proves a real venue-specific capability gap.

### 2026-10-04 — DERIVATIVES REGRESSION AUDIT: REMOVE UNPROVEN SYMBOL FIX / PRESERVE PARTIAL PROVIDER FIELDS

- Audited the recent derivatives symbol-normalization change against the previous known implementation.
- The BTCUSDT → BTC/USDT normalization was not sufficiently established as the cause of the observed diagnostic behavior and was removed rather than retained as an unverified universal change.
- Removed its regression test and removed the corresponding unverified plan entry.
- Identified a separate real robustness gap in CcxtDerivativesProvider: failures in current funding/OI endpoints or ticker lookup could discard otherwise valid fields already obtained from the same venue.
- Hardened current funding, current OI and ticker fallbacks so an unavailable optional/current endpoint leaves that field unavailable while preserving other real derivative observations from the provider.
- Added regression coverage for partial CCXT derivative observations.
- Production commit: cdf49bcfc7fd53a20a3320437906791a7b0797c5.
- Test commit: ed8122e0e0d2c1b267485ff1b423cead03028d55.
- The live VDS diagnostic still needs to be rerun after deployment; no claim is made that BTC/ETH/SOL/LTC/APT or the full 143-market universe is fixed until that verification is actually performed.

### Next exact action

1. Deploy the latest source/test commits through FrostDeploy.
2. Run the complete derivatives-focused test files on the VDS.
3. Run the expanded 12-market diagnostic again.
4. Compare BTC/ETH/SOL/LTC/APT/BONK against the prior green/partial behavior.
5. Only then continue to the complete affected-market and final 143-market verification.

### 2026-10-04 — DIAGNOSTIC SYMBOL CONTRACT FIX

- The 12-market VDS diagnostic exposed a concrete integration bug in `scripts/check_full_market_data.py`: the script passed the resolved primary-market symbol into the universal derivatives fallback.
- For Binance-resolved crypto markets this value is venue-native, e.g. `BTCUSDT`, while the universal derivatives layer expects AICFA's canonical asset identifier such as `BTC/USDT`; authoritative `venue_symbols` remain the mechanism for explicit native futures symbols.
- This caused BTC/ETH/SOL/LTC/APT to fail derivatives acquisition even though their primary OHLCV/trades/order-book data was healthy. The failure was in the diagnostic's symbol handoff, not evidence that those markets themselves lacked futures derivatives.
- Fixed only the diagnostic integration in production commit `826273563c3fc078893fdd15387837c9b62ad93d`: derivatives now receive `asset`, while primary market-data calls continue using the resolved `symbol`.
- The already-green PEPE/XAU/XAG/XCU/WTI/NATGAS results remain untouched.
- No speculative universal symbol normalization was reintroduced into the derivatives provider.
- VDS verification is still required after this commit; no claim is made about the remaining 143-market coverage until the corrected diagnostic is run.

### 2026-10-04 — DERIVATIVES CORE PATH / LIQUIDATION ISOLATION

- The corrected 8-market diagnostic confirmed the canonical-symbol integration fix: ETH, SOL, LTC, APT, XCU and NATGAS are fully green (6/8).
- BTC still failed because the highest-priority Binance derivative attempt timed out, and the fallback batch also timed out across the tested venues. BONK retained OI coverage but was missing funding and mark.
- Code audit found a concrete architectural cause: Binance/Bybit derivative providers fetched the optional liquidation websocket inside the same provider call as required funding/OI/mark. A slow/no-event websocket could consume the provider's 3-second hard budget and discard otherwise valid core derivative fields.
- Fixed in production commit `b95d6108f2b0d1ede3884267b17f8d7a6db1182c`: Binance/Bybit core derivative fetches no longer block on liquidation collection. Liquidations remain explicitly optional event context and are not allowed to veto funding/OI/mark acquisition.
- No symbol normalization was added. The canonical asset + authoritative venue mapping contract remains unchanged.
- Next verification: derivative unit tests, then BTC/BONK targeted diagnostic. 


### 2026-10-04 — DERIVATIVES PARTIAL-ENDPOINT PRESERVATION

- The corrected BTC/BONK diagnostic showed BTC is now fully green: Binance supplied funding, OI and mark, confirming the liquidation-path isolation fix worked.
- BONK remained partial because Binance returned HTTP 400 and Bybit returned API error 10001, while the CCXT fallback venues mostly hit the 3-second provider boundary. The direct Binance/Bybit providers still had one robustness gap: if any one of their funding/OI/mark HTTP calls failed, the entire provider attempt was discarded.
- Hardened Binance and Bybit derivative providers so funding, open interest and mark are acquired independently. A contract-specific endpoint failure now leaves only that field unavailable and preserves other real fields from the same venue for field-level fallback.
- Added regression tests for partial Binance and Bybit provider observations.
- No fabricated derivative values, symbol normalization, asset-specific exception or trading-rule change was introduced.
- Production commit: `793a648c7a6ab130a7aed54eca91ff7dfd63d0b9`.
- Test commit: `90b1a6332f2422e7b533a284f0d6255b6e81a600`.

### Next exact action

1. Deploy the latest source/test commits through FrostDeploy.
2. Run the derivative-focused tests.
3. Re-run only BONK full-data diagnostic.
4. If BONK is still partial, inspect which individual fields remain unavailable and continue provider-level capability/fallback work rather than adding an asset-specific exception.


### 2026-10-04 — BONK OKX DIRECT DERIVATIVES PATH

- VDS verification after the partial-endpoint fix: derivative tests passed (20/20), but BONK remained PARTIAL at 17.19s with the OKX CCXT provider timing out at the 3-second provider boundary; all remaining fallback venues were unsupported or also timed out.
- The concrete bottleneck is now provider transport/market discovery, not missing BONK primary market data: primary OHLCV, trades, order book and history are all green.
- Added a direct, keyless OKX public REST derivatives provider for the universal fallback. It requests funding-rate history, open interest and mark price directly from OKX public V5 endpoints and runs the three independent requests concurrently, so slow CCXT market discovery cannot consume the provider budget.
- The direct provider accepts AICFA canonical symbols and authoritative native venue symbols, maps them to OKX *-USDT-SWAP instrument IDs, preserves partial real fields, and does not fabricate missing observations.
- Replaced the OKX CCXT provider in the default fallback chain with the direct OKX provider. CCXT remains available for the other venues.
- Added unit coverage for complete and partial direct OKX responses.
- Source commit: 0c2c080106350e8d088909491cb416d13dcf2ba1.
- Test commit: 84dc63390cb2ca5ef2aa87031e0f07d39b9b8f65.

### Next exact action

1. Deploy the latest source/test/plan commits through FrostDeploy.
2. Run tests/test_derivatives_market_data.py and tests/test_derivatives_contextual.py.
3. Re-run scripts/check_full_market_data.py --assets BONK.
4. If BONK becomes green, run the affected-market diagnostic next; do not add asset-specific exceptions.


### 2026-10-04 — FUTURES MARKET RESOLVER HARD TIMEOUT / GNS REMOVAL

- VDS diagnostics exposed a separate primary-market resolver bottleneck: the derivatives fallback already has its own 3-second provider boundary, but futures symbol resolution in `MarketAwareFallbackProvider` was sequential and CCXT-backed market discovery could use the normal 10-second transport timeout per venue.
- This explains why unsupported/missing futures markets could reach the diagnostic's 30-second market timeout before the resolver exhausted the venue chain.
- Changed generic market symbol resolution to a bounded fallback: first priority venue is probed alone, then remaining venues are probed in batches of up to 6, with a hard 3-second resolution budget per batch. A successful venue wins by configured priority; unsupported/slow venues are recorded and skipped.
- Explicit authoritative `venue_symbols` mappings remain unchanged and bypass generic discovery.
- Added regression tests proving a slow resolver is bypassed and that a missing market does not serialize all venue waits.
- Confirmed from the VDS diagnostic that `GNS/USDT` is absent from all 19 currently configured futures venues, so it is removed from `config/market_universe.json`.
- External verification also found KuCoin had already delisted GNS USDT-margined perpetuals in 2024. citeturn0search11
- No asset-specific resolver exception or fabricated market mapping was introduced.


### 2026-10-04 — BABYDOGE REMOVED FROM MARKET UNIVERSE

- Removed `BABYDOGE/USDT` from the configured futures market universe at the user's request.
- No resolver/provider exception or special-case routing was added.
- Production universe changed from 142 to **141 markets**.
- Commit: `4d713624ade2d89ccf854fa0cf5ea5e3f459447d`.


### 2026-10-04 — DELISTED FUTURES MARKETS REMOVED

- Removed `PONKE/USDT`, `MYRO/USDT` and `RDNT/USDT` from the configured futures market universe.
- This follows current exchange/delisting evidence and the production resolver's inability to resolve active futures markets for these assets across the configured venue set.
- No asset-specific resolver exception or fabricated venue mapping was added.
- Production universe changed from **141 to 138 markets**.
- `PONKE`: Binance Futures delisted PONKEUSDT in November 2025; Bybit also delisted PONKEUSDT in April 2026. citeturn0search0turn0search1
- `RDNT`: Binance Futures delisted the RDNT contract in March 2026; Bitget also delisted RDNTUSDT futures in March 2026. citeturn0search5turn0search2
- `MYRO`: Bitget's current delisting records show MYROUSDT futures were delisted in November 2025. citeturn0search7
- Market-universe commit: `47792629cf34f4a7cda56213754fc0e00ebce722`.
