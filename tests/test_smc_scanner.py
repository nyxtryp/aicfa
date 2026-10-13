import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.smc.scanner import scan_symbol


def candle(index, *, low=99.0, high=101.0, close=100.0):
    return SimpleNamespace(
        open_time_ms=1_800_000_000_000 + index * 60_000,
        close_time_ms=1_800_000_059_999 + index * 60_000,
        open=100.0,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def analysis(*, trigger_index=39, levels=(105.0, 110.0, 120.0)):
    bullish_break = SimpleNamespace(direction="bullish", candle_index=trigger_index)
    block = SimpleNamespace(
        direction="bullish", lower=98.0, upper=102.0, confirmation_index=30,
    )
    sweep = SimpleNamespace(direction="bullish", candle_index=38)
    liquidity = tuple(SimpleNamespace(price=price) for price in levels)
    return SimpleNamespace(
        structure_breaks=(bullish_break,),
        dealing_range=SimpleNamespace(ote_lower=99.0, ote_upper=101.0),
        premium_discount="discount",
        as_of_index=39,
        order_blocks=(block,),
        order_block_mitigation=(SimpleNamespace(mitigated=False),),
        fvg=(),
        fvg_fill=(),
        sweeps=(sweep,),
        atr=(1.0,) * 40,
        liquidity_levels=liquidity,
        average_volume=(100.0,) * 40,
    )


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.series = {
            timeframe: tuple(candle(i) for i in range(40))
            for timeframe in ("1m", "5m", "15m", "1h", "4h")
        }

    def test_matching_closed_confirmation_produces_deterministic_candidate(self):
        with patch("app.smc.scanner._analysis", side_effect=lambda candles, profile, timeframe: analysis()):
            first = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")
            second = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(len(first), 1)
        self.assertEqual(first, second)
        candidate = first[0]
        self.assertEqual(candidate.profile, "scalp")
        self.assertEqual(candidate.direction, "long")
        self.assertEqual(candidate.confirmation_time_ms, self.series["5m"][-1].close_time_ms)
        self.assertEqual(candidate.targets, (105.0, 110.0, 120.0))
        self.assertEqual(candidate.status, "CANDIDATE")

    def test_old_confirmation_break_is_not_replayed_as_new_candidate(self):
        def mocked_analysis(candles, profile, timeframe):
            return analysis(trigger_index=38 if timeframe == "5m" else 39)

        with patch("app.smc.scanner._analysis", side_effect=mocked_analysis):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])

    def test_unrelated_trigger_timeframe_does_not_run_other_profile(self):
        with patch("app.smc.scanner._analysis", side_effect=AssertionError("analysis should not run")):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="1m")

        self.assertEqual(candidates, [])

    def test_incomplete_series_cannot_generate_candidate(self):
        short_series = dict(self.series)
        short_series["5m"] = short_series["5m"][:39]
        with patch("app.smc.scanner._analysis", side_effect=AssertionError("short series must be rejected first")):
            candidates = scan_symbol("BTCUSDT", short_series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])


    def test_scalp_requires_current_one_minute_confirmation(self):
        # TZ §5–6: scalp candidates require an additional 1m confirmation;
        # having a valid 5m confirmation alone must never create a candidate.
        series_without_1m = dict(self.series)
        series_without_1m["1m"] = ()
        with patch("app.smc.scanner._analysis", side_effect=lambda candles, profile, timeframe: analysis()):
            candidates = scan_symbol("BTCUSDT", series_without_1m, trigger_timeframe="5m")
        self.assertEqual(candidates, [])

    def test_intraday_trigger_only_scans_intraday_profile(self):
        with patch("app.smc.scanner._analysis", side_effect=lambda candles, profile, timeframe: analysis()):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="15m")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].profile, "intraday")
        self.assertEqual(candidates[0].timeframe, "15m")


if __name__ == "__main__":
    unittest.main()
