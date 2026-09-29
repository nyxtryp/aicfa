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
- robust level lifecycle
- better BOS/CHoCH semantics
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

**Last verified code commits:** `18aa8bdf8479c2094c4c8cc3ab5d7870606a29ac`, `c147fec530f8abca4426147f2593e13393813618`, and `37f4db3b5b6ba47b1aaceab35238219197e77449`

**Current layer:** Displacement — verified green on FrostDeploy

**Current state:**
- Market Structure: first causal implementation complete, refinement pending.
- Liquidity: first causal implementation complete, server verification complete.
- Displacement: first causal implementation complete, server verification complete.
- FVG: not started.
- Order Blocks: not started.
- Unified SMC: not started.
- Multi-timeframe: not started.
- Scenario Engine: not started.
- ML dataset/model: not started.
- Experience DB: not started.
- Vision: not started.
- Paper Trading: not started.
- Top-100 assets: explicitly postponed.

**Immediate action:** begin the FVG / Imbalance Engine. Displacement is now verified green on FrostDeploy.

---

# 13. Rule for this document

This document is **living project memory**.

After each commit, immediately update:
- the change log;
- current checkpoint;
- server verification;
- known issues;
- next task.

Before each new implementation step, read this document and continue from the checkpoint rather than reconstructing the project from chat history.


## 2026-09-29 — Displacement Engine

Implementation commits:
- `18aa8bdf8479c2094c4c8cc3ab5d7870606a29ac` — Add causal displacement engine.
- `c147fec530f8abca4426147f2593e13393813618` — Add displacement engine tests.
- `37f4db3b5b6ba47b1aaceab35238219197e77449` — Expose displacement features.

Implemented: range expansion, body expansion, close efficiency, strictly past-only relative volume, impulsive close direction, directional displacement, multi-factor displacement events, and displacement+BOS relationships. Tests cover causality, directionality, multi-factor requirements, and validation.

Server verification is pending. The next concrete action is the full FrostDeploy pytest run against this implementation. If green, proceed to FVG / Imbalance.

## 2026-09-29 — Displacement server verification

Full FrostDeploy test suite was run against release `2026-09-29T04-39-36-a2834ab` using the mandatory command.

Result:
```
32 passed, 12 warnings in 3.10s
```

Verification status: **PASS**.

The 12 warnings are non-blocking and unchanged in scope:
- pandas deprecation warning in `tests/test_dataset.py`;
- NumPy timedelta deprecation warnings in `src/aicfa/labels.py`;
- pytest cache permission warning caused by the immutable FrostDeploy release directory.

No production fixes were required after the Displacement implementation. The Displacement layer is therefore accepted as the current verified foundation for the next layer.

**Next concrete task:** implement the causal FVG / Imbalance Engine, with bullish/bearish FVG detection, size, displacement relationship, mitigation/fill state, and invalidation, followed by focused tests and full FrostDeploy verification.


## 2026-09-29 — FVG / Imbalance Engine implementation

Implementation commits:
- `28aa8f8c3b5d27751bbfb8a64e0ff1ca9af3c859` — Add causal FVG and imbalance engine.
- `436f8d07fcbd8f9e5bbef5b659684bf497118442` — Add FVG and imbalance engine tests.
- `d4f10cb61e652f12c8373d3e10575f457aa07824` — Expose FVG and imbalance features.

Implemented:
- bullish three-candle FVG;
- bearish three-candle FVG;
- gap size and percentage size;
- optional minimum gap filter;
- optional causal displacement requirement;
- FVG creation at the first candle where the gap is knowable;
- causal mitigation and fill lifecycle;
- invalidation state;
- active FVG state;
- bullish/bearish gap bounds;
- focused causality and validation tests.

Server verification: **pending**.

**Next concrete action:** run the complete FrostDeploy pytest suite against the FVG implementation. If green, accept the layer and continue to Order Blocks. If failures occur, fix only the actual failures and re-verify.


## 2026-09-29 — FVG test fixture correction

The first FrostDeploy verification exposed five FVG test failures caused by invalid OHLC fixtures in `tests/test_fvg.py` (some test candles had `low > open`). The FVG validation itself correctly rejected those malformed candles.

Commit:
- `a0424090ddd5eb04f7d3b573f11b68a41325baf3` — Fix invalid OHLC fixtures in FVG tests.

No FVG engine logic was weakened or changed. The fixtures were corrected to valid OHLC while preserving the intended FVG scenarios.

**Next concrete action:** rerun the complete FrostDeploy pytest suite.

## 2026-09-29 — FVG fixture follow-up

The next server verification found one remaining invalid OHLC fixture in the displacement-gated FVG test. Commit `09bc639f6ddb69fecaf666c423b3fb754157012e` corrected only that fixture; FVG engine logic remains unchanged.

**Next concrete action:** rerun the complete FrostDeploy pytest suite.