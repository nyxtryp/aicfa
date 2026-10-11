# AICFA

Real-time market scanner for 50 crypto markets, focused on scalp and intraday setups.

## Product goals

- Stream market data and scan a configurable universe of 50 liquid USDT perpetual markets.
- Generate explainable LONG/SHORT candidates for scalp and intraday strategies.
- Include entry zone, invalidation/stop, take-profit levels, timeframe, setup score, and rationale.
- Persist signals and their lifecycle so results can be measured rather than guessed.
- Expose a responsive dashboard and health endpoints.
- Start in analysis/paper mode. Live order execution is explicitly out of scope until separately designed and enabled.

## Engineering rules

- No fake signals or fabricated market data presented as live.
- Exchange/API failures must be visible in health state.
- Secrets belong in environment variables, never in Git.
- Strategy logic must be testable and include fees/slippage assumptions in evaluation.
- Keep scanner execution independent of browser sessions.

## Deployment

FreimDeploy is expected to watch the configured Git branch and publish commits automatically. Configure runtime environment variables in the deployment platform, not in source control.
