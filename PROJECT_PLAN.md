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

Completed and verified layers include Market Structure, Liquidity, Displacement, FVG, Order Blocks, Premium/Discount, Unified SMC, Multi-Timeframe, Volume/Volatility, Scenario Engine, expanded Derivatives, Order Flow/Microstructure, Knowledge Base, Visual Evidence, Evidence Reasoning, Scenario Reasoning, Setup Analysis, and the evidence-gated Decision Layer.

The project remains **pre-ML**. Do not jump to model training until the market-state representation is sufficiently complete and verified.

---

## Decision Layer — server verification

FrostDeploy release:
`2026-09-29T16-19-55-380db53`

Mandatory full-project verification:
```
235 passed, 4863 warnings in 40.11s
```

The pytest-cache permission warning is the known non-blocking warning caused by immutable FrostDeploy release permissions. The full suite passed with no test failures.

### Status

**Evidence-gated Decision Layer is GREEN / accepted.**

Verified behavior includes:
- READY setup without explicit direction → WAIT;
- explicit LONG directional evidence → LONG;
- explicit SHORT directional evidence → SHORT;
- conflicting LONG/SHORT evidence → WAIT;
- concept names alone never imply direction;
- setup conditions, invalidation and targets are preserved;
- no order placement, quantity, leverage or execution logic.

The Decision Layer remains an analytical evidence gate, not an autonomous signal generator.

### Next implementation step

Proceed to the chart-vision inference boundary: define how AICFA's vision layer reads user-supplied chart screenshots and converts visible chart evidence into structured `VisualObservation` records, including explicit direction where visually supported, without manual user labeling, fabricated unseen history, or screenshot training-data requirements.

The vision layer must preserve uncertainty and request additional screenshots/timeframes when the visible evidence is insufficient.

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

1. User asks AICFA for an urgent/current entry or analysis.
2. If live market-data connection is available, AICFA uses current network market data and its own analytical knowledge.
3. If required live data is unavailable, AICFA asks the user for chart screenshots for the relevant asset and timeframes.
4. AICFA analyzes supplied visual evidence with its own market knowledge and rules.
5. The result is tied to the evidence actually available. No live data is fabricated.

### Explicit product exclusions

- Scalping as a dedicated product mode is removed.
- Autonomous continuous setup scanning is removed.
- AICFA does not continuously analyze Top-50/Top-100 assets looking for setups for no specific user request.
- AICFA does not run a separate market-analysis pipeline per customer.
- There is no requirement to maintain expensive realtime streams for every asset solely so that an autonomous scanner can generate alerts.
- A user request may target any asset.
- The analytical core remains asset/timeframe aware and can use multiple timeframes when the user asks for an entry.

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
- market microstructure

SMC concepts remain descriptive hypotheses until historical evidence establishes their behavior. They must not become automatic trade signals merely because several features co-occur.

---

# 6. Verification policy

Every meaningful implementation stage must be verified on the current FrostDeploy release with the full suite:

```bash
sudo -u fd-aicfa bash -lc '
cd "$(readlink -f /srv/frostdeploy/aicfa/current)"
PYTHONPATH=src .venv/bin/python -m pytest -q
'
```

Never claim GREEN without current deployed-release output.

Known non-blocking warnings currently include pandas/NumPy deprecations, DataFrame fragmentation, fixture dtype warnings, and immutable FrostDeploy pytest-cache permission warnings.

---

## Historical control log

Previously verified analytical stages remain accepted as recorded in Git history and prior plan entries, including Market Structure, Liquidity, Displacement, FVG, Order Blocks, Premium/Discount, Unified SMC, Multi-Timeframe, Volume/Volatility, Derivatives, Taker Flow/Order Flow, Order Book/Market Depth, Liquidity Walls, Absorption, CVD, Price Action, Wyckoff, Setup Detection, Canonical Market State, Setup Event Engine, Knowledge Base, Visual Evidence, Evidence Reasoning, Scenario Reasoning and Setup Analysis.

The current control point is the **GREEN Decision Layer verification above**.


## 2026-09-29 — Chart Vision inference boundary implementation started

### Commits
- `5dd7ca8d3fa05d371b3ccc911893d39b55638a12` — add chart vision inference boundary;
- `6fa38127fe769534acb05f71a51b6af9f419fc16` — test chart vision inference boundary;
- `1aa5699c0154024507fc9534fe5e0a8b36f94746` — document chart vision inference boundary;
- `672a0d7c16f7867e067058bf5028383e1dff480b` — fix test fixture to use a canonical Knowledge Base concept;
- `4438518b2fcf4924c14f143e66dc2f1d65f50ce4` — fix syntax error in chart vision test.

### Implemented

Added `src/aicfa/chart_vision.py` with:
- `ChartVisionRequest` for screenshot bytes + asset/timeframe context;
- `ChartVisionOutput` for structured visual observations, missing context and conflicts;
- `ChartVisionAnalyzer` protocol as the adapter boundary for the future actual vision implementation;
- Knowledge Base validation for every emitted concept;
- conversion into the canonical `VisualEvidence` / `VisualEvidenceSet` contracts.

The first deployed verification exposed one test-fixture error:
```
FAILED tests/test_chart_vision.py::test_build_evidence_set_preserves_multi_timeframe_inputs
ValueError: vision output references unknown Knowledge Base concept: market_structure.range
```
That fixture was corrected to use the existing canonical `premium_discount.dealing_range` concept. The validator was not weakened.

The next deployed release exposed a second, purely syntactic test error:
```
SyntaxError: unmatched '}'
```
The final test function was closed with `}` instead of `)`. This has now been corrected.

Important boundaries:
- no manual user labeling;
- no direction inference;
- no confidence inflation;
- no fabricated unseen history;
- no conversion of possible evidence into observed evidence;
- no trade signal generation;
- screenshot provenance remains `user_screenshot`.

The actual image-recognition model/provider is intentionally **not** faked or hard-coded in this stage. The contract is ready for a real vision implementation.

### Verification status

**PENDING FrostDeploy/server verification after syntax correction.**

The deployed release `2026-09-29T16-34-57-882bea1` still failed collection with:
```
SyntaxError: unmatched ')'
```
The previous correction accidentally left the test with an extra closing parenthesis. This has now been corrected again in:
- `f518af2cb2065a3f05b5ec94f4cff78669f44d3f` — fix chart vision test closing parenthesis.

No production Chart Vision code was changed. The next verification must use the FrostDeploy release containing `f518af2...` and the mandatory full pytest suite.

Required next step:
1. wait for FrostDeploy deployment of the corrected test commits;
2. run the mandatory full pytest suite;
3. if green, accept the Chart Vision inference boundary;
4. only then proceed to attaching a real vision implementation.

### Final server verification

FrostDeploy release: `2026-09-29T16-38-00-f8af81f`

Mandatory full-project verification:
```
243 passed, 4863 warnings in 47.56s
```

The remaining pytest-cache permission warning is the known non-blocking immutable-release warning. No test failures remain.

**Chart Vision inference boundary is GREEN / accepted.** The boundary is verified without implementing or pretending to implement an actual image-recognition provider.

### Next implementation step

Proceed to the real chart-vision provider/adapter stage. Keep it provider-agnostic and cost-conscious: the analytical AICFA core remains the intelligence layer, while the vision component only converts user screenshots into structured visual evidence. Do not assume OpenAI API usage or any other paid external model unless explicitly chosen and verified.


## 2026-09-29 — Self-hosted chart vision adapter started

### Commits
- `f5daa87bc06935edbb049d2d0830a9e2255b61f0` — add `OllamaChartVisionAnalyzer` provider adapter;
- `e1d0c4b9bf53470fbb305e573df7a0a66c8836df` — add provider parsing/validation tests;
- `aba507fc29a7b2e0349ba431b960788bcf1302e8` — document the self-hosted adapter.

### Implemented
- Optional Ollama multimodal HTTP adapter using Python standard library only;
- screenshot sent as base64 image input;
- strict evidence-only prompt with asset/timeframe context;
- structured JSON parsing into canonical `VisualObservation` records;
- Knowledge Base validation remains mandatory before provider output enters the analytical graph;
- explicit direction is preserved only when supplied by the vision provider;
- provider is opt-in and does not download or select a model;
- no paid API is required by the adapter.

### Verification status
**PENDING FrostDeploy/server verification.**

The adapter is intentionally not activated as a production service yet. A capable multimodal model must be installed and served separately (for example through a self-hosted Ollama endpoint). The current AICFA server hardware must not be assumed sufficient for a vision model without testing.

Required next step:
1. wait for FrostDeploy deployment of the adapter commits;
2. run the mandatory full pytest suite;
3. if green, accept the adapter code;
4. separately test a real local/self-hosted vision model before making it the active provider.


## 2026-09-29 — Self-hosted chart vision adapter verification and local model selection

### Server verification

FrostDeploy release:
`2026-09-29T16-44-59-56b75f0`

Mandatory full-project verification:
```
245 passed, 4863 warnings in 40.65s
```

The remaining pytest-cache Permission denied warning is the known non-blocking warning caused by immutable FrostDeploy release permissions. No test failures remain.

**Self-hosted Chart Vision adapter code is GREEN / accepted.**

### Local vision provider

The next operational step is to install and test a real local multimodal model through Ollama.

Baseline candidate selected for the first real chart test:
- `qwen3-vl:4b` — current Ollama local vision model, approximately 3.3 GB model size;
- it accepts text + image input and is intended to provide the visual perception layer only;
- AICFA's Knowledge Base, evidence reasoning, scenario reasoning, setup analysis and Decision Layer remain the authoritative analytical system;
- the provider must not generate trade execution instructions or bypass AICFA evidence validation.

The current server has 3 GB RAM, so the 4B model should not be installed blindly. Increase RAM first (target at least 6 GB total for this baseline) and then test actual CPU inference. If the real server test shows insufficient memory/performance, use a smaller vision model rather than changing the AICFA architecture.

No model is considered production-active until:
1. Ollama is installed and healthy;
2. the selected model is pulled successfully;
3. a real BTC/USDT chart screenshot is processed;
4. the provider output passes AICFA Knowledge Base/evidence validation;
5. the full pytest suite remains green after any integration changes.

### Immediate operator step

On the AICFA server, first inspect resources and Ollama state:
```bash
free -h
nproc
ollama --version || true
nvidia-smi || true
```

Then proceed with the local model installation/test. Do not expose Ollama port 11434 publicly; AICFA should use the local endpoint `127.0.0.1:11434`.
