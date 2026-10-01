## 2026-10-01 — Repair MarketEvidence timeframe column mapping

### Finding
Focused verification of the first MarketEvidence repair produced:
`2 failed, 6 passed`.

The failures exposed a mapping bug in the adapter: it read base-timeframe columns for every requested timeframe, causing the same 1m observations to be emitted repeatedly, and it did not resolve the existing `mtf_<timeframe>_...` columns used by the integrated feature frame.

### Forward fix
- `1b0b71a2fa465adb23187d5c88bd8747efecde11` — make MarketEvidence resolve columns by timeframe.
- Base `1m` uses canonical columns.
- Higher timeframes use the existing `mtf_<timeframe>_<column>` state columns.
- Lifecycle columns use the corresponding timeframe-prefixed state when present.
- No analytical rules or causal boundaries were changed.

### Verification
The repair is committed to Git but has not yet been deployed/verified on FrostDeploy.

### Exact next step
Deploy current `main` and rerun:
1. `tests/test_market_evidence_adapter.py`
2. the three adaptive FindSetup tests
3. full pytest
4. live BTC FindSetup smoke without explicit `limit`.
