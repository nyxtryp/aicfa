# Binance Incremental WebSocket Transport

AICFA now has a provider-agnostic incremental WebSocket transport with a concrete Binance kline implementation.

## Current behavior

- Spot endpoint: `wss://stream.binance.com:9443/ws`
- USDⓈ-M Futures endpoint: `wss://fstream.binance.com/ws`
- subscription uses Binance `SUBSCRIBE`;
- only **closed** kline events are accepted as confirmed observations;
- open/incomplete candles are ignored;
- malformed or incomplete events fail explicitly;
- stream identity is checked against symbol and timeframe;
- disconnects use bounded exponential reconnect backoff;
- each reconnect resubscribes the configured streams;
- confirmed observations can be written directly to `LocalMarketStateStore`;
- exhausted reconnects raise `WebSocketTransportError`;
- no missing candles or prices are fabricated.

## Architectural boundary

The analytical core does not depend on `websocket-client`. The runtime connector is injected, which keeps transport testing deterministic and allows another WebSocket implementation later.

The Binance transport is still a data-input layer. It does not decide whether a market state is fresh enough for a live setup. Freshness remains the responsibility of `LocalMarketStateStore` and the future scanner/decision integration.

## Current limitation

The implementation currently consumes Binance kline streams. Derivatives side channels (funding, open interest, liquidations, order book, etc.) remain separate transport work and are not silently inferred from kline messages.

The first live deployment smoke test should verify that the server can establish the real Spot and Futures WebSocket connections, receive closed BTC/USDT candles, reconnect after a disconnect, and update the local confirmed-state boundary.
