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
