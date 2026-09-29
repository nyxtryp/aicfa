"""Causal data reliability and freshness state for AICFA."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import pandas as pd

class DataFreshness(str, Enum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"

@dataclass(frozen=True)
class ConfirmedMarketState:
    data: pd.DataFrame
    last_update_ms: int | None
    def __post_init__(self):
        if self.last_update_ms is not None and int(self.last_update_ms) < 0:
            raise ValueError("last_update_ms must be non-negative")
        object.__setattr__(self, "data", self.data.copy())

@dataclass(frozen=True)
class FreshnessSnapshot:
    status: DataFreshness
    last_update_ms: int | None
    data_age_ms: int | None
    max_age_ms: int

class LocalMarketStateStore:
    """Retain latest confirmed state independently of provider health."""
    def __init__(self, *, max_age_ms: int):
        if max_age_ms <= 0: raise ValueError("max_age_ms must be positive")
        self.max_age_ms=int(max_age_ms); self._states={}
    def update(self, key, data: pd.DataFrame, *, observed_at_ms: int):
        if int(observed_at_ms) < 0: raise ValueError("observed_at_ms must be non-negative")
        state=ConfirmedMarketState(data, int(observed_at_ms)); self._states[key]=state
        return ConfirmedMarketState(state.data, state.last_update_ms)
    def get(self, key):
        state=self._states.get(key)
        return None if state is None else ConfirmedMarketState(state.data, state.last_update_ms)
    def freshness(self, key, *, now_ms: int):
        if int(now_ms) < 0: raise ValueError("now_ms must be non-negative")
        state=self._states.get(key)
        if state is None or state.last_update_ms is None:
            return FreshnessSnapshot(DataFreshness.UNAVAILABLE,None,None,self.max_age_ms)
        age=max(0,int(now_ms)-state.last_update_ms)
        status=DataFreshness.FRESH if age <= self.max_age_ms else DataFreshness.STALE
        return FreshnessSnapshot(status,state.last_update_ms,age,self.max_age_ms)
