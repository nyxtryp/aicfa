# AICFA — Binance Market Data Adapter

## Status

Binance is the first concrete provider implemented against the provider-agnostic
`MarketDataProvider` contract. This stage is an OHLCV REST adapter for BTC/USDT
and other compatible symbols; it does not yet lock Binance as the final
production provider for the full 24/7 system.

## Current transport

- Spot public klines: `data-api.binance.vision/api/v3/klines`.
- USDⓈ-M futures public klines: `fapi.binance.com/fapi/v1/klines`.
- No API key is required for these public market-data endpoints.
- Symbol input accepts `BTC/USDT` or `BTCUSDT` and is normalized to Binance format.
- The adapter returns only the canonical six OHLCV fields required by AICFA.
- Incremental requests use `startTime` when `since_ms` is supplied.
- The adapter caps requests at 1000 rows so the scanner default remains conservative.
- `1M` is deliberately deferred to provider-aware scanner semantics.

Binance documents public market-data-only REST access without authentication,
including the klines endpoint. See the official documentation reviewed during
implementation.

## Reliability boundary

This adapter currently does not implement:

- retry/backoff;
- rate-limit scheduling;
- WebSocket transport;
- persistent raw-data storage;
- automatic reconnect;
- provider failover.

Those concerns remain separate from the analytical Feature Engine and will be
implemented only after their operational requirements are defined.

## Provider assessment

For the current BTC/USDT prototype, Binance has the required public REST OHLCV
transport and public WebSocket market-data infrastructure. Binance also publishes
bulk public historical market data. These facts make it suitable for the next
prototype integration step.

It is **not yet declared the permanent production provider**. Before that decision
AICFA must verify operational limits, latency, reconnect behavior, historical
coverage, regional/network accessibility, commercial/usage terms and the needs
of the future Top-100 scanner.

## REST recovery and failure handling

The Binance adapter now applies bounded recovery before surfacing a transport failure:

- network/timeout errors are retryable;
- HTTP 429 and 5xx responses are retryable;
- HTTP 4xx responses other than 429 are treated as non-recoverable;
- retries use exponential backoff;
- the retry count and initial backoff are configurable;
- after the retry budget is exhausted, the adapter raises an explicit BinanceTransportError with a retryable classification;
- the adapter never fabricates OHLCV data after a failed request.

This transport layer does not own stale-state decisions. The existing LocalMarketStateStore remains the boundary that preserves the last confirmed state and exposes FRESH/STALE/UNAVAILABLE.
