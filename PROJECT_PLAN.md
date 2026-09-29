# AICFA — Project Control Plan

**Project:** AICFA — AI for Digital Financial Assets  
**Repository:** `nyxtryp/aicfa`  
**Primary asset during current development:** BTC/USDT  
**Rule:** build BTC/USDT core first. Top-100 CoinMarketCap support is postponed until the BTC core is stable.

This file is the persistent project memory and control log. It must be updated after **every meaningful commit** and used as the first reference before starting the next implementation step.

---

## Current implementation checkpoint

The analytical core is being built causally from the canonical finest timeframe upward:
**1m → 5m → 15m → 1h → 4h → 1d → 1w**.

Completed and verified layers include Market Structure, Liquidity, Displacement, FVG, Order Blocks, Premium/Discount, Unified SMC, Multi-Timeframe, Volume/Volatility, Scenario Engine, and the first Derivatives layer.

The project remains **pre-ML**. Do not jump to model training until the market-state representation is sufficiently complete and verified.

---

# 1. Mission

AICFA is a specialized AI system for analysis of crypto markets and digital financial assets.

It is not intended to be a simple chatbot, wrapper around a third-party LLM, collection of indicators, or static signal bot.

The long-term goal is an analytical system with its own market representation, historical evidence, models, knowledge base, experience database, scenario engine and decision logic.

Possible final states:
- LONG
- SHORT
- WAIT
- NO TRADE

WAIT / NO TRADE are valid analytical outcomes.

---

# 2. Core principles

1. Own specialized intelligence.
2. Data before assumptions.
3. Strict causality.
4. No future leakage.
5. Statistical verification of hypotheses.
6. Context over indicator counting.
7. Every important rule must be mechanically definable and testable.
8. Backtest is not a guarantee.
9. BTC/USDT first.
10. Forward-only change control; no rollback unless explicitly requested.

---

# 3. Target architecture

```
BTC/USDT OHLCV
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
Unified SMC state
  ↓
Multi-Timeframe
  ↓
Volume / Volatility
  ↓
Derivatives
  ↓
Scenario
  ↓
Risk
  ↓
Decision
  ↓
LONG / SHORT / WAIT / NO TRADE
  ↓
Historical Outcome
  ↓
Experience / Dataset / Model improvement
```

---

# 4. Trading modes

### Scalping
1M / 5M / 15M + microstructure, liquidity, displacement, volume, volatility, derivatives.

### Intraday
5M / 15M / 1H / 4H + structure, liquidity, derivatives and execution context.

### Swing
1H / 4H / 1D + higher-timeframe structure, liquidity, derivatives and risk.

### Position
1D / 1W + macro structure, cycles, major liquidity and volatility regimes.

---

# 5. SMC / Market Intelligence requirements

Required:
- HH / HL / LH / LL
- BOS / CHoCH / displacement-aware MSS
- internal/external structure
- protected highs/lows
- liquidity pools, previous highs/lows, equal highs/lows
- sweep / grab / breakout distinction
- FVG / IFVG / imbalance / mitigation
- bullish/bearish OB, breaker, invalidation
- premium / discount / equilibrium
- Price Action
- Wyckoff
- Volume
- Derivatives
- later market microstructure

SMC concepts remain descriptive hypotheses until historical evidence establishes their behavior. They must not become automatic trade signals merely because several features co-occur.

---

# 6. Derivatives layer

## First causal derivatives layer — accepted

Implemented:
- funding rate;
- funding delta/change/z-score;
- open interest;
- OI delta/change/z-score;
- descriptive price/OI relationship states;
- optional liquidation volume fields.

Important semantics:
- funding is point-in-time;
- OI is a state carried forward from the latest known observation;
- derivative changes/z-scores are calculated in source observation order;
- optional liquidation data is preserved only when actually supplied;
- no derivative field creates a trade signal by itself.

Verified on FrostDeploy release `2026-09-29T06-27-33-b022845`:
```
91 passed, 2843 warnings in 30.84s
```

---

## 2026-09-29 — Derivatives positioning expansion

### `666edd4f7beacbff3d9dbb8c3f2fbbf12c1f8f2b`
**Add causal derivatives positioning features**

Expanded `src/aicfa/derivatives.py` with optional historical derivatives fields:

### Long/Short Ratio
Supported fields:
- `long_short_ratio`
- `long_short_ratio_global`
- `long_short_ratio_top_trader`

For each supplied ratio AICFA derives:
- raw ratio;
- delta;
- change percentage;
- causal z-score.

Ratio values must be positive when supplied.

### Basis
Supported:
- `basis`
- `basis_pct`

For each supplied basis field AICFA derives:
- raw basis;
- delta;
- change percentage;
- causal z-score.

Basis remains signed; positive/negative values are preserved rather than converted into a bullish/bearish score.

### Positioning semantics
Positioning and basis are treated as latest-known state observations and carried forward only from timestamps already available to the base candle.

Funding remains point-in-time.

Liquidations remain event observations and are not forward-filled.

### `91a0b4c94d6373e8db7495ed15522ababe834b80`
**Test causal derivatives positioning features**

Added tests for:
- global/top-trader long/short ratio;
- basis;
- causal carry-forward;
- derived delta/z-score fields;
- future-change invariance;
- invalid ratio rejection.

**Server verification:** pending. The implementation is not accepted until the complete FrostDeploy suite is run.

---

# 7. Existing completed analytical layers

The following layers were implemented and previously verified green:

- Market Structure — causal/refined.
- Liquidity — causal/refined.
- Displacement — causal.
- FVG — causal.
- Order Blocks — causal lifecycle.
- Premium/Discount — structural dealing range.
- Unified SMC — causal integrated state.
- Multi-Timeframe — explicit 1m/5m/15m/1h/4h/1d/1w causal mapping.
- Volume/Volatility — causal regimes.
- Scenario Engine — descriptive scenario families, not decisions.
- Derivatives — funding/OI/liquidations accepted; positioning/basis expansion pending verification.

---

# 8. Warnings / technical debt

Warnings observed in the suite are currently non-blocking:
- pandas/NumPy deprecations;
- DataFrame fragmentation PerformanceWarnings;
- Premium/Discount test fixture dtype FutureWarning;
- immutable FrostDeploy release pytest-cache permission warnings.

Do not mix warning cleanup into analytical feature work unless a warning becomes an actual failure or materially affects correctness/performance.

---

# 9. Mandatory server verification

```bash
sudo -u fd-aicfa bash -lc '
cd "$(readlink -f /srv/frostdeploy/aicfa/current)"
PYTHONPATH=src .venv/bin/python -m pytest -q
'
```

Never claim green status without the current deployed release output.

---

# 10. Immediate next work

1. Run and verify the new Derivatives positioning/basis layer.
2. If failures occur, fix only the actual semantic/test failure and rerun the full suite.
3. If green, record the exact release and test count here.
4. Continue remaining derivatives/market-state inputs:
   - broader positioning;
   - basis variants where source data supports them;
   - later taker flow/order flow;
   - later order book / market depth.
5. Keep derivatives descriptive and causal; no premature signals.
6. Then continue market-state completeness before ML.

ML training remains postponed.

---

# 11. Later roadmap

After the analytical representation is mature:

- Knowledge Base;
- Experience DB;
- historical similarity;
- Active Information Gathering;
- historical situation datasets;
- first ML baseline;
- PyTorch model(s);
- chronological evaluation;
- backtesting with fees/slippage/funding;
- paper trading;
- platform/API;
- vision.

Top-100 asset expansion remains postponed until the BTC core is stable.

---

# 12. Change-control protocol

After every meaningful commit:
1. record SHA;
2. record message;
3. record exact change;
4. record tests;
5. record verification status;
6. record known limitations;
7. record next task.

Never claim deployment/test verification without actual server output.

---

# 13. Current checkpoint

Latest implementation:
`666edd4f7beacbff3d9dbb8c3f2fbbf12c1f8f2b`

Latest tests:
`91a0b4c94d6373e8db7495ed15522ababe834b80`

Latest documentation:
this commit.

**Current task:** verify Long/Short Ratio + Basis + positioning expansion on FrostDeploy.

**Important:** The positioning expansion is implemented but NOT YET ACCEPTED until the full server suite is green.
