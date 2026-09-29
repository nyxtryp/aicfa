# AICFA — Data Reliability / Freshness

External providers are inputs, not dependencies of the analytical core.

`LocalMarketStateStore` retains the latest confirmed state and tracks
`last_update_ms`. Freshness is calculated explicitly:

- `FRESH` — within configured `max_age_ms`;
- `STALE` — older than the freshness window;
- `UNAVAILABLE` — no confirmed local state.

A stale state remains available for descriptive analysis, but is never treated
as a new observation. This layer never fabricates candles, prices, trades or
order-book observations.

Later REST recovery, WebSocket and provider failover can all update the same
store without changing the analytical core.