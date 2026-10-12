import unittest

from app.smc.liquidity import (
    LiquidityLevel,
    detect_liquidity_sweeps,
    find_liquidity_levels,
)
from app.smc.structure import SwingPoint


class LiquidityTests(unittest.TestCase):
    def test_equal_swing_highs_merge_within_atr_tolerance(self):
        swings = (
            SwingPoint("high", 2, 3, 100.0),
            SwingPoint("high", 8, 9, 100.5),
            SwingPoint("low", 5, 6, 90.0),
        )
        levels = find_liquidity_levels(swings, [1.0] * 12, tolerance_atr=0.6)
        equal = [level for level in levels if level.equal_level]
        self.assertEqual(len(equal), 1)
        self.assertEqual(equal[0].source_indices, (2, 8))
        self.assertEqual(equal[0].confirmation_index, 9)

    def test_sweep_requires_wick_beyond_and_close_back_inside(self):
        level = LiquidityLevel("high", 10.0, (2, 5), 2, True)
        events = detect_liquidity_sweeps(
            highs=[9, 9, 9, 11, 12],
            lows=[8, 8, 8, 9, 9],
            closes=[8.5, 8.5, 8.5, 9.5, 9.5],
            levels=[level],
        )
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].direction, events[0].candle_index), ("bearish", 3))

    def test_low_sweep_is_bullish_and_level_emits_once(self):
        level = LiquidityLevel("low", 5.0, (1,), 2, False)
        events = detect_liquidity_sweeps(
            highs=[7, 7, 7, 7],
            lows=[4, 4, 4, 4],
            closes=[6, 6, 6, 6],
            levels=[level],
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].direction, "bullish")

    def test_levels_without_positive_atr_are_skipped(self):
        swings = (SwingPoint("low", 1, 2, 5.0),)
        self.assertEqual(find_liquidity_levels(swings, [0.0, 0.0, 0.0]), ())

    def test_rejects_inconsistent_candles(self):
        with self.assertRaises(ValueError):
            detect_liquidity_sweeps([1], [2], [1], [])


if __name__ == "__main__":
    unittest.main()
