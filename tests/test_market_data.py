import unittest
from decimal import Decimal

from app.market_data import (
    ALL_SYMBOLS,
    CRYPTO_SYMBOLS,
    EXPECTED_STREAM_COUNT,
    TIMEFRAMES,
    TRADFI_SYMBOLS,
    combined_stream_url,
    parse_closed_kline,
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

    def test_invalid_price_range_raises(self):
        message = event()
        message["data"]["k"]["h"] = "98"
        with self.assertRaises(ValueError):
            parse_closed_kline(message)


if __name__ == "__main__":
    unittest.main()
