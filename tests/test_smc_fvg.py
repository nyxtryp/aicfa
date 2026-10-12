import unittest

from app.smc.fvg import FairValueGap, find_fair_value_gaps


class FairValueGapTests(unittest.TestCase):
    def test_detects_bullish_gap_only_after_third_candle_is_available(self):
        highs = [10, 12, 14]
        lows = [8, 11, 13]
        self.assertEqual(
            find_fair_value_gaps(highs, lows),
            (FairValueGap("bullish", 0, 2, 10.0, 13.0),),
        )
        self.assertEqual(find_fair_value_gaps(highs[:2], lows[:2]), ())

    def test_detects_bearish_gap_with_correct_zone(self):
        self.assertEqual(
            find_fair_value_gaps([12, 11, 8], [10, 9, 7]),
            (FairValueGap("bearish", 0, 2, 8.0, 10.0),),
        )

    def test_touching_edges_is_not_a_gap(self):
        self.assertEqual(find_fair_value_gaps([10, 12, 13], [8, 11, 10]), ())

    def test_rejects_invalid_input(self):
        with self.assertRaises(ValueError):
            find_fair_value_gaps([1, 2], [0])
        with self.assertRaises(ValueError):
            find_fair_value_gaps([0], [1])


if __name__ == "__main__":
    unittest.main()
