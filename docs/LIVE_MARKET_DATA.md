# AICFA — Live Market Data / Scanner Foundation

This stage defines the provider-agnostic boundary between live market data and
the existing causal Feature Engine.

## Architecture

Provider / Exchange API / WebSocket adapter
              ↓
      MarketDataProvider
              ↓
      CentralMarketScanner
              ↓
      completed OHLCV only
              ↓
        Feature Engine
              ↓
 Canonical Market State / Setup Events
              ↓
      later notification layer

The provider adapter is intentionally outside the analytical core. AICFA can
therefore add Binance, another exchange, a free API, or a WebSocket adapter
without changing the Feature Engine contract.

## Source contract

A provider must return:

- timestamp
- open
- high
- low
- close
- volume

Provider timestamps represent the **candle-open timestamp**.

Before data reaches the Feature Engine, the scanner filters candles using the
known interval duration. An interval is eligible only when:

timestamp + timeframe_duration <= now

Therefore an open/incomplete candle is never treated as a completed observation.

1M is included in the canonical universe, but monthly completion is deferred
to provider-specific calendar semantics rather than approximating a month as a
fixed number of milliseconds.

## Incremental semantics

For each (exchange, symbol, market_type, timeframe) key:

1. retain local completed history;
2. request data after the latest local candle;
3. merge by timestamp;
4. deduplicate;
5. keep only completed candles;
6. rebuild causal features from the available history;
7. expose only the latest resulting state.

Repeated scan cycles are idempotent with respect to duplicate candles.

## Centralization

The scanner analyzes each configured market key once per cycle. User accounts,
subscriptions and notifications are deliberately absent from this layer.

This is the foundation for later fan-out:

one market analysis → many users.

## Causality

The scanner never passes an open/incomplete candle into the Feature Engine.
Future provider observations cannot rewrite already completed history except for
an explicit provider correction delivered at the same candle timestamp; such
corrections are handled by the idempotent merge and are not interpreted as a
future observation.

## Current limitations

- no concrete exchange adapter is locked yet;
- no WebSocket transport yet;
- no persistent raw-data store yet;
- no retry/backoff policy yet;
- no rate-limit scheduler yet;
- no Top-100 universe discovery yet;
- no user subscriptions/notifications yet;
- 1M completion remains provider-specific;
- derivatives/order-book live transport is not connected yet.

Those are separate implementation stages and are not silently assumed here.

## Next step

Add a concrete provider adapter only after its rate limits, latency, WebSocket
support, historical access, reliability and commercial terms have been checked.
