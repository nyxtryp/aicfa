import numpy as np
import pandas as pd
import pytest

from aicfa.order_book import build_order_book


def _base():
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=5, freq="min", tz="UTC"),
            "close": [100, 101, 102, 103, 104],
        }
    )


def _book():
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01 00:01:00+00:00",
                    "2026-01-01 00:03:00+00:00",
                ]
            ),
            "bid_price": [99.9, 101.9],
            "ask_price": [100.1, 102.1],
            "bid_size": [10.0, 20.0],
            "ask_size": [5.0, 10.0],
        }
    )


def test_order_book_is_causally_aligned():
    out = build_order_book(_base(), _book())

    assert np.isnan(out.loc[0, "bid_price"])
    assert out.loc[1, "bid_price"] == pytest.approx(99.9)
    assert out.loc[2, "bid_price"] == pytest.approx(99.9)
    assert out.loc[3, "bid_price"] == pytest.approx(101.9)
    assert out.loc[4, "bid_price"] == pytest.approx(101.9)


def test_bid_ask_imbalance_and_microprice():
    out = build_order_book(_base(), _book())

    assert out.loc[1, "bid_ask_imbalance"] == pytest.approx(1 / 3)
    assert out.loc[1, "mid_price"] == pytest.approx(100.0)
    assert out.loc[1, "microprice"] == pytest.approx(100.0333333333)


def test_depth_features_are_optional_and_causal():
    book = _book().copy()
    book["bid_depth_volume"] = [100.0, 160.0]
    book["ask_depth_volume"] = [80.0, 120.0]

    out = build_order_book(_base(), book)

    assert np.isnan(out.loc[0, "depth_imbalance"])
    assert out.loc[1, "depth_total_volume"] == pytest.approx(180.0)
    assert out.loc[1, "depth_imbalance"] == pytest.approx(20 / 180)
    assert out.loc[2, "depth_imbalance"] == pytest.approx(20 / 180)
    assert out.loc[3, "depth_imbalance"] == pytest.approx(40 / 280)


def test_future_order_book_changes_do_not_change_past_results():
    original = _book()
    altered = original.copy()
    altered.loc[1, ["bid_price", "ask_price", "bid_size", "ask_size"]] = [
        90.0,
        90.2,
        1000.0,
        1.0,
    ]

    first = build_order_book(_base(), original)
    second = build_order_book(_base(), altered)

    pd.testing.assert_frame_equal(first.iloc[:3], second.iloc[:3])


def test_order_book_rejects_crossed_market():
    book = _book().copy()
    book.loc[0, "bid_price"] = 100.2

    with pytest.raises(ValueError, match="bid_price cannot exceed ask_price"):
        build_order_book(_base(), book)


def test_order_book_rejects_negative_size():
    book = _book().copy()
    book.loc[0, "bid_size"] = -1

    with pytest.raises(ValueError, match="bid_size must be non-negative"):
        build_order_book(_base(), book)


def test_order_book_requires_top_of_book_fields():
    with pytest.raises(ValueError, match="missing required columns"):
        build_order_book(
            _base(),
            pd.DataFrame({"timestamp": ["2026-01-01T00:01:00Z"]}),
        )


def test_zero_top_size_produces_nan_ratios():
    book = _book().copy()
    book.loc[0, ["bid_size", "ask_size"]] = [0.0, 0.0]

    out = build_order_book(_base(), book)

    assert np.isnan(out.loc[1, "bid_ask_imbalance"])
    assert np.isnan(out.loc[1, "microprice"])


def test_snapshot_changes_are_source_order_deltas():
    out = build_order_book(_base(), _book())

    assert np.isnan(out.loc[1, "bid_size_delta"])
    assert out.loc[3, "bid_size_delta"] == pytest.approx(10.0)
    assert out.loc[3, "ask_size_delta"] == pytest.approx(5.0)
