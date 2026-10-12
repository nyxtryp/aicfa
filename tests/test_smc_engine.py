import unittest

from app.smc.engine import analyze_smc


class SMCAnalysisTests(unittest.TestCase):
    @staticmethod
    def candles(count=16):
        closes = [10, 11, 12, 11, 9, 8, 10, 12, 13, 11, 10, 14, 15, 12, 11, 13][:count]
        opens = [
            close - 0.25 if i == 0 or close >= closes[i - 1] else close + 0.25
            for i, close in enumerate(closes)
        ]
        highs = [max(o, c) + 0.5 for o, c in zip(opens, closes)]
        lows = [min(o, c) - 0.5 for o, c in zip(opens, closes)]
        volumes = [float(i + 1) for i in range(len(closes))]
        timestamps = [1_790_000_000_000 + i * 60_000 for i in range(len(closes))]
        return opens, highs, lows, closes, volumes, timestamps

    def test_control_candles_produce_expected_bullish_fvg(self):
        from app.smc.fvg import FairValueGap, FairValueGapFill

        result = analyze_smc(
            opens=[9.0, 11.0, 13.2],
            highs=[10.0, 12.0, 14.0],
            lows=[8.0, 10.0, 13.0],
            closes=[9.0, 11.0, 13.5],
            volumes=[100.0, 110.0, 120.0],
            timestamps_ms=[1_790_000_000_000, 1_790_000_060_000, 1_790_000_120_000],
            swing_left=1, swing_right=1, atr_period=1, volume_period=1,
        )
        expected_gap = FairValueGap("bullish", 0, 2, 10.0, 13.0)
        self.assertEqual(result.fvg, (expected_gap,))
        self.assertEqual(result.fvg_fill, (FairValueGapFill(expected_gap, 2, 0.0, False),))

    def test_snapshot_is_deterministic(self):
        args = self.candles()
        first = analyze_smc(*args, as_of_index=12, atr_period=3, volume_period=3)
        second = analyze_smc(*args, as_of_index=12, atr_period=3, volume_period=3)
        self.assertEqual(first, second)

    def test_future_candles_cannot_change_past_snapshot(self):
        args = self.candles()
        snapshot = analyze_smc(*args, as_of_index=10, atr_period=3, volume_period=3)
        prefix = tuple(values[:11] for values in args)
        prefix_snapshot = analyze_smc(*prefix, atr_period=3, volume_period=3)
        self.assertEqual(snapshot, prefix_snapshot)
        self.assertTrue(all(x.confirmation_index <= 10 for x in snapshot.swings))
        self.assertTrue(all(x.candle_index <= 10 for x in snapshot.structure_breaks))
        self.assertTrue(all(x.confirmation_index <= 10 for x in snapshot.fvg))
        self.assertEqual(len(snapshot.order_block_mitigation), len(snapshot.order_blocks))
        self.assertTrue(all(
            x.mitigation_index is None or x.mitigation_index <= 10
            for x in snapshot.order_block_mitigation
        ))

    def test_controlled_candles_produce_expected_bos_choch_and_order_blocks(self):
        opens = [9.0, 10.0, 10.0, 9.0, 11.0, 11.0, 10.0, 12.0, 8.0]
        highs = [10.0, 12.0, 11.0, 10.0, 13.0, 12.0, 11.0, 14.0, 9.0]
        lows = [8.0, 9.0, 8.0, 7.0, 10.0, 9.0, 8.0, 11.0, 7.0]
        closes = [9.5, 11.0, 9.0, 9.5, 12.5, 11.5, 9.0, 12.5, 7.5]
        volumes = [100.0] * len(closes)
        timestamps = [1_790_000_000_000 + i * 60_000 for i in range(len(closes))]

        result = analyze_smc(
            opens, highs, lows, closes, volumes, timestamps,
            swing_left=1, swing_right=1, atr_period=2, volume_period=2,
        )

        self.assertEqual(
            [(event.kind, event.direction, event.candle_index, event.swing_index)
             for event in result.structure_breaks],
            [("BOS", "bullish", 4, 1), ("CHoCH", "bearish", 8, 6)],
        )
        self.assertEqual(
            [(block.direction, block.candle_index, block.confirmation_index)
             for block in result.order_blocks],
            [("bullish", 2, 4), ("bearish", 7, 8)],
        )

    def test_previous_day_high_can_be_swept_on_first_candle_of_new_utc_day(self):
        opens = [8.2, 9.0, 9.2, 10.5]
        highs = [9.0, 10.0, 9.5, 11.0]
        lows = [8.0, 8.5, 8.2, 9.0]
        closes = [8.5, 9.5, 9.0, 9.5]
        volumes = [100.0, 110.0, 105.0, 120.0]
        timestamps = [1_791_849_420_000 + i * 60_000 for i in range(4)]

        result = analyze_smc(
            opens, highs, lows, closes, volumes, timestamps,
            swing_left=1, swing_right=1, atr_period=2, volume_period=2,
        )

        self.assertTrue(any(
            sweep.candle_index == 3
            and sweep.direction == "bearish"
            and sweep.level == 10.0
            and sweep.level_kind == "high"
            for sweep in result.sweeps
        ))

    def test_rejects_mismatched_arrays_and_out_of_range_index(self):
        args = self.candles()
        mismatched = list(args)
        mismatched[4] = mismatched[4][:-1]
        with self.assertRaises(ValueError):
            analyze_smc(*mismatched, as_of_index=4)
        with self.assertRaises(ValueError):
            analyze_smc(*args, as_of_index=len(args[0]))

    def test_zone_filter_requires_atr_before_it_can_keep_levels(self):
        args = self.candles()
        result = analyze_smc(
            *args, as_of_index=12, atr_period=3, volume_period=3,
            zone_bounds=(0.0, 100.0), max_zone_distance_atr=0.0,
        )
        self.assertTrue(all(0.0 <= level.price <= 100.0 for level in result.liquidity_levels))


if __name__ == "__main__":
    unittest.main()
