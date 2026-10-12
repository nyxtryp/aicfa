import unittest

from app.smc.fvg import FairValueGap, FairValueGapFill, find_fair_value_gaps, measure_fvg_fill


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


    def test_bullish_gap_fill_progress_uses_only_post_confirmation_candles(self):
        gap = FairValueGap("bullish", 0, 2, 10.0, 13.0)
        highs = [10, 12, 14, 14, 12]
        lows = [8, 11, 13, 12, 10]
        self.assertEqual(
            measure_fvg_fill(gap, highs, lows, as_of_index=3),
            FairValueGapFill(gap, 3, 33.33333333, False),
        )
        self.assertEqual(
            measure_fvg_fill(gap, highs, lows, as_of_index=4),
            FairValueGapFill(gap, 4, 100.0, True),
        )

    def test_bearish_gap_fill_progress(self):
        gap = FairValueGap("bearish", 0, 2, 8.0, 10.0)
        result = measure_fvg_fill(gap, [12, 11, 8, 9, 10], [10, 9, 7, 8, 9])
        self.assertEqual(result.fill_percent, 100.0)
        self.assertTrue(result.fully_filled)

    def test_fvg_fill_rejects_future_or_invalid_index(self):
        gap = FairValueGap("bullish", 0, 2, 10.0, 13.0)
        with self.assertRaises(ValueError):
            measure_fvg_fill(gap, [10, 12, 14], [8, 11, 13], as_of_index=3)


    def test_rounding_does_not_mark_near_full_gap_as_fully_filled(self):
        gap = FairValueGap("bullish", 0, 2, 10.0, 13.0)
        result = measure_fvg_fill(
            gap,
            [10, 12, 14, 11],
            [8, 11, 13, 10.0000000001],
        )
        self.assertEqual(result.fill_percent, 100.0)
        self.assertFalse(result.fully_filled)


if __name__ == "__main__":
    unittest.main()
