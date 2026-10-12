import asyncio
import unittest
import tempfile
import urllib.error
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from decimal import Decimal

from app.market_data import (
    ALL_SYMBOLS,
    CRYPTO_SYMBOLS,
    CANDLES_PER_SERIES,
    ClosedCandle,
    EXPECTED_STREAM_COUNT,
    TIMEFRAMES,
    TRADFI_SYMBOLS,
    combined_stream_url,
    MarketDataManager,
    parse_closed_kline,
    SQLiteCandleStore,
)


def event(*, closed: bool = True, symbol: str = "BTCUSDT", timeframe: str = "1m"):
    return {
        "stream": f"{symbol.lower()}@kline_{timeframe}",
        "data": {
            "e": "kline",
            "k": {
                "s": symbol,
                "i": timeframe,
                "t": 1_791_000_000_000,
                "T": 1_791_000_059_999,
                "o": "100.00",
                "h": "105.00",
                "l": "99.00",
                "c": "103.00",
                "v": "12.5",
                "x": closed,
            },
        },
    }


class RestRateLimitTests(unittest.TestCase):
    def test_retry_helper_parses_numeric_retry_after(self):
        from app.market_data import _retry_after_seconds
        error = urllib.error.HTTPError("https://example.com", 429, "limited", {"Retry-After": "3"}, None)
        self.assertEqual(_retry_after_seconds(error), 3.0)


    def test_rate_limit_retries_once_and_honors_retry_after(self):
        from app import market_data
        error = urllib.error.HTTPError("https://example.com", 429, "limited", {"Retry-After": "3"}, None)
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b"[]"
        with patch("app.market_data.urllib.request.urlopen", side_effect=[error, response]) as request:
            with patch("app.market_data.time.sleep") as sleep:
                with patch.object(market_data, "_rest_next_request_at", 0.0):
                    result = MarketDataManager._fetch_rest_klines("BTCUSDT", "1m")
        self.assertEqual(result, [])
        self.assertEqual(request.call_count, 2)
        sleep.assert_called_once_with(3.0)

    def test_rate_limit_retries_are_bounded(self):
        from app import market_data
        error = urllib.error.HTTPError("https://example.com", 429, "limited", {}, None)
        with patch("app.market_data.urllib.request.urlopen", side_effect=error) as request:
            with patch("app.market_data.time.sleep"):
                with patch.object(market_data, "_rest_next_request_at", 0.0):
                    with self.assertRaises(urllib.error.HTTPError):
                        MarketDataManager._fetch_rest_klines("BTCUSDT", "1m")
        self.assertEqual(request.call_count, market_data.REST_MAX_RATE_LIMIT_RETRIES + 1)


class ReconciliationScheduleTests(unittest.IsolatedAsyncioTestCase):
    async def test_first_rest_reconciliation_waits_one_hour_after_history(self):
        from app.market_data import RECONCILIATION_INTERVAL_SECONDS

        manager = MarketDataManager()
        manager._history_task = None
        calls = []
        sleep_count = 0

        async def sleep_side_effect(seconds):
            nonlocal sleep_count
            sleep_count += 1
            calls.append(("sleep", seconds))
            if sleep_count == 2:
                manager._stopping = True

        async def reconcile_side_effect():
            calls.append(("reconcile", None))

        manager.reconcile_all_series = AsyncMock(side_effect=reconcile_side_effect)
        with patch("app.market_data.asyncio.sleep", new=AsyncMock(side_effect=sleep_side_effect)):
            await manager._reconciliation_loop()

        self.assertEqual(calls, [
            ("sleep", RECONCILIATION_INTERVAL_SECONDS),
            ("reconcile", None),
            ("sleep", RECONCILIATION_INTERVAL_SECONDS),
        ])


class MarketDataTests(unittest.TestCase):
    def test_watchlist_has_exactly_50_unique_symbols(self):
        self.assertEqual(len(TRADFI_SYMBOLS), 21)
        self.assertEqual(len(CRYPTO_SYMBOLS), 29)
        self.assertEqual(len(ALL_SYMBOLS), 50)
        self.assertEqual(len(set(ALL_SYMBOLS)), 50)
        self.assertNotIn("TONUSDT", ALL_SYMBOLS)

    def test_only_five_approved_timeframes_and_250_streams(self):
        self.assertEqual(TIMEFRAMES, ("1m", "5m", "15m", "1h", "4h"))
        self.assertEqual(EXPECTED_STREAM_COUNT, 250)

    def test_unclosed_candle_is_ignored(self):
        self.assertIsNone(parse_closed_kline(event(closed=False)))

    def test_closed_candle_is_parsed_exactly(self):
        candle = parse_closed_kline(event())
        self.assertIsNotNone(candle)
        assert candle is not None
        self.assertEqual(candle.symbol, "BTCUSDT")
        self.assertEqual(candle.timeframe, "1m")
        self.assertEqual(candle.open, Decimal("100.00"))
        self.assertEqual(candle.high, Decimal("105.00"))
        self.assertEqual(candle.low, Decimal("99.00"))
        self.assertEqual(candle.close, Decimal("103.00"))
        self.assertEqual(candle.volume, Decimal("12.5"))
        self.assertEqual(candle.open_time_ms, 1_791_000_000_000)

    def test_unknown_symbol_or_timeframe_is_ignored(self):
        self.assertIsNone(parse_closed_kline(event(symbol="TONUSDT")))
        self.assertIsNone(parse_closed_kline(event(timeframe="1s")))

    def test_non_kline_event_is_ignored(self):
        self.assertIsNone(parse_closed_kline({"e": "aggTrade"}))

    def test_combined_url_uses_market_endpoint_and_only_configured_timeframes(self):
        url = combined_stream_url(("BTCUSDT",), TIMEFRAMES)
        self.assertTrue(url.startswith("wss://fstream.binance.com/market/stream?streams="))
        self.assertIn("btcusdt@kline_1m", url)
        self.assertIn("btcusdt@kline_4h", url)
        self.assertNotIn("@kline_1s", url)


    def test_manager_starts_with_two_groups_and_250_expected_streams(self):
        manager = MarketDataManager()
        status = manager.status()
        self.assertEqual(status["expected_streams"], 250)
        self.assertEqual(status["instruments"], 50)
        self.assertEqual(status["timeframes"], ["1m", "5m", "15m", "1h", "4h"])
        self.assertEqual(status["groups"]["tradfi"]["expected_streams"], 105)
        self.assertEqual(status["groups"]["crypto"]["expected_streams"], 145)
        self.assertEqual(status["latest_series"], 0)
        self.assertEqual(status["stored_candles"], 0)
        self.assertEqual(status["window_size"], 500)

    def test_rolling_window_keeps_500_newest_closed_candles(self):
        manager = MarketDataManager()
        base_time = 1_791_000_000_000
        for index in range(501):
            candle = ClosedCandle(
                symbol="BTCUSDT",
                timeframe="1m",
                open_time_ms=base_time + index * 60_000,
                close_time_ms=base_time + index * 60_000 + 59_999,
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=Decimal("12.5"),
            )
            self.assertTrue(manager.add_closed_candle(candle))

        window = manager.candle_window("BTCUSDT", "1m")
        self.assertEqual(len(window), CANDLES_PER_SERIES)
        self.assertEqual(window[0].open_time_ms, base_time + 60_000)
        self.assertEqual(window[-1].open_time_ms, base_time + 500 * 60_000)
        self.assertEqual(manager.status()["stored_candles"], 500)

    def test_rolling_window_rejects_duplicate_or_older_candles(self):
        manager = MarketDataManager()
        candle = parse_closed_kline(event())
        assert candle is not None
        self.assertTrue(manager.add_closed_candle(candle))
        self.assertFalse(manager.add_closed_candle(candle))
        older = ClosedCandle(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            open_time_ms=candle.open_time_ms - 60_000,
            close_time_ms=candle.close_time_ms - 60_000,
            open=candle.open,
            high=candle.high,
            low=candle.low,
            close=candle.close,
            volume=candle.volume,
        )
        self.assertFalse(manager.add_closed_candle(older))
        self.assertEqual(len(manager.candle_window("BTCUSDT", "1m")), 1)

    def test_rest_candle_parser_excludes_unclosed_candle(self):
        row = [
            1_791_000_000_000,
            "100.00",
            "105.00",
            "99.00",
            "103.00",
            "12.5",
            1_791_000_059_999,
        ]
        candle = MarketDataManager._parse_rest_candle("BTCUSDT", "1m", row)
        self.assertIsNotNone(candle)
        assert candle is not None
        self.assertEqual(candle.symbol, "BTCUSDT")
        self.assertEqual(candle.timeframe, "1m")
        self.assertEqual(candle.open_time_ms, 1_791_000_000_000)

    def test_rest_candle_parser_rejects_currently_forming_candle(self):
        now_ms = __import__("time").time_ns() // 1_000_000
        row = [
            now_ms,
            "100.00",
            "105.00",
            "99.00",
            "103.00",
            "12.5",
            now_ms + 59_999,
        ]
        self.assertIsNone(MarketDataManager._parse_rest_candle("BTCUSDT", "1m", row))

    def test_invalid_price_range_raises(self):
        message = event()
        message["data"]["k"]["h"] = "98"
        with self.assertRaises(ValueError):
            parse_closed_kline(message)



class SQLiteCandleStoreTests(unittest.TestCase):
    def make_candle(self, index: int) -> ClosedCandle:
        base = 1_791_000_000_000
        return ClosedCandle(
            symbol="BTCUSDT", timeframe="1m",
            open_time_ms=base + index * 60_000,
            close_time_ms=base + index * 60_000 + 59_999,
            open=Decimal("100"), high=Decimal("105"), low=Decimal("99"),
            close=Decimal("103"), volume=Decimal("12.5"),
        )

    def test_sqlite_wal_persists_and_restores_latest_500_candles(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "candles.sqlite3"
            store = SQLiteCandleStore(db_path)
            store.initialize()
            mode = store._db().execute("PRAGMA journal_mode").fetchone()[0]
            self.assertEqual(str(mode).lower(), "wal")
            candles = [self.make_candle(i) for i in range(501)]
            store.upsert_many(candles)
            self.assertEqual(store.count(), 500)
            restored = store.load_window("BTCUSDT", "1m")
            self.assertEqual(len(restored), 500)
            self.assertEqual(restored[0].open_time_ms, candles[1].open_time_ms)
            self.assertEqual(restored[-1].open_time_ms, candles[-1].open_time_ms)
            # Same primary key is an upsert, not a duplicate.
            store.upsert_many((candles[-1], candles[-1]))
            self.assertEqual(store.count(), 500)
            store.close()

            restarted = SQLiteCandleStore(db_path)
            self.assertEqual(restarted.count(), 500)
            again = restarted.load_window("BTCUSDT", "1m")
            self.assertEqual(again, restored)
            restarted.close()

    def test_manager_persists_live_closed_candle_when_store_is_initialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = MarketDataManager()
            manager.store = SQLiteCandleStore(Path(tmp) / "candles.sqlite3")
            manager.store.initialize()
            candle = self.make_candle(0)
            self.assertTrue(manager.add_closed_candle(candle))
            manager.store.close()
            reopened = SQLiteCandleStore(Path(tmp) / "candles.sqlite3")
            self.assertEqual(reopened.load_window("BTCUSDT", "1m"), (candle,))
            reopened.close()


class MarketDataGapRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_websocket_gap_triggers_rest_recovery_before_current_candle(self):
        manager = MarketDataManager()
        current = parse_closed_kline(event())
        self.assertIsNotNone(current)
        assert current is not None
        previous = ClosedCandle(
            symbol=current.symbol, timeframe=current.timeframe,
            open_time_ms=current.open_time_ms - 120_000,
            close_time_ms=current.open_time_ms - 60_001,
            open=Decimal("100"), high=Decimal("105"), low=Decimal("99"),
            close=Decimal("103"), volume=Decimal("12.5"),
        )
        manager.candles[(previous.symbol, previous.timeframe)] = __import__("collections").deque(
            [previous], maxlen=CANDLES_PER_SERIES
        )
        manager.latest[(previous.symbol, previous.timeframe)] = previous
        manager._recover_series_gap = AsyncMock()

        class OneMessageSocket:
            def __init__(self):
                self.sent = False

            def __aiter__(self):
                return self

            async def __anext__(self):
                if self.sent:
                    raise StopAsyncIteration
                self.sent = True
                import json
                return json.dumps(event())

        await manager._consume_socket("crypto", OneMessageSocket())

        manager._recover_series_gap.assert_awaited_once_with("BTCUSDT", "1m")
        self.assertEqual(manager.latest[("BTCUSDT", "1m")].open_time_ms, current.open_time_ms)
        self.assertEqual(manager.groups["crypto"]["closed_candles"], 1)

    async def test_rest_gap_recovery_merges_missing_candles_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = MarketDataManager()
            manager.store = SQLiteCandleStore(Path(tmp) / "candles.sqlite3")
            manager.store.initialize()
            base = 1_700_000_000_000

            def candle_at(index: int) -> ClosedCandle:
                return ClosedCandle(
                    symbol="BTCUSDT", timeframe="1m",
                    open_time_ms=base + index * 60_000,
                    close_time_ms=base + index * 60_000 + 59_999,
                    open=Decimal("100"), high=Decimal("105"), low=Decimal("99"),
                    close=Decimal("103"), volume=Decimal("12.5"),
                )

            first = candle_at(0)
            manager.candles[("BTCUSDT", "1m")] = __import__("collections").deque(
                [first], maxlen=CANDLES_PER_SERIES
            )
            manager.latest[("BTCUSDT", "1m")] = first
            rows = [
                [c.open_time_ms, str(c.open), str(c.high), str(c.low), str(c.close),
                 str(c.volume), c.close_time_ms]
                for c in (candle_at(1), candle_at(2))
            ]
            manager._fetch_rest_klines = lambda symbol, timeframe: rows

            await manager._recover_series_gap("BTCUSDT", "1m")

            window = manager.candle_window("BTCUSDT", "1m")
            self.assertEqual([c.open_time_ms for c in window],
                             [base, base + 60_000, base + 120_000])
            self.assertEqual(manager.store.count(), 3)
            manager.store.close()

    async def test_periodic_reconciliation_corrects_rest_candle_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = MarketDataManager()
            manager.store = SQLiteCandleStore(Path(tmp) / "candles.sqlite3")
            manager.store.initialize()
            base = 1_700_000_000_000
            stale = ClosedCandle(
                symbol="BTCUSDT", timeframe="1m", open_time_ms=base,
                close_time_ms=base + 59_999, open=Decimal("100"),
                high=Decimal("105"), low=Decimal("99"), close=Decimal("103"),
                volume=Decimal("12.5"),
            )
            corrected = ClosedCandle(
                symbol="BTCUSDT", timeframe="1m", open_time_ms=base,
                close_time_ms=base + 59_999, open=Decimal("100"),
                high=Decimal("106"), low=Decimal("99"), close=Decimal("104"),
                volume=Decimal("13.5"),
            )
            manager.candles[("BTCUSDT", "1m")] = __import__("collections").deque(
                [stale], maxlen=CANDLES_PER_SERIES
            )
            manager.latest[("BTCUSDT", "1m")] = stale
            manager.store.upsert_many((stale,))
            manager._fetch_rest_klines = lambda symbol, timeframe: [[
                corrected.open_time_ms, str(corrected.open), str(corrected.high),
                str(corrected.low), str(corrected.close), str(corrected.volume),
                corrected.close_time_ms,
            ]]

            checked = await manager._reconcile_series("BTCUSDT", "1m")

            self.assertEqual(checked, 1)
            self.assertEqual(manager.candle_window("BTCUSDT", "1m"), (corrected,))
            self.assertEqual(manager.store.load_window("BTCUSDT", "1m"), (corrected,))
            manager.store.close()

    async def test_full_reconciliation_checks_all_250_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            manager = MarketDataManager()
            manager.store = SQLiteCandleStore(Path(tmp) / "candles.sqlite3")
            manager.store.initialize()
            base = 1_700_000_000_000
            row = [base, "100", "105", "99", "103", "12.5", base + 59_999]
            manager._fetch_rest_klines = lambda symbol, timeframe: [row]

            await manager.reconcile_all_series()

            self.assertEqual(manager.reconciliation_status["status"], "complete")
            self.assertEqual(manager.reconciliation_status["series_checked"], 250)
            self.assertEqual(manager.reconciliation_status["candles_checked"], 250)
            self.assertEqual(manager.reconciliation_status["errors"], [])
            self.assertEqual(manager.store.count(), 250)
            manager.store.close()

    async def test_websocket_rotation_confirms_replacement_before_closing_old_socket(self):
        manager = MarketDataManager()
        manager._stopping = False
        events = []

        class FakeSocket:
            def __aiter__(self):
                return self

            async def __anext__(self):
                await asyncio.Event().wait()
                raise StopAsyncIteration

        class FakeContext:
            def __init__(self, number):
                self.number = number

            async def __aenter__(self):
                events.append(("enter", self.number))
                return FakeSocket()

            async def __aexit__(self, exc_type, exc, tb):
                events.append(("exit", self.number))

        contexts = []

        def fake_connect(*args, **kwargs):
            context = FakeContext(len(contexts))
            contexts.append(context)
            return context

        with patch("app.market_data.websockets.connect", side_effect=fake_connect), \
             patch("app.market_data.WS_ROTATION_INTERVAL_SECONDS", 0.03), \
             patch("app.market_data.WS_ROTATION_CONFIRM_SECONDS", 0.001):
            task = asyncio.create_task(manager._run_group_connection("crypto", "wss://example.test"))
            try:
                await asyncio.sleep(0.05)
            finally:
                manager._stopping = True
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        self.assertGreaterEqual(len(contexts), 2)
        self.assertIn(("enter", 1), events)
        self.assertIn(("exit", 0), events)
        self.assertLess(events.index(("enter", 1)), events.index(("exit", 0)))
        self.assertGreaterEqual(manager.groups["crypto"]["rotations"], 1)

    async def test_failed_rotation_keeps_old_socket_until_shutdown(self):
        manager = MarketDataManager()
        events = []

        class FakeSocket:
            def __aiter__(self):
                return self

            async def __anext__(self):
                await asyncio.Event().wait()

        class FakeContext:
            def __init__(self, number):
                self.number = number

            async def __aenter__(self):
                events.append(("enter_attempt", self.number))
                if self.number == 1:
                    manager._stopping = True
                    raise OSError("replacement unavailable")
                events.append(("entered", self.number))
                return FakeSocket()

            async def __aexit__(self, exc_type, exc, tb):
                events.append(("exit", self.number))

        contexts = []

        def fake_connect(*args, **kwargs):
            ctx = FakeContext(len(contexts))
            contexts.append(ctx)
            return ctx

        with (
            patch("app.market_data.websockets.connect", side_effect=fake_connect),
            patch("app.market_data.WS_ROTATION_INTERVAL_SECONDS", 0.001),
            patch("app.market_data.WS_ROTATION_RETRY_SECONDS", 0.001),
        ):
            task = asyncio.create_task(manager._run_group_connection("crypto", "wss://example.test"))
            await asyncio.sleep(0.01)
            manager._stopping = True
            await asyncio.wait_for(task, timeout=0.2)

        self.assertIn(("entered", 0), events)
        self.assertIn(("enter_attempt", 1), events)
        self.assertIn(("exit", 0), events)
        self.assertLess(events.index(("enter_attempt", 1)), events.index(("exit", 0)))
        self.assertEqual(manager.groups["crypto"]["rotations"], 0)

    async def test_rest_fallback_polls_series_when_websocket_is_down(self):
        manager = MarketDataManager()
        manager.groups["crypto"]["status"] = "reconnecting"

        async def one_poll(symbol, timeframe):
            manager._stopping = True
            return 1

        manager._reconcile_series = AsyncMock(side_effect=one_poll)
        await manager._rest_fallback_loop("crypto", ("BTCUSDT",))

        manager._reconcile_series.assert_awaited_once_with("BTCUSDT", "1m")
        self.assertEqual(manager.groups["crypto"]["fallback_polls"], 1)
        self.assertEqual(manager.groups["crypto"]["fallback_errors"], 0)

    async def test_rest_fallback_retries_after_transient_rest_error(self):
        manager = MarketDataManager()
        manager.groups["crypto"]["status"] = "reconnecting"
        calls = 0

        async def flaky_poll(symbol, timeframe):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("temporary REST failure")
            manager._stopping = True
            return 1

        async def fast_sleep(_seconds):
            return None

        manager._reconcile_series = AsyncMock(side_effect=flaky_poll)
        with patch("app.market_data.asyncio.sleep", side_effect=fast_sleep):
            await manager._rest_fallback_loop("crypto", ("BTCUSDT",))

        self.assertEqual(calls, 2)
        self.assertEqual(manager.groups["crypto"]["fallback_errors"], 1)
        self.assertEqual(manager.groups["crypto"]["fallback_polls"], 1)
        self.assertEqual(manager.groups["crypto"]["last_error"], "rest_fallback:OSError")

    async def test_rest_fallback_pauses_when_websocket_recovers(self):
        manager = MarketDataManager()
        manager.groups["crypto"]["status"] = "reconnecting"
        calls = 0

        async def poll_then_recover(symbol, timeframe):
            nonlocal calls
            calls += 1
            manager.groups["crypto"]["status"] = "connected"
            return 1

        async def stop_after_recovery_wait(_seconds):
            manager._stopping = True

        manager._reconcile_series = AsyncMock(side_effect=poll_then_recover)
        with patch("app.market_data.asyncio.sleep", side_effect=stop_after_recovery_wait):
            await manager._rest_fallback_loop("crypto", ("BTCUSDT",))

        self.assertEqual(calls, 1)
        self.assertEqual(manager.groups["crypto"]["fallback_polls"], 1)
        self.assertEqual(manager.groups["crypto"]["fallback_errors"], 0)

    def test_supported_timeframe_durations(self):
        manager = MarketDataManager()
        self.assertEqual(manager._timeframe_ms("1m"), 60_000)
        self.assertEqual(manager._timeframe_ms("5m"), 300_000)
        self.assertEqual(manager._timeframe_ms("15m"), 900_000)
        self.assertEqual(manager._timeframe_ms("1h"), 3_600_000)
        self.assertEqual(manager._timeframe_ms("4h"), 14_400_000)
        with self.assertRaises(ValueError):
            manager._timeframe_ms("1s")


class MarketDataStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_does_not_wait_for_rest_history_before_health_check(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        manager = MarketDataManager()
        manager.store = SQLiteCandleStore(Path(tempdir.name) / "candles.sqlite3")

        async def blocked_history():
            await asyncio.Event().wait()

        manager.load_history = AsyncMock(side_effect=blocked_history)
        manager._run_group = AsyncMock()

        await asyncio.wait_for(manager.start(), timeout=0.2)
        await asyncio.sleep(0)

        self.assertIsNotNone(manager._history_task)
        self.assertFalse(manager._history_task.done())
        self.assertEqual(len(manager._tasks), 2)

        await manager.stop()
        self.assertIsNone(manager._history_task)
        self.assertEqual(manager._tasks, [])


if __name__ == "__main__":
    unittest.main()
