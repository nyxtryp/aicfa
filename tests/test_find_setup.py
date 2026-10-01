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

    def fetch_trades(self, *, symbol, market_type, limit):
        self.trade_calls = getattr(self, "trade_calls", [])
        self.trade_calls.append((symbol, market_type, limit))
        base = 60 * 60_000
        return pd.DataFrame({
            "timestamp": [base + i * 10_000 for i in range(min(limit, 60))],
            "price": np.full(min(limit, 60), 100.0),
            "volume": np.full(min(limit, 60), 1.0),
            "side": ([1] * min(limit, 60) if self.direction == "buy" else [1 if i % 2 == 0 else -1 for i in range(min(limit, 60))]),
        })

    def fetch_order_book(self, *, symbol, market_type, limit=1):
        self.book_calls = getattr(self, "book_calls", [])
        self.book_calls.append((symbol, market_type, limit))
        return pd.DataFrame({
            "timestamp": [90 * 60_000],
            "bid_price": [99.9],
            "bid_size": [5.0],
            "ask_price": [100.1],
            "ask_size": [4.0],
        })

    def fetch_order_book_history(self, *, symbol, market_type, snapshots, interval_seconds):
        self.history_calls = getattr(self, "history_calls", [])
        self.history_calls.append((symbol, market_type, snapshots, interval_seconds))
        base = 60 * 60_000
        return pd.DataFrame({
            "timestamp": [base + i * 10_000 for i in range(snapshots)],
            "bid_price": np.full(snapshots, 99.9),
            "bid_size": [5.0 + i for i in range(snapshots)],
            "ask_price": np.full(snapshots, 100.1),
            "ask_size": [4.0] * snapshots,
        })


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



def test_find_setup_uses_dependency_depth_when_no_diagnostic_limit_is_given():
    provider = FakeProvider()
    find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
    )
    assert [call[4] for call in provider.calls] == [60] * 7 + [120] * 7 + [240] * 7



class BoundedProvider(FakeProvider):
    def fetch_ohlcv(self, *, symbol, market_type, timeframe, since_ms, limit):
        self.calls.append((symbol, market_type, timeframe, since_ms, limit))
        return candles(min(limit, 130), timeframe=timeframe)


def test_find_setup_expands_missing_context_until_provider_boundary():
    provider = BoundedProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
    )

    assert result.decision in {"LONG", "SHORT", "WAIT", "NO TRADE"}
    assert [call[4] for call in provider.calls if call[2] == "1m"] == [60, 120, 240]
    assert [call[4] for call in provider.calls if call[2] == "1w"] == [60, 120, 240]
    assert len(result.frames["1m"]) == 130


class UnboundedNoContextProvider(FakeProvider):
    """Provider boundary is intentionally absent; expansion must still terminate."""


def test_find_setup_stops_expansion_when_context_signature_stalls():
    provider = UnboundedNoContextProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
    )

    assert result.decision in {"LONG", "SHORT", "WAIT", "NO TRADE"}
    assert all(call[4] in {60, 120, 240} for call in provider.calls)
    assert [call[4] for call in provider.calls if call[2] == "1m"] == [60, 120, 240]


def test_find_setup_feeds_request_scoped_microstructure_data():
    provider = FakeProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert provider.trade_calls == [("BTC/USDT", "spot", 60)]
    assert provider.book_calls == [("BTC/USDT", "spot", 1)]
    assert not result.trades.empty
    assert not result.order_book.empty
    assert not result.order_flow_analysis.empty
    assert result.order_flow_analysis["taker_net_volume"].notna().any()
    assert not result.order_book_analysis.empty
    assert result.trades_provider
    assert result.order_book_provider


def test_find_setup_integrates_causal_l1_history_and_absorption():
    provider = FakeProvider("buy")
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert provider.history_calls == [("BTC/USDT", "spot", 8, 1.0)]
    assert result.order_book_history_provider == "fakeprovider"
    assert len(result.order_book_history) == 8
    assert not result.absorption_analysis.empty
    assert result.absorption_analysis["timestamp"].is_monotonic_increasing


def test_find_setup_exposes_causal_trade_cvd():
    provider = FakeProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert not result.cvd_analysis.empty
    assert result.cvd_analysis["cvd"].notna().any()
    assert np.isclose(result.cvd_analysis.iloc[-1]["cvd"], 0.0)
