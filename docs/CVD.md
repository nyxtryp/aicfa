# AICFA — CVD / Cumulative Taker Delta

## Purpose

CVD is a cumulative representation of taker buy volume minus taker sell volume.
It is a descriptive order-flow state feature, not a trade signal.

## Source contract

Required fields:
- timestamp — availability timestamp of a completed flow interval;
- taker_buy_volume;
- taker_sell_volume.

Optional:
- reset — explicit boolean marker that starts a new cumulative segment.

The implementation does not infer resets from arbitrary calendar boundaries. Without
documented reset semantics, CVD is cumulative over the supplied source sequence.

## Calculation

taker_delta = taker_buy_volume - taker_sell_volume

Without resets: CVD_t = CVD_(t-1) + taker_delta_t.

When reset=True, that observation starts a new cumulative segment.

## Causality

Source timestamps are availability times. A base observation at T may use only source
intervals with timestamp <= T. CVD uses backward as-of alignment and is carried
forward only as the latest known state. Future flow cannot alter earlier CVD.

## Scope limitation

This implementation does not claim to reconstruct an exchange-native lifetime, session,
or account-specific CVD unless the supplied source defines that scope.
If historical data is loaded in independent chunks, chunk boundaries must be explicit;
concatenating chunks without a continuity contract can produce a different CVD series.
CVD is not used as a standalone LONG/SHORT rule.