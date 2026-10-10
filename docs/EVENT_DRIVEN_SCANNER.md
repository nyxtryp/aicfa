# Event-driven live scanner

## Runtime contract

- Binance closed-kline events are the normal analysis triggers. Scalping reacts to 1m and 5m closes, Intraday to 15m, Swing to 1h, and Position to 4h.
- Each symbol/timeframe has a FIFO dispatch lane. Confirmed candles are not replaced by newer events when analysis is slow.
- A candle checkpoint advances only after its scan succeeds. A failed event remains queued for retry.
- When a WebSocket stream exhausts bounded reconnects, the coordinator fetches actual closed OHLCV rows after the last checkpoint and submits them in timestamp order before restarting the stream.
- The legacy one-market rotation is a safety net only after no closed candle has arrived for 180 seconds.
- The continuous ticker stream remains separate for active setup SL/TP lifecycle checks.
- Confirmed 15m, 1h, 4h, 1d, and 1w feature frames are cached by the full OHLCV snapshot. A 1m/5m event can reuse unchanged higher-timeframe SMC features.
- The live SMC scan now explicitly disables derivatives, trades, and order-book collection; its input evidence is OHLCV only.
- A bounded in-process zone cache retains active OB/FVG bounds from completed 5m+ feature frames. 1m candle events outside all cached zones are acknowledged without running the full setup pipeline; events that overlap a zone run the canonical Scalping analysis.

## Remaining architectural work

- The 1m gate is based on the latest active OB/FVG bounds exposed by the cached feature frames. Its skip rate and false-negative behavior must be measured against historical replay before production rollout.
- If a READY long candidate's entire execution candle is already above its entry zone, or a short candidate's entire candle is below its zone, the lifecycle emits `MISSED_BY_PRICE`, records the direction-specific entry limit, and persists the terminal status. The terminal watch card shows the limit rather than inviting a chase entry.
- Notifications are intentionally out of scope for this implementation; the priority is correct event-driven OHLCV analysis and lifecycle state.
- Latency targets (1–3 seconds) must be measured on the production VDS under live load; they are not inferred from the design alone.
