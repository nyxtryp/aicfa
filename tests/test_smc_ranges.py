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

    def test_fractional_and_boolean_indices_are_rejected(self):
        invalid_inputs = [
            ([SwingPoint("low", 1.5, 2, 100.0)], 2),
            ([SwingPoint("low", 1, True, 100.0)], 2),
            ([], 1.5),
            ([], True),
        ]
        for swings, as_of_index in invalid_inputs:
            with self.subTest(swings=swings, as_of_index=as_of_index):
                with self.assertRaises(ValueError):
                    find_dealing_range(swings, as_of_index=as_of_index)

    def test_invalid_swing_indices_are_rejected(self):
        malformed = [
            SwingPoint("low", -1, 2, 100.0),
            SwingPoint("high", 5, 4, 200.0),
        ]
        for swing in malformed:
            with self.subTest(swing=swing):
                with self.assertRaisesRegex(ValueError, "swing indices"):
                    find_dealing_range([swing], as_of_index=10)


    def test_directional_ote_skips_latest_countertrend_leg(self):
        swings = (
            SwingPoint("low", 2, 4, 100.0),
            SwingPoint("high", 8, 10, 200.0),
            SwingPoint("low", 14, 16, 120.0),
        )
        result = find_dealing_range(swings, as_of_index=16, direction="bullish")
        self.assertEqual((result.start_index, result.end_index), (2, 8))
        self.assertEqual((result.ote_lower, result.ote_upper), (121.0, 138.0))
        self.assertEqual(result.direction, "bullish")

    def test_htf_range_can_anchor_to_swing_broken_by_structure_event(self):
        swings = (
            SwingPoint("low", 2, 4, 100.0),
            SwingPoint("high", 8, 10, 200.0),
            SwingPoint("low", 14, 16, 120.0),
            SwingPoint("high", 20, 22, 220.0),
        )
        result = find_dealing_range(
            swings, as_of_index=25, direction="bullish", end_swing_index=8,
        )
        self.assertEqual((result.start_index, result.end_index), (2, 8))
        self.assertEqual(result.equilibrium, 150.0)

    def test_anchored_range_cannot_use_swing_unconfirmed_at_break(self):
        swings = (
            SwingPoint("low", 2, 4, 100.0),
            SwingPoint("high", 8, 10, 200.0),
        )
        result = find_dealing_range(
            swings, as_of_index=9, direction="bullish", end_swing_index=8,
        )
        self.assertIsNone(result)

    def test_bullish_pd_uses_latest_confirmed_bullish_impulse_not_old_bos_swing(self):
        # The latest HTF BOS can reference an old swing. Later confirmed
        # structure has formed a newer bullish impulse and then a pullback.
        # PD must use the latest bullish leg (150 -> 240), not the stale 100 -> 200.
        swings = (
            SwingPoint("low", 2, 4, 100.0),
            SwingPoint("high", 8, 10, 200.0),
            SwingPoint("low", 14, 16, 150.0),
            SwingPoint("high", 20, 22, 240.0),
            SwingPoint("low", 26, 28, 180.0),  # countertrend pullback
            SwingPoint("high", 34, 36, 260.0),  # not confirmed at snapshot
        )
        result = find_dealing_range(swings, as_of_index=30, direction="bullish")
        self.assertEqual((result.start_index, result.end_index), (14, 20))
        self.assertEqual((result.low, result.high, result.equilibrium), (150.0, 240.0, 195.0))
        self.assertEqual(result.confirmation_index, 22)

    def test_bearish_pd_uses_latest_confirmed_bearish_impulse_not_old_choch_swing(self):
        # Mirror of the bullish case: a newer bearish impulse wins over the
        # stale range that the latest structure event originally broke.
        swings = (
            SwingPoint("high", 2, 4, 300.0),
            SwingPoint("low", 8, 10, 200.0),
            SwingPoint("high", 14, 16, 250.0),
            SwingPoint("low", 20, 22, 140.0),
            SwingPoint("high", 26, 28, 180.0),  # countertrend pullback
            SwingPoint("low", 34, 36, 120.0),  # not confirmed at snapshot
        )
        result = find_dealing_range(swings, as_of_index=30, direction="bearish")
        self.assertEqual((result.start_index, result.end_index), (14, 20))
        self.assertEqual((result.low, result.high, result.equilibrium), (140.0, 250.0, 195.0))
        self.assertEqual(result.confirmation_index, 22)

    def test_anchored_range_requires_direction(self):
        with self.assertRaisesRegex(ValueError, "direction is required"):
            find_dealing_range(
                [SwingPoint("low", 2, 4, 100.0), SwingPoint("high", 8, 10, 200.0)],
                as_of_index=10, end_swing_index=8,
            )

    def test_invalid_direction_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "direction must be"):
            find_dealing_range([], as_of_index=0, direction="long")


if __name__ == "__main__":
    unittest.main()
