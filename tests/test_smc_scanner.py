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


def analysis(*, trigger_index=39, levels=(105.0, 110.0, 120.0), swings=()):
    bullish_break = SimpleNamespace(direction="bullish", candle_index=trigger_index)
    range_swings = (
        SimpleNamespace(kind="low", index=20, confirmation_index=22, price=96.0),
        SimpleNamespace(kind="high", index=30, confirmation_index=32, price=104.0),
    )
    block = SimpleNamespace(
        direction="bullish", lower=98.0, upper=102.0, confirmation_index=30,
    )
    sweep = SimpleNamespace(direction="bullish", candle_index=38)
    liquidity = tuple(SimpleNamespace(price=price) for price in levels)
    return SimpleNamespace(
        structure_breaks=(bullish_break,),
        swings=tuple((*range_swings, *swings)),
        dealing_range=SimpleNamespace(ote_lower=99.0, ote_upper=101.0, high=104.0, low=96.0),
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
            timeframe: tuple(candle(i, close=99.0) if timeframe == "1h" else candle(i) for i in range(40))
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

    def test_tp2_tp3_can_use_confirmed_swings_after_nearest_liquidity_tp1(self):
        swings = (
            SimpleNamespace(kind="high", index=34, confirmation_index=36, price=110.0),
            SimpleNamespace(kind="high", index=37, confirmation_index=39, price=120.0),
        )

        with patch(
            "app.smc.scanner._analysis",
            side_effect=lambda candles, profile, timeframe: analysis(levels=(105.0,), swings=swings),
        ):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].targets, (105.0, 110.0, 120.0))

    def test_tp1_alone_is_enough_when_tp2_and_tp3_are_not_confirmed(self):
        # The fixture's range edge is not beyond TP1, and no farther swings
        # exist. TP2/TP3 must remain absent rather than rejecting the setup.
        with patch(
            "app.smc.scanner._analysis",
            side_effect=lambda candles, profile, timeframe: analysis(levels=(105.0,), swings=()),
        ):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].targets, (105.0,))

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
        # The 4h bias close must be strictly below the range EQ for a long.
        series = dict(self.series)
        series["4h"] = tuple(candle(i, close=99.0) for i in range(40))
        with patch("app.smc.scanner._analysis", side_effect=lambda candles, profile, timeframe: analysis()):
            candidates = scan_symbol("BTCUSDT", series, trigger_timeframe="15m")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].profile, "intraday")
        self.assertEqual(candidates[0].timeframe, "15m")

    def test_stale_one_minute_confirmation_is_rejected(self):
        stale_series = dict(self.series)
        stale_series["1m"] = tuple(candle(i - 10) for i in range(40))
        with patch("app.smc.scanner._analysis", side_effect=lambda candles, profile, timeframe: analysis()):
            candidates = scan_symbol("BTCUSDT", stale_series, trigger_timeframe="5m")
        self.assertEqual(candidates, [])

    def test_zone_touch_before_confirmation_does_not_require_price_still_inside_zone(self):
        zone_series = list(self.series["15m"])
        zone_series[-1] = candle(39, low=103.0, high=105.0, close=104.0)
        series = dict(self.series)
        series["15m"] = tuple(zone_series)
        with patch("app.smc.scanner._analysis", side_effect=lambda candles, profile, timeframe: analysis()):
            candidates = scan_symbol("BTCUSDT", series, trigger_timeframe="5m")
        self.assertEqual(len(candidates), 1)


    def test_premium_discount_mismatch_is_confluence_not_hard_veto(self):
        def mocked_analysis(candles, profile, timeframe):
            result = analysis()
            # Deliberately put price in HTF premium despite bullish structure.
            if timeframe == "1h":
                result.premium_discount = "premium"
            elif timeframe == "15m":
                result.premium_discount = "discount"
            return result

        diagnostics = {}
        with patch("app.smc.scanner._analysis", side_effect=mocked_analysis):
            candidates = scan_symbol(
                "BTCUSDT", self.series, trigger_timeframe="5m", diagnostics=diagnostics
            )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].direction, "long")
        self.assertFalse(candidates[0].evidence["premium_discount_aligned"])
        self.assertIn(
            "premium_discount_not_aligned_confluence_only", candidates[0].reasons
        )
        self.assertEqual(diagnostics.get("premium_discount_mismatch"), 1)


    def test_future_candles_on_other_timeframes_are_excluded_from_snapshot(self):
        # Timeframes can advance independently; analysis must be frozen at the
        # newest closed trigger candle, not use later HTF/zone/1m data.
        series = dict(self.series)
        for timeframe in ("1m", "15m", "1h"):
            series[timeframe] = series[timeframe] + (candle(40),)
        seen = {}

        def mocked_analysis(candles, profile, timeframe):
            seen[timeframe] = tuple(c.close_time_ms for c in candles)
            return analysis()

        with patch("app.smc.scanner._analysis", side_effect=mocked_analysis):
            candidates = scan_symbol("BTCUSDT", series, trigger_timeframe="5m")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(set(seen), {"1h", "15m", "5m", "1m"})
        trigger_close = series["5m"][-1].close_time_ms
        for timeframe, timestamps in seen.items():
            self.assertTrue(all(ts <= trigger_close for ts in timestamps), timeframe)
            self.assertEqual(len(timestamps), 40, timeframe)


if __name__ == "__main__":
    unittest.main()
