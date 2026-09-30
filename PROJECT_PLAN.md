## CURRENT PROJECT CONTROL STATE

**Purpose:** This file is the persistent AICFA project diary and control document. A new ChatGPT session must be able to read it and continue the project without previous chat history.

### What we are building
AICFA (AI for Digital Financial Assets) is a specialized crypto/digital-financial-asset analysis system with its own deterministic analytical core, market representation, evidence/reasoning layers, scenario/setup analysis and decision logic. It is not a wrapper that delegates market analysis to a generic LLM.

### Current product direction
- BTC/USDT is the primary development asset.
- User-driven analysis, not autonomous continuous market scanning.
- Main path is text-first: user asks in plain language; AICFA obtains explicit market data and runs its own analytical core.
- Screenshots/Chart Vision are experimental and are not on the critical path after the real-chart benchmark proved the current pixel extraction approach unreliable.
- Final analytical states may be LONG / SHORT / WAIT / NO TRADE.
- Decision Layer is authoritative for the final analytical state.
- No autonomous trading, order placement, leverage/quantity execution logic.

### Current architecture
User text → optional local text/interface layer → AICFA orchestration → Market Data + Knowledge Base + deterministic analytical layers → Evidence Reasoning → Scenario Reasoning → Setup Analysis → Decision Layer → human-readable response.

The local text model, if used, is only an interface/verbalization/reasoning assistant. It must never invent live market data, redefine AICFA terminology, replace deterministic calculations, or override the Decision Layer.

### Core analytical chain
Canonical causal timeframe direction: 1m → 5m → 15m → 1h → 4h → 1d → 1w.

Accepted components include Market Structure, Liquidity, Displacement, FVG, Order Blocks, Premium/Discount, Unified SMC, Multi-Timeframe, Volume/Volatility, Derivatives, Order Flow/Microstructure, Knowledge Base, Visual Evidence, Evidence Reasoning, Scenario Reasoning, Setup Analysis and the evidence-gated Decision Layer.

### Non-negotiable development rules
1. Data before assumptions.
2. Strict causality; no future leakage.
3. Every important rule must be mechanically definable and testable.
4. Never claim GREEN without current deployed verification.
5. Do not install/test models blindly.
6. Record model provenance, size/quantization, RAM, CPU latency and output-quality findings.
7. Do not repeat rejected experiments.
8. No paid API unless explicitly chosen.
9. Respect CPU/RAM/storage limits.
10. After every meaningful commit, update this file with commit SHA, what changed, verification/result, status, discovered issues and exact next step.
11. This file is the source of truth for project continuity; chat history is not required to resume work.
12. Work forward-only; no rollback unless explicitly requested.

### Rejected approaches
- Native screenshot pixel-trace Chart Vision implementation: rejected/pending for real-chart reliability; do not add visual BOS/CHoCH/FVG/OB semantics until trace localization is fixed.
- MiniCPM-V 4.6: rejected after real BTC chart benchmark.
- Granite 3.2 Vision 2B and other tested small VLM paths: rejected; see chronological history.
- Shirdel-Finance-E4B Q6_K: rejected after OOM and removed.
- SmolLM3 3B Q4_K_M: rejected for terminology/instruction reliability and latency; removed.
- NEXUS-Finance 1.5B: rejected after domain and trivial instruction-following failures; removed.
- Ministral 3 3B official GGUF: rejected as direct AICFA explanation model; final closed-world test still invented unsupported interpretations; removed.

### Current local-model state
**No local text model is installed or production-active.** Any next candidate must have documented/verified provenance before download. Do not return to random/community finance fine-tunes merely because they are small.

### Current workstream
**Local Text AI / interface architecture is unresolved.** The immediate question is whether a local model can safely act as a closed-world verbalizer/interface around deterministic AICFA output without inventing facts. If this cannot be demonstrated reliably, continue AICFA without a local model rather than weaken the analytical core.

### Latest completed event
2026-09-30 — Ministral 3B benchmark closed and model removed. Final closed-world test: 141 generated tokens, about 4.02 tok/s, about 52.6s total. It preserved WAIT, JSON and the requested size but added unsupported claims. Model removal was verified with an empty ollama list.
GitHub commit recording this event: a8a62b4cf8edfdbc8d6323b7c0cf39c5489085fd

### Exact next step
1. Review current official local-model candidates suitable for the server.
2. Verify provenance/model card, parameter count, quantization size, context and intended task.
3. Do not download until a candidate passes the resource/role screen.
4. If selected, benchmark it isolated first.
5. Integrate only after safe closed-world behavior is demonstrated.
6. After every resulting commit, immediately update this diary with commit SHA and outcome.

### Continuity instruction
Read CURRENT PROJECT CONTROL STATE first, then the latest chronological entries. Do not ask the user to reconstruct project history unless information is genuinely absent. Continue from Exact next step and preserve rejected approaches and constraints.

---
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


## 2026-09-30 — Deterministic CV benchmark: vision-market-structure-analyzer evaluated

### Benchmark method
- A temporary GitHub Actions benchmark branch was used so the public chart image could be downloaded and the external implementation could be executed without changing AICFA production code.
- Benchmark image: public dark BTC/USDT 4H candlestick chart, 512×400 price/volume content.
- Candidate: Rudra-kakade/vision-market-structure-analyzer, MIT licensed.
- Manual ROI was bypassed with the full image bounds; the implementation itself clipped the actual image to 512×400.

### Results
- Runtime was extremely fast: approximately 0.011–0.014 seconds per run.
- Sensitivity sweep:
- scale 1 → 14 pivots: H, LH, LH, HH, HH, LH, HH, LH, LH, LH, L, LH, LH, HH
- scale 3 → 6 pivots: H, LH, LH, HH, LH, LH
- scale 5 → 4 pivots: H, HH, LH, LH
- scale 7 → 4 pivots: H, HH, LH, LH
- scale 9 → 4 pivots: H, LH, HH, LH
- At the useful higher sensitivities it detected no confirmed swing lows at all on this chart; at scale 1 it produced only one low among 14 pivots.
- The algorithm therefore cannot currently provide a reliable HH/HL/LH/LL market-structure representation for this chart, despite excellent raw latency.

### Decision
Reject the external implementation as the AICFA Chart Vision implementation. Keep its preprocessing/price-trace ideas as reference only. Its current column-mask extraction is too dependent on the chart's pixel geometry and does not robustly recover both swing highs and lows from the tested dark TradingView-style chart.

### Operator actions recorded
- A temporary benchmark branch and PR were created solely to run the benchmark through GitHub Actions; nothing from that branch was merged into main.
- The benchmark was run at scales 1, 3, 5, 7 and 9 and completed successfully.
- No AICFA production source code was modified by this benchmark.

### Next exact step
Stop benchmarking external repositories. Build the first AICFA-native deterministic Chart Vision stage around the actual requirement:
1. chart/price-panel localization;
2. candle/color segmentation that preserves both bullish and bearish candles;
3. normalized high/low price trace extraction;
4. swing candidate detection with image-resolution-independent thresholds;
5. HH/HL/LH/LL classification;
6. output only into the existing visual-evidence boundary.

The first native stage must be tested on synthetic chart images plus real public chart screenshots and must remain CPU-only and comfortably below the user's ~60-second interactive limit.


## 2026-09-30 — AICFA-native deterministic Chart Vision stage started

### Commits
- 06c6d084a54f7530e5d334105eeb7a301df88c8b — add native deterministic chart structure extractor;
- 5798d156ab2fe9e448c9119bdc009a1683898d84 — add OpenCV runtime dependency;
- 7a254e6e0e406a18a0a186f50034a08495ef34d3 — add synthetic-image tests;
- 2fc084683205735ca77f7315fa7257e1e58a8641 — fix deterministic swing-extrema comparison;
- d1d9acc070dfe5877cf8d533e976a483144d10fd — document the native Chart Vision stage.

### Implemented
- Added CPU-only pixel-to-structure extraction in src/aicfa/chart_structure_cv.py.
- The first stage decodes screenshots, segments saturated/high-value candle colors, restricts the price panel, builds a per-column high/low trace, interpolates small gaps, smooths the trace, detects local swing highs/lows, confirms later movement using a normalized image-height threshold, and labels HH/HL/LH/LL.
- The output is an intermediate ChartStructure representation, deliberately separate from VisualEvidence semantics. It does not fabricate prices, infer trade direction, or emit BOS/CHoCH/FVG/OB/liquidity or orders.
- Added deterministic synthetic-image tests.

### Verification status
**PENDING current FrostDeploy/server verification.**
The implementation has not yet been accepted as GREEN. The next required check is the full current-release pytest suite on FrostDeploy. After that, the native extractor should be benchmarked against the public dark BTC/USDT chart and additional TradingView-style themes before expanding into BOS/CHoCH or SMC visual detectors.

### Next exact step
Run the mandatory full pytest suite on the current FrostDeploy release. If green, run focused Chart Structure CV tests/benchmarks and inspect extracted swings before adding the next visual structure layer.


## 2026-09-30 — Native Chart Vision test exposed fixed-spacing trace bug

### Operator verification
- User ran the mandatory full pytest suite on the current FrostDeploy release.
- Result: **246 passed, 1 failed, 4864 warnings in 25.04s**.
- Failing test:
  `tests/test_chart_structure_cv.py::test_native_chart_structure_extracts_price_trace_and_swings`
- Failure was `assert ()` at the swing assertion: the synthetic chart produced an empty structure trace/swings.

### Root cause
The first native `_column_trace()` implementation grouped colored columns using a hard-coded maximum x-gap of 3 pixels before interpolation. That assumption is invalid for charts where candle color segmentation leaves wider gaps between candle bodies/wicks. The synthetic test therefore split the candle sequence into isolated one-point runs and discarded them as too short.

This is a test/implementation defect in the new native CV stage, not a reason to weaken the test or accept the stage as GREEN.

### Forward fix commits
- `a920d8ad4c988d906dc0e8833df714a4561c0c9e` — make chart trace grouping adaptive to observed candle spacing;
- `8cb7c04110726ca962386fa7020af576b9a00bd6` — correct the adaptive-spacing implementation to derive spacing from the raw trace before grouping.

The grouping now uses observed x-spacing instead of an image-specific fixed 3px threshold and selects the dominant chart span by horizontal coverage.

### Verification status
**PENDING FrostDeploy verification after the fix.**

Do not mark the native Chart Vision stage GREEN yet.

### Next exact step
1. wait for deployment of `8cb7c041...`;
2. rerun the mandatory full pytest suite;
3. if green, benchmark `chart_structure_cv.py` on the real public BTC/USDT chart and inspect the extracted trace/swings;
4. only after that consider BOS/CHoCH visual detection.


## 2026-09-30 — Second native Chart Vision test failure: plateau extrema

### Operator verification
- User reran the full FrostDeploy suite after `8cb7c04...`.
- Result remained **246 passed, 1 failed, 4864 warnings in 24.56s**.
- The same synthetic Chart Vision test failed with an empty swings tuple.

### Root cause
The adaptive trace grouping was not the remaining issue. The smoothed synthetic price trace contains short flat plateaus from candle bodies and interpolation. The local-extrema detector required every neighboring value to be strictly higher/lower than the center, so legitimate plateau extrema were rejected and no swing candidates survived.

### Forward fix
- `41929bdc0cc896ecd2028d7c229c98d9269bd4f9` — allow plateau extrema while still requiring at least one strict side comparison.

This changes only the candidate-extrema predicate; it does not weaken the downstream confirmation threshold or invent swings.

### Verification status
**PENDING FrostDeploy verification.**

### Next exact step
Rerun the mandatory full pytest suite after deployment. If green, benchmark the native extractor on the real BTC/USDT chart before adding further visual semantics.

## 2026-09-30 — Native Chart Vision real-chart review: plateau deduplication and low-label correction

### Review finding

The first real BTC/USDT benchmark exposed a problem that the synthetic test did not cover: the plateau-extrema rule introduced by 41929bdc... correctly allowed flat extrema, but every pixel of a flat plateau could then become a separate swing candidate.

Observed symptoms on the real chart included repeated adjacent swing points at nearly identical coordinates, for example multiple highs at the same y and consecutive x values, plus repeated lows over flat runs. This is not acceptable as a market-structure representation.

The review also exposed an independent semantic bug in low-swing labeling: image y increases downward, so a larger low_y means a lower price and must be labeled LL, while a smaller low_y means a higher low and must be labeled HL. The previous implementation had these two labels reversed.

### Forward fixes

- 68c8baa047be3c2bdd385ab4702c571cd3de093e — collapse consecutive plateau extrema candidates to one representative swing and correct low-swing HH/HL/LH/LL-direction semantics.
- 17fef157fee057fddfe868d755409c11bba8658d — add regression tests for plateau collapse and low-swing labels.
- 72f9a07f6a5bc3203f6928c7bf6e6a6a30219d09 — correct the plateau regression-test expectations.

### Verification status

**PENDING FrostDeploy verification.**

The fixes have been committed forward-only, but no new deployed-release pytest result has been recorded yet. The previous known full-suite result remains:

```
247 passed, 4863 warnings in 24.00s
```

That result belongs to the earlier plateau-extrema implementation and does not validate these new changes.

### Important boundary

No BOS/CHoCH or additional visual semantics are being added yet. The current goal is to make the pixel-derived trace and swing representation structurally sane on real charts before building higher-level visual market structure.

### Next exact step

1. wait for FrostDeploy deployment containing 72f9a07...;
2. run the mandatory full pytest suite on the current release;
3. if green, rerun the real /tmp/btc.png benchmark;
4. inspect the resulting trace/swings for duplicate plateaus and correct HH/HL/LH/LL semantics;
5. only after the real-chart output is acceptable proceed to the next visual structure layer.


## 2026-09-30 — Native Chart Vision plateau regression: candidate grouping corrected

### Operator verification
- User ran the mandatory full FrostDeploy pytest suite after commits `68c8baa...`, `17fef157...` and `72f9a07...`.
- Result: **248 passed, 1 failed, 4864 warnings in 24.04s**.
- Failing test:
  `tests/test_chart_structure_cv.py::test_local_extrema_collapses_flat_plateau_to_one_swing`
- Failure:
```
assert [5, 7] == [6]
```

### Root cause
The first plateau-collapse fix grouped only **consecutive candidate indices**. On a flat extremum such as `[12, 12, 12]`, the strict-side predicate correctly rejects the center pixel, leaving edge candidates `5` and `7`. Because those candidates are separated by one non-candidate index, the previous collapse logic treated them as two swings.

This is an implementation defect in plateau grouping, not a reason to weaken the regression test.

### Forward fix
- `611d6e0cc192a77e6295f67582839b48cf45b769` — group plateau candidates across the full flat span when all values between the candidate edges equal the same extremal value, then select the midpoint as the single representative swing.

The change remains local to deterministic extrema candidate normalization. It does not alter confirmation thresholds, fabricate structure, or add higher-level SMC semantics.

### Verification status
**PENDING FrostDeploy verification.**

The current failing result must not be marked GREEN. The previous `248 passed, 1 failed` result is superseded by the forward fix but remains the latest actual server verification until the new deployment is tested.

### Next exact step
1. wait for FrostDeploy deployment containing `611d6e0...`;
2. rerun the mandatory full pytest suite;
3. if green, rerun the real `/tmp/btc.png` benchmark;
4. inspect whether duplicate plateau swings are gone and whether HH/HL/LH/LL labels are correct;
5. only after real-chart output is acceptable continue to the next visual structure layer.


## 2026-09-30 — Chart Vision plateau representative fix

- Verification result from deployed release before this fix: `248 passed, 1 failed, 4864 warnings in 24.33s`.
- Failing test: `tests/test_chart_structure_cv.py::test_local_extrema_collapses_flat_plateau_to_one_swing`.
- Observed failure: `assert [5] == [6]`.
- Root cause: plateau candidates can be the two edge indices of one flat span (for example 5 and 7). The collapse logic selected the midpoint of the candidate-list positions, which returned candidate 5 instead of the numeric midpoint index 6.
- Forward-only fix commit: `0572cddedbd29f386081ede9fcee182321719646`.
- Code change: representative plateau index is now calculated as `(candidates[start] + candidates[end]) // 2`.
- Status: **PENDING** until the new commit is deployed and the mandatory full pytest passes.
- Next exact steps:
  1. Wait for FrostDeploy release containing `0572cddedbd29f386081ede9fcee182321719646`.
  2. Run mandatory full pytest on the deployed `current` release.
  3. If GREEN, rerun native Chart Vision against the real BTC chart and inspect duplicate plateau swings plus HH/HL/LH/LL labels.

## 2026-09-30 — Native Chart Vision real BTC benchmark: current trace is rejected

### Operator verification
- User ran the native Chart Vision benchmark against the deployed /srv/frostdeploy/aicfa/btc-test.png (1131×817 historical BTC/USDT chart).
- Result: 423 trace points and 56 detected swings.
- The mandatory full pytest suite immediately before this benchmark was green: 249 passed, 4863 warnings in 23.83s on FrostDeploy release 2026-09-30T09-20-05-76a69aa.

### Real-chart finding
The current pixel trace is **not structurally acceptable** for real BTC charts.

Observed failures include:
- repeated highs at approximately y=59 across many unrelated x positions;
- repeated lows at approximately y=669 across many unrelated x positions;
- adjacent/near-adjacent EH/EL and repeated swings that do not represent meaningful market turning points;
- therefore the current 56-swing sequence cannot be treated as a valid HH/HL/LH/LL market-structure representation.

The output strongly indicates that the current saturated-pixel trace is capturing chart/UI or non-price regions at the vertical boundaries. In particular, y≈669 coincides with the configured bottom_fraction=0.82 boundary on an 817px image, so the current fixed fractional price-panel boundary is not sufficiently reliable for this real chart. The repeated y≈59 ceiling similarly indicates contamination by a horizontal chart/UI region or another saturated visual element rather than genuine independent price highs.

### Decision
**Native Chart Vision real-chart stage remains PENDING / REJECTED for this implementation iteration.**
The synthetic test suite passing is not sufficient; the actual pixel-to-market-state extraction must first produce a plausible price trace and swing sequence on the real BTC chart.

No BOS/CHoCH/FVG/OB visual semantics will be added yet.

### Next exact implementation step
Fix the **price-panel/price-trace localization** before changing swing thresholds:
1. inspect the mask's vertical distribution and identify the actual price plot region separately from the volume/UI regions;
2. prevent volume bars, chart borders and saturated UI elements from entering the high/low trace;
3. replace the current fixed top_fraction / bottom_fraction assumption with robust price-panel localization or an explicit price-panel ROI fallback;
4. add a regression test representing the discovered boundary contamination;
5. rerun the full deployed pytest suite;
6. rerun the same real BTC benchmark and inspect the swing sequence again.

Do not tune HH/HL/LH/LL thresholds to hide the contamination. The trace itself must be corrected first.


## 2026-09-30 — Architecture pivot: text AI becomes the user-facing reasoning layer; screenshot Vision removed from critical path

### Decision

The real BTC benchmark demonstrated that the current screenshot/pixel Chart Vision approach is not reliable enough to block the product on it. The project therefore pivots forward-only to a **text-first AICFA architecture**.

The goal is to let the user ask AICFA questions in plain text, while AICFA itself obtains current market data and runs its deterministic analytical core. **Screenshots are no longer required for the main analytical path.** The current native Chart Vision implementation remains in the repository as an experimental/rejected path and is not allowed to block the core product.

### Target architecture

```
User text
   ↓
Local Text AI / reasoning interface
   ↓
AICFA orchestration
   ├── Market Data
   │    ├── OHLCV
   │    ├── trades
   │    ├── order book
   │    ├── funding
   │    ├── open interest
   │    ├── liquidations
   │    └── volume / volatility / derived features
   │
   ├── Knowledge Base
   │    ├── SMC / market structure

## 2026-09-30 — Market Evidence contract introduced

### What was done
Introduced a dedicated market-data evidence contract so the main AICFA path does not represent deterministic market data as screenshot/vision observations.

### Changes
- Added `src/aicfa/market_evidence.py`.
- Added `MarketObservation` with explicit timeframe, evidence, state and optional explicit direction.
- Added `MarketEvidence` with explicit `source="market_data"` and duplicate concept/timeframe protection.
- Added `tests/test_market_evidence.py` covering valid observations, direction validation, source validation and duplicate detection.
- No screenshot/Vision dependency was added to the new contract.

### Commits
- implementation: `40038241b02b6c711a33b791ccd918b2c5487554`
- tests: `dd905a00f3b763a91fa0bfab87b9a1ee283c4675`

### Verification
FrostDeploy release/test verification has not yet been run after this change. Therefore this step is **PENDING verification**, not GREEN.

### Status
**IMPLEMENTED / PENDING DEPLOYED VERIFICATION**.

### Architecture decision
The production FindSetup path uses Market Evidence, not VisualObservation. Vision/screenshots are not part of the main AICFA product flow. The authoritative Decision Layer remains the final gate.

### Exact next step
Connect Market Evidence to the existing Evidence/Scenario/Setup contracts without fabricating visual observations, then route FindSetup through the authoritative Decision Layer. Run the mandatory full pytest before accepting the step.


## 2026-09-30 — Market Evidence connected through existing reasoning and Decision contracts

### What was done
Created the first real market-data path through the existing AICFA reasoning stack without converting market data into screenshot/vision observations.

### Changes
- Extended `MarketEvidence` with `missing_context` and `conflicts`.
- Added `assess_market_evidence()` to the evidence-reasoning layer.
- Allowed Scenario Reasoning, Setup Analysis and Decision Layer to consume the shared observation shape used by market evidence.
- Added an end-to-end test proving deterministic market evidence can flow through Evidence → Scenario → Setup → authoritative Decision Layer and produce LONG only when explicit directional evidence exists.
- Added a guard test proving structurally sufficient market evidence without explicit direction produces WAIT.
- No screenshot/Vision dependency was added to the market path.

### Commits
- `72a171dc659c8c420751591adfc396eb8bc8efa8` — extend MarketEvidence context/conflicts
- `5d3cebe026b233a94f7d839d86f65cd7bc10de9a` — add market evidence assessment
- `cb466dbf1dafbab4f738fce8c4304421e17932ce` — shared observation typing in Scenario Reasoning
- `8eced563ec2c328a3413f1633d585418d68a8509` — shared observation typing in Setup Analysis
- `1a8d803dd4acdd644c3d602a922be55897bc69c6` — shared observation typing in Decision Layer
- `e480375a8b0141083cc0e5b2e44b2863097cab8b` — end-to-end market evidence tests

### Verification
No FrostDeploy verification has been run after these commits yet. Therefore this implementation step is **PENDING** and must not be called GREEN.

### Status
**IMPLEMENTED / PENDING DEPLOYED VERIFICATION**.

### Important result
The authoritative `src/aicfa/decision.py` is now reachable by a dedicated market-data evidence path. The Decision Layer still requires explicit directional evidence and therefore does not derive LONG/SHORT merely from concept names.

### Exact next step
Deploy these commits to FrostDeploy and run the mandatory full pytest suite. If green, replace the temporary test-only market observations with a deterministic adapter from the actual `build_features()` / `market_state` output, then connect that adapter to `FindSetup`.


## 2026-09-30 — FrostDeploy collection failure: missing legacy VisualObservation imports

### Operator verification
User ran the mandatory full pytest suite on the deployed release after the Market Evidence bridge changes.

Result:
```
ERROR tests/test_decision.py - NameError: name 'VisualObservation' is not defined
ERROR tests/test_market_evidence_pipeline.py - NameError: name 'VisualObservation' is not defined
ERROR tests/test_scenario_reasoning.py - NameError: name 'VisualObservation' is not defined
ERROR tests/test_setup_analysis.py - NameError: name 'VisualObservation' is not defined
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! Interrupted: 4 errors during collection !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
2 warnings, 4 errors in 1.85s
```

### Root cause
The Market Evidence refactor changed imports toward `MarketObservation`, but three existing modules still referenced the legacy `VisualObservation` type in runtime-evaluated annotations without importing that symbol:
- `src/aicfa/decision.py`
- `src/aicfa/scenario_reasoning.py`
- `src/aicfa/setup_analysis.py`

This is a collection-time NameError. It is not evidence that the Market Evidence runtime path itself is correct.

### Forward fix
Restored the explicit legacy type imports so the existing VisualEvidence tests and the new MarketEvidence path can coexist:
- `038793f4b09e0ade49dc95aa5fdfdf64ec753f74` — fix `decision.py` VisualObservation import;
- `624afea43723f4147e297a8d1a6ccec860f5ba32` — fix `scenario_reasoning.py` VisualObservation import;
- `328fbad0a85712817baed5da39f1b34dfe1ebf68` — fix `setup_analysis.py` VisualObservation import.

No analytical rule was changed. No screenshot dependency was added to the market path.

### Status
**FAIL → FIXED IN SOURCE / PENDING DEPLOYED VERIFICATION.**

The reported FrostDeploy run is the latest actual verification and must not be treated as GREEN.

### Exact next step
1. Wait for FrostDeploy deployment containing all three forward fixes.
2. Run the mandatory full pytest suite again.
3. If collection and tests pass, record the exact deployed release/output as GREEN.
4. Then continue with the planned deterministic adapter from actual `build_features()` / `market_state` output into `MarketObservation` / `MarketEvidence`.
5. Do not install or test another local model.


## 2026-09-30 — Market Evidence bridge collection fix verified

### Operator verification
FrostDeploy release:
`2026-09-30T16-27-34-e60c9b9`

Mandatory full-project pytest:
```
263 passed, 5579 warnings in 27.67s
```

The pytest-cache Permission denied warning remains the known non-blocking immutable-release warning.

### Result
**GREEN / accepted for this verification stage.**

The previous collection-time `NameError: VisualObservation is not defined` is resolved. Existing VisualObservation-based tests and the new MarketEvidence pipeline now coexist without collection errors.

### Relevant fix commits
- `038793f4b09e0ade49dc95aa5fdfdf64ec753f74`
- `624afea43723f4147e297a8d1a6ccec860f5ba32`
- `328fbad0a85712817baed5da39f1b34dfe1ebf68`
- plan record: `e60c9b9f17fd19a65d83074aa46e7856525bf742`

### Important boundary
This verifies the test suite and compatibility of the Market Evidence bridge. It does **not** yet prove that real market-data output is correctly converted into MarketObservation records or that FindSetup is product-ready.

### Exact next step
Implement a deterministic adapter from the existing `build_features()` / `market_state` output into `MarketObservation` / `MarketEvidence`. Then connect that adapter to FindSetup and remove its temporary local decision logic in favor of the authoritative Decision Layer.


## 2026-09-30 — Deterministic Market State → Market Evidence adapter added

### What was done
Added the first production-path adapter that converts the latest completed deterministic AICFA feature/state row into the canonical MarketEvidence contract.

### Changes
- Added `src/aicfa/market_evidence_adapter.py`.
- Emits observations only when supported deterministic feature columns are active.
- Maps explicit directional evidence for:
  - `market_structure.bos`
  - `displacement`
  - `imbalance.fvg`
  - `order_block.bullish`
  - `order_block.bearish`
  - `liquidity.sweep`
- Reads higher-timeframe market-structure/BOS columns from the existing `mtf_<timeframe>_` output instead of inventing higher-timeframe values.
- Records timeframes with no active supported observation in `missing_context`.
- Records coexistence of explicit long and short evidence as a conflict.
- Added `tests/test_market_evidence_adapter.py` for base observations, higher-timeframe structure and conflicts.

### Commits
- `f9033865175dd74799776aa81a115c7bb18e57a5` — adapter implementation
- `b137c48cb741c24af76c4f6e1c6dbbf97898a380` — adapter tests

### Verification
No FrostDeploy verification has been run after these new commits yet.

Status: **IMPLEMENTED / PENDING DEPLOYED VERIFICATION**.

### Important limitation
The current feature engine calculates many detailed concepts on the 1m base frame, while the existing MTF layer currently exposes higher-timeframe structure fields. The adapter therefore does not pretend that higher-timeframe FVG/OB/displacement/liquidity observations exist when they are not actually present. Those contexts remain unavailable rather than fabricated.

### Exact next step
Deploy these commits and run the mandatory full pytest suite. If green, connect `build_market_evidence()` into `find_setup.py`, replacing its temporary local `_decision()` with the authoritative Evidence → Scenario → Setup → Decision chain.


## 2026-09-30 — Current product state / continuation checkpoint

### Verification just completed
FrostDeploy release: `2026-09-30T16-36-37-a815896`

Mandatory full suite:
`266 passed, 5579 warnings in 27.61s`

The only known recurring warning is FrostDeploy's pytest-cache PermissionError inside immutable release directories. It is non-blocking and does not invalidate the passing test result.

Status: **GREEN / ACCEPTED** for the deterministic Market State → Market Evidence adapter stage.

### Product goal — final target
AICFA is a specialized AI system for analysis of digital financial assets / crypto markets. It is not intended to be a wrapper around an external LLM.

The final user experience must be extremely simple:

`Найди сетап <актив>`

The user names an asset. The system resolves the asset against an available real market-data provider, obtains the available market data, runs the canonical AICFA analysis across:

`1m → 5m → 15m → 1h → 4h → 1d → 1w`

and returns the deterministic AICFA decision:

- `LONG`
- `SHORT`
- `WAIT`
- `NO TRADE`

with a concise human-readable explanation of the evidence and why the Decision Layer reached that state.

### What AICFA already contains
The deterministic analytical core has been built in layers, including:
- Market Structure
- Liquidity
- Displacement
- Fair Value Gaps
- Order Blocks
- Premium / Discount
- Unified SMC
- Multi-Timeframe analysis
- Volume / Volatility
- Derivatives
- Order Flow / Microstructure
- Knowledge Base
- Evidence Reasoning
- Scenario Reasoning
- Setup Detection
- Setup Analysis
- authoritative Decision Layer

The Decision Layer is authoritative for the final `LONG / SHORT / WAIT / NO TRADE` state. No interface model may override it.

### Market-data architecture
Existing foundation:
- provider-agnostic OHLCV contract;
- Binance Spot and USDⓈ-M Futures public REST klines;
- completed-candle handling;
- incremental scanner/history infrastructure;
- canonical causal timeframe chain.

The remaining product problem is not building another isolated indicator. It is connecting these existing layers into one reliable user-facing FindSetup pipeline for an arbitrary user-named supported asset.

### Current bridge
Implemented:
`feature/state row → MarketObservation → MarketEvidence`

Current adapter: `src/aicfa/market_evidence_adapter.py`

It deliberately emits only deterministic observations supported by actual columns and records unavailable contexts instead of inventing them.

### What remains to reach final product
1. **Universal asset/symbol resolution**
   - `BTC/USDT`, `BTC-USDT`, `BTC_USDT`, and bare assets such as `BTC` must be resolved deterministically against the configured provider.
   - No BTC/ETH/SOL-only hard-coded routing.
   - Unsupported or unavailable assets must return an explicit unavailable-data result, never fabricated analysis.

2. **FindSetup orchestration**
   - User command → normalized request → resolved symbol → real market data → seven causal timeframes → existing AICFA Core.
   - No screenshot dependency.
   - No manual timeframe input from the user.

3. **Real MarketEvidence construction**
   - Feed actual `build_features()` / `build_market_state()` output into the adapter.
   - Preserve evidence provenance and unavailable context.
   - Expand concept mappings only when corresponding deterministic source columns actually exist.

4. **Authoritative reasoning chain**
   - `MarketEvidence → Evidence Reasoning → Scenario Reasoning → Setup Analysis → Decision Layer`
   - Remove the temporary local `_decision()` from `find_setup.py`.
   - Do not create a second decision algorithm in FindSetup.

5. **Final structured FindSetup result**
   - asset/symbol;
   - data availability by timeframe;
   - key evidence;
   - scenario/setup state;
   - authoritative decision;
   - concise reason;
   - explicit unavailable context where applicable.

6. **AICFA Interface Knowledge Pack**
   The future local text model needs only a compact interface/terminology contract:
   - what AICFA is;
   - command grammar;
   - asset extraction/normalization;
   - canonical AICFA terminology;
   - structured result schema;
   - explanation rules;
   - prohibition on inventing data;
   - Decision Layer is authoritative.

7. **Local text model — optional interface layer only**
   Screenshots are intentionally removed from the main product path.
   A local lightweight text model may later:
   - parse the user's command;
   - verbalize structured AICFA results in Russian;
   - optionally provide a clearly separated second opinion.
   It must never calculate unavailable market facts, invent indicators, or override the deterministic Decision Layer.
   No further model downloads until the FindSetup contract and Interface Knowledge Pack are stable.

8. **Production user flow verification**
   Final acceptance must demonstrate a real user request such as:
   `Найди сетап <asset>`
   → real provider resolution
   → real market data
   → all required causal timeframes
   → deterministic AICFA Core
   → MarketEvidence
   → Evidence
   → Scenario
   → Setup
   → Decision
   → human-readable result.

### Explicitly rejected / out of critical path
- screenshot-based analysis as the main path;
- blind cycling through random local VLM/text models;
- paid external AI APIs as a required component;
- execution/autotrading/order placement;
- leverage/position sizing logic;
- letting an LLM invent or override analytical results.

### Current exact next step
**Connect `build_market_evidence()` to `find_setup.py`, but first inspect the existing asset/provider contract and Decision/Scenario/Setup APIs so the integration uses the real interfaces rather than adding another parallel decision path.**

Operating rule remains:
`change → commit → deploy → verify → record result in PROJECT_PLAN.md → commit plan → next step`


## 2026-09-30 — FindSetup wired to authoritative reasoning chain

### What was done
Replaced the temporary local FindSetup decision logic with the existing authoritative AICFA reasoning pipeline.

### Changes
`src/aicfa/find_setup.py` now performs:
`real OHLCV → build_features → MarketEvidence adapter → Evidence Reasoning → Scenario Reasoning → Setup Analysis → Decision Layer`

The result now preserves:
- MarketEvidence;
- EvidenceAssessment;
- ScenarioAssessment;
- SetupAssessment;
- DecisionAssessment;
- final decision derived directly from `DecisionAssessment.action`.

The old private `_decision()` function was removed, so FindSetup no longer contains a second competing decision algorithm.

Added an integration test proving FindSetup exposes MarketEvidence and derives its public decision from the authoritative DecisionAssessment.

### Commits
- `8366782e1651be2abd42c2be628f2c3613ddae1` — FindSetup integration
- `7fa570986e7d93f3917a5c2e78833232a5124c18` — integration test

### Verification
Not yet run on FrostDeploy after these commits.

Status: **IMPLEMENTED / PENDING DEPLOYED VERIFICATION**.

### Current limitation
Asset resolution is still not universal. A bare asset such as `DOGE` is normalized but not yet resolved to a provider symbol/quote. The next product step is provider-backed symbol resolution rather than guessing a quote.

### Exact next step
After deployed pytest passes, implement a deterministic Binance symbol resolver for user-named assets, including explicit pairs and bare base assets, with clear unsupported/unavailable errors. Then wire the resolver into FindSetup.


## 2026-09-30 — FindSetup decision-chain deployment verification

### Verification
FrostDeploy release: `2026-09-30T16-44-06-bb8fbd8`

Mandatory full pytest:
`267 passed, 5937 warnings in 28.03s`

The pytest-cache PermissionError under the immutable release directory remains a known non-blocking FrostDeploy warning.

### Result
**GREEN / ACCEPTED.**

FindSetup integration is now verified on the deployed release:
`OHLCV → Features → MarketEvidence → Evidence Reasoning → Scenario Reasoning → Setup Analysis → Decision Layer`

The public FindSetup decision is derived from the authoritative DecisionAssessment.

### Exact next step
Implement deterministic provider-backed asset/symbol resolution for user commands, without hardcoded BTC/ETH/SOL-only routing and without guessing unsupported instruments.


## 2026-09-30 — Universal Binance asset resolver verified
- Done: added provider-backed Binance symbol resolution to support the user-facing `Найди сетап <asset>` flow without a hardcoded asset list.
- Changes:
  - bare asset resolves to an active USDT symbol;
  - explicit pair syntax is validated against Binance exchangeInfo;
  - non-trading/unknown symbols are rejected explicitly;
  - added resolver regression tests.
- Implementation commit: `289e3cc8d52ca9541fcf89b868d6c5c09f682992`.
- Test commit: `d7611fba25e6a676212151a4a69c83561faaff38`.
- FrostDeploy verification release: `2026-09-30T16-53-51-d7611fb`.
- Verification output: `269 passed, 5937 warnings in 28.40s`.
- Warnings observed: existing DataFrame fragmentation warning; existing pandas incompatible-dtype FutureWarning; immutable FrostDeploy pytest-cache PermissionError. None caused test failure.
- Status: GREEN / ACCEPTED.
- Exact next step: integrate the resolver into `find_setup.py`, so a user-supplied bare asset such as `BTC` is resolved before the seven-timeframe market-data fetch. Preserve explicit unsupported-asset handling and do not introduce a parallel decision path.


## 2026-09-30 — FindSetup asset resolver integration implemented
- Done: connected the provider-backed resolver to the FindSetup orchestration.
- Changes:
  - FindSetup resolves the user asset before any OHLCV request;
  - resolved symbol is used consistently for all seven causal timeframes and MarketEvidence;
  - Binance provider remains the default resolver path;
  - injected resolver support keeps non-Binance test providers explicit instead of silently guessing;
  - added integration tests for bare-asset resolution and resolver enforcement.
- Implementation commit: `d8633e0d39c2a6c9039481f4b0d2f8f1d92d2d8d`.
- Test commit: `cd948ef54d92059b0e2578bc070052c1fb79ab0e`.
- Status: IMPLEMENTED / PENDING deployed verification.
- Exact next step: deploy this commit and run the complete pytest suite on the resulting FrostDeploy release. If GREEN, then test the actual user-facing command path with a real Binance-resolved asset and verify unsupported assets fail explicitly.


## 2026-09-30 — FindSetup resolver regression fixed
- Verification of `d7611fb` integration initially failed: 268 passed, 3 failed.
- Causes:
  - two legacy FakeProvider tests did not inject a resolver after the new resolver boundary;
  - the new integration returned a canonical pair through `FindSetup`, while the test exposed the resolver's pair representation mismatch;
  - the non-Binance provider resolver requirement was unnecessarily strict for injected test providers.
- Fix:
  - Binance remains provider-backed and resolves real user assets;
  - FindSetup canonicalizes the resolver result before use;
  - non-Binance injected providers retain a deterministic normalization fallback;
  - regression tests updated to make the resolver boundary explicit where needed.
- Fix implementation commit: `a9bb3affb923fc5bea30532da69abd1c2e4bd232`.
- Test commit: `4abbb4169bd81c023eded53f0a8b5077dbfdfc63`.
- Status: FIXED / PENDING deployed verification.
- Exact next step: deploy and rerun the complete pytest suite. Do not proceed to live Binance validation until the deployed suite is GREEN.


## 2026-10-01 — FindSetup resolver return-field regression fixed
- Deployed verification after the previous fix: 269 passed, 1 failed.
- Cause: the resolver correctly produced `DOGE/USDT` and that symbol was used for market-data/evidence processing, but `FindSetupResult.symbol` still returned the original user request (`DOGE`).
- Fix commit: `d388ca1de48597de2fbf59bfb60cce52a455907d`.
- Status: FIXED / PENDING deployed verification.
- Exact next step: deploy this one-line correction and rerun the full pytest suite. Only after zero failures proceed to live Binance validation.


## 2026-10-01 — FindSetup resolver integration GREEN
- FrostDeploy verification release: `2026-09-30T17-00-31-1eab26a`.
- Verification output: `270 passed, 6295 warnings in 27.50s`.
- The only relevant warning is the known immutable-release pytest-cache PermissionError; it does not fail tests.
- The resolved symbol regression is verified fixed.
- Status: GREEN / ACCEPTED.
- Exact next step: perform a controlled live Binance validation of the user-facing asset resolution path, starting with a real supported asset such as BTC and verifying that `BTC` resolves to an active `BTC/USDT` market before the seven-timeframe fetch.


## 2026-10-01 — Pre-live resolver hardening
- Before live Binance validation, identified an edge case: an exact exchange symbol such as `BTCUSDT` could otherwise be mistaken for a bare base asset and become `BTCUSDTUSDT`.
- Fixed resolver to check exact active exchange symbols before applying the default USDT quote.
- Added regression coverage for exact `BTCUSDT`.
- Implementation commit: `1943b8e91ba24c095e4e43ba210fca887fe4150c`.
- Test commit: `a68c169cf1a72c18618d1a178dbf8e738b0016d2`.
- FrostDeploy release: `2026-09-30T17-02-40-9d8f800`.
- Verification: `270 passed, 6295 warnings in 28.26s`.
- Known non-blocking warning: immutable FrostDeploy release prevents pytest cache creation.
- Status: GREEN / ACCEPTED.
- Exact next step: deploy this hardening change, run full pytest, then run the live Binance FindSetup smoke test.


## 2026-10-01 — Live Binance asset-resolution smoke test
- FrostDeploy release: `2026-09-30T17-02-40-9d8f800`.
- Real Binance validation succeeded: user asset `BTC` resolved to `BTCUSDT`.
- Real Spot 1m OHLCV request succeeded with 1 row.
- Observed live candle: timestamp `1790787840000`; open `84334.01000000`; high `84353.90000000`; low `84283.57000000`; close `84283.57000000`; volume `16.08461000`.
- No fake provider or fixture was used.
- Status: GREEN / ACCEPTED for live Binance resolver + 1m transport smoke test.
- Exact next step: run the real user-facing `FindSetup BTC` flow across all seven causal timeframes and capture the complete AICFA result.


## 2026-10-01 — First real FindSetup BTC end-to-end run
- FrostDeploy release: `2026-09-30T17-05-39-1861af7`.
- Real `FindSetupRequest("BTC")` resolved to `BTCUSDT` and fetched all seven causal timeframes: `1m, 5m, 15m, 1h, 4h, 1d, 1w`.
- The authoritative chain executed successfully through MarketEvidence → Evidence Reasoning → Scenario Reasoning → Setup Analysis → Decision Layer.
- Result: `WAIT`, reason: `required context is missing`.
- Evidence contained only 1 active observation; missing context reported no active supported observation for `1m, 5m, 15m, 1h, 4h, 1d`.
- This is not a production GREEN: the run exposed an architecture gap in the current bridge. FindSetup fetches seven real timeframe datasets, but MarketEvidence is still primarily built from the latest 1m feature row plus currently exposed MTF structure columns, so detailed deterministic concepts are not yet independently evaluated on each timeframe.
- Status: LIVE PIPELINE EXECUTED / PRODUCT PENDING.
- Exact next step: extend the deterministic MarketEvidence construction so each of the seven real timeframe frames is independently analyzed and contributes its own supported observations, while preserving causal closed-candle rules and the authoritative Decision Layer.


## 2026-10-01 — Independent seven-timeframe evidence path implemented
- Reworked FindSetup so each completed causal timeframe is independently passed through the deterministic feature engine before MarketEvidence construction.
- Added `build_market_evidence_from_frames()` to aggregate observations from independent timeframe analyses and detect cross-timeframe directional conflicts.
- Preserved the existing single-analysis adapter for compatibility.
- Changes: `src/aicfa/find_setup.py`, `src/aicfa/market_evidence_adapter.py`.
- Implementation commits: `09fe4129bb81ab34d07b69576d8703a18b0a88b1`, `e1dbd61366d24869bc4c85c8126d7efdb744bba3`.
- Test commit: `c77e14bcebb0e1f1c64f4280bf8232b50c82df46`.
- Status: IMPLEMENTED / PENDING deployed verification.
- Exact next step: deploy and run full pytest; if GREEN, repeat live FindSetup BTC across seven timeframes and inspect evidence count, missing context, conflicts, and final Decision Layer action.


## 2026-10-01 — Independent timeframe evidence verification
- FrostDeploy release: `2026-09-30T17-09-41-2d52c1e`.
- Verification: `271 passed, 8959 warnings in 31.35s`.
- No test failures.
- Known warnings remain non-blocking: pandas performance/deprecation warnings and immutable FrostDeploy pytest-cache PermissionError.
- Status: GREEN / ACCEPTED for independent per-timeframe evidence implementation.
- Exact next step: repeat the real user-facing `FindSetup BTC` flow on this release and inspect whether observations are now present across multiple causal timeframes and whether missing context has decreased.
