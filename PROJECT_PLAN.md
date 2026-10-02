# AICFA PROJECT PLAN / CONTINUITY

## Continuity checkpoint — 2026-10-03 — TASK 5 FVG / IMBALANCE LIFECYCLE

### What was done
- Task 4 — Order Block Lifecycle is GREEN.
- Server full regression before Task 5: 377 passed in 44.89s.
- Audited current FVG implementation and unified SMC integration before changing code.
- Confirmed features.py already propagates FVG fields and passes FVG data into unified SMC.
- Task 5 implementation committed:
- 76257aa — feat: add causal FVG lifecycle depth
- 82d6dde — test: cover FVG lifecycle states and concurrent zones
- FVG lifecycle now distinguishes UNTOUCHED, TOUCHED, PARTIAL, FILLED, INVALIDATED.
- Added causal penetration ratio 0..1.
- Added FVG creation provenance fields.
- Multiple simultaneously active bullish/bearish FVG zones are tracked independently instead of a newer zone overwriting an older active zone.
- Existing binary fields are retained for compatibility.
- Added focused regression coverage for creation, touch/partial/fill, invalidation, concurrent active zones and causal provenance.

### Verification status
- Server focused FVG test has NOT yet been run.
- No Task 5 GREEN status is claimed yet.
- Exact command: sudo -u fd-aicfa bash -lc 'cd "$(readlink -f /srv/frostdeploy/aicfa/current)" && PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python -m pytest -q tests/test_fvg.py'

### Current task
Task 5 — FVG / Imbalance Lifecycle

### Immediate next step
1. Run tests/test_fvg.py on the server.
2. If focused tests pass, run full PYTHONWARNINGS=ignore PYTHONPATH=src .venv/bin/python -m pytest -q.
3. Record actual server results here.
4. Only after full regression is GREEN, close Task 5 and proceed to Task 6 — Zone Reaction + Support/Resistance.

## Authoritative SMC integration sequence
1. Confirmed Swing — GREEN.
2. Causal BOS / CHoCH / MSS — GREEN.
3. Liquidity Lifecycle — GREEN.
4. Order Block Lifecycle — GREEN.
5. FVG / Imbalance Lifecycle — ACTIVE.
6. Zone Reaction + Support/Resistance — NEXT.
7. Volume Evidence.
8. Structural Entry / SL / TP.
9. Conservative Backtest / Evaluation.

## Product UX requirement
End-user UX remains asset-only: user enters an asset such as BTC; AICFA internally evaluates all relevant setup variants/horizons and returns the available setup scenarios. User does not select the trading mode.

## Core architecture rules
- AICFA is a specialized crypto-analysis system, not a wrapper around another AI.
- Core analysis is chart/market-data native.
- SMC includes market structure, liquidity, BOS/CHoCH/MSS, HH/HL/LH/LL, FVG/imbalance, Order Blocks, premium/discount, displacement, Wyckoff and related price-action evidence.
- Optional derivatives/microstructure feeds remain auxiliary evidence and do not independently manufacture setups.
- No fabricated missing data.
- All structural/lifecycle logic must remain causal; no future leakage.
- Do not import external fixed strategy, scoring, timeframe hierarchy, killzones, fixed RR or trade labels.
- Every meaningful implementation/test/deploy step must be recorded here with commit SHA, actual server result, status and next step.