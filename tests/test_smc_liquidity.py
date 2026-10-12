import unittest

from app.smc.liquidity import (
    LiquidityLevel,
    detect_liquidity_sweeps,
    find_liquidity_levels,
    find_current_day_extremes,
    is_level_near_zone,
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


    def test_current_day_extremes_exclude_current_candle_and_prior_utc_day(self):
        # 2026-01-01 23:59 UTC, then 2026-01-02 00:00 and 00:01 UTC.
        timestamps = [1767311940000, 1767312000000, 1767312060000]
        levels = find_current_day_extremes(
            timestamps, [100, 102, 110], [90, 91, 80], as_of_index=2
        )
        self.assertEqual([(x.kind, x.price) for x in levels], [("high", 102.0), ("low", 91.0)])
        self.assertEqual(levels[0].confirmation_index, 1)

    def test_level_distance_from_zone_uses_atr_limit(self):
        self.assertTrue(is_level_near_zone(99, 100, 105, 2, max_distance_atr=0.5))
        self.assertFalse(is_level_near_zone(98.9, 100, 105, 2, max_distance_atr=0.5))
        self.assertTrue(is_level_near_zone(103, 100, 105, 2, max_distance_atr=0))


if __name__ == "__main__":
    unittest.main()


    def test_previous_utc_day_extremes_are_not_visible_during_source_day(self):
        from datetime import datetime, timezone
        from app.smc.liquidity import find_previous_day_extremes

        def ms(value):
            return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)

        levels = find_previous_day_extremes(
            highs=[10, 12, 11, 13],
            lows=[7, 8, 6, 9],
            timestamps_ms=[
                ms("2026-10-12T23:59:00"),
                ms("2026-10-13T00:00:00"),
                ms("2026-10-13T00:01:00"),
                ms("2026-10-14T00:00:00"),
            ],
        )
        # The 12 Oct levels are known only after a candle from 13 Oct exists.
        day_12 = [level for level in levels if level.source_indices[0] == 0]
        self.assertEqual(len(day_12), 2)
        self.assertEqual({level.kind: level.price for level in day_12}, {"high": 10.0, "low": 7.0})
        self.assertTrue(all(level.confirmation_index == 1 for level in day_12))

    def test_previous_day_extremes_reject_unsorted_timestamps(self):
        from app.smc.liquidity import find_previous_day_extremes
        with self.assertRaises(ValueError):
            find_previous_day_extremes([2, 3], [1, 2], [2000, 1000])

    def test_previous_day_extremes_require_equal_array_lengths(self):
        from app.smc.liquidity import find_previous_day_extremes
        with self.assertRaises(ValueError):
            find_previous_day_extremes([2], [1, 0], [1000])
