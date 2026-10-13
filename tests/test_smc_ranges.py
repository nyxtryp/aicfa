import unittest

from app.smc.ranges import DealingRange, find_dealing_range, premium_discount
from app.smc.structure import SwingPoint


class DealingRangeTests(unittest.TestCase):
    def test_bullish_leg_equilibrium_and_ote(self):
        swings = (
            SwingPoint("low", 2, 4, 100.0),
            SwingPoint("high", 8, 10, 200.0),
        )
        result = find_dealing_range(swings, as_of_index=10)
        self.assertEqual(
            result,
            DealingRange("bullish", 2, 8, 10, 100.0, 200.0, 150.0, 121.0, 138.0),
        )
        self.assertEqual(premium_discount(120, result), "discount")
        self.assertEqual(premium_discount(180, result), "premium")
        self.assertEqual(premium_discount(150, result), "equilibrium")

    def test_bearish_leg_ote_is_measured_up_from_low(self):
        result = find_dealing_range(
            [SwingPoint("high", 2, 4, 200.0), SwingPoint("low", 8, 10, 100.0)],
            as_of_index=10,
        )
        self.assertEqual((result.ote_lower, result.ote_upper), (162.0, 179.0))
        self.assertEqual(result.direction, "bearish")

    def test_future_unconfirmed_swings_are_not_used(self):
        swings = (
            SwingPoint("low", 2, 4, 100.0),
            SwingPoint("high", 8, 10, 200.0),
        )
        self.assertIsNone(find_dealing_range(swings, as_of_index=9))

    def test_same_kind_swings_collapse_to_more_extreme(self):
        result = find_dealing_range(
            [
                SwingPoint("low", 1, 2, 110.0),
                SwingPoint("low", 3, 4, 100.0),
                SwingPoint("high", 6, 7, 180.0),
            ],
            as_of_index=7,
        )
        self.assertEqual((result.start_index, result.end_index), (3, 6))
        self.assertEqual((result.low, result.high), (100.0, 180.0))

    def test_invalid_future_swing_kind_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "swing kind"):
            find_dealing_range(
                [SwingPoint("unknown", 5, 8, 200.0)],
                as_of_index=4,
            )

    def test_non_finite_swing_price_is_rejected_even_if_unconfirmed(self):
        for price in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(price=price):
                with self.assertRaisesRegex(ValueError, "swing prices"):
                    find_dealing_range(
                        [SwingPoint("high", 5, 8, price)],
                        as_of_index=4,
                    )

    def test_invalid_ote_bounds_rejected(self):
        with self.assertRaises(ValueError):
            find_dealing_range([], as_of_index=0, ote_min=0.8, ote_max=0.7)

    def test_invalid_swing_indices_are_rejected(self):
        malformed = [
            SwingPoint("low", -1, 2, 100.0),
            SwingPoint("high", 5, 4, 200.0),
        ]
        for swing in malformed:
            with self.subTest(swing=swing):
                with self.assertRaisesRegex(ValueError, "swing indices"):
                    find_dealing_range([swing], as_of_index=10)


if __name__ == "__main__":
    unittest.main()
