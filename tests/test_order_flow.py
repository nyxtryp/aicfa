import numpy as np
import pandas as pd
import pytest

from aicfa.order_flow import build_order_flow


def base_frame(n=8):
    ts = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame({"timestamp": ts})


def flow_frame():
    # Timestamp is availability/close time, not interval open time.
    ts = pd.date_range(
        "2026-01-01T00:00:30Z", periods=4, freq="2min", tz="UTC"
    )
    return pd.DataFrame(
        {
            "timestamp": ts,
            "taker_buy_volume": [60.0, 40.0, 80.0, 20.0],
            "taker_sell_volume": [40.0, 60.0, 20.0, 80.0],
        }
    )


def test_order_flow_aligns_only_completed_intervals():
    out = build_order_flow(base_frame(), flow_frame(), baseline_window=2)

    assert pd.isna(out.loc[0, "taker_net_volume"])
    assert np.isclose(out.loc[1, "taker_net_volume"], 20.0)
    assert np.isclose(out.loc[3, "taker_net_volume"], -20.0)


def test_order_flow_derives_sell_volume_from_total():
    d = flow_frame().drop(columns=["taker_sell_volume"])
    d["total_volume"] = d["taker_buy_volume"] + [40.0, 60.0, 20.0, 80.0]

    out = build_order_flow(base_frame(), d, baseline_window=2)

    assert np.isclose(out.loc[1, "taker_sell_volume"], 40.0)
    assert np.isclose(out.loc[1, "taker_imbalance"], 0.2)
    assert np.isclose(out.loc[1, "taker_buy_share"], 0.6)


def test_order_flow_is_causal_under_future_changes():
    base = base_frame()
    d = flow_frame()

    altered = d.copy()
    altered.loc[
        altered["timestamp"] >= pd.Timestamp("2026-01-01T00:06:30Z"),
        "taker_buy_volume",
    ] *= 10
    altered.loc[
        altered["timestamp"] >= pd.Timestamp("2026-01-01T00:06:30Z"),
        "taker_sell_volume",
    ] *= 0.1

    a = build_order_flow(base, d, baseline_window=2)
    b = build_order_flow(base, altered, baseline_window=2)
    pd.testing.assert_frame_equal(a.iloc[:6], b.iloc[:6], check_dtype=False)


def test_order_flow_computes_deltas_changes_and_zscores():
    out = build_order_flow(base_frame(), flow_frame(), baseline_window=2)

    for col in (
        "taker_buy_volume_delta",
        "taker_buy_volume_change_pct",
        "taker_buy_volume_zscore",
        "taker_net_volume_delta",
        "taker_imbalance_zscore",
    ):
        assert col in out


def test_order_flow_rejects_inconsistent_total():
    d = flow_frame()
    d["total_volume"] = d["taker_buy_volume"] + d["taker_sell_volume"] + 1.0

    with pytest.raises(ValueError):
        build_order_flow(base_frame(), d, baseline_window=2)


def test_order_flow_rejects_negative_values():
    d = flow_frame()
    d.loc[1, "taker_buy_volume"] = -1.0

    with pytest.raises(ValueError):
        build_order_flow(base_frame(), d, baseline_window=2)


def test_order_flow_requires_sell_or_total_volume():
    d = flow_frame().drop(columns=["taker_sell_volume"])

    with pytest.raises(ValueError):
        build_order_flow(base_frame(), d, baseline_window=2)


def test_order_flow_handles_zero_total_volume():
    d = flow_frame()
    d.loc[0, "taker_buy_volume"] = 0.0
    d.loc[0, "taker_sell_volume"] = 0.0

    out = build_order_flow(base_frame(), d, baseline_window=2)

    assert pd.isna(out.loc[1, "taker_imbalance"])
