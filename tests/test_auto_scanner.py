import unittest
from decimal import Decimal

from app.market_data import ClosedCandle, TIMEFRAMES
from app.smc.scanner import SetupCandidate, scan_symbol


class AutomaticScannerTests(unittest.TestCase):
    def candles(self, symbol="BTCUSDT", timeframe="5m", count=20):
        step = 60_000 if timeframe == "1m" else 300_000
        return tuple(
            ClosedCandle(
                symbol=symbol, timeframe=timeframe,
                open_time_ms=i * step, close_time_ms=(i + 1) * step - 1,
                open=Decimal("100"), high=Decimal("101"),
                low=Decimal("99"), close=Decimal("100"),
                volume=Decimal("10"),
            )
            for i in range(count)
        )

    def test_insufficient_windows_never_emit_a_setup(self):
        series = {tf: self.candles(timeframe=tf) for tf in TIMEFRAMES}
        self.assertEqual(scan_symbol("BTCUSDT", series, trigger_timeframe="5m"), [])
        self.assertEqual(scan_symbol("BTCUSDT", series, trigger_timeframe="15m"), [])

    def test_only_profile_confirmation_timeframes_trigger_scans(self):
        series = {tf: self.candles(timeframe=tf, count=60) for tf in TIMEFRAMES}
        self.assertEqual(scan_symbol("BTCUSDT", series, trigger_timeframe="1m"), [])
        self.assertEqual(scan_symbol("BTCUSDT", series, trigger_timeframe="4h"), [])

    def test_candidate_serialization_is_json_ready(self):
        candidate = SetupCandidate(
            key="BTCUSDT:scalp:long:OB:1:2", symbol="BTCUSDT",
            profile="scalp", direction="long", status="CANDIDATE",
            confirmation_time_ms=2, confirmation_price=100.0, stop_price=95.0,
            targets=(110.0, 115.0), score=7, reasons=("sweep",),
            zone=(98.0, 101.0), timeframe="5m",
        )
        payload = candidate.as_dict()
        self.assertEqual(payload["targets"], [110.0, 115.0])
        self.assertEqual(payload["zone"], [98.0, 101.0])
        self.assertEqual(payload["status"], "CANDIDATE")


if __name__ == "__main__":
    unittest.main()
