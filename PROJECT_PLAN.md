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

---

# AICFA — Project Control Plan

**Project:** AICFA — AI for Digital Financial Assets
**Repository:** `nyxtryp/aicfa`
**Primary asset during current development:** BTC/USDT

## Current implementation checkpoint

The analytical core is being built causally from the canonical finest timeframe upward:
**1m → 5m → 15m → 1h → 4h → 1d → 1w**.

Completed and verified layers include Market Structure, Liquidity, Displacement, FVG, Order Blocks, Premium/Discount, Unified SMC, Multi-Timeframe, Volume/Volatility, Scenario Engine, expanded Derivatives, Order Flow/Microstructure, Knowledge Base, Visual Evidence, Evidence Reasoning, Scenario Reasoning, Setup Analysis, and the evidence-gated Decision Layer.

The project remains **pre-ML**. Do not jump to model training until the market-state representation is sufficiently complete and verified.

## Latest control state

The latest deployed control point before the current Git changes was FrostDeploy release `2026-10-01T08-31-11-5bcc6e6`:

```
304 passed, 18168 warnings in 49.16s
```

The focused MTF verification after the NumPy import repair also passed:

```
2 passed, 928 warnings in 12.13s
```

The subsequent full suite on the same deployed code passed:

```
304 passed, 18145 warnings in 48.12s
```

The known immutable-release pytest-cache Permission denied warning remains non-blocking.

## 2026-10-01 — Repair MarketEvidence context consumption

### Finding

The adaptive expansion path correctly detected missing context, but the MarketEvidence adapter still inspected only the latest completed row. Therefore historical-but-causally-relevant events such as BOS, displacement, FVG creation, Order Block creation and liquidity sweeps disappeared from evidence as soon as the latest candle no longer carried the event flag.

This could cause adaptive expansion to keep requesting deeper context without actually using the newly available recent event information.

### Actions taken

- `d3e7a8dde7209d4f5c925d4b78c256af149d6ee2` — Repair MarketEvidence to consume causal recent events and active states.
  - Market Structure BOS/CHoCH, Displacement, FVG, Order Block and Liquidity Sweep now use the latest causally knowable event available in the completed analysis frame rather than only the latest row.
  - FVG and Order Block lifecycle state is checked on the latest completed row.
  - When a lifecycle state is active, its direction is recovered from the latest corresponding creation event at or before the current row.
  - No future rows are consulted.
  - Existing conflict detection remains deterministic.
- `7e67498686a7c84b66340aa8dd6dda5a23cd2498` — Repair lifecycle direction selection.
  - Prevents a shared `order_block_active` state from being incorrectly attributed to the wrong bullish/bearish Order Block.
  - Uses the most recent directional creation event for the currently active lifecycle.
- `30a2e1d7877a338395c708877a90341af587d625` — Add regression coverage proving an earlier causal BOS remains available when the latest completed row is quiet.

### Verification

The above Git changes are **not yet deployed** to FrostDeploy.

### Performance work disposition

The recent pytest performance investigation is now **paused/backlog**. The deployed suite is green at 304 tests, and further test-runtime optimization is not on the critical path. Do not spend the next development cycle optimizing pytest unless runtime becomes a concrete blocker.

### Exact next step

1. Deploy current `main` containing the MarketEvidence repair.
2. Run the focused MarketEvidence adapter tests.
3. Run the adaptive FindSetup tests.
4. Run the mandatory full pytest once.
5. Run the live BTC FindSetup smoke without explicit `limit`.
6. Inspect whether missing-context output decreases and whether adaptive expansion now reaches useful causal context instead of merely increasing depth.
7. If context is still incomplete, continue the next analytical requirement from the actual evidence result rather than inventing a fixed depth table.
