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

## 2026-09-29 — Local Chart Vision model shortlist revised

The previous baseline `qwen3-vl:4b` is **no longer the default first candidate**. Current model selection must be evidence-driven and tested on the actual AICFA server rather than decided from model size or generic benchmarks.

### Current test order

1. **MiniCPM-V 4.6 1B** — first candidate because the server currently has only 3 GB RAM and this is the lightest practical candidate in the shortlist.
2. **Granite 3.2 Vision 2B** — second candidate; specifically interesting for AICFA because its documented use cases include charts, plots, diagrams and other visual structures.
3. **Qwen3.5 2B** — third candidate; newer multimodal family and a useful general comparison point.
4. **Qwen3-VL 2B** — fallback comparison candidate.
5. **Qwen3-VL 4B / Qwen3.5 4B** — only after smaller models are tested and server resources are increased if necessary.

### Selection rule

Do **not** install a larger model merely because it is larger. The winner for AICFA must be selected from actual BTC/USDT chart tests using the same screenshots and the same structured-output contract.

Evaluate each candidate on:
- visible candle/chart reading;
- HH / HL / LH / LL;
- BOS / CHoCH;
- liquidity sweep;
- FVG / imbalance;
- Order Block;
- Premium / Discount;
- explicit direction only when visually supported;
- uncertainty / `possible` vs `observed`;
- hallucination rate;
- valid structured JSON;
- AICFA Knowledge Base validation;
- inference latency on the current CPU;
- peak RAM usage;
- multi-timeframe consistency.

The vision model is only the **perception layer**. AICFA Knowledge Base, evidence reasoning, scenario reasoning, setup analysis and Decision Layer remain authoritative.

### Hardware rule

Current server baseline:
- RAM: 3 GB;
- CPU: 1 vCPU;
- GPU: none currently.

Do not assume that RAM alone solves inference performance. CPU inference speed and peak memory must be measured. If a 2B/4B candidate requires more headroom, increase RAM based on measured requirements rather than an arbitrary target.

### First real model test

Before changing the architecture:
1. inspect `free -h`, `nproc`, `ollama --version`, `nvidia-smi || true`;
2. install/verify Ollama locally;
3. test the smallest viable candidate first;
4. process the same real BTC/USDT chart screenshot;
5. pass the result through the existing AICFA vision/evidence validation;
6. record latency, memory and output quality;
7. compare the next candidate only if needed.

No candidate becomes production-active until it passes the real chart test and the full AICFA test suite remains green.

### Persistent workflow rule

The project plan is the source of truth for **what we are building, why, current architecture, completed stages, exact commits, deployment verification, model decisions, known limitations, and the next step**. After every meaningful implementation/model/documentation commit, update this file with:
- commit SHA;
- what changed;
- verification/deployment result;
- limitations or unresolved issues;
- exact next step.

Never rely on the chat history alone for project state.

## 2026-09-29 — Real local vision benchmark: MiniCPM-V 4.6 rejected

### Operator actions and environment
- Verified `/tmp/btc.png`: PNG, 1131×817, RGB, 48 KB.
- The image is a historical BTC/USDT 30-minute Binance/TradingView chart from 2025-07-08 and is used only as a vision benchmark, not as current market data.
- Installed Ollama locally; version `0.34.4`; endpoint `127.0.0.1:11434`.
- Hardware during the test: 2.8 GiB RAM, 1 vCPU, no GPU, 2.0 GiB swap.
- Pulled `minicpm-v4.6` and processed the screenshot through the Ollama vision API with a Russian evidence-focused prompt.
- During inference `llama-server` reached about 1.9 GiB RSS and about 95–100% CPU on the single vCPU; swap was used.
- Inference completed in 299.5 seconds.
- The inference process was then stopped; memory returned to about 523 MiB used / 1.9 GiB free.
- Removed `minicpm-v4.6` with `ollama rm minicpm-v4.6`; `ollama list` is now empty.

### Benchmark result
MiniCPM-V 4.6 identified Bitcoin / TetherUS, but was insufficient for AICFA visual market-structure work: timeframe interpretation was wrong/ambiguous; HH/HL/LH/LL, BOS/CHoCH, FVG/imbalance and Order Block were not reliably identified; volume was incorrectly treated as liquidity evidence; and the response mixed Russian with Chinese/English despite the Russian-only instruction.

### Decision
**MiniCPM-V 4.6 is rejected as the active AICFA vision candidate.** The combination of about 5 minute latency, about 1.9 GiB resident memory on a 2.8 GiB RAM server, and insufficient SMC/chart-structure recognition does not meet the AICFA perception requirements. The model was removed. No AICFA architecture change was made.

### Next exact step
Proceed strictly to candidate 2: **Granite 3.2 Vision 2B**. Use the same `/tmp/btc.png` benchmark image and an equivalent evidence-focused prompt. Record latency, peak RAM, candle/chart reading, HH/HL/LH/LL, BOS/CHoCH, liquidity/sweep, FVG/imbalance, Order Block, Premium/Discount where visible, uncertainty/hallucinations, structured-output quality and AICFA validation compatibility.

Do not activate any model in production until a candidate passes a real chart test and the full AICFA pytest suite remains green after any integration change. Do not install a larger model merely because it is larger.

### Control rule reaffirmed
All assistant and operator actions relevant to AICFA development must be recorded in this `PROJECT_PLAN.md`. The plan is the persistent source of truth; chat history alone is not sufficient. Before the next implementation/model step, read this plan first.

## 2026-09-29 — Granite 3.2 Vision 2B installed for benchmark

### Operator action
- User pulled `granite3.2-vision` successfully through local Ollama.
- Downloaded model components: approximately 1.5 GB + 892 MB; manifest verification and write completed successfully.
- The model is installed locally but is **not production-active**.

### Next exact step
- Run the same `/tmp/btc.png` historical BTC/USDT chart benchmark used for MiniCPM-V 4.6.
- Measure inference latency and observe RAM/CPU usage.
- Compare visual recognition of chart structure, HH/HL/LH/LL, BOS/CHoCH, liquidity/sweep, FVG/imbalance, Order Block, Premium/Discount, uncertainty and hallucinations.
- Do not change AICFA code or declare the model suitable before the benchmark result is reviewed.

## 2026-09-29 — Granite 3.2 Vision 2B benchmark: resource observation

### Operator observation during live inference
- User ran the Granite 3.2 Vision benchmark against the same historical `/tmp/btc.png` chart.
- At the observed point, `llama-server` (PID 412797) had approximately **2.4 GiB RSS / 83.3% of RAM**.
- System RAM: **2.85 GiB total**, only **136 MiB free**, with about **1.06 GiB swap in use**.
- CPU showed **80.2% iowait**, and `kswapd0` was active, indicating substantial memory pressure/swapping.
- Granite inference is therefore materially resource-constrained on the current 1 vCPU / 3 GB RAM server.
- This is an intermediate resource measurement only; the final model decision must also use the actual Granite response and measured end-to-end latency.
- Do not start another model test concurrently and do not declare Granite suitable from resource usage alone.

### Next exact step
Wait for the current Granite request to finish and record:
1. exact inference time;
2. full model response;
3. chart/SMC recognition quality;
4. whether the output can be converted and validated by AICFA's existing visual-evidence boundary;
5. final peak RAM/swap observation if available.

Then decide whether Granite is rejected or retained for a deeper AICFA validation test.

## 2026-09-29 — Granite 3.2 Vision 2B benchmark: inference timeout

### Operator result
- User ran the Granite benchmark against the same historical `/tmp/btc.png` chart.
- The Ollama HTTP request did not complete within the configured **600 second timeout** and ended with Python `TimeoutError: timed out`.
- No usable Granite model response was produced, so chart-recognition quality and structured-output validation could not be evaluated.
- The earlier live resource observation remains relevant: approximately 2.4 GiB RSS for `llama-server`, only ~136 MiB free RAM, ~1.06 GiB swap used, and ~80% iowait.
- This is a failed benchmark on the current hardware, not evidence that Granite's visual quality is poor in general. The practical issue demonstrated here is that the current 1 vCPU / 3 GB RAM environment cannot complete this test within 10 minutes.
- Do not leave the model process consuming the server indefinitely after the timeout; first confirm that no active `llama-server` remains, then reclaim resources.

### Decision status
**Granite 3.2 Vision 2B is not suitable for continued testing on the current server configuration unless resources are increased.** It is not production-active.

### Next exact step
1. Check `ollama ps` and `pgrep -af llama-server` to confirm whether inference has stopped.
2. If the model process is still running, stop only the stuck inference process.
3. Record the final resource state.
4. Remove `granite3.2-vision` if the user wants to keep the current low-resource server configuration.
5. Before trying another model, decide whether to test a smaller candidate or increase RAM/vCPU based on these measured constraints.

## 2026-09-30 — Server resources increased for Granite re-test

### Operator action
- User stopped the server, increased resources, and started it again.
- Current RAM: **4.8 GiB total**, ~4.0 GiB free, ~4.3 GiB available.
- Current CPU: **2 vCPU**.
- Swap: **2.0 GiB total, 0 B used** after restart.
- Ollama remains installed and healthy: **0.34.4**.
- No AICFA code or architecture changes were made.

### Benchmark status
The previous Granite 3.2 Vision 2B timeout occurred on the old 1 vCPU / ~3 GiB RAM configuration. The new hardware provides substantially more RAM and CPU, so the Granite benchmark should be repeated before rejecting the model.

### Next exact step
Repeat the same Granite 3.2 Vision 2B benchmark, using the same /tmp/btc.png and equivalent prompt, and measure:
- end-to-end inference time;
- peak RAM and swap;
- CPU/iowait;
- actual chart/SMC recognition quality;
- structured-output quality and AICFA validation compatibility.

## 2026-09-30 — Granite 3.2 Vision 2B re-test failed; model removed

### Operator result
- User repeated the Granite 3.2 Vision 2B benchmark after increasing the server to **4.8 GiB RAM and 2 vCPU**.
- During inference, `llama-server` reached approximately **3.7 GiB RSS / 76.6% RAM** and about **198% CPU** across the two vCPUs.
- Swap remained almost unused during the observed run, so the larger RAM allocation removed the previous severe swap pressure, but CPU inference was still fully saturated.
- The same HTTP request again failed to complete within the configured **600 second timeout** and ended with Python `TimeoutError: timed out`.
- No usable Granite response was produced; therefore chart/SMC quality and structured-output compatibility could not be validated.
- After the timeout, the user stopped Ollama and confirmed there was no remaining `ollama`/`llama-server` process. Final resource state: **4.8 GiB RAM total, ~565 MiB used, ~3.8 GiB free, ~4.3 GiB available; 2 GiB swap with only 36 MiB used**.

### Decision
**Granite 3.2 Vision 2B is rejected for AICFA local chart-vision testing on this server.** The rejection is based on the repeated >10-minute inference timeout even after the hardware was increased to 2 vCPU / 4.8 GiB RAM. No claim is made about its visual quality because it never returned a usable benchmark response.

The model is no longer installed. Ollama itself remains installed for the next candidate.

### Next exact step
Proceed to the next shortlisted candidate: **Qwen3.5 2B**.

Before pulling it:
1. start the existing Ollama service;
2. confirm `ollama --version` and available RAM;
3. pull the Qwen3.5 2B vision-capable model;
4. run the same `/tmp/btc.png` benchmark with the same evidence-focused Russian prompt;
5. record latency, peak RAM/swap, CPU usage and actual structured chart output;
6. do not modify AICFA code during the model comparison.


## 2026-09-30 — Local VLM candidates exhausted; GitHub CV research for custom Chart Vision

### Operator actions
- User removed `qwen3.5:2b` from Ollama after deciding that local CPU vision inference must not exceed roughly 60 seconds for the AICFA interactive workflow.
- User installed `qwen3-vl:2b` (1.9 GB) and ran the same historical `/tmp/btc.png` benchmark with a 60-second timeout.
- `qwen3-vl:2b` failed to return within **60.1 seconds** with Python `TimeoutError: timed out`.
- User removed `qwen3-vl:2b`. Ollama model storage is intentionally empty again.
- Current server baseline remains approximately **2 vCPU / 4.8 GiB RAM / 2 GiB swap / CPU-only**.

### Local VLM conclusion
The practical CPU-only VLM path has now been tested enough to stop blind model cycling:
- MiniCPM-V 4.6 — 299.5 s, weak SMC/chart recognition;
- Granite 3.2 Vision 2B — >600 s timeout even after 2 vCPU / 4.8 GiB RAM;
- Qwen3-VL 2B — >60 s timeout;
- Qwen3.5 2B was pulled briefly but removed before benchmark at the user's request.

**Decision:** do not continue downloading small VLMs merely hoping for sub-minute chart perception. No local VLM is production-active.

### GitHub research: deterministic CV route
Reviewed public GitHub implementations that can provide fast chart perception without a VLM:

1. **nessos666/chart-vision-mcp** — MIT. Local TradingView chart analysis using OpenCV + Tesseract, no GPU, offline. Its standalone `chart_vision.py` uses deterministic color masks, Hough horizontal-line detection, contours, volume-bar analysis and OCR. The README reports sub-second structural analysis. It explicitly does not claim semantic chart understanding and recommends a hybrid approach where deterministic visual extraction feeds an LLM. Strong reference for AICFA's low-level CV layer, not something to import wholesale.
2. **Rudra-kakade/vision-market-structure-analyzer** — MIT. Screenshot-based CV pipeline for HH/HL/LH/LL, support/resistance and ZigZag trend shifts. The structure detector removes grid/background noise, extracts a price trace by column, smooths it, finds peaks and classifies confirmed swing points. Directly relevant to AICFA Market Structure.
3. **Ankitkumar7217734/Candlestick-Chart-OHLC-Extractor-Streamlit-Web-App** — YOLOv8 candlestick detector with bullish/bearish classification, body detection and pixel-to-price mapping. Useful reference for the harder candle/OHLC extraction layer, but not a reason to adopt the whole Streamlit app.
4. **StephanAkkerman/chart-info-detector** — MIT. YOLO detector trained specifically for TradingView symbol-title and last-price-pill regions, with a public pretrained model/dataset. Useful for chart metadata localization/OCR, but not core market-structure analysis.

### Architectural decision
Do **not** concatenate these repositories into one monolithic dependency stack.

Preferred direction:
- build an **AICFA-native Chart Vision** module;
- borrow/adapt only narrowly useful algorithms/components after license and code review;
- keep the existing `VisualEvidence` contract as the output boundary;
- use deterministic CV for fast, non-hallucinating visual extraction;
- let AICFA's existing Knowledge Base, Evidence Reasoning, Scenario Reasoning, Setup Analysis and Decision Layer perform semantic/causal interpretation;
- add ML only where deterministic CV is genuinely insufficient (for example candle localization or chart-widget localization).

Conceptual pipeline:
```
screenshot
  ↓
chart/ROI localization + OCR
  ↓
candle / price-trace extraction
  ↓
swings + HH/HL/LH/LL
  ↓
visual structures (liquidity/FVG/OB/etc. where mechanically detectable)
  ↓
AICFA VisualEvidence
  ↓
existing analytical layers
```

### Important limitation
The GitHub projects were reviewed at README/source level. Their reported speed and capabilities are **not yet verified on AICFA's `/tmp/btc.png`**.

### Next exact step
Benchmark the most relevant existing deterministic CV code — starting with `chart-vision-mcp` and `vision-market-structure-analyzer` — against the same `/tmp/btc.png`, measure runtime and inspect actual extracted structure. Do not modify AICFA production code until the benchmark demonstrates useful output.


### Source-code review findings

The deeper source review changes the assessment slightly:

- `chart-vision-mcp` is useful as a **reference implementation**, but its current candle analysis is mostly aggregate color-pixel ratios, not true candle-by-candle OHLC reconstruction. Its level detector counts horizontal Hough lines, and its zone detector relies on configured color ranges. Therefore its README's "structural analysis" should not be interpreted as reliable SMC detection. The code is MIT and modular enough to borrow small utilities from.
- `vision-market-structure-analyzer/new_markings.py` is more relevant to AICFA's Market Structure layer. It removes background/grid noise, builds a per-column high/low trace, smooths it with Savitzky-Golay, finds peaks/troughs, applies a 25-pixel confirmation move, and labels HH/HL/LH/LL. However, it assumes a manually supplied/selected ROI and pixel-based thresholds, and it does not recover real price values or understand TradingView-specific overlays. Its "20–50 pixel" style thresholds are image-resolution dependent and must be redesigned for AICFA rather than copied directly.
- `Candlestick-Chart-OHLC-Extractor` uses a trained YOLOv8 model to detect bullish/bearish candle boxes, then derives body/wick geometry and maps pixels to price. This is potentially useful for a later candle-localization component, but the model weights/training domain must be independently verified before adoption.
- `chart-info-detector` is narrowly scoped to TradingView symbol title and last-price pill localization. It is useful for metadata extraction, not for market structure.
- Both first two projects are MIT-licensed, so adaptation is legally straightforward provided the required copyright/license notices are retained. Any copied substantial code must still be tracked and attributed in AICFA.

### Technical conclusion from source review

The most promising path is **not** "take one repository and call it AICFA vision." It is to build a small deterministic pipeline around the strongest ideas:
1. TradingView/chart ROI + metadata localization;
2. robust candle/price-trace extraction;
3. normalized swing detection;
4. AICFA-native HH/HL/LH/LL and structure rules;
5. only then add mechanical visual detectors for liquidity/FVG/OB;
6. emit canonical `VisualObservation` objects;
7. let the existing AICFA analytical stack reason over them.

The key engineering problem is now identified as **pixel-to-market-state extraction**, not image-to-chat generation. This is much better aligned with the sub-minute requirement and the existing AICFA architecture.

No source code from these external repositories has been merged into AICFA yet.

## 2026-09-30 — Deterministic CV benchmark: chart-vision-mcp rejected

### Operator actions
- User installed the required Debian package `tesseract-ocr` on the server for the temporary external benchmark.
- User cloned `nessos666/chart-vision-mcp` under `/tmp/chart-vision-mcp` and installed its temporary Python dependencies.
- User benchmarked the repository against the existing historical `/tmp/btc.png` BTC/USDT chart.
- User removed the temporary repository and result file with:
  `rm -rf /tmp/chart-vision-mcp /tmp/chart-vision-result.txt`.
- No AICFA production files were changed by this benchmark.

### Benchmark result
- Runtime before failure: **0.351 seconds**.
- The tool loaded the 1131×817 image and produced a rough bearish bias from aggregate red/green pixel counts.
- It then failed in `detect_horizontal_lines()` with:
```
TypeError: cannot unpack non-iterable numpy.int32 object
```
- The source review confirmed that the implementation does not reconstruct candle-by-candle OHLC or reliably derive HH/HL/LH/LL, BOS/CHoCH, FVG or Order Blocks. Its "zones" are primarily color-area detection and its trend is based on pixel-color ratios.

### Decision
**`chart-vision-mcp` is rejected as an AICFA Chart Vision implementation.** Its sub-second runtime is useful evidence that deterministic CV can meet the latency target, but its current semantics are too shallow and the standalone analyzer has a runtime bug on this benchmark. It remains only a reference for low-level OpenCV techniques.

### Next exact step
Benchmark the second deterministic-CV candidate, **`Rudra-kakade/vision-market-structure-analyzer`**, against the same `/tmp/btc.png`. Measure runtime and inspect whether its price-trace/swing logic can reliably extract HH/HL/LH/LL. Keep all work outside AICFA until the benchmark demonstrates useful output.
