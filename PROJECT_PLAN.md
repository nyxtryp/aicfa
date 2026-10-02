## 2026-10-02 — MTF TRADING-MODE ARCHITECTURE: AUTHORITATIVE DESIGN CHECKPOINT

### User-confirmed target architecture

AICFA must not treat the universal seven-timeframe chain as the default trading model. The analytical engine must be mode-aware and stateless: every FindSetup call reads fresh market data, while the selected trading horizon determines which timeframes have authority.

Required mode/timeframe hierarchy:

- **Scalping:** 15m → 5m → 1m
- **Intraday:** 1D → 4H → 1H → 15m
- **Swing:** 1W → 1D → 4H → 1H
- **Position:** 1M → 1W → 1D → 4H

Interpretation is hierarchical, not merely a list of candles:
- the highest timeframe establishes the broader directional/context bias;
- the next timeframe(s) establish structure and setup geometry;
- lower timeframe(s) refine/confirm;
- the final timeframe is the execution/entry layer;
- a lower timeframe must not invalidate or override a setup whose analytical horizon is higher unless the relevant authoritative structural timeframe actually changes;
- **1m belongs only to Scalping**. It must not participate in Intraday, Swing, or Position setup decisions.

### Exact repository finding

Inspection of src/aicfa/data_requirements.py, src/aicfa/analysis_depth.py, src/aicfa/setup_analysis.py, and src/aicfa/find_setup.py confirmed why ordinary FindSetup currently processes all seven TFs.

`default_setup_requirements()` has no trading mode/horizon. It merges knowledge concepts into semantic timeframe roles. `DataRequirementPlan.required_timeframes` then maps roles globally:

- EXECUTION → 1m
- LOWER_CONFIRMATION → 5m, 15m
- HIGHER_STRUCTURE → 1h, 4h
- BROADER_CONTEXT → 1d, 1w

Therefore the default result is always: 1m → 5m → 15m → 1h → 4h → 1d → 1w.

`analysis_depth.py` is not the source of the seven-timeframe selection. It only resolves minimum/adaptive historical depth for whichever timeframes the requirement plan has already selected. Its current largest explicit feature dependency is 60 rows.

`FindSetupRequest` currently contains only asset and market_type. There is no strategy/mode/horizon field. `find_setup()` therefore calls `default_setup_requirements(symbol)` with no mode and fetches every timeframe returned by that universal plan.

`setup_analysis.py` is explicitly written around a single seven-timeframe context: SETUP_TIMEFRAMES = 1m, 5m, 15m, 1h, 4h, 1d, 1w; higher structure = 1w, 1d, 4h, 1h; confirmation = 15m, 5m; execution = 1m.

This architecture is not sufficient for the four required trading modes.

### Critical analytical problem identified

The current implementation can mix incompatible horizons inside one candidate. A real captured BTC LONG contained a 4h entry zone, 1w higher-timeframe direction, 15m + 5m confirmation, source_timeframes containing all seven TFs, and targets sourced from 5m/15m.

That is exactly the kind of mixed-horizon setup that the new mode-aware architecture must prevent.

The previous idea of solving LONG → WAIT through persistent `SetupLifecycle` is explicitly **not** the current solution. AICFA remains stateless. The correct fix is analytical timeframe authority/horizon selection, not memory that keeps an old LONG alive.

### Required future setup output

AICFA must explain the complete setup, not only return LONG/SHORT. The result should identify at minimum:
- trading mode;
- setup/scenario type;
- directional bias;
- role/result for every participating timeframe;
- setup/structure timeframe;
- entry timeframe;
- Entry zone;
- Invalidation;
- TP1/TP2 where available;
- RR;
- confirmation;
- rationale/evidence;
- explicit invalidation conditions.

Example Intraday conceptual flow: 1D context/bias → 4H setup structure/zone → 1H refinement/confirmation → 15m entry trigger.

### Architectural implementation direction

Do **not** solve this by merely filtering the existing seven-TF output after analysis.

The mode must enter the requirement/analysis pipeline before data collection:

FindSetupRequest(mode) → mode-specific requirement profile → required TFs → analysis_depth → feature/evidence analysis → scenario reasoning → mode-aware setup analysis → structured setup explanation.

The implementation must reuse the existing knowledge/SMC/evidence layers rather than redesigning them.

`analysis_depth` should remain responsible for historical context depth, not trading-mode selection.

`setup_analysis` must become horizon-aware so that only selected mode timeframes are processed, roles are explicit, low TF evidence cannot override a higher-horizon structural premise, Entry/Invalidation/Targets are sourced from appropriate role layers, confirmation is mode-specific, and 1m is unavailable outside Scalping.

### Current state

- This is an architecture/design checkpoint only.
- No production code was changed in this step.
- No RR threshold was changed.
- No SetupLifecycle integration was performed.
- No model-training work was started.
- Existing deterministic SMC/evidence/order-flow/CVD/L1/Absorption layers remain intact.
- `PROJECT_PLAN.md` remains the single source of truth.

### NEXT UNFINISHED

1. Implement the explicit trading-mode contract in the request/requirements layer.
2. Define mode-specific timeframe roles for the four exact hierarchies above.
3. Make `default_setup_requirements()` (or an equivalent explicit mode profile) return only the required TFs for the selected mode.
4. Pass only those TFs into `analysis_depth` and FindSetup collection.
5. Make Setup Analysis consume mode-specific role mappings rather than the universal seven-TF constants.
6. Add regression tests for exact TF selection: Scalping = 15m, 5m, 1m; Intraday = 1d, 4h, 1h, 15m; Swing = 1w, 1d, 4h, 1h; Position = 1m excluded and 1m must never be fetched/used.
7. Add tests proving a lower timeframe cannot override a higher-horizon setup merely because its direction changes.
8. Produce the full structured setup explanation with mode, scenario, timeframe roles, Entry, Invalidation, TP1/TP2, RR, confirmation, rationale, and invalidation conditions.
9. Run focused tests, then full pytest, then live BTC FindSetup smoke for each mode.
10. Only after this MTF mode architecture is GREEN continue to the next unfinished AICFA block.

### Continuity checkpoint

If the chat is restarted, resume from this section. The active task is **mode-aware MTF analytical architecture**, not SetupLifecycle integration and not model training. Do not revert to the universal seven-timeframe FindSetup design.

