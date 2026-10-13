import unittest

from app.smc.breaks import StructureBreak, detect_structure_breaks
from app.smc.structure import SwingPoint


class StructureBreakTests(unittest.TestCase):
    def test_close_breaks_confirmed_high_as_bos_not_wick(self):
        swings = (SwingPoint("high", 1, 3, 10.0),)
        # The level is not eligible until index 3; close must exceed 10.
        self.assertEqual(
            detect_structure_breaks([9, 9, 9.5, 10, 10.1], swings),
            (
                StructureBreak("BOS", "bullish", 4, 1, 10.0),
            ),
        )

    def test_opposite_break_is_choch_and_flips_direction(self):
        swings = (
            SwingPoint("high", 1, 2, 10.0),
            SwingPoint("low", 3, 4, 6.0),
            SwingPoint("high", 5, 6, 12.0),
        )
        events = detect_structure_breaks([8, 9, 10.1, 8, 5.9, 11, 12.1], swings)
        self.assertEqual(
            [(e.kind, e.direction, e.candle_index) for e in events],
            [("BOS", "bullish", 2), ("CHoCH", "bearish", 4), ("CHoCH", "bullish", 6)],
        )

    def test_same_swing_never_emits_twice(self):
        swings = (SwingPoint("high", 1, 2, 10.0),)
        events = detect_structure_breaks([8, 9, 10.1, 11, 12], swings)
        self.assertEqual(len(events), 1)

    def test_future_swing_is_ignored_until_confirmation(self):
        swings = (SwingPoint("high", 1, 4, 10.0),)
        self.assertEqual(
            detect_structure_breaks([11, 12, 13, 14], swings),
            (),
        )
        self.assertEqual(
            detect_structure_breaks([8, 9, 9, 9, 11], swings)[0].candle_index,
            4,
        )

    def test_invalid_swing_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            detect_structure_breaks([1, 2], (SwingPoint("middle", 0, 0, 1.0),))


    def test_break_that_happened_before_swing_confirmation_is_not_emitted_late(self):
        swings = (SwingPoint("high", 1, 3, 10.0),)
        # Price closed above the eventual swing level before that swing became
        # knowable; confirmation must not retroactively manufacture a BOS.
        self.assertEqual(
            detect_structure_breaks([9, 11, 11.5, 12, 13], swings),
            (),
        )

    def test_non_finite_or_non_numeric_close_is_rejected(self):
        for closes in ([1, float("nan")], [1, float("inf")], [1, True], [1, "2"]):
            with self.subTest(closes=closes), self.assertRaises(ValueError):
                detect_structure_breaks(closes, ())

    def test_invalid_swing_indices_and_price_are_rejected_even_for_future_swings(self):
        invalid_swings = (
            SwingPoint("high", True, 99, 10.0),
            SwingPoint("high", 1, 1.5, 10.0),
            SwingPoint("high", 1, 99, float("nan")),
            SwingPoint("high", 1, 99, float("inf")),
        )
        for swing in invalid_swings:
            with self.subTest(swing=swing), self.assertRaises(ValueError):
                detect_structure_breaks([1, 2], (swing,))


if __name__ == "__main__":
    unittest.main()
