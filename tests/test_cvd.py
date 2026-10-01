import numpy as np
import pandas as pd
import pytest

from aicfa.cvd import build_cvd


def base_frame(n=8):
    ts = pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame({"timestamp": ts})


def flow_frame():
    ts = pd.date_range("2026-01-01T00:00:30Z", periods=4, freq="2min", tz="UTC")
    return pd.DataFrame({"timestamp": ts, "taker_buy_volume": [60.0,40.0,80.0,20.0], "taker_sell_volume": [40.0,60.0,20.0,80.0]})


def test_cvd_aligns_completed_intervals_causally():
    out=build_cvd(base_frame(), flow_frame())
    assert pd.isna(out.loc[0,"cvd"])
    assert np.isclose(out.loc[1,"cvd"],20.0)
    assert np.isclose(out.loc[3,"cvd"],0.0)
    assert np.isclose(out.loc[5,"cvd"],60.0)


def test_cvd_supports_explicit_resets():
    d=flow_frame(); d["reset"]=[True,False,True,False]
    out=build_cvd(base_frame(),d)
    assert np.isclose(out.loc[1,"cvd"],20.0)
    assert np.isclose(out.loc[3,"cvd"],0.0)
    assert np.isclose(out.loc[5,"cvd"],60.0)


def test_cvd_is_causal_under_future_changes():
    base=base_frame(); d=flow_frame(); altered=d.copy()
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:06:30Z"),"taker_buy_volume"]*=10
    altered.loc[altered["timestamp"] >= pd.Timestamp("2026-01-01T00:06:30Z"),"taker_sell_volume"]*=0.1
    a=build_cvd(base,d); b=build_cvd(base,altered)
    pd.testing.assert_frame_equal(a.iloc[:6],b.iloc[:6],check_dtype=False)


def test_cvd_exposes_delta_and_change():
    out=build_cvd(base_frame(),flow_frame())
    assert np.isclose(out.loc[3,"cvd_delta"],-20.0)
    assert np.isclose(out.loc[5,"cvd_delta"],60.0)
    assert "cvd_change_pct" in out


def test_cvd_rejects_negative_flow():
    d=flow_frame(); d.loc[1,"taker_sell_volume"]=-1.0
    with pytest.raises(ValueError): build_cvd(base_frame(),d)


def test_cvd_future_rows_do_not_backfill_earlier_state():
    d=flow_frame()
    original=build_cvd(base_frame(),d)
    d.loc[3,"taker_buy_volume"]=9999.0
    altered=build_cvd(base_frame(),d)
    # The modified source row becomes available at 00:06:30, after base row 5.
    # Earlier CVD must remain exactly unchanged.
    pd.testing.assert_frame_equal(original.iloc[:6], altered.iloc[:6], check_dtype=False)


def trade_frame():
    ts = [1000, 1000, 2000, 3000]
    return pd.DataFrame({
        "timestamp": ts,
        "price": [100, 100, 101, 100],
        "volume": [2.0, 3.0, 4.0, 1.0],
        "side": [1, -1, 1, -1],
    })


def test_trade_cvd_preserves_same_timestamp_trades_and_is_causal():
    from aicfa.cvd import build_trade_cvd

    base = pd.DataFrame({
        "timestamp": pd.to_datetime([500, 1000, 2000, 3000], unit="ms", utc=True)
    })
    out = build_trade_cvd(base, trade_frame())
    assert np.isclose(out.loc[1, "cvd"], -1.0)
    assert np.isclose(out.loc[2, "cvd"], 3.0)
    assert np.isclose(out.loc[3, "cvd"], 2.0)

    altered = trade_frame()
    altered.loc[3, "volume"] = 999.0
    changed = build_trade_cvd(base, altered)
    pd.testing.assert_frame_equal(
        out.iloc[:3], changed.iloc[:3], check_dtype=False
    )


def test_trade_cvd_rejects_invalid_side():
    from aicfa.cvd import build_trade_cvd

    bad = trade_frame()
    bad.loc[0, "side"] = 0
    base = pd.DataFrame({
        "timestamp": pd.to_datetime([1000], unit="ms", utc=True)
    })
    with pytest.raises(ValueError):
        build_trade_cvd(base, bad)
