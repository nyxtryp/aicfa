import pandas as pd
import pytest

from aicfa.features import build_features
from aicfa.scenarios import build_scenarios


def sample_state(n=140):
    ts=pd.date_range("2026-01-01",periods=n,freq="min",tz="UTC")
    close=pd.Series(range(n),dtype=float)+100.0
    base=pd.DataFrame({"timestamp":ts.astype("int64")//10**6,"open":close-0.4,
        "high":close+1.0,"low":close-1.0,"close":close,"volume":range(10,10+n)})
    return build_features(base)


def test_scenario_columns():
    result=build_scenarios(sample_state())
    for column in ["scenario_expansion_up","scenario_expansion_down",
        "scenario_continuation_up","scenario_continuation_down",
        "scenario_reversal_up","scenario_reversal_down",
        "scenario_failed_breakout_up","scenario_failed_breakout_down",
        "scenario_range","scenario_event","scenario_direction",
        "scenario_active","scenario_entry_reference",
        "scenario_invalidation_reference"]:
        assert column in result.columns


def test_scenario_has_no_score_or_signal():
    result=build_scenarios(sample_state())
    assert "scenario_score" not in result.columns
    assert "scenario_signal" not in result.columns


def test_failed_breakout_is_mechanical():
    state=sample_state(6)
    state["smc_liquidity_event"]=[0,0,0,-1,0,0]
    state["smc_sweep_high_reclaim"]=[0,0,0,1,0,0]
    result=build_scenarios(state)
    assert result.loc[3,"scenario_failed_breakout_up"]==1


def test_expansion_requires_matching_displacement_and_bos():
    state=sample_state(4)
    state["smc_displacement_direction"]=[0,1,0,-1]
    state["smc_displacement_bos_up"]=[0,0,1,0]
    state["smc_displacement_bos_down"]=[0,0,0,1]
    result=build_scenarios(state)
    assert result["scenario_expansion_up"].tolist()==[0,0,0,0]
    assert result["scenario_expansion_down"].tolist()==[0,0,0,1]


def test_scenario_is_causal_under_future_changes():
    base=sample_state(120)
    altered=base.copy()
    altered.loc[80:,"high"]*=1000
    altered.loc[80:,"low"]*=0.001
    altered.loc[80:,"close"]*=500
    altered.loc[80:,"volume"]*=100
    a=build_scenarios(base)
    b=build_scenarios(altered)
    pd.testing.assert_frame_equal(a.iloc[:80],b.iloc[:80],check_dtype=False)


def test_invalid_state_is_rejected():
    bad=sample_state(10).drop(columns=["smc_structure_direction"])
    with pytest.raises(ValueError):
        build_scenarios(bad)
