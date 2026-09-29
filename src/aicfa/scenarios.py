"""Causal market-scenario engine for AICFA.

Converts already-observed market-state events into mechanically defined
scenario hypotheses. It does not produce a score or count confirmations.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

_REQUIRED = [
    "timestamp","open","high","low","close","volume",
    "smc_structure_direction","smc_structure_event","smc_structure_shift",
    "smc_liquidity_event","smc_sweep_low_reclaim","smc_sweep_high_reclaim",
    "smc_displacement_direction","smc_displacement_bos_up",
    "smc_displacement_bos_down","smc_state_ready",
]

def _validate_state(df: pd.DataFrame) -> pd.DataFrame:
    missing=[c for c in _REQUIRED if c not in df.columns]
    if missing: raise ValueError(f"Missing required scenario-state columns: {missing}")
    x=df.copy().sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for c in ["open","high","low","close","volume"]: x[c]=x[c].astype(float)
    if (x["high"] < x[["open","close"]].max(axis=1)).any(): raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open","close"]].min(axis=1)).any(): raise ValueError("Invalid OHLC: low is above open/close")
    if (x["volume"] < 0).any(): raise ValueError("Invalid volume: negative values are not allowed")
    return x

def build_scenarios(df: pd.DataFrame) -> pd.DataFrame:
    """Build causal scenario hypotheses from an already-built market state."""
    x=_validate_state(df); out=x.copy()
    direction=x["smc_structure_direction"].fillna(0).astype(float)
    event=x["smc_structure_event"].fillna(0).astype(float)
    shift=x["smc_structure_shift"].fillna(0).astype(float)
    liq=x["smc_liquidity_event"].fillna(0).astype(float)
    low_reclaim=x["smc_sweep_low_reclaim"].fillna(0).astype(float)
    high_reclaim=x["smc_sweep_high_reclaim"].fillna(0).astype(float)
    disp=x["smc_displacement_direction"].fillna(0).astype(float)
    bos_up=x["smc_displacement_bos_up"].fillna(0).astype(float)
    bos_down=x["smc_displacement_bos_down"].fillna(0).astype(float)
    ready=x["smc_state_ready"].fillna(0).astype(float)
    prev=direction.shift(1).fillna(0)

    out["scenario_expansion_up"]=((disp==1)&(bos_up==1)).astype("int8")
    out["scenario_expansion_down"]=((disp==-1)&(bos_down==1)).astype("int8")
    out["scenario_continuation_up"]=((direction==1)&(disp==1)&((bos_up==1)|(prev==1))).astype("int8")
    out["scenario_continuation_down"]=((direction==-1)&(disp==-1)&((bos_down==1)|(prev==-1))).astype("int8")
    out["scenario_reversal_up"]=((shift==1)|((low_reclaim==1)&(disp==1))).astype("int8")
    out["scenario_reversal_down"]=((shift==-1)|((high_reclaim==1)&(disp==-1))).astype("int8")
    out["scenario_failed_breakout_up"]=((liq==-1)&(high_reclaim==1)).astype("int8")
    out["scenario_failed_breakout_down"]=((liq==1)&(low_reclaim==1)).astype("int8")
    out["scenario_range"]=((ready==1)&(event==0)&(disp==0)).astype("int8")

    names=["expansion_up","expansion_down","reversal_up","reversal_down",
           "failed_breakout_up","failed_breakout_down","continuation_up",
           "continuation_down","range"]
    matrix=np.column_stack([out[f"scenario_{n}"].to_numpy() for n in names]).astype(bool)
    counts=matrix.sum(axis=1)
    labels=np.array(names,dtype=object)
    out["scenario_event"]=np.where(counts==1,labels[matrix.argmax(axis=1)],"")
    direction_map={"expansion_up":1,"expansion_down":-1,"reversal_up":1,
                   "reversal_down":-1,"failed_breakout_up":-1,
                   "failed_breakout_down":1,"continuation_up":1,
                   "continuation_down":-1}
    out["scenario_direction"]=out["scenario_event"].map(direction_map).fillna(0).astype("int8")
    out["scenario_active"]=(counts>0).astype("int8")
    out["scenario_entry_reference"]=x["close"].astype(float)
    out["scenario_invalidation_reference"]=np.nan
    return out
