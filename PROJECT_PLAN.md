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


## 2026-10-01 — MarketEvidence base-timeframe repair

### Finding
FrostDeploy verification of `1b0b71a` still had 2 failures:
- base 1m FVG was missing;
- independent 4h analysis was missing.

Root cause: the adapter's column resolver assumed every non-1m timeframe required `mtf_<timeframe>_...`. That is correct when reading a combined multi-timeframe frame, but incorrect for `build_market_evidence_from_frames()`, where each independent frame contains its own canonical/base columns.

### Forward fix
- `91c7216f6a98881ecf567c6ac93d13af54601619`
- Column resolution is now relative to `base_timeframe`.
- The base timeframe reads canonical columns.
- Other requested timeframes read `mtf_<timeframe>_...`.
- Lifecycle state follows the same rule.
- No rollback and no change to analytical concepts or causal policy.

### Verification
Not yet deployed/verified.

### Exact next step
Deploy current `main` and rerun the focused MarketEvidence + adaptive FindSetup tests. If green, continue to mandatory full pytest and live BTC FindSetup smoke.


## MarketEvidence follow-up — bb00dd0f60e7af67ddc5a9635b42c0bb463bca47
- Finding: build_market_evidence() used a single emitted flag, so once BOS/displacement/etc. emitted, later FVG/Order Block concepts were skipped even when independently active.
- Fix: track emitted_concepts and suppress only a concept already emitted by its lifecycle path; independent supported concepts can now coexist.
- Status: code committed; deployment/verification pending.
- Exact next step: deploy current main, then rerun the focused MarketEvidence + adaptive FindSetup tests. If green, run full pytest.


## MarketEvidence verification — 2026-10-01
- Focused verification: 8 passed, 9217 warnings, 15.97s.
- Full suite verification: 305 passed, 18145 warnings, 47.09s.
- Result: MarketEvidence repair and adaptive FindSetup regression coverage are GREEN on the deployed current release.
- Performance optimization remains backlog; analytical development continues forward.
- Exact next step: proceed to the next analytical roadmap item after MarketEvidence repair.
