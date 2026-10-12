import unittest

from app.smc.structure import SwingPoint, find_confirmed_swings


class ConfirmedSwingTests(unittest.TestCase):
    def test_confirms_only_after_required_right_candles(self):
        points = find_confirmed_swings(
            [1, 2, 5, 3, 2],
            [0, 1, 2, 1, 0],
            left=1,
            right=2,
        )
        self.assertIn(SwingPoint("high", 2, 4, 5.0), points)
        self.assertIn(SwingPoint("low", 2, 4, 2.0), points)

    def test_equal_high_plateau_selects_earliest_candle(self):
        points = find_confirmed_swings(
            [1, 4, 4, 2, 1],
            [0, 1, 1, 1, 0],
            left=1,
            right=1,
        )
        highs = [point for point in points if point.kind == "high"]
        self.assertEqual([(point.index, point.confirmation_index) for point in highs], [(1, 2)])

    def test_equal_low_plateau_selects_earliest_candle(self):
        points = find_confirmed_swings(
            [5, 4, 4, 6, 7],
            [3, 1, 1, 2, 4],
            left=1,
            right=1,
        )
        lows = [point for point in points if point.kind == "low"]
        self.assertEqual([(point.index, point.confirmation_index) for point in lows], [(1, 2)])

    def test_rejects_invalid_window_or_mismatched_data(self):
        with self.assertRaises(ValueError):
            find_confirmed_swings([1], [0], left=0, right=1)
        with self.assertRaises(ValueError):
            find_confirmed_swings([1, 2], [0], left=1, right=1)
        with self.assertRaises(ValueError):
            find_confirmed_swings([0], [1], left=1, right=1)

    def test_does_not_emit_unconfirmed_tail(self):
        points = find_confirmed_swings([1, 2, 9], [0, 1, 2], left=1, right=2)
        self.assertEqual(points, ())


if __name__ == "__main__":
    unittest.main()
