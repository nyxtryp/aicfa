# AICFA — Project Control Plan

**Project:** AICFA — AI for Digital Financial Assets  
**Repository:** `nyxtryp/aicfa`  
**Primary asset during current development:** BTC/USDT  
**Rule:** build BTC/USDT core first. Top-100 CoinMarketCap support is postponed until the BTC core is stable.

This file is the persistent project memory and control log. It must be updated after **every meaningful commit** and used as the first reference before starting the next implementation step.

---

## 1. Mission

AICFA is a specialized AI system for analysis of crypto markets and digital financial assets.

It is **not** intended to be:
- a simple chatbot;
- a wrapper around a third-party LLM;
- a collection of technical indicators;
- a static signal bot.

The long-term goal is an analytical system with its own market representation, historical evidence, models, knowledge base, experience database, scenario engine and decision logic.

Possible final states:
- LONG
- SHORT
- WAIT
- NO TRADE

WAIT / NO TRADE are valid analytical outcomes.

---

## 2. Core principles

1. **Own intelligence** — specialized market logic, datasets and models are developed inside AICFA.
2. **Data before assumptions** — conclusions must be based on market data and historical evidence.
3. **Causality** — a feature at time t must not use information unavailable at t.
4. **Leakage prevention** — training/validation/test are chronological and future data must not leak into past features.
5. **Statistical verification** — SMC and other concepts are hypotheses/features to test, not automatic truths.
6. **Context over indicator counting** — do not implement “N confirmations = BUY”.
7. **Every important rule must be mechanically definable and testable.**
8. **Backtest ≠ guarantee** — fees, slippage, funding and execution assumptions must eventually be included.
9. **BTC first** — do not prematurely generalize the whole system for many assets.
10. **Change control** — work forward only; do not roll back commits unless explicitly requested.

---

# 3. Target analytical architecture

```
BTC/USDT OHLCV
      ↓
Data normalization
      ↓
Market Structure
      ↓
Liquidity
      ↓
Displacement
      ↓
FVG / Imbalance
      ↓
Order Blocks
      ↓
Premium / Discount
      ↓
SMC Market State
      ↓
Multi-Timeframe Structure
      ↓
Volume / Volatility
      ↓
Derivatives
      ↓
Scenario Engine
      ↓
Risk Engine
      ↓
Decision Engine
      ↓
LONG / SHORT / WAIT / NO TRADE
      ↓
Historical Outcome
      ↓
Experience Database
      ↓
Dataset / Model improvement
```

---

# 4. Trading modes

All four modes are required, but they do not need to be implemented simultaneously.

### Scalping
Primary context:
- 1M
- 5M
- 15M
- microstructure
- liquidity
- displacement
- volume
- volatility
- later OI/funding/liquidations/order flow/order book

### Intraday
Primary context:
- 5M
- 15M
- 1H
- 4H
- intraday structure
- liquidity
- derivatives
- sessions
- execution conditions

### Swing
Primary context:
- 1H
- 4H
- 1D
- higher-timeframe structure
- liquidity
- cycles
- derivatives
- risk/reward

### Position
Primary context:
- 1D
- 1W
- macro structure
- market cycles
- major liquidity
- volatility regimes

---

# 5. SMC / Market Intelligence requirements

## Market Structure
Required:
- HH
- HL
- LH
- LL
- BOS
- CHoCH
- MSS
- trend
- range
- expansion
- consolidation
- displacement
- internal structure
- external structure
- protected highs/lows

## Liquidity
Required:
- buy-side liquidity
- sell-side liquidity
- equal highs
- equal lows
- previous highs/lows
- liquidity pools
- sweep
- grab
- stop-run behaviour
- breakout traps
- internal/external liquidity

## Imbalance
Required:
- FVG
- IFVG
- imbalance
- displacement
- mitigation/fill state

## Order Blocks
Required:
- bullish OB
- bearish OB
- breaker
- mitigation
- invalidation
- relation to displacement

## Premium / Discount
Required:
- dealing range
- premium
- discount
- equilibrium

## Other knowledge
Required later:
- inducement
- POI
- SMT/divergence
- Price Action
- Wyckoff
- Volume
- Derivatives
- Market Microstructure

---

# 6. Current implementation status

## Foundation
Completed:
- AICFA project/repository
- brand/provenance work
- BTC/USDT as current development asset
- Python foundation
- deterministic causal feature engine
- triple-barrier-style labels
- initial tests
- FrostDeploy deployment/test workflow

## Existing feature engine
`src/aicfa/features.py` currently contains:
- returns
- log returns
- candle body/wicks
- candle range
- close location
- volatility
- range statistics
- volume statistics
- relative volume
- rolling highs/lows
- breakout proxies
- sweep proxies
- dealing range
- premium/discount
- trend proxies
- time context
- Market Structure features
- Liquidity features

## Market Structure
Implemented as first causal layer:
- swing highs
- swing lows
- HH
- HL
- LH
- LL
- BOS
- CHoCH
- structure direction
- reserved MSS fields

Important limitation:
**MSS is NOT yet genuinely implemented.** It must later be displacement-aware rather than simply renamed CHoCH.

Current structure also needs later refinement:
- internal/external structure
- protected highs/lows
- robust BOS/CHoCH semantics
- configurable sensitivity by timeframe
- careful treatment of same-row swing confirmation and break detection

## Liquidity
Implemented as first causal layer:
- equal highs
- equal lows
- buy-side liquidity
- sell-side liquidity
- liquidity price levels
- sweep high
- sweep low
- sweep + reclaim
- causal lookahead test

Important limitation:
Current equal-high/equal-low detection compares sequential confirmed swings. It is a foundation, not the final liquidity model. Later add:
- previous high/low liquidity
- multiple active pools
- internal/external liquidity
- pool lifecycle
- invalidation/mitigation
- more robust sweep/grab classification.

---

# 7. Commits / change log

## 2026-09-29 — Market Structure

### `cb0d9298a20ec3db367a4bd70ff94241461044cc`
**Add causal market structure engine**

Added `src/aicfa/structure.py`.

Implemented:
- causal swing confirmation;
- HH/HL/LH/LL;
- BOS;
- CHoCH;
- structure direction;
- reserved MSS columns;
- OHLC validation;
- equal tolerance.

Critical design rule:
A pivot is only emitted after the configured right-side candles confirm it. Information is written at the confirmation candle, not back at the pivot candle.

### `03116dba923207419fc9344866ce633b583ad5fa`
**Add market structure tests**

Added tests for:
- swing confirmation delay;
- HH/HL/LH/LL;
- no future lookahead;
- invalid parameters.

### `852c0044ed7638712eaad763a04678c8bb40ade0`
**Expose market structure features**

Connected structure output to `src/aicfa/features.py`.

---

## 2026-09-29 — Test fixes

### `3a6438a52f179c962a3d60544ea17235a58e68fa`
**Fix downloader path test for FrostDeploy releases**

Adjusted test so it works both in a normal repository checkout and FrostDeploy immutable release directories.

### `d8e5b84a6c5815e2c053b198305d896448ad73e2`
**Fix ambiguous label test to use valid volatility history**

Adjusted the test fixture/anchor only. Production label logic was not changed.

### Server verification

17 tests passed:
```
17 passed, 12 warnings
```

Warnings were left untouched because they were not part of the requested fixes:
- pandas deprecation warning;
- NumPy timedelta warnings;
- pytest cache warning in immutable release directory.

---

## 2026-09-29 — Liquidity

### `761bbfc51a2185e78864020f6c1612cf26c96d19`
**Add causal liquidity pool engine**

Added `src/aicfa/liquidity.py`.

Implemented:
- equal highs/lows;
- buy-side/sell-side liquidity;
- liquidity levels;
- high/low sweeps;
- sweep/reclaim;
- causal processing;
- OHLC validation.

### `8b3c07ed6b6b07b8a3f4c959196808ff46401f52`
**Add liquidity engine tests**

Added tests for:
- delayed equal-high confirmation;
- high sweep/reclaim;
- low sweep/reclaim;
- no future lookahead;
- invalid parameters.

### `c804aca1a789f6b0ecef6d99601750b126ab4714`
**Expose liquidity features**

Connected liquidity output to `src/aicfa/features.py`.

### Server verification after initial Liquidity integration

The FrostDeploy suite was run against the current release and found two failures:
- `tests/test_liquidity.py::test_low_sweep_and_reclaim_is_causal` — the fixture closes exactly at the sell-side liquidity level on reclaim; production logic used a strict `>` boundary.
- `tests/test_structure.py::test_hh_hl_lh_ll` — the fixture did not actually contain a confirmed HL/LL sequence under the configured one-candle swing rule.

Fix commits:

### `d7a04d0ac22e0bed23dcb00a3198474676bdea27`
**Fix low liquidity reclaim boundary**

Changed low sweep/reclaim recognition from `close > level` to `close >= level`, making reclaim symmetric with crossing back to/through the known sell-side level and matching the existing causal test definition.

### `57a180b2f8cde42ec815bb06b506b4c528221804`
**Fix market structure swing test fixture**

Adjusted only the test data so it contains actual confirmed HH/HL/LH/LL swing points while remaining valid OHLC.

**Production impact:** only the low-reclaim boundary changed; no unrelated engine logic was changed.

**Post-fix server verification:** PASS — FrostDeploy ran the full suite after the fixes: `26 passed, 12 warnings in 4.46s`.

Warnings remain non-blocking: pandas deprecation, NumPy timedelta deprecations, and pytest cache permission warnings in immutable FrostDeploy releases.

---

# 8. Mandatory server verification

Current FrostDeploy test command:

```bash
sudo -u fd-aicfa bash -lc '
cd "$(readlink -f /srv/frostdeploy/aicfa/current)"
PYTHONPATH=src .venv/bin/python -m pytest -q
'
```

Never claim a test suite passes unless the current code was actually verified.

---

# 9. Immediate next work

Do NOT jump to ML yet.

Order:

### Step 1 — Verify current branch
Run the complete test suite after each new implementation layer.

### Step 2 — Fix only real failures
Do not change unrelated production code.

### Step 3 — Refine Market Structure
Before calling SMC complete:
- protected highs/lows;
- internal/external structure;
- level lifecycle;
- robust BOS;
- robust CHoCH;
- displacement-aware MSS;
- timeframe sensitivity.

### Step 4 — Refine Liquidity
Add:
- previous highs/lows;
- multiple liquidity pools;
- internal/external liquidity;
- pool lifecycle;
- sweep vs breakout distinction;
- invalidation.

### Step 5 — Displacement Engine
Mechanical features:
- range expansion;
- body expansion;
- close efficiency;
- relative volume;
- impulsive close;
- directional displacement;
- structural-break + displacement relationship.

### Step 6 — FVG / Imbalance Engine
Implement:
- bullish FVG;
- bearish FVG;
- size;
- displacement relation;
- mitigation;
- fill;
- invalidation.

### Step 7 — Order Block Engine
Implement mechanically:
- candidate OB;
- displacement relationship;
- mitigation;
- invalidation;
- breaker transition.

### Step 8 — Premium / Discount refinement
Use structural/dealing ranges rather than only generic rolling ranges.

### Step 9 — Unified SMC state
Combine:
- structure
- liquidity
- displacement
- FVG
- OB
- premium/discount

into a causal market-state representation.

### Step 10 — Multi-timeframe
Only after the single-timeframe components are reliable:
- 1M
- 5M
- 15M
- 1H
- 4H
- 1D
- 1W

The exact active timeframes depend on trading mode.

### Step 11 — Scenario engine
Build separate logic for:
- Scalping
- Intraday
- Swing
- Position

### Step 12 — Labels / datasets
Generate historical situations using causal features and future outcomes only in the label layer.

### Step 13 — First ML baseline
Start with a simple measurable baseline before complex deep learning:
- direction;
- expected move;
- volatility/range;
- risk/outcome.

Then PyTorch models can be evaluated against baselines.

### Step 14 — Backtesting
Include:
- fees;
- slippage;
- funding;
- execution assumptions;
- chronological validation;
- purge/embargo where label horizons overlap.

### Step 15 — Experience database
Store:
- situation;
- market state;
- scenario;
- entry/SL/TP;
- actual outcome;
- MAE/MFE;
- model version;
- error analysis.

### Step 16 — Knowledge + active information gathering
Later:
- structured knowledge base;
- historical similarity;
- determine missing information;
- request additional data;
- information-value selection.

### Step 17 — Vision
Only after Market Brain is useful without screenshots.

### Step 18 — Paper trading
Mandatory before real-money use.

### Step 19 — Platform/API
Only after analytical core is stable.

---

# 10. Top-100 expansion

**NOT NOW.**

Current implementation is BTC/USDT only.

When BTC core is stable:
1. create an asset abstraction;
2. connect CoinMarketCap/top-100 selection;
3. reuse the validated feature/structure/liquidity architecture;
4. add asset-specific data quality handling;
5. do not rewrite the BTC core unnecessarily.

---

# 11. Change-control protocol for every future commit

After every meaningful Git commit:

1. Record commit SHA.
2. Record commit message.
3. Record exactly what changed.
4. Record tests added/changed.
5. Record server/deployment status.
6. Record what was fixed.
7. Record known limitations.
8. Record the next concrete task.
9. Re-read this file before beginning the next task.
10. Update this file again after the next commit.

This file is the persistent handoff/memory for future chats.

**Do not rely on conversation memory when this file can contain the information.**

---

# 12. Current checkpoint

**Latest implementation commits:** `b022845fbae914e5db59a84c65581ac3f067b6fd` (Derivatives refinement), preceded by `a82d51aa1dd0689e8d04bd3e8335c252806a5944`, `092113d0b91d67defd19d9b4dd042b6bb9e99b19`, `389b26c127c3df7d76dd10a08b2d9b99e0e47d37`, `f10aa5b06d0a48963ac7feb60bffc1e61ae23448`.

**Current layer:** Derivatives — first causal funding/open-interest/liquidation representation implemented and fully verified.

**Current state:**
- Market Structure: refined causal implementation complete and verified.
- Liquidity: refined causal implementation complete and verified.
- Displacement: causal implementation complete and verified.
- FVG: implemented and verified green on FrostDeploy.
- Order Blocks: implemented, integrated into the feature engine, and verified green on FrostDeploy.
- Premium / Discount: structural dealing-range implementation added and verified green.
- Unified SMC: causal unified state representation implemented and integrated; refined structure and liquidity namespaces verified.
- Multi-timeframe: causal standalone implementation complete; explicit coverage includes **1m, 5m, 15m, 1h, 4h, 1d, 1w**; integration and future-change coverage verified.
- Volume / Volatility: causal regime layer implemented, integrated, and verified.
- **Derivatives: first causal layer implemented, integrated, and verified.**
- Scenario Engine: implemented and verified; scenario hypotheses remain descriptive and are not final trading decisions.
- ML dataset/model: not started.
- Experience DB: not started.
- Vision: not started.
- Paper Trading: not started.
- Top-100 assets: explicitly postponed.

## 2026-09-29 — Derivatives refinement and server verification

Implementation/refinement commit:
- `99c024e2ba7a4e69259822407a3e507551b3fbf7` — Fix point-in-time derivatives alignment semantics.
- `b022845fbae914e5db59a84c65581ac3f067b6fd` — Refine derivatives funding and OI alignment semantics.

The first implementation used backward alignment for all derivative fields, which incorrectly carried funding observations into base candles between funding updates. The refinement separates semantics:
- funding-rate fields are point-in-time and are visible only at their exact observation timestamp;
- open interest is treated as a state observation and the latest known OI is carried forward causally until a newer observation;
- all derivative-derived changes/z-scores are calculated in derivative-observation order before alignment;
- optional liquidation fields remain causal and are not invented when absent;
- price/OI relationship fields remain descriptive only.

The first server run exposed the expected semantic mismatch in the initial implementation:
```
90 passed, 1 failed, 2844 warnings
```
Failure:
`tests/test_derivatives.py::test_derivatives_align_only_known_observations` — OI at the intervening base candle needed to retain the last known observation.

After the refinement, FrostDeploy verification passed against release `2026-09-29T06-27-33-b022845`:

```
91 passed, 2843 warnings in 30.84s
```

Verification status: **PASS**.

The 2843 warnings are non-blocking and deferred to the dedicated cleanup/optimization pass. They include:
- pandas/NumPy deprecations;
- DataFrame fragmentation PerformanceWarnings in feature/MTF construction;
- a Premium/Discount test-fixture dtype FutureWarning;
- immutable FrostDeploy release pytest-cache permission warnings.

The Derivatives layer is **accepted**.

Known limitations for the next derivatives expansion:
- current derivatives layer covers funding and OI plus optional liquidation fields;
- Long/Short Ratio, Basis and broader positioning data are still pending;
- richer order-flow/order-book/microstructure data remains future work;
- derivatives remain descriptive market-state inputs and do not yet produce trading signals or decisions.

**Next concrete task:** continue the documented analytical core with the next missing derivatives/market-state components — Long/Short Ratio, Basis and positioning where historical source data is available — while preserving the causal contract. Do not jump to ML yet.
