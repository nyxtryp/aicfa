import pandas as pd
import pytest
from aicfa.data_reliability import DataFreshness, LocalMarketStateStore

def frame(close=100.0):
    return pd.DataFrame({"timestamp":[0],"open":[99.0],"high":[101.0],"low":[98.0],"close":[close],"volume":[10.0]})

def test_local_store_retains_last_confirmed_state_when_provider_is_unavailable():
    key=("binance","BTC/USDT","spot","1m"); store=LocalMarketStateStore(max_age_ms=60000)
    store.update(key,frame(),observed_at_ms=120000)
    state=store.get(key); freshness=store.freshness(key,now_ms=150000)
    assert state is not None and state.last_update_ms==120000
    assert state.data["close"].tolist()==[100.0]
    assert freshness.status is DataFreshness.FRESH and freshness.data_age_ms==30000

def test_local_state_becomes_stale_without_fabricating_new_data():
    key=("binance","BTC/USDT","spot","1m"); store=LocalMarketStateStore(max_age_ms=60000)
    store.update(key,frame(),observed_at_ms=120000)
    freshness=store.freshness(key,now_ms=181000); state=store.get(key)
    assert freshness.status is DataFreshness.STALE and freshness.data_age_ms==61000
    assert state.data["timestamp"].tolist()==[0]

def test_unknown_state_is_unavailable():
    store=LocalMarketStateStore(max_age_ms=60000)
    assert store.freshness(("missing",),now_ms=1).status is DataFreshness.UNAVAILABLE

def test_store_rejects_invalid_configuration_and_time():
    with pytest.raises(ValueError): LocalMarketStateStore(max_age_ms=0)
    store=LocalMarketStateStore(max_age_ms=60000)
    with pytest.raises(ValueError): store.update(("x",),frame(),observed_at_ms=-1)
