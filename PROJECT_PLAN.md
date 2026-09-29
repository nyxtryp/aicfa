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

# 4. Product operating model

AICFA is **user-driven**, not an autonomous market-scanning signal bot.

The primary interaction is:

1. User asks AICFA for an urgent/current entry or analysis, for example: "find me an entry in any asset".
2. If the live market-data connection is available, AICFA uses its current network market data and its own analytical knowledge to search the relevant assets and produce a setup/analysis.
3. If required live data is unavailable, AICFA asks the user for chart screenshots for the relevant asset and timeframes.
4. AICFA analyzes the supplied visual evidence with its own market knowledge and rules and produces the requested setup/analysis.
5. The result is tied to the evidence actually available. No live data is fabricated.

### Explicit product exclusions

- **Scalping as a dedicated product mode is removed.**
- **Autonomous continuous setup scanning is removed.**
- AICFA does **not** continuously analyze Top-50/Top-100 assets looking for setups for no specific user request.
- AICFA does **not** run a separate market-analysis pipeline per customer.
- There is no requirement to maintain expensive realtime streams for every asset solely so that an autonomous scanner can generate alerts.
- A user request may target any asset; the asset is not fixed to BTC.
- The analytical core remains asset/timeframe aware and can use multiple timeframes when the user asks for an entry.

The historical analytical concepts previously described as Scalping/Intraday/Swing/Position remain knowledge/features of the analytical core where useful, but they are **not separate autonomous product modes or scheduled scanners**.

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

Known non-blocking warnings remain unchanged: pandas/NumPy deprecations, DataFrame fragmentation, Premium/Discount fixture dtype warning, and immutable FrostDeploy pytest-cache permission warnings.

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

## 2026-09-29 — Taker Flow / Order Flow verification

### Verification attempt — 2026-09-29

FrostDeploy release: `2026-09-29T08-13-25-97c16f6`

Full suite:
```
107 passed, 2843 warnings in 30.78s
```

The current Taker Flow / Order Flow implementation is now **accepted and green**.

Verified coverage includes:
- causal alignment of completed taker-flow intervals;
- taker buy volume;
- taker sell volume or causal derivation from total volume;
- net taker volume / delta;
- taker imbalance;
- buy/sell shares;
- change percentage;
- strictly-past z-score;
- rejection of inconsistent and negative volume inputs;
- zero-total handling;
- future-change invariance.

Known non-blocking warnings remain: pandas/NumPy deprecations, DataFrame fragmentation, Premium/Discount fixture dtype FutureWarning, and immutable FrostDeploy pytest-cache permission warnings.

Current limitation: CVD, absorption, liquidity walls, order-book changes, and market depth are not implemented yet because their source contracts and historical-availability semantics must be defined before implementation.

---

## 2026-09-29 — Order Book / Market Depth implementation started

### `32e98ba98ba9c28ba6bfb65037f97becde541d8e`
**Add causal order book and market depth features**

Added `src/aicfa/order_book.py` with a source contract for completed order-book snapshots.

Implemented descriptive features:
- best bid / ask price and size;
- mid price;
- spread and spread percentage;
- microprice;
- top-of-book Bid/Ask imbalance;
- bid/ask size deltas and change percentages;
- spread, mid-price and microprice changes;
- optional aggregate depth volume;
- optional depth imbalance and depth changes.

Causal semantics:
- snapshot timestamps represent availability time;
- base observations may use only snapshots already available at that time;
- source deltas are calculated in source observation order;
- no future snapshot may change an already available result.

The implementation deliberately does not infer liquidity walls or absorption from aggregate depth alone.

### `5aa450ef029d8aa2a3304e735a95d327399a506b`
**Test causal order book and market depth features**

Added tests for:
- causal snapshot alignment;
- Bid/Ask imbalance and microprice;
- optional aggregate depth;
- future-change invariance;
- crossed-market and negative-size validation;
- required source fields;
- zero-size ratio handling;
- source-order deltas.

### `530a803386031668ef3bda8e56e45d131d26ea1a`
**Define causal order book source contract**

Documented the source contract and availability-time semantics in `docs/AICFA_TZ.md`.

### Verification status

**Not yet server-verified.**

Required next step:
1. deploy these commits to FrostDeploy;
2. run the mandatory full pytest suite;
3. fix any real failures;
4. rerun until green;
5. only then mark Order Book / Market Depth accepted.

Current limitations:
- level-by-level liquidity walls are not implemented;
- order-book add/cancel flow is not implemented;
- absorption is not implemented;
- CVD remains deferred until its source/reset semantics are defined.


## 2026-09-29 — Level-by-level Order Book / Liquidity Walls implementation started

### `4a6ea7764cc1628aff3910da32af1d045348a9d5`
**Add causal level-by-level order book changes and liquidity walls**

Added `src/aicfa/order_book_levels.py`.

Implemented:
- normalized bid/ask level validation;
- per-level size delta;
- displayed additions;
- displayed cancellations/removals;
- aggregate bid/ask displayed-flow changes;
- persistent liquidity-wall detection;
- same-side snapshot-relative wall threshold;
- wall size multiple.

The layer remains descriptive. A removed level is accounted for as displayed cancellation/removal, without claiming the economic reason.

### `2d92f387be47ce3f869006ac0129a4f764d8c773`
**Fix liquidity wall persistence across unchanged snapshots**

Corrected wall persistence so a wall can remain a wall even when its displayed size does not change between consecutive complete snapshots. Persistence is now evaluated from the complete snapshot sequence rather than only from change rows.

### `6a86c2cf4d1f13bc60b4c202089f3def36a3f74b`
**Test level changes and liquidity wall features**

Added tests for:
- additions and cancellations;
- explicit level removal;
- aggregate bid/ask displayed flow;
- persistence-required wall detection;
- future-change invariance;
- invalid side and negative-size rejection.

### `f6df0f23bd2e3691a94e3c4be87d342c5db69066`
**Document level order book and liquidity wall semantics**

Documented the level-by-level source contract, wall persistence semantics and the limitation that displayed liquidity does not prove execution.

### Verification status

**Not yet server-verified.**

Required next step:
1. deploy the current commits to FrostDeploy;
2. run the mandatory full pytest suite;
3. fix any real failures;
4. rerun until green;
5. only then mark this stage accepted.

Absorption is intentionally deferred until synchronized trade/taker flow + order-book changes + price-response semantics are defined.


## 2026-09-29 — Level-by-level Order Book / Liquidity Walls verification

FrostDeploy release: `2026-09-29T08-34-31-a9154a8`

Full suite:
```
123 passed, 2843 warnings in 31.56s
```

The level-by-level Order Book / Liquidity Walls stage is now **accepted and green**.

Verified coverage includes:
- per-level additions;
- per-level cancellations/removals;
- displayed size deltas;
- aggregate bid/ask displayed-flow changes;
- persistence across unchanged snapshots;
- same-side relative wall threshold;
- liquidity-wall classification;
- future-change invariance;
- validation of invalid sides and negative sizes.

Known non-blocking warnings remain unchanged: pandas/NumPy deprecations, DataFrame fragmentation, Premium/Discount fixture dtype warning, and immutable FrostDeploy pytest-cache permission warnings.

Current limitation:
- liquidity walls remain descriptive displayed-liquidity features;
- no execution/absorption is inferred from a wall alone;
- absorption requires synchronized trade/taker flow, order-book changes and a defined price-response interval.

# 10. Immediate next work

1. Define and implement causal Absorption from synchronized Taker Flow + level-by-level book changes + price response.
2. Keep all market-microstructure features descriptive and causal; no premature signals.
3. Then continue market-state completeness before ML.

ML training remains postponed.

---

# 11. Later roadmap

After the analytical representation is mature:

- Knowledge Base as the primary durable intelligence layer;
- user-driven Active Information Gathering;
- screenshot/vision analysis as an independent evidence path;
- on-demand current-market analysis using available live connections;
- historical similarity / experience only where it materially improves an answer;
- historical situation datasets;
- first ML baseline;
- PyTorch model(s);
- chronological evaluation;
- platform/API;
- later optional execution adapter only if explicitly required.

Autonomous continuous setup scanning and a dedicated Scalping product mode are **not roadmap items**.

Top-100 expansion is no longer a product requirement by itself; asset selection should follow the user's current request and available evidence.

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


## 2026-09-29 — Absorption and CVD verification

### Absorption accepted

FrostDeploy verification confirmed the causal Absorption layer and its tests as part of the full suite. The feature remains an **absorption candidate**, not proof of execution.

Verified semantics:
- synchronized taker flow + level-by-level displayed liquidity;
- persistence and displayed replenishment/cancellation;
- bounded contemporaneous price-response measurements;
- strict backward window and availability-time causality;
- no future price movement in the live feature.

### CVD accepted

FrostDeploy release:
`2026-09-29T08-53-55-8153eb4`

Full suite:
```
133 passed, 2847 warnings in 34.70s
```

The CVD layer is now **accepted and green**.

Verified:
- completed taker-flow interval alignment;
- cumulative taker delta;
- explicit reset semantics;
- derived CVD delta/change fields;
- future-change invariance;
- invalid negative-flow validation.

Known non-blocking warnings remain unchanged: pandas/NumPy deprecations, DataFrame fragmentation, Premium/Discount fixture dtype warning, and immutable FrostDeploy pytest-cache permission warnings.

## 2026-09-29 — Price Action implementation started

### `a396c16f2fb355cc8443d7935ed0b15de21c9bb0`
**Add causal Price Action feature layer**

Added `src/aicfa/price_action.py`.

Implemented descriptive, causal features for:
- candle body and wick proportions;
- close location;
- bullish/bearish rejection;
- prior support/resistance levels;
- breakout and failed breakout;
- breakout retest;
- short candle-sequence continuation;
- short candle-sequence reversal;
- range expansion/compression;
- consolidation.

Prior levels are calculated strictly from previously available candles.

### `1f7b98d41d4844ababb50cd954d1316e0511f404`
**Test causal Price Action features**

Added tests for:
- required Price Action columns;
- strictly-prior level construction;
- future-change invariance;
- rejection classification;
- parameter validation.

### `6e72ff14ae80dea71e2b0e95ad7b264958e1dd78`
**Document Price Action source contract and causality**

Added `docs/PRICE_ACTION.md`.

### `7ad4680dd5bfd3c1b31d6b48aea5be6d7d7a8456`
**Integrate causal Price Action features**

Integrated `pa_*` features into the main Feature Engine.

### `16bd7c53f2b96b222536059ef4cc112f3370cda9`
**Test Price Action feature integration**

Extended Feature Engine integration coverage.

### `f632c111f7b275c11b562e1a3d53a5aba233a63f`
**Define causal Price Action contract**

Updated `docs/AICFA_TZ.md` with the Price Action source contract and limitations.

### Verification status

**Not yet server-verified.**

Required next step:
1. deploy current Price Action commits to FrostDeploy;
2. run the mandatory full pytest suite;
3. fix any real failures;
4. rerun until green;
5. only then mark Price Action accepted.

## Current implementation direction

With SMC, derivatives and the market-microstructure stack now substantially represented, the next conceptual layer after Price Action is **Wyckoff**, implemented as explicit causal events/states and kept descriptive until historical statistical validation.

# 13. Current checkpoint

Latest implementation:
`122c397e4d80b97e138a60695df00fed0e17a9df`

Latest verified FrostDeploy release:
`2026-09-29T08-53-55-8153eb4`

Latest full-suite result:
`133 passed, 2847 warnings in 34.70s`

**Current status:** Market Structure, Liquidity, Displacement, FVG, Order Blocks, Premium/Discount, Unified SMC, Multi-Timeframe, Volume/Volatility, Scenario Engine, Derivatives, Taker Flow / Order Flow, Order Book / Market Depth, level-by-level Order Book / Liquidity Walls, Absorption, and CVD are implemented and verified green.

**Current unverified stage:** Price Action.

**Next task:** deploy and verify Price Action. After Price Action is green, continue with the causal Wyckoff representation before moving toward historical statistical evaluation and the pre-ML dataset/model boundary.


## 2026-09-29 — Causal Wyckoff implementation

### `ca545ba24805acc088f83763cc7f9d06b0ca2a12`
**Add causal Wyckoff feature layer**

Added `src/aicfa/wyckoff.py` with deterministic, causal descriptive features for:
- trading-range boundaries and position;
- breakout / failed breakout;
- Spring candidate;
- Upthrust candidate;
- Sign of Strength / Sign of Weakness;
- range expansion/compression;
- optional volume context;
- deterministic Wyckoff state;
- explicit Accumulation/Distribution proxy fields.

The implementation is asset-agnostic and timeframe-agnostic. Missing optional
volume is represented by unavailable volume-derived features rather than
fabricated values. Order Book is not required.

### `d906773b6224c5c77550af14ef6d667dd1176f55`
**Test causal Wyckoff features**

Added coverage for:
- required Wyckoff features;
- strictly-prior range levels;
- Spring / Upthrust observable candidates;
- future-change invariance;
- operation without volume;
- parameter validation.

### `9be43129653fc6b7acbbbfa9d022c61fc0fd06d6`
**Document Wyckoff source contract and causality**

Added `docs/WYCKOFF.md` documenting source availability, causal semantics,
observable-event limitations and the non-signal nature of the layer.

### `2e6c97310b9643b174e212917f435b2a5237bf63`
**Integrate causal Wyckoff features**

Integrated `wyckoff_*` features into the main Feature Engine.

### `091d3e80252f3d649f996bd1094f62f8ada0272a`
**Test Wyckoff feature integration**

Extended Feature Engine integration coverage for core Wyckoff fields.

### `a9ef16b957e4c6361ac3b7535538a2958a00d406`
**Define causal Wyckoff contract**

Updated `docs/AICFA_TZ.md` with the Wyckoff source contract, asset/timeframe
generality, optional-volume semantics and the explicit rule that Order Book is
not required.

### Verification status

**Not yet server-verified.**

Required next step:
1. deploy current Wyckoff commits to FrostDeploy;
2. run the mandatory full pytest suite;
3. fix any real failures;
4. rerun until green;
5. only then mark Wyckoff accepted.

## 2026-09-29 — Current checkpoint after Wyckoff implementation

Latest implementation:
`a9ef16b957e4c6361ac3b7535538a2958a00d406`

Latest verified release remains:
`2026-09-29T08-58-11-9d4e39`

Latest verified full-suite result remains:
`138 passed, 3279 warnings in 33.75s`

**Current unverified stage:** causal Wyckoff representation.

**Next task:** server verification of the current Wyckoff implementation. If
green, continue with the next market-state representation layer; do not mark
Wyckoff accepted before actual FrostDeploy test output.


## 2026-09-29 — Architecture direction: autonomous 24/7 market scanner

### New project requirement

AICFA должна развиваться не только как AI, отвечающий на скриншоты/вопросы, но и как автономная 24/7 Market Scanner + Setup Event Engine.

Цель:
- централизованно анализировать заданный Universe of Assets;
- в дальнейшем поддерживать Top-N ликвидных активов, включая Top 100, и пользовательские watchlists;
- постоянно пересчитывать текущие market features/state;
- обнаруживать setup candidates независимо от пользовательского запроса;
- формировать события created / strengthened / invalidated / expired / outcome;
- отправлять релевантные уведомления подписанным пользователям;
- рассчитывать рынок один раз и раздавать результаты множеству пользователей, а не запускать отдельный scanner на каждого.

### Latency modes

- Scalping: требует low-latency streaming/WebSocket или сопоставимого realtime source. Polling раз в минуту может быть достаточен для некоторых минутных состояний, но не является полноценным источником для низколатентного scalp execution.
- Intraday: регулярное обновление текущего состояния.
- Swing: более редкие обновления на старших таймфреймах.
- Position: HTF monitoring.

### Important architectural boundary

Scanner/analysis и trade execution — отдельные подсистемы. Базовый AICFA должен работать без доступа к торговому аккаунту. В будущем допускается отдельный opt-in execution adapter через биржу/брокера/торговый терминал после paper trading, backtest, risk controls и отдельной валидации.

### Scaling

Market features и setup events вычисляются централизованно. Пользователи получают уже рассчитанные события через subscription/notification layer. Архитектура должна быть пригодна для большого количества подключённых пользователей без N-кратного повторения одного и того же анализа.

### Data provider

Market Data Engine должен использовать абстракцию provider. Бесплатные API допустимы для прототипа/периодического мониторинга, но не считаются гарантированным источником для 24/7 low-latency Top-100 коммерческой нагрузки до проверки rate limits, latency, websocket, historical access, commercial terms и reliability.

### Status

Зафиксировано как архитектурное направление/требование. Реализация scanner начинается после достаточной полноты market-state representation и не должна преждевременно заменять текущий causal feature-engineering этап.


## 2026-09-29 — Setup Detection Engine implementation

### New causal analytical layer

Implemented `src/aicfa/setup_detection.py` and integrated it into the main Feature Engine.

Initial setup families:
- liquidity reversal up/down;
- structure continuation up/down;
- breakout retest up/down;
- failed breakout up/down;
- Wyckoff Spring/Upthrust;
- expansion up/down.

The engine also exposes separate contextual fields for available FVG, Order Block, Premium/Discount, absorption, CVD, taker-flow and derivatives state. No additive confirmation score is used.

Opposite-direction candidates on the same timestamp are marked `setup_candidate_conflicted`; direction is set to neutral rather than forced.

The engine is causal and descriptive. It does not create future labels, probabilities, confidence scores or trade instructions.

### Commits

- `98777dd7bea6058c33cc7adb4c0189eed1d082bf` — setup engine
- `c1d4c96a0f80176b7420d7e03e85fe86172a80cb` — setup tests
- `20b9d7983f3e37da88de2392120ae7bbbf98db64` — setup documentation
- `1db0286c6b9738bdabbe755c037842997c93b989` — Feature Engine integration
- `bbb42d8a5523e2c53b60461875c97088b22a5bb3` — integration test
- `492380a23b741e83a1b70acfcc918f60d65e73ee` — positive flow context fix

### Verification status

**Not yet server-verified.**

Required next step: deploy the current main branch to FrostDeploy and run the mandatory full pytest suite. Do not mark Setup Detection green before actual server output.

### Next after verification

If green, extend setup coverage with additional causal market-state combinations and then build the Setup Event lifecycle (created / updated / invalidated / expired / outcome) before the live 24/7 scanner. Historical future outcome labels remain a separate pipeline.


## 2026-09-29 — Canonical Market State implementation

### New causal representation layer

Implemented `src/aicfa/market_state.py` and integrated it into the main Feature Engine after Scenario and Setup Detection.

Purpose:
- convert already-built features/scenarios/setup candidates into a stable machine-readable current-state representation;
- preserve structure, scenario, setup, SMC readiness, premium/discount, volume/volatility and Wyckoff context;
- explicitly expose optional CVD, taker-flow, absorption and order-book source availability;
- provide deterministic `market_state_changed` input for the future Setup Event Engine.

The layer does not create scores, probabilities, rankings, trade signals or future outcome labels. Conflicted setup candidates remain neutral. Missing optional sources remain unavailable and are never synthesized.

Commits:
- `9ffaf3781f08fb82e8c9ac9ecb18fdf26dffa506` — canonical market-state implementation
- `4d7b3ac8085b45bf678f61180e063b8a776c7ea1` — market-state tests
- `9a54368d54258539c2be8c2f58d0e22bcfc89a24` — Feature Engine integration
- `61a18285651159e1a48f8e403811f2f4e6e70` — Feature Engine integration coverage
- `953b2ee8d646ec4b16697e3bf6fdd2ebe3f2ecbc` — market-state documentation
- `19d8cb3a021b4f62dc3ddf1cc008072294085d54` — TZ update

### Verification status

**Not yet server-verified.**

Required next step:
1. deploy current main to FrostDeploy;
2. run the mandatory full pytest suite;
3. fix any actual failures;
4. rerun until green;
5. only then mark Market State accepted.

### Next after verification

Implement the causal Setup Event Engine lifecycle: created / strengthened / invalidated / expired / outcome, without future labels in the live state. This will become the event boundary used later by the autonomous 24/7 Market Scanner.


## 2026-09-29 — Setup Event Engine implementation

Implemented the causal Setup Event Engine and integrated it after Canonical Market State.

Pipeline:
`Features → Scenario/Setup Detection → Canonical Market State → Setup Event Engine → 24/7 Scanner`

Implemented lifecycle fields:
- created;
- strengthened/updated;
- invalidated;
- expired;
- stable setup identity from family + resolved direction;
- explicit neutral handling for conflicted candidates;
- empty live `setup_event_outcome`, with historical outcomes reserved for a separate label/validation pipeline.

Commits:
- `9fcbe8de1eabc279fb268ace480fffe3a21ef55a` — setup event lifecycle
- `2f312aef5e303b2219feba1fe298ebf329a95076` — setup event tests
- `6138493c20819d38847181c955892fe8ee3f422d` — Feature Engine integration
- `4e16c4fea4ca887ed51f318274ecef1da9faeacb` — setup event documentation
- `c2bb4411d7a136e79228d6759dc08246442a9281` — integration coverage
- `e8bedcd63f2c311ca8f32ba622498aa2e8b8acd5` — fix setup event lifecycle precedence and identity
- `c9c72b339ebe21f75b5cbff2e95e686be5a0b306` — strengthen setup event lifecycle regression tests
- `d9df6e6708c839dba577f27098c50f37813b623c` — fix setup creation on replacement identity
- `43b06bf5d8acff21dc6eaf012c083624204a02cd` — make setup creation transition explicit
- `ba03388ab9945536b25a27ce75db0efebbaac6c2` — fix setup event replacement test fixture

### Final FrostDeploy verification — 2026-09-29

Deployed release:
`2026-09-29T11-33-43-ba03388`

Full suite:
```
163 passed, 4863 warnings in 38.29s
```

The Setup Event Engine is now **accepted and green**.

Verified coverage includes:
- creation of a new setup identity;
- strengthening of an unchanged active identity when descriptive state changes;
- direct replacement of an active identity producing `created=1` and `invalidated=1`;
- expiration when an active identity disappears without replacement;
- creation after expiration without falsely marking the new setup as an invalidation;
- neutral handling of conflicted setups;
- causal future-change invariance;
- no live outcome labels.

Known non-blocking warning:
- pytest cache cannot be created inside immutable FrostDeploy release directories due to permissions.

### Current next task

Proceed to the **provider-agnostic Live Market Data / Scanner foundation**:
- define source contracts for live/incremental market data;
- define asset/timeframe universe and canonical current-state updates;
- implement centralized scan-loop architecture;
- preserve causal semantics and provider abstraction;
- do not yet assume a free provider is sufficient for 24/7 low-latency Top-100;
- verify provider rate limits, latency, WebSocket availability, historical access, commercial terms and reliability before locking the production provider.


## 2026-09-29 — Provider-agnostic Live Market Data / Scanner foundation

### Commits

- `0a64f467acfe47bdd5eb5617eaf2a9813ab6e9e6` — add provider-agnostic live market data contract
- `7531f1b5d4c8c7f7d665d4eab26e49ba062403b9` — add centralized live market scanner foundation
- `438a2678ab02069fa1700ebc6fade19d7c677535` — test live market data contracts
- `a7c990ca1e5ecbf86bdaa3b71855dae84b7a0de8` — test centralized market scanner
- `d27e3350a3330f1217ab268720d884dcf78743ae` — document live market data scanner foundation

### Implemented

Added `src/aicfa/market_data.py`:
- explicit canonical timeframes `1m/5m/15m/1h/4h/1d/1w/1M`;
- `MarketKey` containing exchange, symbol, market type and timeframe;
- provider-agnostic `MarketDataProvider` contract;
- OHLCV validation;
- deterministic deduplication/sorting;
- idempotent incremental merge;
- completed-candle filtering based on candle-open timestamp plus interval duration;
- incremental cursor calculation;
- explicit deferral of variable-calendar `1M` completion to provider-specific semantics.

Added `src/aicfa/market_scanner.py`:
- centralized scanner over a configured asset/timeframe universe;
- one provider fetch per market key per scan cycle;
- incremental `since_ms`;
- completed-candle-only Feature Engine input;
- causal feature rebuild from retained local history;
- latest current feature state returned as `ScanResult`;
- no per-user scanning or notification logic.

Added:
- `tests/test_market_data.py`;
- `tests/test_market_scanner.py`;
- `docs/LIVE_MARKET_DATA.md`.

### Verification status

**Not yet server-verified.**

The new tests cover:
- OHLCV validation;
- duplicate handling;
- completion filtering;
- incremental cursor;
- provider-independent scanner calls;
- centralized one-pass-per-market-key behavior;
- incremental second scan;
- duplicate universe rejection.

The full mandatory FrostDeploy suite must be run after deployment before this stage can be marked green.

### Current limitations

- no concrete exchange/provider adapter is locked;
- no WebSocket transport;
- no retry/backoff or rate-limit scheduler;
- no persistent live raw-data store;
- no Top-100 discovery;
- no subscriptions/notifications;
- derivatives/order-book live transport is not connected;
- `1M` completion remains provider-specific.

### Next task

Before locking a production provider, verify its actual rate limits, latency,
WebSocket support, historical access, reliability and commercial terms.
Then implement the first concrete BTC/USDT provider adapter against the
provider-agnostic contract and verify the scanner on FrostDeploy.


## 2026-09-29 — Live Market Data / Scanner verification attempt and test fixes

### FrostDeploy verification attempt

Current deployed test run:
```
2 failed, 172 passed, 4864 warnings in 42.96s
```

Failures:
- `tests/test_market_data.py::test_merge_is_idempotent_and_keeps_newest_duplicate` — the test fixture changed `close` above the fixture's valid `high`, so production OHLCV validation correctly rejected the row.
- `tests/test_market_scanner.py::test_scanner_processes_each_market_key_once_and_only_completed_data` — the expected latest derived value was incorrect. The completed latest candle has close `101.5`, so the test feature value is `203.0`.

Production Live Market Data / Scanner code was not changed in response to these failures.

### Fix commits

- `92a7a9f5e434b6408b1e6b1cbc57867b750b4861` — fix live market data OHLCV test fixture
  - changed the duplicate candle close to a valid value below its high;
  - production validation unchanged.
- `eab84fa73cf9e57f336606482622eb9703b5de94` — fix live scanner latest-state test expectation
  - corrected expected derived value from `201.0` to `203.0`;
  - scanner implementation unchanged.

### Verification status

**Still not server-verified green.**

Both fixes are test-only. FrostDeploy will automatically deploy these commits from `main`.

### Required next step

Run the mandatory full pytest suite against the new automatically deployed release. Do not mark Live Market Data / Scanner foundation green until the new server output is clean.



## 2026-09-29 — Live Market Data / Scanner second verification attempt

FrostDeploy release `2026-09-29T11-52-19-70af0aa` produced:
```
1 failed, 173 passed, 4864 warnings in 41.95s
```

The remaining failure was again test-fixture-only: `test_merge_is_idempotent_and_keeps_newest_duplicate` set `close=101.75` while that fixture row had `high=101.0`, so the production OHLCV validator correctly rejected the invalid candle. No production scanner/data code was changed.

Fix commit:
- `70667b74a2746e960b23a1362d4a92331ef380ad` — `Fix duplicate OHLCV fixture bounds`; changed the test duplicate close to `100.75`, preserving the intended duplicate-replacement assertion while keeping the candle valid.

Status remains **not green** until the next FrostDeploy full-suite run passes.

## 2026-09-29 — Live Market Data / Scanner final verification

### Final test-fixture fix

- `70667b74a2746e960b23a1362d4a92331ef380ad` — `Fix duplicate OHLCV fixture bounds`
  - changed the duplicate test candle close from `101.75` to `100.75` so it remains valid against `high=101.0`;
  - production market-data validation and scanner logic were unchanged.
- `b5a3bc400261a09948eaecad83034ef1846436a3` — `Record remaining live scanner test fixture fix`
  - recorded this final fixture correction and the pending verification state in the project control log.

### Final FrostDeploy verification — 2026-09-29

Deployed release:
`2026-09-29T11-56-14-b5a3bc4`

Mandatory full suite:
```
174 passed, 4863 warnings in 42.23s
```

The provider-agnostic **Live Market Data / Scanner foundation is now accepted and green**.

Verified coverage includes:
- OHLCV validation and causal completed-candle handling;
- deterministic deduplication and idempotent incremental merge;
- incremental cursor calculation;
- centralized one-pass-per-market-key scanning;
- incremental second scans;
- completed-candle-only Feature Engine input;
- retained-history feature rebuild and current-state output;
- duplicate-universe rejection.

Known non-blocking warning:
- pytest cache cannot be created inside immutable FrostDeploy release directories due to permissions.

### Current limitations

- no concrete exchange/provider adapter is locked;
- no WebSocket transport;
- no retry/backoff or rate-limit scheduler;
- no persistent live raw-data store;
- no Top-100 discovery;
- no subscriptions/notifications;
- derivatives/order-book live transport is not connected;
- `1M` completion remains provider-specific.

### Next task

Verify current candidate market-data providers before implementation. Check actual:
- REST/WebSocket availability;
- rate limits and connection limits;
- BTC/USDT historical access;
- realtime latency and candle semantics;
- reliability and reconnect behavior;
- commercial/usage terms;
- whether the provider can support the intended centralized 24/7 scanner.

Only after that verification should the first concrete BTC/USDT provider adapter be implemented against the existing provider-agnostic contract.

    
## 2026-09-29 — First concrete market-data provider: Binance REST OHLCV

### Provider verification research

Current official Binance documentation confirms:
- public market-data-only REST endpoints are available without authentication;
- Spot klines are available through `data-api.binance.vision`;
- public market-data WebSocket infrastructure is available;
- Binance publishes downloadable public historical market data;
- futures klines are available through the public futures REST API.

These capabilities satisfy the immediate prototype requirement for a concrete BTC/USDT OHLCV source. They do **not** by themselves lock Binance as the permanent production provider.

### Commits

- `de77e3b3e0b5c74f09b22975ab41161004316df0` — Add Binance public market data adapter
- `f29c2a37e0970522ebfa6e06a3b28111d7e4cd65` — Test Binance market data adapter
- `136d15081cc11922d68d3e639980904d12875123` — Document Binance market data adapter

### Implemented

Added `src/aicfa/binance_market_data.py`:
- public Spot OHLCV endpoint;
- public USDⓈ-M futures OHLCV endpoint;
- BTC/USDT symbol normalization;
- canonical timeframe mapping;
- incremental `startTime` support;
- timeout configuration;
- provider-response validation;
- canonical six-column OHLCV output;
- explicit deferral of `1M` scanner semantics.

Added `tests/test_binance_market_data.py` covering:
- Spot URL/parameter mapping;
- futures endpoint selection;
- limit validation;
- explicit `1M` deferral.

Added `docs/BINANCE_MARKET_DATA.md`.

### Verification status

**Implementation deployed but not yet server-verified.**

Required next step:
1. let FrostDeploy deploy the current main branch;
2. run the mandatory full pytest suite;
3. fix any actual failures;
4. rerun until green;
5. only then mark the concrete Binance adapter accepted.

### Important limitation

Binance is currently the **first concrete prototype provider**, not yet the permanent production-provider decision. Before locking it for the 24/7 Top-100 system, verify rate limits, WebSocket behavior, reconnect handling, latency, historical coverage, network/regional accessibility, commercial/usage terms and operational reliability.

### Next task

Server-verify the Binance adapter. If green, perform a real BTC/USDT provider smoke test and then extend the transport toward WebSocket/incremental live operation without changing the causal Feature Engine contract.

## 2026-09-29 — Data Reliability / Freshness architecture decision

### Architectural decision

External market-data providers are **replaceable inputs, not dependencies of AICFA intelligence**.

Binance is currently only the first concrete BTC/USDT prototype adapter. AICFA analysis must not stop merely because one REST API or WebSocket is unavailable.

Target flow:

```
External Providers
  ├─ REST/API
  ├─ WebSocket
  ├─ future Provider B/C
  └─ historical/local sources
          ↓
Market Data Layer
          ↓
Local Latest Confirmed Market State
          ↓
AICFA Analysis Core
          ↓
Features → Canonical State → Setup Events
```

### Required Data Reliability / Freshness layer

Before treating live transport as production-ready, implement a dedicated reliability boundary that:

- stores the latest confirmed market state/data locally;
- tracks `last_update`, data age and explicit freshness status;
- distinguishes at least `FRESH`, `STALE`, and unavailable/no-confirmed-state conditions;
- continues analysis from the latest confirmed local state when an external provider fails;
- never fabricates candles, trades, order-book states or other market observations;
- never presents stale data as current;
- exposes freshness/staleness explicitly to downstream Setup/Decision logic;
- allows later provider failover without changing the analytical core.

When data becomes stale, AICFA may continue descriptive analysis of the last confirmed state, but downstream decision logic must be able to enter WAIT / no-action behavior or otherwise account for stale data. A stale state is not a new market observation.

### Knowledge Base vs Historical Experience

Do **not** continuously dump live candles into the Knowledge Base.

Keep these stores conceptually separate:

**Knowledge Base**
- definitions and rules;
- SMC / Price Action / Wyckoff concepts;
- market-regime concepts;
- methodology;
- source/version/relationship metadata.

**Historical / Experience / Outcome data**
- historical market states;
- detected setups;
- setup lifecycle;
- what happened after each setup;
- future outcome labels generated only in a separate causal/historical validation pipeline;
- regime/context and statistical results.

Live data therefore feeds the current market state and later produces historical experience/outcomes. It does not need to mutate the conceptual Knowledge Base on every update.

### Updated forward roadmap

1. Server-verify Binance prototype.
2. Real BTC/USDT smoke test.
3. Implement Data Reliability / Freshness + Local Latest Confirmed State.
4. Add REST recovery and WebSocket/live incremental transport behind the provider-agnostic contract.
5. Connect live transport to the centralized scanner and current Setup Event Engine.
6. Persist historical market situations and completed setup outcomes in a separate Experience/Outcome store.
7. Build structured Knowledge Base separately from market-event history.
8. Historical similarity / Active Information Gathering.
9. Dataset construction and first ML baseline.
10. PyTorch models and chronological evaluation.
11. Backtest with fees/slippage/funding.
12. Paper trading.
13. Production API/platform and later optional execution adapter.

Top-100 expansion remains postponed until BTC/USDT core and the live reliability architecture are stable.

### Control rule for future chat continuity

`PROJECT_PLAN.md` is the persistent control memory for this project. Before every new implementation stage, read it first. After every meaningful commit, append the SHA, exact change, tests/verification, limitations and next step. Never mark a stage green without actual current FrostDeploy/server verification.

Current state at this checkpoint:
- provider-agnostic Live Market Data / Scanner foundation: **GREEN**;
- Binance REST OHLCV prototype: **implemented, server verification pending**;
- Data Reliability / Freshness layer: **architecture fixed, implementation pending**;
- Knowledge Base: **planned, intentionally separate from live market history/experience**.

## 2026-09-29 — Data Reliability / Freshness layer implementation

### Commits
- `656ddb081f86c3d320caf3b0ad09e4442901f1d6` — Add data reliability and freshness layer
- `974cbf29f3a1ff15d79e2d55306ebeafcc6df360` — Add data reliability tests
- `277bc0a77943b556ad4e7b796537c5601452d76a` — Document data reliability and freshness

### Implemented
Added `src/aicfa/data_reliability.py` with:
- `DataFreshness.FRESH / STALE / UNAVAILABLE`;
- `ConfirmedMarketState` for the latest locally confirmed observation;
- `FreshnessSnapshot` with `last_update_ms`, `data_age_ms` and configured freshness window;
- `LocalMarketStateStore` that retains confirmed state independently of provider health;
- explicit non-fabrication semantics.

A provider outage therefore does not erase the last confirmed market state. Time passing changes freshness metadata only; it does not create new market observations.

### Tests
Added coverage for:
- retaining last confirmed state;
- stale transition without fabricated data;
- unavailable state;
- invalid configuration/time rejection.

### Verification status
**Implementation deployed to FrostDeploy but not yet server-verified.**

Mandatory next step:
```
sudo -u fd-aicfa bash -lc '
cd "$(readlink -f /srv/frostdeploy/aicfa/current)"
PYTHONPATH=src .venv/bin/python -m pytest -q
'
```

Do not mark this layer green until current deployed server output passes.

### Current architectural boundary
This layer is intentionally separate from provider transport. Binance REST, future WebSocket, recovery REST calls and future provider failover can all feed the same local confirmed-state boundary without changing the analytical core.

### Next task
1. Server-verify the Binance/reliability changes.
2. Perform real BTC/USDT REST smoke test.
3. Extend provider transport with retry/reconnect semantics and WebSocket behind the existing provider-agnostic contract.
4. Connect fresh/stale status to centralized scanner and Setup Event lifecycle.

## 2026-09-29 — Real Binance BTC/USDT REST smoke test

### Server verification

FrostDeploy release:
`2026-09-29T12-43-03-a3c008f`

Mandatory full suite:
```
184 passed, 4863 warnings in 40.70s
```

Real server-side Binance REST smoke test was then executed as `fd-aicfa` against the deployed release.

Verified successfully:
- Binance Spot BTC/USDT `1m` endpoint returned 5 real OHLCV candles;
- Binance USDⓈ-M Futures BTC/USDT `1m` endpoint returned 5 real OHLCV candles;
- both responses contained valid timestamp/open/high/low/close/volume data;
- the latest returned candle timestamp was identical across Spot/Futures;
- the adapter successfully normalized the responses into AICFA's canonical OHLCV DataFrame.

Observed latest closes during the smoke test:
- Spot: `84306.01`
- Futures: `84252.3`

These values are only the smoke-test observation and are not stored as a permanent market fact.

### Status

**Binance REST BTC/USDT prototype: GREEN for current server-side connectivity and response parsing.**

This does not yet mean Binance is permanently selected as AICFA's production provider.

### Next task

Implement provider-agnostic live transport reliability:
1. bounded REST retry/recovery behavior;
2. explicit transport failure classification;
3. WebSocket incremental market-data transport;
4. reconnect/resubscribe behavior;
5. feed confirmed observations into the existing LocalMarketStateStore;
6. keep stale-state semantics and the analytical core independent of provider availability.

No live transport implementation should fabricate missing market observations.

## 2026-09-29 — Provider-independent screenshot analysis requirement

AICFA's analytical core must remain usable when live market-data providers are unavailable.

### Required behavior

- Live provider failure means no new live observations are accepted.
- AICFA must not fabricate price, volume, structure, liquidity, or other market data.
- The latest confirmed local market state may remain available as `STALE` for descriptive/reference analysis.
- AICFA must not produce a current live setup from stale/unavailable provider data.
- For a current user request, screenshot/chart analysis remains independently available because it operates on user-supplied visual evidence plus AICFA's own analytical knowledge.
- Screenshot analysis must not be represented as live provider data unless the screenshot itself contains the relevant evidence.
- Live data transport and screenshot analysis are separate input paths into the same analytical knowledge/rule core.

### Next implementation stage

Proceed with **REST transport recovery and failure handling** behind the provider-agnostic market-data contract:
1. classify transient vs non-recoverable provider errors;
2. bounded retry/backoff;
3. preserve last confirmed state during transport failure;
4. expose failure/freshness state without fabricating observations;
5. add tests for recovery, failure, and no-data behavior.

After REST recovery is green, implement WebSocket incremental transport with reconnect/resubscribe.

## 2026-09-29 — Binance REST recovery / failure handling implementation

### Commits
- `01f0cd5392460f920d80a4ac5a51a5641a5f0ac3` — Add Binance REST recovery and failure classification
- `e5fd2f6b9eb4708910371cf4b38a37b63eb6ce73` — Test Binance REST recovery and failure handling
- `1be82d3b2e2a14b31a83bcdbbcd52468698f9824` — Document Binance REST recovery behavior

### Implemented
- bounded retry budget for Binance REST requests;
- exponential backoff with injectable sleeper for deterministic tests;
- transient classification for network/timeout errors, HTTP 429 and HTTP 5xx;
- non-recoverable classification for other HTTP 4xx errors;
- explicit `BinanceTransportError` carrying retryability state;
- no fabricated OHLCV data after exhausted transport failures.

### Verification status
**Implementation deployed to GitHub main; current FrostDeploy/server verification is pending.**

The new tests cover:
- transient network retry and backoff;
- 429 and 5xx recovery;
- non-recoverable 4xx behavior;
- exhausted transient failures;
- invalid recovery configuration.

### Important boundary
REST recovery does not decide whether market state is stale. `LocalMarketStateStore` remains responsible for retaining the last confirmed observation and exposing `FRESH` / `STALE` / `UNAVAILABLE`.

### Next step
Run the full FrostDeploy pytest suite. If green, perform a real failure/recovery smoke test where practical. Then proceed to provider-agnostic WebSocket incremental transport with reconnect/resubscribe, while feeding confirmed observations into the existing local-state boundary.



## 2026-09-29 — Binance REST recovery server verification

### FrostDeploy verification

Current deployed release:
`2026-09-29T12-55-13-788da16`

Full suite:
```
190 passed, 4863 warnings in 40.49s
```

The warnings are non-blocking in the current FrostDeploy environment, including pytest cache permission warnings caused by immutable release directories.

### Status

**Binance REST recovery / failure handling: GREEN.**

The deployed implementation and its tests are verified on the current server.

### Next implementation stage

Proceed to provider-agnostic WebSocket incremental transport with reconnect/resubscribe, then connect it to the centralized scanner and freshness/setup lifecycle.

## 2026-09-29 — Binance incremental WebSocket transport

### Commits
- `ebd1c6dc8ef79a68c37594da3797edd739525d38` — Add Binance incremental WebSocket transport
- `cd05bba3d6aa8660065470494dfb4a827bda0c89` — Test Binance incremental WebSocket transport
- `9496dac57fe0c3f4251d0260d372010a1e346f26` — Validate Binance WebSocket stream identity
- `8a85a2a414885eae9ff0f67e1141b88087c2c2d9` — Add runtime Binance WebSocket connector
- `b169a22358d7a2c35a45b1c0723e68182de83fc4` — Add WebSocket client dependency
- `965af52f732cd5172256174b60b492a93fccef7a` — Document Binance incremental WebSocket transport

### Implemented

Added `src/aicfa/websocket_market_data.py` with:
- provider-agnostic WebSocket connection/connector contracts;
- Binance Spot and USDⓈ-M Futures kline endpoints;
- Binance `SUBSCRIBE` messages;
- closed-candle-only confirmation semantics;
- symbol/timeframe stream validation;
- malformed/incomplete message rejection;
- bounded exponential reconnect;
- automatic resubscription after reconnect;
- optional direct updates into `LocalMarketStateStore`;
- explicit reconnect exhaustion without fabricated observations;
- runtime `websocket-client` connector.

Added tests for parsing, closed/open candle behavior, malformed messages, subscription, reconnect/resubscribe, local-state updates, and exhausted reconnect budget.

### Verification status

**WebSocket implementation deployed to GitHub main; current FrostDeploy/server verification is PENDING.**

The implementation is not marked GREEN until the current release passes the full suite and a real server-side Binance Spot/Futures WebSocket smoke test confirms connection, closed BTC/USDT candle reception, reconnect behavior, and local-state update.

### Boundary

This stage transports kline observations only. Funding, open interest, liquidations, order book and other derivatives/microstructure streams remain separate transport work. Freshness remains owned by `LocalMarketStateStore`; the WebSocket layer does not create observations when the provider is unavailable.

### Next step

1. Run full FrostDeploy pytest suite on the new release.
2. Run real BTC/USDT Spot and Futures WebSocket smoke test.
3. If green, connect live transport to the centralized scanner and Setup Event lifecycle.
4. Then begin persistent historical situations / Experience-Outcome storage.
5. Screenshot/Vision remains a planned first-class input path sharing the analytical core; it is not dependent on live provider availability.


## 2026-09-29 — WebSocket malformed-payload verification fix

### Server verification attempt

Current FrostDeploy run produced:
```
1 failed, 194 passed, 4864 warnings in 40.59s
```

Failure:
```
tests/test_websocket_market_data.py::test_parse_binance_websocket_rejects_invalid_payload
Failed: DID NOT RAISE WebSocketTransportError
```

The failure exposed a validation-order bug in the WebSocket parser: an incomplete kline payload such as `{"k": {"x": true}}` was treated as a non-matching stream before its required kline identity was validated. That allowed malformed input to be silently ignored instead of rejected.

### Fix

- `de46379d7ce6155cb902b2b938228a7ecfe17841` — **Fix WebSocket malformed kline validation**
- malformed kline payloads now require the kline identity fields (`s`, `i`, `x`) before stream-mismatch filtering;
- required candle fields now include the Binance close/event timestamp `T`;
- invalid top-level payloads are explicitly rejected;
- removed an accidental duplicate `default_websocket_connector` definition.

Production transport behavior remains forward-only; no rollback.

### Status

**WebSocket stage remains PENDING verification.**

Next:
1. wait for the new FrostDeploy release;
2. rerun the full pytest suite;
3. if green, run the real Binance Spot/Futures WebSocket smoke test;
4. only then mark WebSocket transport GREEN.


## 2026-09-29 — WebSocket read-timeout handling fix

### Real smoke finding

The real Binance smoke test successfully received a closed BTC/USDT Spot 1m candle, but the combined Spot/Futures run then failed on Futures with:

    websocket._exceptions.WebSocketTimeoutException: Connection timed out

The failure occurred because the client read timeout (timeout_seconds=15) was shorter than the possible wait until the next closed 1m candle. Binance can continue sending/opening the stream while AICFA intentionally ignores incomplete candles. A socket read timeout therefore does not by itself prove that the WebSocket connection is dead.

### Forward-only fix

Commits:
- bf8122eee4922d44cfbcc58bf14d0d5e72bbee67 — Handle WebSocket read timeouts without reconnecting
- 70ffc81fb8b0b3ffdb5f402a1384fc8a3276685a — Handle Binance WebSocket read timeout exception
- b99f5c353b678513c767da36e741196e88dce1ce — Test WebSocket read timeout handling
- 49ba7b5f21ca20de8e5464728d24e60fbb211383 — Document WebSocket read timeout behavior

Behavior:
- TimeoutError / WebSocketTimeoutException during recv() is treated as a read wait;
- the existing connection is retained;
- the transport continues waiting for the next closed candle;
- actual disconnect/network errors still use the bounded reconnect/resubscribe path;
- no market observation is fabricated.

### Verification status

WebSocket stage remains PENDING server verification.

The prior full suite was green at 195 passed, 4863 warnings in 33.94s, but that was before this fix. The fix must be deployed and the full suite rerun.

### Next step

1. wait for the new FrostDeploy release;
2. rerun the mandatory full pytest suite;
3. rerun real Binance Spot + Futures BTC/USDT WebSocket smoke;
4. if both pass, record WebSocket transport as GREEN;
5. then connect live WebSocket observations to the centralized scanner and Setup Event lifecycle.


## 2026-09-29 — WebSocket bounded idle-timeout fix

### Real smoke finding

After the read-timeout fix, Spot received a real closed BTC/USDT 1m candle, but the combined Spot/Futures smoke remained waiting indefinitely on Futures. Treating every read timeout as harmless removed the previous immediate failure but introduced an unbounded wait if the stream stops delivering messages.

### Forward-only fix

Commits:
- `a613810720c32c2af7a1a51a39dd35ba3d5ffbaf` — Bound continuous Binance WebSocket read timeouts
- `dd09e7c966febc85869857b03dd2b48c2fcb6a65` — Test bounded Binance WebSocket idle timeout

Behavior:
- normal read timeouts remain non-fatal;
- a healthy 1m stream may wait across the 15-second socket read timeout;
- continuous timeout without any message is now bounded by an idle watchdog;
- default idle budget is two fixed candle periods (for example, 120 seconds for 1m);
- after the idle budget, the connection enters the existing reconnect path;
- the idle timeout is injectable in tests;
- no market observation is fabricated.

### Verification status

**PENDING server verification.**

Next:
1. wait for the new FrostDeploy release;
2. run the full pytest suite;
3. rerun real Binance Spot + Futures BTC/USDT WebSocket smoke;
4. if both pass, mark WebSocket transport GREEN;
5. then connect live WebSocket observations to the centralized scanner and Setup Event lifecycle.

## 2026-09-29 — WebSocket idle-watchdog enforcement fix

### Commit
- `479da79575656cf6ea119750572835a53cb62ab1` — **Fix WebSocket idle watchdog enforcement**

### Change
The bounded-idle watchdog now actually enforces its deadline when repeated `TimeoutError` / `WebSocketTimeoutException` reads occur. Previously the timeout branch could continue indefinitely, causing `test_transport_bounds_continuous_read_timeouts` to hang despite an idle deadline being configured.

A successfully received WebSocket message resets the idle deadline. Continuous timeouts beyond the idle budget raise a connection failure and enter the existing bounded reconnect path. No market observations are fabricated.

### Verification status
**PENDING server verification.** The previous server run reached this test and remained at 95% for more than 17 minutes.

### Next step
Wait for FrostDeploy deployment, run the mandatory full pytest suite, then rerun the real Binance Spot + Futures BTC/USDT WebSocket smoke test if the suite passes.


## 2026-09-29 — WebSocket confirmed-candle wait bound

### Problem found in real smoke
The Spot side produced a real closed BTC/USDT 1m candle, while the Futures side could remain waiting after the user stopped the combined smoke run. The transport-level idle watchdog is intentionally reset by healthy open-kline messages, so it proves socket activity but does not guarantee that a confirmed closed candle will arrive within the expected candle interval.

### Forward-only fix
Commits:
- `e33826684741e36251fe9192a166190aeff1ce82` — Bound WebSocket wait for confirmed candles
- `9d66b8e82bbd9abb765de47a3ba951a993812873` — Test bounded wait for confirmed WebSocket candle
- `728d1be53dbd5ad1ffb19d7cff42e3fdf717f280` — Document bounded confirmed-candle wait

Added a separate confirmed-observation deadline. Open kline updates still reset the transport idle watchdog, but they do not reset the confirmed-candle deadline. The default confirmed-candle budget is two fixed candle periods; it is injectable for tests and controlled smoke runs. If the budget expires without a closed candle, the existing bounded reconnect path is entered. No market observation is fabricated.

### Verification status
**PENDING server verification.** The code/test/documentation commits are on GitHub main and must be verified on the next FrostDeploy release with the full pytest suite.

### Next step
Run the full FrostDeploy pytest suite. If green, rerun the real Binance Spot + Futures BTC/USDT WebSocket smoke with an explicit confirmed-candle timeout appropriate for 1m. Do not mark WebSocket GREEN until both sides complete successfully.


## 2026-09-29 — WebSocket watchdog test clock-sampling fix

### Server verification finding

The first server verification of the confirmed-candle watchdog release produced:
```
2 failed, 196 passed, 4864 warnings in 44.26s
```

Failures:
- `tests/test_websocket_market_data.py::test_transport_bounds_continuous_read_timeouts`
- `tests/test_websocket_market_data.py::test_transport_bounds_wait_for_confirmed_candle`

Both failed with `RuntimeError: generator raised StopIteration`.

### Root cause

The tests use deterministic iterator-backed clocks. The transport sampled the injected clock multiple times during one receive cycle: once for deadline initialization, again for idle-deadline reset on a received open-kline message, and again for timeout evaluation. The test clock was intentionally sized for the required state transitions, so the extra sample exhausted the iterator and PEP 479 surfaced it as `RuntimeError: generator raised StopIteration`.

### Forward-only fix

Commit:
- `18aa80d21c2b4f24a4d5a75143de511f6e546864` — **Fix WebSocket watchdog clock sampling**

The transport now:
- samples the clock once when a connection starts and uses that timestamp for both watchdog deadlines;
- samples once when a stream message is received before resetting the idle watchdog;
- keeps timeout evaluation based on its existing single time sample;
- preserves the actual watchdog semantics; this is a deterministic-test/clock-sampling correction, not a relaxation of timeout bounds.

### Verification status

**PENDING server verification.**

Next:
1. wait for FrostDeploy deployment;
2. rerun the full pytest suite;
3. if green, run real Binance Spot + Futures BTC/USDT WebSocket smoke with explicit confirmed-candle timeout;
4. only then mark WebSocket transport GREEN.


## 2026-09-29 — Product direction reset: knowledge-first, user-driven analysis

This section **supersedes earlier roadmap language that treated Scalping as a dedicated product mode or autonomous setup scanning as a planned always-on function**.

### Product decision

AICFA is not an always-on signal bot.

The product behavior is:

**User request → gather the best available evidence → AICFA analyzes it with its own knowledge → return the requested setup/analysis.**

Example:
- User: "Find me an entry in any asset urgently."
- If live network data is available, AICFA can use the connected market-data sources to inspect relevant assets and identify a current setup.
- If live network data is unavailable, AICFA asks for screenshots of the relevant charts/timeframes and analyzes those screenshots using its own market knowledge and causal rules.
- The answer must clearly distinguish live network evidence from user-supplied screenshot evidence.

### No autonomous scanner

AICFA will not continuously scan Top-50/Top-100 and create setup events merely because market data is connected.

Therefore:
- no continuous per-minute setup search across the whole universe;
- no setup-alert engine whose primary purpose is generating autonomous signals;
- no separate realtime analysis workload per user;
- no requirement to keep every asset at maximum microstructure resolution continuously.

A live connection exists to provide **current evidence when AICFA needs it**, not because AICFA must constantly manufacture setups.

### Live connections: purpose

Live market connections remain important, but their purpose is narrower and more useful:

- obtain current market evidence on demand;
- inspect an asset the user requests;
- inspect a set of assets when the user asks AICFA to find an opportunity across assets;
- support current-data analysis when screenshots are unavailable;
- optionally maintain minimal state/cache needed for reliable current analysis.

The project does **not** assume that storing a huge market history is itself the intelligence of AICFA. Historical data can be useful for validation and learning, but the durable intelligence is the **Knowledge Base + analytical rules + verified relationships + later specialized models**.

### Knowledge-first principle

The user explicitly prioritizes:

**AICFA needs knowledge first.**

The Knowledge Base therefore becomes a first-class product foundation:
- market concepts and definitions;
- causal relationships;
- SMC and market-structure semantics;
- liquidity behavior;
- price action;
- volume/volatility;
- derivatives;
- order flow and microstructure;
- scenario interpretation;
- risk/invalidation concepts;
- evidence/provenance for important rules;
- limitations and counterexamples.

Historical market data is supporting evidence, not a substitute for knowledge.

Screenshot analysis is also not a separate intelligence. It is an evidence-ingestion path into the same AICFA analytical brain.

### Consequence for current live-data work

Existing Binance REST/WebSocket work is retained as infrastructure because current user requests may require live evidence.

However, the next live-data architecture must optimize for:
- on-demand access;
- bounded resource usage;
- provider recovery;
- current-state correctness;
- explicit freshness;
- no fabricated observations.

It must **not** be extended merely to support an autonomous setup scanner.

### Consequence for Setup Event Engine

The existing Setup Event Engine remains part of the analytical machinery and can be used when AICFA is evaluating a specific user request.

It is **not** a requirement to generate autonomous setup events continuously for every asset.

### Current product flow

```
USER REQUEST
    ↓
What evidence is available?
    ├── LIVE NETWORK DATA
    │      ↓
    │   current market state
    │      ↓
    │   AICFA analytical brain
    │
    └── NO LIVE DATA
           ↓
       ask for chart screenshots/timeframes
           ↓
       visual evidence → structured evidence
           ↓
       AICFA analytical brain

                 ↓
          setup / entry analysis
                 ↓
       explanation + invalidation + WAIT when evidence is insufficient
```

### Status

**Accepted product direction as of 2026-09-29.**

Future implementation work must follow this direction unless the user explicitly changes it.

### Clarification — screenshots are inference-time evidence, not training data

This is an explicit correction to the product model and supersedes any earlier wording that made screenshot datasets, screenshot training, or historical candle databases a prerequisite for AICFA analysis.

- AICFA does **not** need a prebuilt historical candle database as a core intelligence layer.
- AICFA does **not** need to learn/train on user screenshots before it can analyze them.
- A user-supplied chart screenshot is an **inference-time input/evidence**.
- AICFA must visually read the screenshot itself and apply its existing Knowledge Base and analytical rules to it.
- If the visible history/context is insufficient, AICFA must determine what is missing and explicitly ask the user for additional screenshot(s), asset context, or timeframe(s).
- For example, AICFA may request 4H for context, 1H for structure, 15M for the setup zone, and 5M for entry confirmation when those views are needed. It must not fabricate unseen history.
- Multi-timeframe screenshots are correlated by AICFA itself; the user does not label BOS, FVG, liquidity, OB, or other concepts manually.
- The desired path is:

```
USER REQUEST
    ↓
AICFA determines required evidence
    ↓
current screenshot(s) / requested additional screenshot(s)
    ↓
Vision: read the chart
    ↓
structured visual market evidence
    ↓
Knowledge Base + analytical rules
    ↓
setup / entry / WAIT
```

### Historical candle data policy

The previously implemented historical/live candle infrastructure is **supporting infrastructure, not the product's intelligence foundation**. Do not continue expanding a large historical candle database, historical scanner, or candle-driven training pipeline unless the user explicitly reintroduces that requirement.

If historical context is needed for a specific analysis, AICFA should prefer asking the user for the relevant chart history/timeframe screenshots rather than assuming a permanently maintained historical candle database is required.

Existing market-data code may remain available as optional infrastructure for on-demand current evidence and future explicitly requested uses. It must not drive the roadmap or justify autonomous scanning.



## 2026-09-29 — Knowledge Base v1 implementation

The knowledge-first stage has now started in code.

### Commits
- 76cc1d2ac95483beb933e9af1ba7a4d797709d97 — add structured AICFA Knowledge Base v1 module;
- 1f2c6f48d0a5517780a92e90ea2799a833826296 — add Knowledge Base contract tests;
- 7f9b7ac7a2bda9f2f75d6407c3f809d09bdaa683 — document Knowledge Base v1 and its runtime/history boundaries.

### Implemented

src/aicfa/knowledge_base.py introduces an immutable KnowledgeEntry contract with:
- stable identifier;
- domain;
- definition;
- observable chart evidence;
- relationships to other concepts;
- confirmations;
- invalidations;
- counterexamples;
- setup relevance.

The initial registry covers Market Structure, Liquidity, FVG/Imbalance, Order Blocks, Premium/Discount, Price Action, Wyckoff, Derivatives and Risk/Invalidation.

The registry is deliberately descriptive. It does not emit LONG/SHORT signals and has no dependency on OHLCV history, screenshots as training data, live providers or historical outcomes.

### Verification boundary

The implementation and tests are committed to main. FrostDeploy full-suite verification is required before this stage can be marked GREEN.

### Next implementation step

Expand the Knowledge Base to the full project specification, including the remaining SMC concepts, structure states, liquidity variants, FVG/IFVG, order-block lifecycle, volume/volatility, derivatives/microstructure semantics, Wyckoff/Price Action relationships, scenario/risk semantics and contradictory-evidence handling. Then build the visual-evidence contract that will map user screenshots into this knowledge layer.


## 2026-09-29 — Knowledge Base full-spec expansion

### `12bd00e495f8cb5e7b2156f9474729bb5002c181`
**Expand Knowledge Base to full analytical specification**

Expanded the Knowledge Base registry from the initial 10 concepts to a full descriptive v1 coverage across:
- market structure: HH/HL/LH/LL, BOS, CHoCH, MSS, internal/external structure, protected swings, range, expansion and consolidation;
- liquidity: equal levels, previous extremes, internal/external liquidity, inducement, pools and breakout-vs-sweep distinction;
- imbalance: FVG, IFVG, mitigation and displacement relationship;
- order blocks: bullish/bearish OB, lifecycle, mitigation and breaker behavior;
- premium/discount: dealing range, equilibrium and location;
- price action: rejection, breakout, retest, continuation, reversal, support/resistance and compression;
- Wyckoff: Spring, Upthrust, trading range, SOS, SOW, markup/markdown;
- volume/volatility: expansion, contraction, price/volume relationship and volatility regime;
- derivatives: funding, OI, price/OI, liquidations, long/short positioning, basis and liquidation imbalance;
- microstructure: taker flow, CVD, absorption, displayed liquidity walls and depth imbalance;
- scenario: continuation, reversal, range, breakout failure, evidence quality and contradictory evidence;
- risk: entry condition, target, invalidation and explicit WAIT/insufficient-evidence state.

The registry remains immutable and descriptive. It does not create LONG/SHORT signals, does not require historical candles, and does not treat screenshots as training data.

Added contract tests covering the expanded domains and representative concepts.

### Verification status

**PENDING FrostDeploy/server verification.**

The implementation is on GitHub main. The stage is not GREEN until the current FrostDeploy release passes the mandatory full pytest suite.

### Next step

1. Run the full FrostDeploy pytest suite on the new release.
2. Fix only actual failures.
3. Rerun until green.
4. Then build the Visual Evidence contract so user screenshots are mapped into structured evidence consumed by this Knowledge Base.

### Evidence reasoning implementation

Commits:
- `ad1f37c6a21d470c3b5a1d98367b9cb22dcd9726` — add evidence reasoning layer;
- `8ff426d47fe1aa023bc6f02b3dddad97cdad740f` — test evidence reasoning;
- `a4d43b1313176fb3d05d9d3e801fadfea879c6b3` — document evidence reasoning.

Implemented:
- evidence sufficiency assessment before scenario/setup reasoning;
- PROCEED / NEED_MORE_EVIDENCE / WAIT states;
- required concept/timeframe checks;
- uncertainty preservation;
- contradiction preservation;
- Knowledge Base relationship lookup;
- explicit separation from directional trade signals;
- dynamic multi-timeframe support without a four-timeframe limit.

Verification status: **PENDING FrostDeploy/server verification.**

Post-deploy test correction: `8ff426d` asserted a relationship that was not present in the canonical Knowledge Base (`liquidity.sweep` relates to `market_structure.choch`). Corrected by `0d3447c2e01e5c08ebbebeebac39daae9fb31bcb`; no analytical behavior was changed.

Next step after green verification: build the scenario reasoning layer that combines supported Knowledge Base concepts and their relationships into continuation/reversal/range/breakout-failure hypotheses while preserving evidence quality, invalidation and WAIT semantics.

## 2026-09-29 — Knowledge Base full-spec server verification

FrostDeploy release: `2026-09-29T15-42-00-c01cbbf`

Mandatory full-project verification on the deployed release:

```
203 passed, 4863 warnings in 42.78s
```

The expanded Knowledge Base stage is now **GREEN / accepted**.

Verified on the current deployed release:
- full pytest suite passes;
- expanded Knowledge Base registry and contract tests pass;
- required AICFA timeframe-grid test including 1m passes;
- no test failures remain.

Observed warnings are non-blocking and remain known technical debt:
- pandas DataFrame fragmentation PerformanceWarning in Multi-Timeframe output construction;
- pandas FutureWarning from the Premium/Discount test fixture dtype assignment;
- pytest-cache permission warnings caused by immutable FrostDeploy release directories.

These warnings do not block the Knowledge Base stage and are not being mixed into the analytical feature work.

### Next implementation step

Build the **Visual Evidence contract**: a causal, structured representation of user-supplied chart screenshots that can be consumed by the existing Knowledge Base and analytical rules. Screenshot evidence remains inference-time input, not training data, and the user must not manually label BOS/FVG/liquidity/OB concepts.


## 2026-09-29 — Visual Evidence contract implementation

### `a3893958ec97b6e0a95467f82caa8546d941ba64`
**Add structured visual evidence contract**

Added `src/aicfa/visual_evidence.py` as the first runtime contract for screenshot-based analysis.

Implemented:
- immutable `VisualObservation` records tied to Knowledge Base concept IDs;
- explicit observed / possible / not_visible states;
- bounded confidence and required visible evidence;
- screenshot-only provenance, separate from live market-provider data;
- asset/timeframe context and optional capture timestamp;
- explicit missing-context and contradiction fields;
- multi-timeframe `VisualEvidenceSet` with duplicate protection;
- no LONG/SHORT decision generation and no screenshot-training dependency.

This is the evidence boundary between future chart vision and the existing analytical Knowledge Base. The vision layer will produce these observations; users do not manually label market concepts.

### Verification status

**PENDING FrostDeploy/server verification.**

Next: add contract tests, document the screenshot evidence path, then deploy and run the mandatory full pytest suite before accepting the stage.


### `1130c440209dca03abd5a7850bc1bb11b1083770`
**Test visual evidence contract**

Added contract tests for immutable observations, confidence/evidence validation, screenshot provenance, duplicate protection, multi-timeframe bundles, and separation from live-provider state.

Verification remains pending on the deployed FrostDeploy release.


### `356d465c66b1907c0dd72b44fb2d7e8a53fc50fe`
**Document screenshot visual evidence contract**

Added `docs/VISUAL_EVIDENCE.md` describing the runtime path from user screenshots through vision into the Knowledge Base, including no-manual-labeling, no-fabricated-history, screenshot/live separation, multi-timeframe evidence and no-signal-generation boundaries.

### Verification status

**PENDING FrostDeploy/server verification.**

The Visual Evidence contract implementation is complete for this stage. Required next verification:

```bash
sudo -u fd-aicfa bash -lc '
cd "$(readlink -f /srv/frostdeploy/aicfa/current)"
PYTHONPATH=src .venv/bin/python -m pytest -q
'
```

After the deployed suite is green, the next implementation stage is the **AICFA evidence/reasoning layer**: map visual/live observations to Knowledge Base relationships, preserve contradictions and determine when more evidence is required before producing setup analysis or WAIT.

## 2026-09-29 — Scenario Reasoning implementation

Commits:
- `a2e6ab0356c0bb088cd9ba42d044bdd370b051b7` — add Scenario Reasoning layer;
- `8af787ca2faa5959b729397c9f7e9a2d5e018040` — test Scenario Reasoning;
- `b151633a045a0d5de4592c882d79dc5535be28c2` — document Scenario Reasoning.

Implemented:
- continuation, reversal, range and breakout-failure hypothesis families;
- preservation of multiple plausible scenarios;
- confirmation and invalidation requirements per hypothesis;
- propagation of evidence insufficiency and contradictions;
- no automatic direction, entry, stop or execution fields;
- dynamic multi-timeframe input without a fixed four-timeframe chain.

Verification status: **PENDING FrostDeploy/server verification.**

Next after green: combine scenario hypotheses with richer Knowledge Base confirmation/invalidation semantics and evidence quality into structured setup analysis.


## 2026-09-29 — Setup Analysis implementation started

### `e2fc9a5172c6036443282105b2ee10d7589241e8`
**Add structured setup analysis layer**

Added `src/aicfa/setup_analysis.py`.

Implemented:
- structured `SetupAssessment` and `SetupCandidate` contracts;
- READY / NEED_MORE_EVIDENCE / WAIT decisions;
- preservation of multiple scenario candidates;
- contextual setup-zone extraction from observed visual concepts;
- Knowledge Base confirmation/invalidation enrichment;
- conditional entry requirements, invalidation conditions and target objectives;
- optional price-location propagation only when actually present in visual evidence;
- no fabricated numeric levels;
- no order execution or automatic trade placement.

The layer requires contradiction-free evidence, a supported scenario and at least two supporting observed concepts plus a visible contextual zone before forming a candidate.

Verification status: **PENDING FrostDeploy/server verification.**

Next: add Setup Analysis contract tests, document the layer, deploy, and run the mandatory full pytest suite.


### `29263479df43b9a34cf707789e42686fb26925d3`
**Test setup analysis layer**

Added `tests/test_setup_analysis.py` covering:
- conditional continuation setup formation;
- zone and price-location propagation;
- no fabricated numeric levels;
- insufficient supporting evidence;
- missing contextual zone;
- contradiction propagation to WAIT;
- preservation of multiple plausible setup candidates;
- absence of execution/order fields.

Verification remains **PENDING FrostDeploy/server verification**.
