import numpy as np
import pandas as pd
import pytest

from aicfa.order_book_levels import (
    build_level_changes,
    build_liquidity_walls,
    build_order_book_flow,
)


def _levels():
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01 00:01:00Z",
                    "2026-01-01 00:01:00Z",
                    "2026-01-01 00:02:00Z",
                    "2026-01-01 00:02:00Z",
                    "2026-01-01 00:03:00Z",
                    "2026-01-01 00:03:00Z",
                ]
            ),
            "side": ["bid", "ask"] * 3,
            "price": [99.0, 101.0, 99.0, 101.0, 99.0, 101.0],
            "size": [10.0, 5.0, 14.0, 3.0, 0.0, 8.0],
        }
    )


def test_level_changes_capture_additions_and_cancellations():
    out = build_level_changes(_levels())

    bid = out[(out["timestamp"] == pd.Timestamp("2026-01-01 00:02:00Z")) & (out["side"] == "bid")]
    assert bid.iloc[0]["size_delta"] == pytest.approx(4.0)
    assert bid.iloc[0]["added_size"] == pytest.approx(4.0)
    assert bid.iloc[0]["cancelled_size"] == pytest.approx(0.0)

    ask = out[(out["timestamp"] == pd.Timestamp("2026-01-01 00:02:00Z")) & (out["side"] == "ask")]
    assert ask.iloc[0]["size_delta"] == pytest.approx(-2.0)
    assert ask.iloc[0]["cancelled_size"] == pytest.approx(2.0)


def test_level_removal_is_explicit():
    out = build_level_changes(_levels())
    row = out[
        (out["timestamp"] == pd.Timestamp("2026-01-01 00:03:00Z"))
        & (out["side"] == "bid")
        & (out["price"] == 99.0)
    ].iloc[0]

    assert row["level_removed"]
    assert row["cancelled_size"] == pytest.approx(14.0)


def test_order_book_flow_aggregates_by_side():
    out = build_order_book_flow(_levels())
    row = out[out["timestamp"] == pd.Timestamp("2026-01-01 00:02:00Z")].iloc[0]

    assert row["bid_added_volume"] == pytest.approx(4.0)
    assert row["ask_cancelled_volume"] == pytest.approx(2.0)
    assert row["net_displayed_bid_change"] == pytest.approx(4.0)
    assert row["net_displayed_ask_change"] == pytest.approx(-2.0)


def test_liquidity_wall_requires_persistence():
    levels = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01 00:01:00Z",
                    "2026-01-01 00:01:00Z",
                    "2026-01-01 00:02:00Z",
                    "2026-01-01 00:02:00Z",
                    "2026-01-01 00:03:00Z",
                    "2026-01-01 00:03:00Z",
                ]
            ),
            "side": ["bid", "bid"] * 3,
            "price": [99.0, 98.0] * 3,
            "size": [100.0, 10.0, 100.0, 10.0, 100.0, 10.0],
        }
    )

    out = build_liquidity_walls(levels, min_persistence=3, quantile=0.9)
    wall = out[(out["price"] == 99.0) & (out["timestamp"] == pd.Timestamp("2026-01-01 00:03:00Z"))].iloc[0]
    early = out[(out["price"] == 99.0) & (out["timestamp"] == pd.Timestamp("2026-01-01 00:02:00Z"))].iloc[0]

    assert wall["liquidity_wall"]
    assert not early["liquidity_wall"]
    assert wall["persistence_count"] == pytest.approx(3.0)


def test_future_snapshot_change_does_not_modify_past_level_changes():
    original = _levels()
    altered = original.copy()
    altered.loc[altered["timestamp"] == pd.Timestamp("2026-01-01 00:03:00Z"), "size"] = [500.0, 1.0]

    first = build_level_changes(original)
    second = build_level_changes(altered)

    pd.testing.assert_frame_equal(
        first[first["timestamp"] <= pd.Timestamp("2026-01-01 00:02:00Z")].reset_index(drop=True),
        second[second["timestamp"] <= pd.Timestamp("2026-01-01 00:02:00Z")].reset_index(drop=True),
    )


def test_validation_rejects_invalid_side():
    levels = _levels().copy()
    levels.loc[0, "side"] = "middle"

    with pytest.raises(ValueError, match="side must be 'bid' or 'ask'"):
        build_level_changes(levels)


def test_validation_rejects_negative_size():
    levels = _levels().copy()
    levels.loc[0, "size"] = -1

    with pytest.raises(ValueError, match="size must be non-negative"):
        build_level_changes(levels)
