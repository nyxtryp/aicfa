import numpy as np
import pandas as pd
import pytest
from aicfa.structure import build_structure

def frame(close, high=None, low=None):
    close=np.asarray(close,dtype=float); high=close+0.5 if high is None else np.asarray(high,dtype=float); low=close-0.5 if low is None else np.asarray(low,dtype=float)
    return pd.DataFrame({"timestamp":pd.date_range("2026-01-01",periods=len(close),freq="min",tz="UTC").astype("int64")//10**6,"open":close,"high":high,"low":low,"close":close})

def test_swing_confirmation_delay():
    df=frame([100,101,105,102,101,103,100],[100.5,101.5,106,102.5,101.5,103.5,100.5],[99.5,100.5,104.5,101.5,100.5,102.5,99.5])
    r=build_structure(df,left=2,right=2); assert r.loc[2,"swing_high"]==0; assert r.loc[4,"swing_high"]==1; assert r.loc[4,"swing_high_price"]==106

def test_hh_hl_lh_ll():
    close=[100,102,105,102,101,103,108,104,102,104,101,102,96]; highs=[c+.4 for c in close]; lows=[c-.4 for c in close]
    highs[2],lows[2]=106,104; highs[4],lows[4]=101.5,100; highs[6],lows[6]=109,107; highs[8],lows[8]=102.5,101; highs[9],lows[9]=104.4,103; highs[10],lows[10]=102,99; highs[11],lows[11]=102.4,100; highs[12],lows[12]=96.5,95
    r=build_structure(frame(close,highs,lows),left=1,right=1); assert r["hh"].sum()>=1 and r["hl"].sum()>=1 and r["lh"].sum()>=1 and r["ll"].sum()>=1

def test_internal_structure_is_exposed_and_causal():
    base=frame([100,102,105,102,99,101,98,100,104,102,106,103]); altered=base.copy(); altered.loc[8:,["high","low","close"]]*=[1000,0.001,500]
    a=build_structure(base,left=2,right=2,internal_left=1,internal_right=1); b=build_structure(altered,left=2,right=2,internal_left=1,internal_right=1)
    for column in ["internal_swing_high","internal_swing_low","internal_hh","internal_hl","internal_lh","internal_ll","internal_bos_up","internal_bos_down","internal_choch_up","internal_choch_down"]: assert column in a.columns
    pd.testing.assert_frame_equal(a.iloc[:8],b.iloc[:8],check_dtype=False)

def test_protected_levels_follow_bos_and_have_lifecycle():
    close=[100,102,105,102,99,101,98,100,104]; r=build_structure(frame(close),left=1,right=1)
    assert r.loc[6,"bos_down"]==1; assert r.loc[6,"protected_high_created"]==1; assert r.loc[6,"protected_high_active"]==1; assert r.loc[6,"protected_high_price"]==pytest.approx(101.5)
    assert r.loc[8,"bos_up"]==1; assert r.loc[8,"protected_low_created"]==1; assert r.loc[8,"protected_low_active"]==1; assert r.loc[8,"protected_low_price"]==pytest.approx(97.5); assert r.loc[8,"protected_high_broken"]==1

def test_bos_and_choch_reference_only_confirmed_swings():
    # With right=2, the swing high at pivot 2 is unavailable until row 4.
    # The later break must reference confirmation row 4, never pivot row 2.
    close = [100, 102, 105, 102, 101, 103, 107]
    highs = [100.5, 102.5, 106, 102.5, 101.5, 103.5, 108]
    lows = [99.5, 101.5, 104, 101.5, 100.5, 102.5, 106]
    r = build_structure(frame(close, highs, lows), left=2, right=2)

    assert r.loc[4, "swing_high"] == 1
    assert r.loc[6, "bos_up"] == 1
    assert r.loc[6, "bos_up_reference_pivot_index"] == 2
    assert r.loc[6, "bos_up_reference_confirmation_index"] == 4
    assert r.loc[6, "bos_up_reference_confirmation_index"] > r.loc[6, "bos_up_reference_pivot_index"]


def test_bos_does_not_repeat_a_consumed_level():
    close = [100, 102, 105, 102, 101, 103, 107, 106, 107.5, 108]
    r = build_structure(frame(close), left=1, right=1)

    bos_rows = r.index[r["bos_up"] == 1].tolist()
    assert bos_rows
    assert len(bos_rows) == len(set(bos_rows))


def test_mss_requires_displacement_and_is_not_choch_rename():
    close=[100,102,105,102,99,101,98,100,104]; df=frame(close); displacement=pd.DataFrame({"displacement_up":[0,0,0,0,0,0,0,0,1],"displacement_down":[0]*9})
    without=build_structure(df,left=1,right=1); with_displacement=build_structure(df,left=1,right=1,displacement=displacement)
    assert without.loc[8,"choch_up"]==1; assert without.loc[8,"mss_up"]==0; assert with_displacement.loc[8,"choch_up"]==1; assert with_displacement.loc[8,"mss_up"]==1

def test_displacement_shape_and_columns_are_validated():
    df=frame([1,2,1,2,1])
    with pytest.raises(ValueError): build_structure(df,displacement=pd.DataFrame({"displacement_up":[0]*5}))
    with pytest.raises(ValueError): build_structure(df,displacement=pd.DataFrame({"displacement_up":[0]*4,"displacement_down":[0]*4}))

def test_no_future_lookahead():
    base=frame([100+np.sin(i/2) for i in range(80)]); altered=base.copy(); altered.loc[50:,["high","low","close"]]*=[1000,0.001,500]
    a=build_structure(base); b=build_structure(altered); pd.testing.assert_frame_equal(a.iloc[:50],b.iloc[:50],check_dtype=False)

def test_invalid_parameters():
    with pytest.raises(ValueError): build_structure(frame([1,2,1]),left=0)
    with pytest.raises(ValueError): build_structure(frame([1,2,1]),right=0)
    with pytest.raises(ValueError): build_structure(frame([1,2,1]),internal_left=0)

def test_swing_confirmation_contract_exposes_pivot_and_availability_time():
    df = frame(
        [100, 101, 105, 102, 101, 103, 100],
        [100.5, 101.5, 106, 102.5, 101.5, 103.5, 100.5],
        [99.5, 100.5, 104.5, 101.5, 100.5, 102.5, 99.5],
    )
    r = build_structure(df, left=2, right=2)

    assert r.loc[4, "swing_high"] == 1
    assert r.loc[4, "swing_high_pivot_index"] == 2
    assert r.loc[4, "swing_high_confirmation_index"] == 4
    assert r.loc[4, "swing_high_pivot_timestamp"] == df.loc[2, "timestamp"]
    assert r.loc[4, "swing_high_confirmation_timestamp"] == df.loc[4, "timestamp"]

    # The pivot candle itself is descriptive only; availability starts at
    # the confirmation row.
    assert r.loc[2, "swing_high"] == 0
    assert r.loc[2, "swing_high_confirmation_index"] == -1


def test_swing_confirmation_delay_is_configurable():
    df = frame(
        [100, 101, 105, 102, 101, 103, 100],
        [100.5, 101.5, 106, 102.5, 101.5, 103.5, 100.5],
        [99.5, 100.5, 104.5, 101.5, 100.5, 102.5, 99.5],
    )
    r = build_structure(df, left=2, right=3)

    assert r.loc[5, "swing_high"] == 1
    assert r.loc[5, "swing_high_pivot_index"] == 2
    assert r.loc[5, "swing_high_confirmation_index"] == 5
