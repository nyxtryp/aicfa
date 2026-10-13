import unittest

from app.smc.liquidity import (
    LiquidityLevel,
    detect_liquidity_sweeps,
    detect_current_day_sweeps,
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

    def test_liquidity_rejects_non_finite_prices_and_invalid_parameters(self):
        level = LiquidityLevel("high", 10.0, (0,), 0, False)
        for value in (float("nan"), float("inf"), True, "10"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                detect_liquidity_sweeps([11], [8], [9], [LiquidityLevel("high", value, (0,), 0)])
            with self.subTest(atr=value), self.assertRaises(ValueError):
                find_liquidity_levels((SwingPoint("high", 0, 0, 10.0),), [value])
        with self.assertRaises(ValueError):
            detect_liquidity_sweeps([11], [8], [9], [level], max_age=1.5)
        with self.assertRaises(ValueError):
            find_liquidity_levels((SwingPoint("high", True, 1, 10.0),), [1.0, 1.0])

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

    def test_current_day_sweep_uses_only_prior_candles(self):
        # Both candles are on the same UTC day. Candle 1 sweeps candle 0's high.
        events = detect_current_day_sweeps(
            timestamps_ms=[1791849600000, 1791849660000],
            highs=[10.0, 12.0],
            lows=[8.0, 8.5],
            closes=[9.0, 9.5],
        )
        self.assertEqual(
            [(event.direction, event.candle_index, event.level, event.source_indices)
             for event in events],
            [("bearish", 1, 10.0, (0,))],
        )

    def test_current_day_sweep_rejects_duplicate_timestamps(self):
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            detect_current_day_sweeps([1000, 1000], [2, 3], [1, 1], [1.5, 2.0])

    def test_level_distance_from_zone_uses_atr_limit(self):
        self.assertTrue(is_level_near_zone(99, 100, 105, 2, max_distance_atr=0.5))
        self.assertFalse(is_level_near_zone(98.9, 100, 105, 2, max_distance_atr=0.5))
        self.assertTrue(is_level_near_zone(103, 100, 105, 2, max_distance_atr=0))


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
        self.assertTrue(all(level.confirmation_index == 0 for level in day_12))

    def test_previous_day_extremes_reject_unsorted_timestamps(self):
        from app.smc.liquidity import find_previous_day_extremes
        with self.assertRaises(ValueError):
            find_previous_day_extremes([2, 3], [1, 2], [2000, 1000])

    def test_previous_day_extremes_reject_duplicate_timestamps(self):
        from app.smc.liquidity import find_previous_day_extremes
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            find_previous_day_extremes([2, 3], [1, 2], [1000, 1000])

    def test_previous_day_extremes_require_equal_array_lengths(self):
        from app.smc.liquidity import find_previous_day_extremes
        with self.assertRaises(ValueError):
            find_previous_day_extremes([2], [1, 0], [1000])


    def test_prior_day_level_can_be_swept_on_first_next_day_candle(self):
        from datetime import datetime, timezone
        from app.smc.liquidity import find_previous_day_extremes

        def ms(value):
            return int(datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp() * 1000)

        levels = find_previous_day_extremes(
            highs=[10, 11],
            lows=[7, 8],
            timestamps_ms=[ms("2026-10-12T23:59:00"), ms("2026-10-13T00:00:00")],
        )
        events = detect_liquidity_sweeps(
            highs=[10, 11], lows=[7, 8], closes=[9, 9.5], levels=levels
        )
        self.assertEqual([(event.direction, event.candle_index) for event in events], [("bearish", 1)])



    def test_previous_day_extremes_reject_non_finite_prices_and_bad_timestamps(self):
        from app.smc.liquidity import find_previous_day_extremes
        for value in (float("nan"), float("inf"), True, "10"):
            with self.subTest(price=value), self.assertRaises(ValueError):
                find_previous_day_extremes([value, 11], [1, 2], [1000, 86401000])
        for value in (True, 1000.5, "1000"):
            with self.subTest(timestamp=value), self.assertRaises(ValueError):
                find_previous_day_extremes([2, 3], [1, 2], [value, 86401000])

    def test_current_day_extremes_reject_bad_inputs(self):
        for index in (True, 1.0):
            with self.subTest(index=index), self.assertRaises(ValueError):
                find_current_day_extremes([1000, 2000], [2, 3], [1, 2], as_of_index=index)
        for timestamps in ([1000, True], [1000, 1500.5], [2000, 1000]):
            with self.subTest(timestamps=timestamps), self.assertRaises(ValueError):
                find_current_day_extremes(timestamps, [2, 3], [1, 2], as_of_index=1)
        with self.assertRaises(ValueError):
            find_current_day_extremes([1000, 2000], [2, float("nan")], [1, 2], as_of_index=1)

    def test_current_day_sweeps_reject_non_finite_ohlc_and_bad_timestamp_types(self):
        for value in (float("nan"), float("inf"), True, "10"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                detect_current_day_sweeps([1000], [value], [1], [1.5])
        for value in (True, 1000.5, "1000"):
            with self.subTest(timestamp=value), self.assertRaises(ValueError):
                detect_current_day_sweeps([value], [2], [1], [1.5])

    def test_zone_distance_rejects_non_finite_inputs(self):
        for value in (float("nan"), float("inf"), True, "100"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                is_level_near_zone(value, 100, 105, 2, max_distance_atr=1)


if __name__ == "__main__":
    unittest.main()
