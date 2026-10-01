import pandas as pd
import pytest

from aicfa.microstructure import compute_book_state, compute_trade_flow


def test_trade_flow_uses_venue_aggressor_side():
    trades = pd.DataFrame(
        [
            {"timestamp": 1, "price": 100, "volume": 2, "side": 1},
            {"timestamp": 2, "price": 101, "volume": 1, "side": -1},
            {"timestamp": 3, "price": 102, "volume": 3, "side": 1},
        ]
    )
    result = compute_trade_flow(trades)
    assert result.buy_volume == 5
    assert result.sell_volume == 1
    assert result.signed_volume == 4
    assert result.imbalance == pytest.approx(4 / 6)
    assert result.buy_count == 2
    assert result.sell_count == 1


def test_trade_flow_is_causal_under_future_append():
    base = pd.DataFrame(
        [{"timestamp": 1, "price": 100, "volume": 2, "side": 1}]
    )
    future = pd.DataFrame(
        [{"timestamp": 2, "price": 80, "volume": 100, "side": -1}]
    )
    first = compute_trade_flow(base)
    extended = compute_trade_flow(pd.concat([base, future], ignore_index=True))
    assert first.signed_volume == 2
    assert extended.signed_volume == -98


def test_trade_flow_rejects_unknown_side():
    trades = pd.DataFrame(
        [{"timestamp": 1, "price": 100, "volume": 1, "side": 0}]
    )
    with pytest.raises(ValueError, match="side must be -1 or \+1"):
        compute_trade_flow(trades)


def test_trade_flow_rejects_non_causal_order():
    trades = pd.DataFrame(
        [
            {"timestamp": 2, "price": 100, "volume": 1, "side": 1},
            {"timestamp": 1, "price": 100, "volume": 1, "side": -1},
        ]
    )
    with pytest.raises(ValueError, match="sorted causally"):
        compute_trade_flow(trades)


def test_book_state_uses_latest_observed_quote_only():
    book = pd.DataFrame(
        [
            {"timestamp": 1, "bid_price": 99, "bid_size": 4, "ask_price": 101, "ask_size": 2},
            {"timestamp": 2, "bid_price": 100, "bid_size": 8, "ask_price": 102, "ask_size": 2},
        ]
    )
    result = compute_book_state(book)
    assert result.bid_price == 100
    assert result.ask_price == 102
    assert result.spread == 2
    assert result.spread_bps == pytest.approx(2 / 101 * 10_000)
    assert result.imbalance == pytest.approx(6 / 10)


def test_book_state_rejects_crossed_book():
    book = pd.DataFrame(
        [{"timestamp": 1, "bid_price": 101, "bid_size": 1, "ask_price": 100, "ask_size": 1}]
    )
    with pytest.raises(ValueError, match="ask price"):
        compute_book_state(book)


def test_book_state_rejects_negative_depth():
    book = pd.DataFrame(
        [{"timestamp": 1, "bid_price": 99, "bid_size": -1, "ask_price": 100, "ask_size": 1}]
    )
    with pytest.raises(ValueError, match="non-negative"):
        compute_book_state(book)


def test_empty_trade_flow_is_deterministic():
    result = compute_trade_flow(
        pd.DataFrame(columns=["timestamp", "price", "volume", "side"])
    )
    assert result.signed_volume == 0
    assert result.imbalance == 0
