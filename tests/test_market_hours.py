import unittest
from datetime import datetime, timezone

from app.market_hours import tradfi_market_is_open


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

    def test_unmapped_tradfi_contract_fails_closed(self):
        instant = datetime(2026, 10, 13, 14, 0, tzinfo=timezone.utc)
        self.assertIsNone(tradfi_market_is_open("XAUUSDT", instant))
        self.assertIsNone(tradfi_market_is_open("UNKNOWNUSDT", instant))

    def test_naive_datetimes_are_rejected(self):
        with self.assertRaises(ValueError):
            tradfi_market_is_open("SPYUSDT", datetime(2026, 10, 13, 14, 0))


if __name__ == "__main__":
    unittest.main()
