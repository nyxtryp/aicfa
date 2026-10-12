import asyncio
import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock
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
