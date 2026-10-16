import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.smc.scanner import _recent_internal_structure_direction


def candle(index, *, high=101.0, low=99.0, close=100.0):
    return SimpleNamespace(high=high, low=low, close=close)


class InternalStructureConfluenceTests(unittest.TestCase):
    def test_no_event_returns_none(self):
        candles = tuple(candle(i) for i in range(40))
        with patch("app.smc.scanner.find_confirmed_swings", return_value=()), patch(
            "app.smc.scanner.detect_structure_breaks", return_value=()
        ):
            self.assertIsNone(_recent_internal_structure_direction(candles))

    def test_recent_internal_break_returns_its_direction(self):
        candles = tuple(candle(i) for i in range(40))
        event = SimpleNamespace(direction="bullish", candle_index=38)
        with patch("app.smc.scanner.find_confirmed_swings", return_value=()), patch(
            "app.smc.scanner.detect_structure_breaks", return_value=(event,)
        ):
            self.assertEqual(_recent_internal_structure_direction(candles), "bullish")

    def test_stale_internal_break_is_not_used(self):
        candles = tuple(candle(i) for i in range(40))
        event = SimpleNamespace(direction="bearish", candle_index=36)
        with patch("app.smc.scanner.find_confirmed_swings", return_value=()), patch(
            "app.smc.scanner.detect_structure_breaks", return_value=(event,)
        ):
            self.assertIsNone(_recent_internal_structure_direction(candles))

    def test_short_history_returns_none_without_analysis(self):
        candles = tuple(candle(i) for i in range(4))
        with patch("app.smc.scanner.find_confirmed_swings") as swings:
            self.assertIsNone(_recent_internal_structure_direction(candles))
            swings.assert_not_called()


if __name__ == "__main__":
    unittest.main()
