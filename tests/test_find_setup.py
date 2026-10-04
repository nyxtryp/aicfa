import numpy as np
import pandas as pd
import pytest

from aicfa.data_requirements import TradingMode
from aicfa.find_setup import CAUSAL_TIMEFRAMES, FindSetupRequest, find_setup, normalize_asset, parse_find_setup
from aicfa.market_data_router import MarketFetchResult


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
    if timeframe == "1M":
        timestamps = [int(ts.timestamp() * 1000) for ts in pd.date_range("1970-01-01", periods=n, freq="MS", tz="UTC")]
    else:
        step = TIMEFRAME_MS[timeframe]
        timestamps = [start + i * step for i in range(n)]
    return pd.DataFrame({
        "timestamp": timestamps,
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

    def fetch_order_book_history_with_source(self, *, symbol, market_type, snapshots, interval_seconds):
        frame = self.fetch_order_book_history(
            symbol=symbol, market_type=market_type,
            snapshots=snapshots, interval_seconds=interval_seconds,
        )
        return MarketFetchResult(
            provider="fakeprovider",
            symbol=symbol,
            frame=frame,
        )

    def fetch_order_book_history(self, *, symbol, market_type, snapshots, interval_seconds):
        self.history_calls = getattr(self, "history_calls", [])
        self.history_calls.append((symbol, market_type, snapshots, interval_seconds))
        base = 60 * 60_000
        return pd.DataFrame({
            "timestamp": [base + i * 10_000 for i in range(snapshots)],
            "bid_price": np.full(snapshots, 99.96),
            "bid_size": [5.0 + i for i in range(snapshots)],
            "ask_price": np.full(snapshots, 100.04),
            "ask_size": [4.0 + 2.0 * i for i in range(snapshots)],
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


def test_find_setup_fetches_only_selected_intraday_timeframes():
    provider = FakeProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT", mode="intraday"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert result.mode is TradingMode.INTRADAY
    assert result.timeframes == ("4h", "1h", "15m", "5m")
    assert result.timeframes == tuple(call[2] for call in provider.calls)
    assert tuple(call[2] for call in provider.calls) == ("4h", "1h", "15m", "5m")
    assert all(call[0] == "BTC/USDT" for call in provider.calls)
    assert all(call[1] == "spot" for call in provider.calls)
    assert result.analysis["timestamp"].is_monotonic_increasing


@pytest.mark.parametrize("mode, expected", [
    ("scalping", ("15m", "5m", "1m")),
    ("intraday", ("4h", "1h", "15m", "5m")),
    ("swing", ("1d", "4h", "1h")),
    ("position", ("1w", "1d", "4h")),
])
def test_find_setup_timeframes_match_exact_mode_contract(mode, expected):
    provider = FakeProvider()
    now_ms = 400 * 24 * 60 * 60_000 if mode == "position" else 120 * 60_000
    result = find_setup(
        FindSetupRequest("BTC/USDT", mode=mode),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=now_ms,
        limit=120,
    )
    assert result.timeframes == expected
    assert tuple(call[2] for call in provider.calls) == expected
    if mode != "scalping":
        assert "1m" not in result.timeframes
        assert all(call[2] != "1m" for call in provider.calls)


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



def test_find_setup_uses_mode_aware_analysis_depth_when_no_diagnostic_limit_is_given():
    provider = FakeProvider()
    find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
    )
    # FindSetup defaults to Intraday: the first pass uses the role-aware
    # baseline 4h=120, 1h=180, 15m=240, 5m=240. Missing context may
    # trigger up to two adaptive expansion passes.
    limits = [call[4] for call in provider.calls]
    assert limits[:4] == [120, 180, 240, 240]
    assert len(limits) <= 12
    assert all(limit >= baseline for limit, baseline in zip(limits[:4], [120, 180, 240, 240]))
    assert limits[4:] == [240, 360, 480, 480, 480, 720, 960, 960]



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
    assert [call[4] for call in provider.calls if call[2] == "4h"] == [120, 240]
    assert [call[4] for call in provider.calls if call[2] == "1h"] == [180, 360]
    assert len(result.frames["5m"]) == 130


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
    assert all(call[4] in {120, 180, 240, 360, 480, 720, 960} for call in provider.calls)
    assert [call[4] for call in provider.calls if call[2] == "4h"] == [120, 240, 480]


def test_find_setup_does_not_fetch_optional_microstructure_by_default():
    provider = FakeProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert getattr(provider, "trade_calls", []) == []
    assert getattr(provider, "book_calls", []) == []
    assert getattr(provider, "history_calls", []) == []
    assert result.trades.empty
    assert result.order_book.empty
    assert result.order_flow_analysis.empty
    assert result.order_book_analysis.empty
    assert result.cvd_analysis.empty
    assert result.absorption_analysis.empty


def test_find_setup_does_not_fetch_l1_history_or_absorption_by_default():
    provider = FakeProvider("buy")
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert getattr(provider, "history_calls", []) == []
    assert result.order_book_history.empty
    assert result.order_book_history_provider == ""
    assert result.absorption_analysis.empty


def test_find_setup_does_not_expose_trade_cvd_without_explicit_requirement():
    provider = FakeProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert result.cvd_analysis.empty
    assert getattr(provider, "trade_calls", []) == []

def test_find_setup_reuses_order_book_history_snapshot_for_futures():
    provider = FakeProvider()
    result = find_setup(
        FindSetupRequest("BTC/USDT", market_type="futures", mode="intraday"),
        provider=provider,
        resolver=lambda asset, market_type: asset,
        now_ms=120 * 60_000,
        limit=120,
    )

    assert not result.order_book_history.empty
    assert result.order_book.shape[0] == 1
    assert provider.history_calls == [("BTC/USDT", "futures", 8, 0.25)]
    assert getattr(provider, "book_calls", []) == []

