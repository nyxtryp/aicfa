import unittest

from app.smc.engine import analyze_smc
from app.smc.presentation import to_chart_payload


class SMCChartPayloadTests(unittest.TestCase):
    @staticmethod
    def controlled_candles():
        opens = [9.0, 10.0, 10.0, 9.0, 11.0, 11.0, 10.0, 12.0, 8.0]
        highs = [10.0, 12.0, 11.0, 10.0, 13.0, 12.0, 11.0, 14.0, 9.0]
        lows = [8.0, 9.0, 8.0, 7.0, 10.0, 9.0, 8.0, 11.0, 7.0]
        closes = [9.5, 11.0, 9.0, 9.5, 12.5, 11.5, 9.0, 12.5, 7.5]
        volumes = [100.0] * len(closes)
        timestamps = [1_790_000_000_000 + i * 60_000 for i in range(10)]
        return opens, highs, lows, closes, volumes, timestamps

    def test_payload_maps_events_to_candle_timestamps_and_ignores_future(self):
        opens, highs, lows, closes, volumes, timestamps = self.controlled_candles()
        analysis = analyze_smc(
            opens, highs, lows, closes, volumes, timestamps[:len(closes)],
            swing_left=1, swing_right=1, atr_period=2, volume_period=2,
        )
        payload = to_chart_payload(analysis, timestamps)

        self.assertEqual(payload["as_of_timestamp_ms"], timestamps[8])
        self.assertEqual(
            [(event["kind"], event["timestamp_ms"])
             for event in payload["structure_breaks"]],
            [("BOS", timestamps[4]), ("CHoCH", timestamps[8])],
        )
        self.assertEqual(payload["order_blocks"][0]["mitigation_timestamp_ms"], timestamps[8])
        self.assertNotIn(str(timestamps[9]), str(payload))

    def test_payload_rejects_missing_or_non_increasing_timestamps(self):
        opens, highs, lows, closes, volumes, timestamps = self.controlled_candles()
        analysis = analyze_smc(
            opens, highs, lows, closes, volumes, timestamps[:len(closes)],
            swing_left=1, swing_right=1, atr_period=2, volume_period=2,
        )
        with self.assertRaisesRegex(ValueError, "outside"):
            to_chart_payload(analysis, timestamps[:8])
        duplicate = list(timestamps)
        duplicate[3] = duplicate[2]
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            to_chart_payload(analysis, duplicate)

    def test_payload_rejects_non_integer_timestamps_instead_of_truncating(self):
        opens, highs, lows, closes, volumes, timestamps = self.controlled_candles()
        analysis = analyze_smc(
            opens, highs, lows, closes, volumes, timestamps[:len(closes)],
            swing_left=1, swing_right=1, atr_period=2, volume_period=2,
        )
        fractional = list(timestamps)
        fractional[2] = fractional[2] + 0.5
        with self.assertRaisesRegex(ValueError, "integer milliseconds"):
            to_chart_payload(analysis, fractional)
        boolean = list(timestamps)
        boolean[2] = True
        with self.assertRaisesRegex(ValueError, "integer milliseconds"):
            to_chart_payload(analysis, boolean)


if __name__ == "__main__":
    unittest.main()
