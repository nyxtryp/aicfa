import numpy as np
import pandas as pd
import pytest

from aicfa.find_setup import CAUSAL_TIMEFRAMES, FindSetupRequest, find_setup, normalize_asset, parse_find_setup


TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
}


def candles(n=120, start=0, timeframe="1m"):
    close = np.arange(n, dtype=float) + 100
    step = TIMEFRAME_MS[timeframe]
    return pd.DataFrame({
        "timestamp": [start + i * step for i in range(n)],
        "open": close - 0.5,
        "high": close + 1,
        "low": close - 1,
        "close": close,
        "volume": np.full(n, 10.0),
    })


class FakeProvider:
    def __init__(self, direction="none"):
        self.calls = []
        self.direction = direction

    def fetch_ohlcv(self, *, symbol, market_type, timeframe, since_ms, limit):
        self.calls.append((symbol, market_type, timeframe, since_ms, limit))
        return candles(limit, timeframe=timeframe)


def test_normalize_asset_preserves_explicit_quote():
    assert normalize_asset(" btc-usdt ") == "BTC/USDT"
    assert normalize_asset("SOL/USDT") == "SOL/USDT"
    assert normalize_asset("DOGE") == "DOGE"


@pytest.mark.parametrize("text, expected", [
    ("Найди сетап BTC/USDT", "BTC/USDT"),
    ("найди сетап sol-usdt", "SOL/USDT"),
    ("Find Setup DOGE/USDT", "DOGE/USDT"),
])
def test_parse_find_setup_extracts_asset(text, expected):
    assert parse_find_setup(text).asset == expected


def test_parse_find_setup_rejects_empty_request():
    with pytest.raises(ValueError):
        parse_find_setup("")


def test_find_setup_fetches_exactly_seven_causal_timeframes():
    provider = FakeProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert result.timeframes == CAUSAL_TIMEFRAMES
    assert result.timeframes == tuple(call[2] for call in provider.calls)
    assert tuple(call[2] for call in provider.calls) == CAUSAL_TIMEFRAMES
    assert all(call[0] == "BTC/USDT" for call in provider.calls)
    assert all(call[1] == "spot" for call in provider.calls)
    assert result.analysis["timestamp"].is_monotonic_increasing


def test_find_setup_does_not_decide_from_an_open_latest_candle():
    provider = FakeProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert result.analysis["timestamp"].max() < 120 * 60_000
    assert result.decision in {"LONG", "SHORT", "WAIT", "NO TRADE"}


def test_find_setup_uses_authoritative_market_evidence_decision_chain():
    provider = FakeProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert result.evidence.asset == "BTC/USDT"
    assert result.evidence.source == "market_data"
    assert result.decision == result.decision_assessment.action.value.upper().replace("_", " ")
    assert result.decision_assessment.reasons


def test_find_setup_resolves_user_asset_before_market_data_fetch():
    provider = FakeProvider()
    seen = []

    def resolver(asset, market_type):
        seen.append((asset, market_type))
        return "DOGE/USDT"

    result = find_setup(
        FindSetupRequest("DOGE"),
        provider=provider,
        resolver=resolver,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert seen == [("DOGE", "spot")]
    assert result.symbol == "DOGE/USDT"
    assert result.evidence.asset == "DOGE/USDT"
    assert all(call[0] == "DOGE/USDT" for call in provider.calls)

