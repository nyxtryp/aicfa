# Event-driven live scanner

## Runtime contract

- Binance closed-kline events are the normal analysis triggers. Scalping reacts to 1m and 5m closes, Intraday to 15m, Swing to 1h, and Position to 4h.
- Each symbol/timeframe has a FIFO dispatch lane. Confirmed candles are not replaced by newer events when analysis is slow.
- A candle checkpoint advances only after its scan succeeds. A failed event remains queued for retry.
- When a WebSocket stream exhausts bounded reconnects, the coordinator fetches actual closed OHLCV rows after the last checkpoint and submits them in timestamp order before restarting the stream.
- The legacy one-market rotation is a safety net only after no closed candle has arrived for 180 seconds.
- The continuous ticker stream remains separate for active setup SL/TP lifecycle checks.
- Confirmed 5m, 15m, 1h, 4h, 1d, and 1w feature frames are cached. Live-cache snapshots use a generation key plus candle-window boundaries, avoiding a full OHLCV hash on every event; offline/test providers retain content-hash validation. A 1m/5m event can reuse unchanged higher-timeframe SMC features.
- The live SMC scan now explicitly disables derivatives, trades, and order-book collection; its input evidence is OHLCV only.
- The optional in-process POI gate can use active OB/FVG, liquidity-pool, OTE, confirmed swing, prior-period, and sweep levels from completed 5m+ feature frames. It is **disabled by default** with `AICFA_ARMED_ZONE_GATE_ENABLED=false`; only enable it after the read-only historical replay is available and setup-candidate false negatives are acceptable. Empty/unready caches and concurrent refreshes fail open.

## Remaining architectural work

- The 1m/5m gate is experimental and remains disabled until the self-hosted read-only VDS replay can run. An earlier OB/FVG-only replay skipped some raw structural confirmations, so structural swing, sweep, liquidity, and OTE levels were added. Do not enable the gate in production until replay reports setup-candidate miss rates for a meaningful sample.
- If a READY long candidate's entire execution candle is already above its entry zone, or a short candidate's entire candle is below its zone, the lifecycle emits `MISSED_BY_PRICE`, records the direction-specific entry limit, and persists the terminal status. The terminal watch card shows the limit rather than inviting a chase entry.
- Notifications are intentionally out of scope for this implementation; the priority is correct event-driven OHLCV analysis and lifecycle state.
- Feature reuse is incremental at the snapshot/cache level, but a changed timeframe still rebuilds its feature frame; true candle-by-candle incremental SMC state updates remain future work.
- Latency targets (1–3 seconds) must be measured on the production VDS under live load; they are not inferred from the design alone.
