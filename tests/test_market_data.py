import pandas as pd
import pytest

from aicfa.market_data import (
    BASE_TIMEFRAMES,
    MarketKey,
    completed_ohlcv,
    merge_ohlcv,
    next_since_ms,
    timeframe_ms,
    validate_ohlcv,
)


def candles(timestamps):
    return pd.DataFrame({
        "timestamp": timestamps,
        "open": [100.0 + i for i in range(len(timestamps))],
        "high": [101.0 + i for i in range(len(timestamps))],
        "low": [99.0 + i for i in range(len(timestamps))],
        "close": [100.5 + i for i in range(len(timestamps))],
        "volume": [10.0 + i for i in range(len(timestamps))],
    })


def test_base_timeframes_are_explicit():
    assert BASE_TIMEFRAMES == ("1m", "5m", "15m", "1h", "4h", "1d", "1w", "1M")


def test_market_key_validates_market_context():
    assert MarketKey("binance", "BTC/USDT", "spot", "1m")
    with pytest.raises(ValueError):
        MarketKey("binance", "BTC/USDT", "margin", "1m")


def test_validate_ohlcv_deduplicates_and_sorts():
    frame = candles([120000, 60000, 120000])
    out = validate_ohlcv(frame)
    assert out["timestamp"].tolist() == [60000, 120000]


def test_validate_ohlcv_rejects_bad_ohlc():
    frame = candles([60000])
    frame.loc[0, "high"] = 99.0
    with pytest.raises(ValueError):
        validate_ohlcv(frame)


def test_completed_ohlcv_excludes_open_candle():
    frame = candles([0, 60000, 120000])
    out = completed_ohlcv(frame, timeframe="1m", now_ms=150000)
    assert out["timestamp"].tolist() == [0, 60000]


def test_merge_is_idempotent_and_keeps_newest_duplicate():
    first = candles([0, 60000])
    second = candles([60000, 120000])
    second.loc[0, "close"] = 100.75
    out = merge_ohlcv(first, second)
    assert out["timestamp"].tolist() == [0, 60000, 120000]
    assert out.loc[1, "close"] == 100.75


def test_next_since_uses_next_candle_open():
    frame = candles([0, 60000])
    assert next_since_ms(frame, timeframe="1m") == 120000


def test_month_timeframe_uses_calendar_completion_and_cursor():
    frame = candles([
        int(pd.Timestamp("2026-01-01", tz="UTC").timestamp() * 1000),
        int(pd.Timestamp("2026-02-01", tz="UTC").timestamp() * 1000),
    ])
    february_start = int(pd.Timestamp("2026-02-15", tz="UTC").timestamp() * 1000)
    out = completed_ohlcv(frame, timeframe="1M", now_ms=february_start)
    assert out["timestamp"].tolist() == [
        int(pd.Timestamp("2026-01-01", tz="UTC").timestamp() * 1000)
    ]
    assert next_since_ms(frame.iloc[[0]], timeframe="1M") == int(
        pd.Timestamp("2026-02-01", tz="UTC").timestamp() * 1000
    )
