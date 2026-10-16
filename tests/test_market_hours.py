import unittest
from datetime import datetime, timezone

from app.market_hours import tradfi_market_is_open, tradfi_scan_block_reason


class TradFiMarketHoursTests(unittest.TestCase):
    def test_us_equity_session_accounts_for_daylight_saving(self):
        summer_open = datetime(2026, 3, 10, 13, 45, tzinfo=timezone.utc)
        winter_preopen = datetime(2026, 2, 10, 13, 45, tzinfo=timezone.utc)
        self.assertTrue(tradfi_market_is_open("SPYUSDT", summer_open))
        self.assertFalse(tradfi_market_is_open("SPYUSDT", winter_preopen))

    def test_weekend_and_exchange_holiday_are_closed(self):
        saturday = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)
        thanksgiving = datetime(2026, 11, 26, 15, 0, tzinfo=timezone.utc)
        self.assertFalse(tradfi_market_is_open("NVDAUSDT", saturday))
        self.assertFalse(tradfi_market_is_open("NVDAUSDT", thanksgiving))


    def test_commodity_contracts_use_sunday_to_friday_session_and_daily_break(self):
        weekday_open = datetime(2026, 10, 13, 15, 0, tzinfo=timezone.utc)  # 11:00 ET
        maintenance_break = datetime(2026, 10, 13, 21, 30, tzinfo=timezone.utc)  # 17:30 ET
        weekend = datetime(2026, 10, 17, 15, 0, tzinfo=timezone.utc)
        sunday_open = datetime(2026, 10, 18, 22, 30, tzinfo=timezone.utc)  # 18:30 ET
        self.assertTrue(tradfi_market_is_open("XAUUSDT", weekday_open))
        self.assertFalse(tradfi_market_is_open("CLUSDT", maintenance_break))
        self.assertFalse(tradfi_market_is_open("NATGASUSDT", weekend))
        self.assertTrue(tradfi_market_is_open("BZUSDT", sunday_open))


    def test_korean_equities_use_korea_exchange_calendar(self):
        open_session = datetime(2026, 10, 13, 1, 0, tzinfo=timezone.utc)  # 10:00 KST
        after_close = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)  # 16:00 KST
        self.assertTrue(tradfi_market_is_open("SKHYNIXUSDT", open_session))
        self.assertTrue(tradfi_market_is_open("SAMSUNGUSDT", open_session))
        self.assertFalse(tradfi_market_is_open("SAMSUNGUSDT", after_close))

    def test_us_listed_adr_and_spacex_underlying_use_us_calendar(self):
        open_session = datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc)
        self.assertTrue(tradfi_market_is_open("SKHYUSDT", open_session))
        self.assertTrue(tradfi_market_is_open("SPCXUSDT", open_session))

    def test_unmapped_tradfi_contract_fails_closed(self):
        instant = datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc)
        self.assertIsNone(tradfi_market_is_open("UNMAPPEDUSDT", instant))
        self.assertIsNone(tradfi_market_is_open("UNKNOWNUSDT", instant))

    def test_naive_datetimes_are_rejected(self):
        with self.assertRaises(ValueError):
            tradfi_market_is_open("SPYUSDT", datetime(2026, 10, 13, 14, 0))

    def test_scan_gate_blocks_closed_and_unverified_markets(self):
        closed = datetime(2026, 10, 13, 7, 0, tzinfo=timezone.utc)  # Samsung after KRX close
        opened = datetime(2026, 10, 13, 1, 0, tzinfo=timezone.utc)
        self.assertEqual(tradfi_scan_block_reason("SAMSUNGUSDT", closed), "tradfi_market_closed")
        self.assertIsNone(tradfi_scan_block_reason("SAMSUNGUSDT", opened))
        self.assertEqual(tradfi_scan_block_reason("UNMAPPEDUSDT", opened), "market_hours_unverified")


if __name__ == "__main__":
    unittest.main()
