import numpy as np
import pandas as pd
import pytest

from aicfa.multi_timeframe import build_multi_timeframe_structure

def candles(start: str, periods: int, freq: str, base: float = 100.0) -> pd.DataFrame:
    ts = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    close = base + np.arange(periods, dtype=float)
    return pd.DataFrame({
        "timestamp": ts.astype("int64") // 10**6,
        "open": close - 0.25, "high": close + 0.5, "low": close - 0.5,
        "close": close, "volume": np.full(periods, 100.0),
    })

def test_higher_timeframe_state_is_not_available_before_candle_close():
    base = candles("2026-01-01", 30, "5min")
    htf = candles("2026-01-01", 3, "1h")
    result = build_multi_timeframe_structure(base, {"1h": htf}, structure_left=1, structure_right=1)
    column = "mtf_1h_structure_direction"
    assert result.loc[0:11, column].isna().all()
    assert not pd.isna(result.loc[12, column])

def test_structure_events_are_mapped_only_after_their_confirming_htf_close():
    base = candles("2026-01-01", 60, "5min")
    htf = candles("2026-01-01", 5, "1h")
    htf.loc[2, "high"] = 110.0
    htf.loc[2, "close"] = 109.0
    htf.loc[2, "open"] = 108.0
    htf.loc[2, "low"] = 107.0
    result = build_multi_timeframe_structure(base, {"1h": htf}, structure_left=1, structure_right=1)
    swing_col = "mtf_1h_swing_high"
    assert result.loc[:47, swing_col].fillna(0).sum() == 0
    assert result.loc[48:, swing_col].fillna(0).sum() >= 1

def test_future_htf_changes_do_not_change_earlier_base_rows():
    base = candles("2026-01-01", 72, "5min")
    htf = candles("2026-01-01", 8, "1h")
    altered = htf.copy()
    altered.loc[5:, "high"] *= 1000
    altered.loc[5:, "low"] *= 0.001
    altered.loc[5:, "close"] *= 500
    altered.loc[5:, "volume"] *= 100
    a = build_multi_timeframe_structure(base, {"1h": htf})
    b = build_multi_timeframe_structure(base, {"1h": altered})
    pd.testing.assert_frame_equal(a.iloc[:60], b.iloc[:60], check_dtype=False)

def test_multiple_timeframes_are_kept_separate():
    base = candles("2026-01-01", 36, "5min")
    frames = {"15m": candles("2026-01-01", 12, "15min"), "1h": candles("2026-01-01", 4, "1h")}
    result = build_multi_timeframe_structure(base, frames)
    assert "mtf_15m_structure_direction" in result.columns
    assert "mtf_1h_structure_direction" in result.columns
    assert len(result) == len(base)

def test_invalid_timeframe_and_inputs():
    base = candles("2026-01-01", 12, "5min")
    htf = candles("2026-01-01", 2, "1h")
    with pytest.raises(ValueError):
        build_multi_timeframe_structure(base, {"hour": htf})
    with pytest.raises(ValueError):
        build_multi_timeframe_structure(base, {})
    with pytest.raises(ValueError):
        build_multi_timeframe_structure(base, {"1h": htf.assign(volume=-1.0)})
