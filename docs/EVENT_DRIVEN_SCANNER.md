# Event-driven live scanner

## Runtime contract

- Binance closed-kline events are the normal analysis triggers. Scalping reacts to 1m and 5m closes, Intraday to 15m, Swing to 1h, and Position to 4h.
- Each symbol/timeframe has a FIFO dispatch lane. Confirmed candles are not replaced by newer events when analysis is slow.
- A candle checkpoint advances only after its scan succeeds. A failed event remains queued for retry.
- When a WebSocket stream exhausts bounded reconnects, the coordinator fetches actual closed OHLCV rows after the last checkpoint and submits them in timestamp order before restarting the stream.
- The legacy one-market rotation is a safety net only after no closed candle has arrived for 180 seconds.
- The continuous ticker stream remains separate for active setup SL/TP lifecycle checks.
- Confirmed 15m, 1h, 4h, 1d, and 1w feature frames are cached by the full OHLCV snapshot. A 1m/5m event can reuse unchanged higher-timeframe SMC features.

## Telegram

Configure both `AICFA_TELEGRAM_BOT_TOKEN` and `AICFA_TELEGRAM_CHAT_ID`. The `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` aliases are also accepted. Messages are sent asynchronously from a durable outbox, only for newly activated setup lifecycle events. Delivery retries survive process restarts and successful setup identities are deduplicated.

## Remaining architectural work

- The scanner does not yet skip every unarmed symbol on 1m/5m. Higher-timeframe feature reuse is implemented, but the canonical setup pipeline still runs for each configured trigger event.
- A pending setup with an explicit maximum acceptable entry and a visible `missed by price` lifecycle status is not yet implemented. Current lifecycle activation requires the execution candle to touch the entry zone.
- Telegram currently notifies newly activated setups; watch-only/pending candidates are not sent as signals.
- Latency targets (1–3 seconds) must be measured on the production VDS under live load; they are not inferred from the design alone.
