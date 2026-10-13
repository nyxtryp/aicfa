import unittest
from decimal import Decimal

from fastapi import HTTPException

from app.main import market_data, smc_analysis
from app.market_data import ClosedCandle


def candle(symbol, timeframe, index, open_, high, low, close):
    return ClosedCandle(
        symbol=symbol,
        timeframe=timeframe,
        open_time_ms=1_700_000_000_000 + index * 60_000,
        close_time_ms=1_700_000_059_999 + index * 60_000,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("100"),
    )


class SMCAnalysisApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_symbol_and_timeframe_are_rejected(self):
        with self.assertRaises(HTTPException) as symbol_error:
            await smc_analysis("UNKNOWN", "1m")
        self.assertEqual(symbol_error.exception.status_code, 404)
        with self.assertRaises(HTTPException) as timeframe_error:
            await smc_analysis("BTCUSDT", "2m")
        self.assertEqual(timeframe_error.exception.status_code, 404)

    async def test_short_window_returns_warming_up_without_fake_annotations(self):
        key = ("BTCUSDT", "1m")
        original = market_data.candles.get(key)
        market_data.candles[key] = (candle("BTCUSDT", "1m", 0, 10, 11, 9, 10),)
        try:
            result = await smc_analysis("btcusdt", "1m")
            self.assertEqual(result["status"], "warming_up")
            self.assertIsNone(result["annotations"])
        finally:
            if original is None:
                market_data.candles.pop(key, None)
            else:
                market_data.candles[key] = original

    async def test_analysis_api_returns_timestamped_chart_payload(self):
        key = ("BTCUSDT", "1m")
        original = market_data.candles.get(key)
        rows = (
            candle("BTCUSDT", "1m", 0, 10, 11, 9, 10),
            candle("BTCUSDT", "1m", 1, 10, 12, 9.5, 11),
            candle("BTCUSDT", "1m", 2, 11, 13, 10, 12),
            candle("BTCUSDT", "1m", 3, 12, 12.5, 10.5, 11),
        )
        market_data.candles[key] = rows
        try:
            result = await smc_analysis("BTCUSDT", "1m")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["candles"], 4)
            annotations = result["annotations"]
            self.assertEqual(annotations["as_of_index"], 3)
            self.assertEqual(annotations["as_of_timestamp_ms"], rows[-1].open_time_ms)
            self.assertIn("swings", annotations)
            self.assertIn("liquidity_levels", annotations)
        finally:
            if original is None:
                market_data.candles.pop(key, None)
            else:
                market_data.candles[key] = original


if __name__ == "__main__":
    unittest.main()
