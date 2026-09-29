# Absorption source contract

## Purpose

Absorption is a **descriptive market-microstructure event candidate**, not a
LONG/SHORT signal. It describes a completed backward time window in which
aggressive taker flow meets persistent/replenished displayed liquidity while
the contemporaneous price response remains limited.

## Required synchronized inputs

### Price
`timestamp, open, high, low, close`

The timestamp is the availability/close timestamp of the completed price
observation. Only observations at or before event time T may be used.

### Taker Flow
`timestamp, taker_buy_volume, taker_sell_volume`

The timestamp is the availability timestamp of the completed flow interval.
For Binance futures, the documented taker-buy/sell volume endpoint provides
period observations, while kline data also exposes taker-buy volume; the
source timestamp must be interpreted according to the selected feed contract.

### Level-by-level Order Book
`timestamp, side, price, size`

The timestamp is the availability timestamp of a complete snapshot. Level
changes are calculated between consecutive complete snapshots.

## Causal event window

For event time T and configured duration W, the observation window is:

`(T-W, T]`

No price, flow, or book observation after T may influence the event at T.

## Absorption candidate conditions

The implementation requires all of the following:

1. **Aggressive flow:** absolute taker imbalance reaches the configured
   threshold. Buy imbalance is evaluated against ask liquidity; sell imbalance
   against bid liquidity.
2. **Displayed liquidity:** a nearby opposing-side level exists within the
   configured price-distance threshold.
3. **Relative liquidity:** the candidate level is materially larger than the
   median visible level on its side in the same snapshot.
4. **Persistence:** the candidate price remains visible across the configured
   number of snapshots.
5. **Replenishment:** displayed additions on the resting side are sufficient
   relative to displayed cancellations during the same window.
6. **Limited contemporaneous response:** absolute close-to-open price response
   remains below the configured threshold and directional efficiency remains
   limited.

The event is emitted as `absorption=True` only when all configured
conditions pass. Otherwise the row remains a descriptive synchronized
microstructure observation with `absorption=False`.

## Important limitation

A displayed order-book level is not proof of execution. Without synchronized
trade-level prices and matching-engine/order identifiers, the system cannot
claim that a particular resting order absorbed a particular set of trades.
This layer therefore deliberately uses the term **absorption candidate**.

## Historical labels

Future price movement must not be used to create the live feature. If later
research wants to test whether an absorption candidate predicts a future
move, that forward movement belongs in a separate outcome/label dataset and
must never be fed back into the causal feature.

## Exchange-source note

Binance documents futures market streams including `aggTrade` and `depth`
streams, and futures market data exposes order-book levels as price/quantity
pairs. These feeds should be collected with their own event/availability
timestamps and synchronized before this layer is applied.
