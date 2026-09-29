# AICFA Label Engine v2

## Status

This specification replaces the first experimental label implementation.

The previous design used one ATR barrier (close ± 1 ATR) for every horizon and encoded both an unresolved timeout and an intrabar double-touch as the same class. That is not the production target design for AICFA.

## Research basis

The design follows established financial-ML ideas:

- path-dependent triple-barrier labeling;
- volatility-scaled horizontal barriers;
- explicit vertical/maximum-holding barriers;
- separation of directional side prediction from meta-labeling;
- MFE/MAE path statistics;
- awareness that overlapping future labels require purged/embargoed validation.

These methods are described in López de Prado's Advances in Financial Machine Learning, especially Chapters 3, 4 and 7.

## 1. Label families

AICFA does not have one universal "buy/sell/wait" label.

### A. Path targets

For each configured horizon H:

- future simple return;
- future log return;
- MFE for long;
- MFE for short;
- MAE for long;
- MAE for short;
- volatility-normalized MFE/MAE;
- time to maximum favorable excursion;
- causal target volatility used for normalization.

These are regression/path targets. They preserve information instead of collapsing the future path into one class.

### B. Event targets

For each horizon H, construct a volatility-scaled triple-barrier event:

- upper profit-taking barrier;
- lower stop-loss barrier;
- vertical maximum-holding barrier.

Horizontal widths are:

upper = entry * exp(pt_mult * target_vol)
lower = entry * exp(-sl_mult * target_vol)

where target_vol is a causal EWMA standard deviation of log returns.

pt_mult and sl_mult are research parameters. They are not declared optimal and must be selected only through training-period research and out-of-sample validation.

## 2. Event semantics

Each event stores:

- event outcome;
- first-touch type;
- realized event return;
- realized event log return;
- event end offset;
- target volatility;
- ambiguity flag.

First-touch semantics:

- upper barrier first → event_touch = +1;
- lower barrier first → event_touch = -1;
- vertical barrier first → event_touch = 0.

For a vertical-barrier exit, event_outcome uses the sign of the realized return. This avoids manufacturing a huge artificial WAIT class merely because the maximum holding time expired.

### Intrabar ambiguity

If one OHLC candle touches both horizontal barriers, OHLC data cannot tell which happened first.

AICFA therefore:

- marks event_ambiguous = 1;
- does not assign an event winner;
- leaves event_outcome missing for that event.

It must not silently call such a case WAIT or LONG.

When finer-grained data exists, the event can be replayed using that finer data to resolve the path.

## 3. What the model learns

The first AICFA models should not directly learn the final user-facing decision.

### Direction model

Learn directional opportunity from event/path targets.

Possible outputs:

- P(long);
- P(short);
- expected return;
- expected favorable/adverse excursion.

### Meta / trade-quality model

Given a proposed side, learn:

- probability the side reaches its objective before its stop;
- expected side-adjusted return;
- adverse excursion;
- time to resolution.

Meta-labeling is conditional on a proposed side and therefore naturally produces a binary take/pass target rather than another LONG/SHORT target.

### Decision Engine

Only later combine model outputs with:

- fees;
- slippage;
- funding;
- risk limits;
- regime;
- scenario constraints;
- invalidation;
- available information.

The user-facing states remain:

LONG / SHORT / WAIT / NO TRADE

WAIT/NO TRADE are decisions, not a mandatory primitive ground-truth class in the raw label engine.

## 4. Horizons

The current research horizons remain:

- 5 bars;
- 20 bars;
- 60 bars.

They are research horizons, not permanent AICFA truth.

Mode-specific targets will later be selected for:

- Scalping;
- Intraday;
- Swing;
- Position.

Longer timeframes will use appropriately defined horizons rather than inheriting 60 bars blindly.

## 5. Leakage rules

Labels may use future prices.

Features may not.

Every event must expose its effective end time/offset so later validation can purge overlapping training observations.

Random shuffled k-fold is forbidden for these overlapping financial labels. Chronological splits and, for model-selection CV, purged/embargoed validation are required.

## 6. Why there is no single WAIT label

A WAIT decision can mean very different things:

- no statistical edge;
- conflicting scenarios;
- insufficient information;
- excessive transaction cost;
- poor risk/reward;
- ambiguous data;
- model uncertainty.

Those are not the same market outcome.

AICFA should therefore learn measurable future outcomes and let the Decision/Risk layers determine whether the current evidence warrants a trade.

## 7. Research protocol

Barrier and horizon parameters are not chosen by making the class distribution look pretty.

For every candidate configuration:

1. fit/research only on the training period;
2. inspect class/event rates;
3. inspect MFE/MAE and event duration;
4. include fees/slippage/funding assumptions where applicable;
5. train the relevant model;
6. validate chronologically;
7. use purging/embargoing when labels overlap;
8. evaluate out-of-sample;
9. keep the configuration only if the economics survive the validation process.

No configuration is accepted because it produced a visually balanced label distribution.

## 8. Data retention

Raw market data and causal processed features are retained.

Old generated label CSVs and old training datasets must be deleted before rebuilding the new label/dataset artifacts. They are derived products, not source data.

## 9. Next stages

After Label Engine v2:

1. delete old derived labels and datasets;
2. rebuild labels;
3. validate label distributions and ambiguity rates;
4. build task-specific training datasets;
5. implement purged/embargoed validation;
6. train the first CPU-friendly baseline;
7. evaluate out-of-sample;
8. only then begin the AICFA model/decision layer.
