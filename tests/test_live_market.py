import time
import threading
from types import SimpleNamespace

import pandas as pd

from aicfa.live_market import CandleCheckpoint, PersistentCandleStore, LiveMarketDataCache, LiveMarketCoordinator, LIVE_CANDLE_MODE_TRIGGERS, WINDOWS, BINANCE_WS_MAX_STREAMS, BINANCE_WS_ROTATE_SECONDS, chunk_market_keys
from aicfa.market_data import MarketKey
from aicfa.websocket_market_data import WebSocketObservation


def _frame(start=0, count=3):
    return pd.DataFrame({
        "timestamp": [start + i * 300000 for i in range(count)],
        "open": [100 + i for i in range(count)],
        "high": [101 + i for i in range(count)],
        "low": [99 + i for i in range(count)],
        "close": [100.5 + i for i in range(count)],
        "volume": [10.0] * count,
    })


class Provider:
    def __init__(self):
        self.calls = []

    def resolve_symbol(self, asset, *, market_type="spot"):
        return asset

    def fetch_ohlcv(self, *, symbol, market_type, timeframe, since_ms, limit):
        self.calls.append((symbol, market_type, timeframe, limit))
        return _frame(count=limit)

    def fetch_trades(self, **kwargs):
        raise AssertionError

    def fetch_order_book(self, **kwargs):
        raise AssertionError

    def fetch_order_book_history(self, **kwargs):
        raise AssertionError


def test_one_minute_window_is_configured_for_live_scalping():
    assert WINDOWS["1m"] == 500


def test_rolling_store_keeps_configured_window(tmp_path):
    store = PersistentCandleStore(tmp_path / "raw")
    key = MarketKey("binance", "BTC/USDT", "spot", "5m")
    frame = _frame(count=WINDOWS["5m"] + 10)
    stored = store.append(key, frame)

    assert len(stored) == 500
    assert len(store.load(key)) == 500
    assert stored["timestamp"].is_monotonic_increasing


def test_checkpoint_survives_restart(tmp_path):
    path = tmp_path / "journal" / "checkpoints.json"
    key = MarketKey("binance", "BTC/USDT", "spot", "5m")
    first = CandleCheckpoint(path)
    assert first.get(key) is None
    first.mark(key, 12345)

    second = CandleCheckpoint(path)
    assert second.get(key) == 12345
    second.mark(key, 12000)
    assert second.get(key) == 12345


def test_cache_prefers_local_window_after_seed(tmp_path, monkeypatch):
    provider = Provider()
    store = PersistentCandleStore(tmp_path / "raw")
    cache = LiveMarketDataCache(provider, store)
    key = MarketKey("binance", "BTC/USDT", "spot", "5m")

    duration_ms = 5 * 60_000
    now_ms = int(time.time() * 1000)
    current_open = (now_ms // duration_ms) * duration_ms
    # Freeze time safely inside the current candle so the test cannot race a
    # 5-minute boundary while the cache checks freshness.
    fixed_now_ms = current_open + 60_000
    monkeypatch.setattr("aicfa.live_market.time.time", lambda: fixed_now_ms / 1000)
    cache.seed(key, _frame(start=current_open - 20 * duration_ms, count=20))
    result = cache.fetch_ohlcv(
        symbol="BTC/USDT",
        market_type="spot",
        timeframe="5m",
        since_ms=None,
        limit=10,
    )

    assert len(result) == 10
    assert provider.calls == []
    assert result.attrs["aicfa_cache_version"] == 1

    cached = cache.frame(key)
    assert cached is not None
    assert cached.attrs["aicfa_cache_version"] == 1


def test_cache_refreshes_when_a_full_window_is_stale(tmp_path):
    provider = Provider()
    store = PersistentCandleStore(tmp_path / "raw")
    cache = LiveMarketDataCache(provider, store)
    key = MarketKey("binance", "BTC/USDT", "spot", "5m")

    # The old rows are enough in quantity but far behind the current market.
    cache.seed(key, _frame(start=0, count=WINDOWS["5m"]))
    cache.fetch_ohlcv(
        symbol="BTC/USDT",
        market_type="spot",
        timeframe="5m",
        since_ms=None,
        limit=10,
    )

    assert provider.calls == [("BTC/USDT", "spot", "5m", 11)]



def test_live_dispatch_preserves_all_queued_closed_candles_in_order(tmp_path, monkeypatch):
    coordinator = LiveMarketCoordinator(
        SimpleNamespace(markets=()),
        provider=Provider(),
        data_dir=tmp_path / "data",
        on_candle=lambda event: None,
        max_workers=1,
    )
    first_started = threading.Event()
    release_first = threading.Event()
    all_processed = threading.Event()
    processed = []

    def slow_handle(observation):
        timestamp = int(observation.data["timestamp"].iloc[0])
        if timestamp == 1:
            first_started.set()
            assert release_first.wait(2)
        processed.append(timestamp)
        if len(processed) == 3:
            all_processed.set()

    monkeypatch.setattr(coordinator, "_handle", slow_handle)

    def observation(timestamp):
        frame = pd.DataFrame({
            "timestamp": [timestamp],
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
            "volume": [10.0],
        })
        return WebSocketObservation(
            key=MarketKey("binance", "BTC/USDT", "spot", "1m"),
            data=frame,
            observed_at_ms=timestamp + 60_000,
        )

    coordinator._submit_observation(observation(1))
    assert first_started.wait(1)
    coordinator._submit_observation(observation(2))
    coordinator._submit_observation(observation(3))
    release_first.set()

    assert all_processed.wait(2)
    coordinator.stop()
    assert processed == [1, 2, 3]



def test_websocket_freshness_controls_fallback_window(tmp_path):
    coordinator = LiveMarketCoordinator(
        SimpleNamespace(markets=()),
        provider=Provider(),
        data_dir=tmp_path / "data",
        on_candle=lambda event: None,
    )
    started_at = coordinator.last_observation_received_at_ms
    assert not coordinator.websocket_is_stale(max_age_seconds=180, now_ms=started_at + 179_000)
    assert coordinator.websocket_is_stale(max_age_seconds=180, now_ms=started_at + 181_000)
    coordinator.stop()



def test_live_candle_trigger_map_matches_requested_profile_cadence():
    from aicfa.data_requirements import TradingMode

    assert LIVE_CANDLE_MODE_TRIGGERS == {
        "1m": (TradingMode.SCALPING,),
        "5m": (TradingMode.SCALPING,),
        "15m": (TradingMode.INTRADAY,),
        "1h": (TradingMode.SWING,),
        "4h": (TradingMode.POSITION,),
    }
    assert "1d" not in LIVE_CANDLE_MODE_TRIGGERS
    assert "1w" not in LIVE_CANDLE_MODE_TRIGGERS


def test_failed_candle_processing_is_retried_without_losing_event(tmp_path, monkeypatch):
    coordinator = LiveMarketCoordinator(
        SimpleNamespace(markets=()),
        provider=Provider(),
        data_dir=tmp_path / "data",
        on_candle=lambda event: None,
        max_workers=1,
    )
    attempts = []
    recovered = threading.Event()

    def fail_once(observation):
        attempts.append(int(observation.data["timestamp"].iloc[0]))
        if len(attempts) == 1:
            raise RuntimeError("transient test failure")
        recovered.set()

    monkeypatch.setattr(coordinator, "_handle", fail_once)
    frame = pd.DataFrame({
        "timestamp": [1],
        "open": [100.0],
        "high": [101.0],
        "low": [99.0],
        "close": [100.5],
        "volume": [10.0],
    })
    coordinator._submit_observation(WebSocketObservation(
        key=MarketKey("binance", "BTC/USDT", "spot", "1m"),
        data=frame,
        observed_at_ms=60_000,
    ))
    assert recovered.wait(3)
    coordinator.stop()
    assert attempts == [1, 1]



def test_binance_market_keys_are_split_into_groups_of_at_most_200():
    keys = tuple(
        MarketKey("binance", f"COIN{i}/USDT", "spot", "1m")
        for i in range(405)
    )
    chunks = chunk_market_keys(keys)
    assert [len(chunk) for chunk in chunks] == [200, 200, 5]
    assert tuple(key for chunk in chunks for key in chunk) == keys
    assert max(map(len, chunks)) <= BINANCE_WS_MAX_STREAMS
    assert BINANCE_WS_ROTATE_SECONDS == 23 * 60 * 60


def test_binance_market_key_chunking_deduplicates_and_validates_size():
    key = MarketKey("binance", "BTC/USDT", "spot", "1m")
    assert chunk_market_keys((key, key)) == ((key,),)
    import pytest
    with pytest.raises(ValueError, match="max_streams"):
        chunk_market_keys((key,), max_streams=0)



def test_live_coordinator_does_not_mark_failed_rest_gap_recovery_complete(tmp_path, monkeypatch):
    class BrokenRecoveryProvider(Provider):
        def fetch_ohlcv(self, *, symbol, market_type, timeframe, since_ms, limit):
            raise ConnectionError("REST unavailable")

    coordinator = LiveMarketCoordinator(
        SimpleNamespace(markets=()),
        provider=BrokenRecoveryProvider(),
        data_dir=tmp_path / "data",
        on_candle=lambda event: None,
    )
    key = MarketKey("binance", "BTC/USDT", "spot", "1m")
    monkeypatch.setattr(coordinator.checkpoint, "get", lambda _key: 1)

    assert coordinator._recover_missed_candles((key,)) is False
    coordinator.stop()


def test_live_coordinator_accepts_recovery_when_checkpoint_is_current(tmp_path, monkeypatch):
    coordinator = LiveMarketCoordinator(
        SimpleNamespace(markets=()),
        provider=Provider(),
        data_dir=tmp_path / "data",
        on_candle=lambda event: None,
    )
    key = MarketKey("binance", "BTC/USDT", "spot", "1m")
    fixed_now_ms = int(time.time() * 1000)
    monkeypatch.setattr("aicfa.live_market.time.time", lambda: fixed_now_ms / 1000)
    latest = coordinator._latest_closed_open(key.timeframe, fixed_now_ms)
    monkeypatch.setattr(coordinator.checkpoint, "get", lambda _key: latest)

    assert coordinator._recover_missed_candles((key,)) is True
    coordinator.stop()



def test_non_binance_candle_fallback_emits_closed_candle_event(tmp_path, monkeypatch):
    coordinator = LiveMarketCoordinator(
        SimpleNamespace(markets=()),
        provider=Provider(),
        data_dir=tmp_path / "data",
        on_candle=lambda event: None,
    )
    # Place the clock just after a 5-minute boundary so 1m and 5m are due.
    fixed_now_ms = 1_800_000_000_000
    fixed_now_ms = (fixed_now_ms // 300_000) * 300_000 + 3_000
    monkeypatch.setattr("aicfa.live_market.time.time", lambda: fixed_now_ms / 1000)
    coordinator._rest_polled_markets = (
        (0, "futures", "XAU/USDT:USDT", "bybit"),
    )
    submitted = []

    def capture(observation):
        submitted.append(observation)
        coordinator._stopped.set()

    monkeypatch.setattr(coordinator, "_submit_observation", capture)
    coordinator._poll_non_binance_closed_candles()

    assert submitted
    assert submitted[0].key.symbol == "XAU/USDT:USDT"
    assert submitted[0].key.timeframe == "1m"
    assert len(submitted[0].data) == 1
    coordinator.stop()
