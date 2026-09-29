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

Completed and verified layers include Market Structure, Liquidity, Displacement, FVG, Order Blocks, Premium/Discount, Unified SMC, Multi-Timeframe, Volume/Volatility, Scenario Engine, and the expanded Derivatives layer, including the spot/futures relationship.

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

### Verification attempt — 2026-09-29
FrostDeploy run:
```
91 passed, 1 failed, 2844 warnings in 29.31s
```

Failure:
`tests/test_derivatives.py::test_derivatives_positioning_basis_features_are_causal`.

The failure was in the test expectation, not in the causal alignment implementation: the test expected `basis` to be empty on an intervening base candle, while the documented semantics treat basis as a latest-known state, just like positioning and OI. The first basis observation therefore remains visible until a newer observation arrives.

The fix was limited to the test expectation; no production derivative logic was changed.

### `9d6b221662c5ea11d2b6ab87f972feaeb833fde5`
**Fix derivatives basis state test semantics**

Changed only the incorrect test expectation so an already-observed basis value remains visible on intervening base candles under the latest-known-state semantics. Production derivative logic was unchanged.

### Final FrostDeploy verification — 2026-09-29
Deployed release: `2026-09-29T07-27-19-9d6b221`

Full suite:
```
93 passed, 2843 warnings in 31.04s
```

The derivatives positioning/basis expansion is now **accepted and green**.

Known non-blocking warnings remain: pandas/NumPy deprecations, DataFrame fragmentation, Premium/Discount fixture dtype warning, and pytest-cache permission warnings in immutable releases.

---

## 2026-09-29 — Liquidation imbalance

### `72bedcc0f67ad02aaab05e190618f43219c582`
**Add causal liquidation imbalance feature**

Added `liquidation_imbalance` when both directional liquidation streams are supplied:

`(long_liquidation_volume - short_liquidation_volume) / (long_liquidation_volume + short_liquidation_volume)`

Semantics:
- bounded to [-1, 1] when total liquidation volume is positive;
- NaN when total event volume is zero;
- event-based only, never forward-filled;
- emitted only when both long and short liquidation streams are available;
- remains causal under future changes.

### `38f3ea46f633c85c0ce8beb21bbd86596bcb827f`
**Test causal liquidation imbalance**

Added tests for event timestamps, zero-volume handling and future-change invariance.

The first verification exposed incorrect test fixture timestamp expectations. The production calculation was correct; the test was corrected in subsequent commits.

### `f533715a883d757f99c15b8777830e096c7313d5`
**Correct liquidation imbalance test value**

Corrected the event at `00:02`: long liquidation 6 and short liquidation 2 produce `(6-2)/(6+2) = 0.5`, not `0.4`. Production code was unchanged.

### Final FrostDeploy verification — 2026-09-29
Deployed release: `2026-09-29T07-38-38-f533715`

Full suite:
```
95 passed, 2843 warnings in 31.15s
```

The causal liquidation imbalance feature is now **accepted and green**.

Known non-blocking warnings remain unchanged: pandas/NumPy deprecations, DataFrame fragmentation, Premium/Discount fixture dtype warning, and pytest-cache permission warnings in immutable releases.

---

## 2026-09-29 — Futures volume

### `4f998cf8aef4333634d795cfe3e6ad80ba6129eb`
**Add causal futures volume features**

Added optional `futures_volume` to the derivatives layer.

Derived features:
- `futures_volume_delta`
- `futures_volume_change_pct`
- `futures_volume_zscore`

Semantics:
- futures volume is treated as an **event/interval observation**;
- values are aligned only at their own source timestamps;
- intervening base candles remain empty rather than receiving invented carry-forward volume;
- derived changes/z-scores are computed in source-observation order using a strictly past baseline;
- negative futures volume is rejected;
- no futures-volume feature creates a trade signal.

### `5ff0df7a9d34a9500bb6c548f2071aed17d01019`
**Test causal futures volume features**

Added tests for:
- event-based timestamp alignment;
- intervening base-candle NaN behavior;
- derived fields;
- future-change invariance;
- negative-value rejection.

### Verification attempt — 2026-09-29

FrostDeploy release `2026-09-29T07-41-29-5ff0df7`:
```
96 passed, 1 failed, 2844 warnings in 32.65s
```

Failure:
`tests/test_derivatives.py::test_derivatives_futures_volume_is_event_based_and_causal`.

The production code calculated the three derived futures-volume fields, but the event-alignment step initially propagated only the raw `futures_volume` column into the final output. The test correctly exposed the missing propagation of the derived event fields.

### `13c1df136bbe58c5b3d882a67290f90235e004a9`
**Fix futures volume derived event feature alignment**

Fixed the event alignment so `futures_volume`, `futures_volume_delta`, `futures_volume_change_pct`, and `futures_volume_zscore` are transferred together at exact source timestamps. No carry-forward or future leakage was introduced.

### Final FrostDeploy verification — 2026-09-29

Deployed release: `2026-09-29T07-43-01-13c1df1`

Full suite:
```
97 passed, 2843 warnings in 30.68s
```

The futures-volume feature is now **accepted and green**.

The remaining warnings are known non-blocking warnings: pandas/NumPy deprecations, DataFrame fragmentation, Premium/Discount fixture dtype warning, and immutable FrostDeploy pytest-cache permission warnings.

---

# 7. Existing completed analytical layers

The following layers were implemented and verified green:

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
- Derivatives — funding/OI/liquidations/positioning/basis/liquidation imbalance/futures volume/spot-futures relationship accepted.

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

1. Continue remaining derivatives/market-state inputs:
   - remaining source-backed derivatives variants;
   - later taker flow/order flow;
   - later order book / market depth.
2. Keep derivatives descriptive and causal; no premature signals.
3. Then continue market-state completeness before ML.

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
`578457cffacec916dd566b72337f48eacb52ce72`

Latest verified FrostDeploy release:
`2026-09-29T08-04-34-578457c`

Latest full-suite result:
`99 passed, 2843 warnings in 31.63s`

**Current status:** Derivatives positioning/basis, causal liquidation imbalance, futures volume, and the spot/futures relationship are implemented, deployed and verified green.

**Next task:** continue remaining source-backed derivatives/market-state inputs, starting with later taker flow/order flow and then market depth. Preserve strict causality and the pre-ML development boundary.
