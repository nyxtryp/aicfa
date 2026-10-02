### Implementation progress — derivatives integration
- `64160be`: added normalized derivatives adapter path for Binance/Bybit.
- `cbc408e`: switched liquidation collection to the public Binance/Bybit market liquidation streams; no fabricated liquidation values.
- `b182cf3`: added deterministic derivatives completeness/evidence bridge.
- `0298f26`, `903ba73`, `8c69298`: connected derivatives collection and normalized evidence into live FindSetup while keeping injected test providers deterministic.
- `476ec52`: added focused tests for schema normalization, completeness, causal alignment, missing-data behavior and Bybit normalization.
- `85f95cb`: fixed the live integration bug found by the first Scalping smoke. Funding and Open Interest were coming from independent endpoints with different timestamps, but the adapter previously combined them by exact timestamp; this produced rows with null funding/OI and caused `build_derivatives` to reject the live frame. The adapter now builds a causal common timeline: OI is carried forward from the latest known observation, funding is carried forward from the latest known observation, and the current mark price is retained at its own timestamp. No future values are backfilled.
- `7db5cf6`: added a regression test proving funding/OI/mark alignment works when their source timestamps differ and that the resulting frame passes derivatives completeness.
- `279c0c4`: corrected the Bybit timestamp-alignment regression fixture to include an observed liquidation event; an empty mocked liquidation stream must remain incomplete because `liquidation_volume` is a required live source and no liquidation evidence may be fabricated.
- Live FindSetup requests Funding + Open Interest + Liquidations + Mark Price when the knowledge requirement requires all four, computes existing `build_derivatives` analytics, and attaches a causal `derivatives.price_oi` observation. If the required derivatives source fails or is incomplete, the evidence path records explicit unavailable context instead of fabricating a setup.
- Important implementation detail: Binance/Bybit liquidation data is collected from the public market liquidation websocket streams; REST `allForceOrders` is not treated as a valid current source.

### Verification state
Focused and full regression tests were previously green before the timestamp-alignment fix. The first live Scalping smoke exposed a real integration bug: `DERIVATIVES_PROVIDER: unavailable: funding_rate/open_interest must be numeric and non-null`, with zero derivative rows. This was caused by independent Funding/OI timestamps being merged without causal alignment. The fix is now committed and must be verified by focused tests, full `pytest -q`, then the four live BTC mode smoke checks again.

## 2026-10-02 — DATA PIPELINE COMPLETENESS BLOCK: REQUIRED BEFORE FOUR-MODE LIVE SMOKE

### User-confirmed execution order
Before live BTC validation of the four trading modes, AICFA must first have a complete and actually connected market-data pipeline for setup validation.

The order is authoritative:
1. Complete the real market-data/source integration.
2. Verify data completeness and causal alignment.
3. Run regression tests.
4. Only then run four separate live BTC FindSetup smoke checks: Scalping 15m→5m→1m; Intraday 1d→4h→1h→15m; Swing 1w→1d→4h→1h; Position 1M→1w→1d→4h.

End-user UX remains asset-only: the user supplies BTC and the eventual orchestrator evaluates all four horizons automatically. The four separate calls are internal validation only.

### Current repository audit
The repository has a source/capability registry, real Binance and Bybit market-data transports, OHLCV, trades, Order Book/history, CVD, Order Flow, Absorption, deterministic SMC/evidence layers, and derivatives.py with derivatives analytics.

Critical integration gap found: live FindSetup currently defaults to FallbackMarketDataProvider(BinanceMarketDataProvider(), BybitMarketDataProvider()). Funding, Open Interest, Liquidations and Mark Price are represented in the repository/data contract and derivatives analytics, but are not yet fully connected as live source data into the FindSetup evidence pipeline.

The registry's declared capabilities are not proof of a live integration. Only an actual adapter + collection path + normalization + FindSetup integration counts as connected.

### Required implementation block
1. Connect real derivatives source collection: Funding Rate, Open Interest, Liquidations, Mark Price.
2. Use the existing source registry/data-source abstraction; preserve fallback behavior; do not invent unsupported API capabilities.
3. Normalize venue-specific schemas, preserve causal timestamps, prevent future leakage, and align derivatives evidence with selected mode/timeframes.
4. Make live FindSetup actually request and receive required derivatives data and feed it into existing derivatives/evidence analysis without breaking OHLCV/trades/order-book/CVD/absorption.
5. If required data is unavailable, explicitly mark evidence unavailable/insufficient and return WAIT/insufficient evidence where needed. Never fabricate derivatives evidence.
6. Add tests for capability mapping, normalization, causal alignment, required-data completeness, missing-data behavior, no fabricated derivatives evidence, and exact mode-specific requirements.

### Do not do
- Do not revert to universal seven-timeframe analysis.
- Do not make the user select a trading mode.
- Do not weaken existing MTF authority rules.
- Do not add APIs merely for quantity.
- Do not treat a registry entry as a live integration.
- Do not generate a setup when required evidence is absent.
- Do not run the four-mode live smoke until this data block is GREEN.

### Verification gate
This block is complete only when real source adapters are identified and connected for required data, FindSetup receives normalized derivatives data, missing-data behavior is deterministic and safe, focused tests pass, and full pytest -q passes.

Only after that: run the four separate live BTC smoke checks and inspect actual returned timeframes, roles, evidence, decision, reason and setup output.

### Continuity checkpoint
If the chat is restarted, resume from this section first.

ACTIVE TASK: complete the real market-data/derivatives integration and data-sufficiency gate.
NEXT AFTER GREEN: four-mode live BTC FindSetup smoke.

---
