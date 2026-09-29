import numpy as np
import pandas as pd
import pytest
from aicfa.structure import build_structure

def frame(close, high=None, low=None):
    close=np.asarray(close,dtype=float); high=close+0.5 if high is None else high; low=close-0.5 if low is None else low
    return pd.DataFrame({"timestamp":pd.date_range("2026-01-01",periods=len(close),freq="min",tz="UTC").astype("int64")//10**6,"open":close,"high":high,"low":low,"close":close})

def test_swing_confirmation_delay():
    df=frame([100,101,105,102,101,103,100],[100.5,101.5,106,102.5,101.5,103.5,100.5],[99.5,100.5,104.5,101.5,100.5,102.5,99.5])
    r=build_structure(df,left=2,right=2); assert r.loc[2,"swing_high"]==0; assert r.loc[4,"swing_high"]==1; assert r.loc[4,"swing_high_price"]==106

def test_hh_hl_lh_ll():
    close=[100,102,105,102,101,103,108,104,102,99,101,98,96]; highs=[c+.4 for c in close]; lows=[c-.4 for c in close]
    highs[2],lows[2]=106,104; highs[4],lows[4]=101.5,100; highs[6],lows[6]=109,107; highs[8],lows[8]=102.5,101; highs[10],lows[10]=102,100; highs[12],lows[12]=96.5,95
    r=build_structure(frame(close,highs,lows),left=1,right=1)
    assert r["hh"].sum()>=1 and r["hl"].sum()>=1 and r["lh"].sum()>=1 and r["ll"].sum()>=1

def test_no_future_lookahead():
    base=frame([100+np.sin(i/2) for i in range(80)]); altered=base.copy(); altered.loc[50:,["high","low","close"]]*=[1000,0.001,500]
    a=build_structure(base); b=build_structure(altered); pd.testing.assert_frame_equal(a.iloc[:50],b.iloc[:50],check_dtype=False)

def test_invalid_parameters():
    with pytest.raises(ValueError): build_structure(frame([1,2,1]),left=0)
    with pytest.raises(ValueError): build_structure(frame([1,2,1]),right=0)
