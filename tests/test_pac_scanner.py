import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.smc.pac_scanner import scan_symbol


END_MS = 1_800_000_000_000


def candle(index, timeframe_minutes=5, close=100.0):
    step = timeframe_minutes * 60_000
    opened = END_MS - (40 - index) * step
    return SimpleNamespace(
        open_time_ms=opened,
        close_time_ms=opened + step - 1,
        open=close, high=close + 1.0, low=close - 1.0, close=close, volume=100.0,
    )


def fake_analysis(timeframe):
    bias_break = SimpleNamespace(direction="bullish", candle_index=39 if timeframe == "1m" else 37, swing_index=30)
    block = SimpleNamespace(direction="bullish", lower=98.0, upper=101.0,
                            candle_index=25, confirmation_index=30)
    return SimpleNamespace(
        structure_breaks=(bias_break,) if timeframe in {"1h", "15m", "5m", "1m"} else (),
        swings=(), as_of_index=39, order_blocks=(block,),
        order_block_mitigation=(SimpleNamespace(mitigated=False),),
        fvg=(), fvg_fill=(), atr=(1.0,) * 40,
        liquidity_levels=(SimpleNamespace(price=104.0),),
        sweeps=(SimpleNamespace(direction="bullish", candle_index=35),),
        average_volume=(100.0,) * 40,
    )


class PACScannerTests(unittest.TestCase):
    def setUp(self):
        self.series = {
            "1m": tuple(candle(i, 1) for i in range(40)),
            "5m": tuple(candle(i, 5) for i in range(40)),
            "15m": tuple(candle(i, 15) for i in range(40)),
            "1h": tuple(candle(i, 60, 99.0) for i in range(40)),
            "4h": tuple(candle(i, 240, 99.0) for i in range(40)),
        }

    def test_pac_path_generates_candidate_with_real_liquidity_and_score(self):
        def analysis(candles, profile, timeframe):
            return fake_analysis(timeframe)

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.status, "CANDIDATE")
        self.assertEqual(candidate.direction, "long")
        self.assertIn(":PAC:", candidate.key)
        self.assertEqual(candidate.targets[0], 104.0)
        self.assertGreaterEqual(candidate.score, 6)
        self.assertEqual(candidate.evidence["zone_distance_atr"], 0.0)

    def test_scalp_rejects_without_current_aligned_one_minute_confirmation(self):
        def analysis(candles, profile, timeframe):
            result = fake_analysis(timeframe)
            if timeframe == "1m":
                result.structure_breaks = ()
            return result

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])

    def test_scalp_rejects_without_recent_aligned_trigger_structure(self):
        def analysis(candles, profile, timeframe):
            result = fake_analysis(timeframe)
            if timeframe == "5m":
                result.structure_breaks = ()
            return result

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])

    def test_scalp_rejects_sweep_that_is_not_before_trigger(self):
        def analysis(candles, profile, timeframe):
            result = fake_analysis(timeframe)
            if timeframe == "5m":
                result.sweeps = (SimpleNamespace(direction="bullish", candle_index=37),)
            return result

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])

    def test_scalp_rejects_one_minute_confirmation_before_retest(self):
        # A 1m BOS at the current index but with a close time before the 5m
        # retest must not qualify as a reaction confirmation.
        series = dict(self.series)
        one_minute = list(series["1m"])
        last = one_minute[-1]
        retest_close_ms = series["5m"][-2].close_time_ms
        one_minute[-1] = SimpleNamespace(
            open_time_ms=last.open_time_ms, close_time_ms=retest_close_ms - 1,
            open=last.open, high=last.high, low=last.low, close=last.close, volume=last.volume,
        )
        series["1m"] = tuple(one_minute)

        with patch("app.smc.pac_scanner._analysis",
                   side_effect=lambda candles, profile, timeframe: fake_analysis(timeframe)):
            candidates = scan_symbol("BTCUSDT", series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])

    def test_rejects_when_no_directional_liquidity_target(self):
        def analysis(candles, profile, timeframe):
            result = fake_analysis(timeframe)
            if timeframe == "5m":
                result.liquidity_levels = ()
            return result

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])

    def test_nearest_liquidity_below_minimum_rr_is_not_skipped(self):
        def analysis(candles, profile, timeframe):
            result = fake_analysis(timeframe)
            if timeframe == "5m":
                result.liquidity_levels = (
                    SimpleNamespace(price=101.0),
                    SimpleNamespace(price=104.0),
                )
            return result

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])

    def test_old_touch_before_trigger_does_not_count_as_retest(self):
        # Candle 36 touched the zone and candle 37 is the trigger break. Candles
        # 38-39 stay above it; entry remains within 0.75 ATR so only causality
        # (not the anti-chase rule) should reject this candidate.
        series = dict(self.series)
        trigger = list(series["5m"])
        for index in (38, 39):
            original = trigger[index]
            trigger[index] = SimpleNamespace(
                open_time_ms=original.open_time_ms, close_time_ms=original.close_time_ms,
                open=100.0, high=100.5, low=99.8, close=100.0, volume=100.0,
            )
        series["5m"] = tuple(trigger)

        def analysis(candles, profile, timeframe):
            result = fake_analysis(timeframe)
            if timeframe == "15m":
                result.order_blocks = (
                    SimpleNamespace(direction="bullish", lower=99.2, upper=99.5,
                                    candle_index=25, confirmation_index=30),
                )
            return result

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])

    def test_rejects_price_chasing_far_from_zone(self):
        series = dict(self.series)
        trigger = list(series["5m"])
        # Candle 38 retests the zone after the trigger; the latest close then
        # moves 1 ATR away, so the scanner must reject the chased entry.
        for index, high, low in ((38, 100.5, 98.5), (39, 101.0, 99.5)):
            original = trigger[index]
            trigger[index] = SimpleNamespace(
                open_time_ms=original.open_time_ms, close_time_ms=original.close_time_ms,
                open=100.0, high=high, low=low, close=100.0, volume=100.0,
            )
        series["5m"] = tuple(trigger)

        def analysis(candles, profile, timeframe):
            result = fake_analysis(timeframe)
            if timeframe == "15m":
                result.order_blocks = (
                    SimpleNamespace(direction="bullish", lower=98.0, upper=99.0,
                                    candle_index=25, confirmation_index=30),
                )
            return result

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", series, trigger_timeframe="5m")

        self.assertEqual(candidates, [])

    def test_profile_threshold_is_enforced(self):
        strict_scalp = replace(PROFILES_FOR_TEST["scalp"], score_threshold=8)
        with patch("app.smc.pac_scanner._analysis", side_effect=lambda candles, profile, timeframe: fake_analysis(timeframe)):
            with patch("app.smc.pac_scanner.PROFILES", {
                "scalp": strict_scalp,
                "intraday": PROFILES_FOR_TEST["intraday"],
            }):
                candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")
        self.assertEqual(candidates, [])

    def test_uses_nearest_causally_retested_zone_not_nearest_unretested_zone(self):
        def analysis(candles, profile, timeframe):
            result = fake_analysis(timeframe)
            if timeframe == "15m":
                result.order_blocks = (
                    SimpleNamespace(direction="bullish", lower=100.2, upper=100.5,
                                    candle_index=20, confirmation_index=30),
                    SimpleNamespace(direction="bullish", lower=98.5, upper=99.3,
                                    candle_index=24, confirmation_index=30),
                )
                result.order_block_mitigation = (
                    SimpleNamespace(mitigated=False),
                    SimpleNamespace(mitigated=False),
                )
            if timeframe == "5m":
                result.liquidity_levels = (SimpleNamespace(price=104.0),)
            return result

        # The closer OB is never touched; the farther OB is retested after
        # the trigger break and remains within the 0.75 ATR chase limit.
        trigger = list(self.series["5m"])
        for i in range(36, 40):
            trigger[i] = SimpleNamespace(
                open_time_ms=trigger[i].open_time_ms,
                close_time_ms=trigger[i].close_time_ms,
                open=100.0, high=100.1, low=99.2, close=100.0, volume=100.0,
            )
        series = dict(self.series)
        series["5m"] = tuple(trigger)

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", series, trigger_timeframe="5m")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].zone, (98.5, 99.3))
        self.assertGreaterEqual(abs(candidates[0].targets[0] - candidates[0].confirmation_price) /
                                abs(candidates[0].confirmation_price - candidates[0].stop_price), 1.49)

    def test_intraday_profile_uses_15m_trigger(self):
        def analysis(candles, profile, timeframe):
            result = fake_analysis(timeframe)
            if timeframe == "4h":
                result.structure_breaks = (SimpleNamespace(direction="bullish", candle_index=35, swing_index=30),)
            return result

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="15m")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].profile, "intraday")
        self.assertEqual(candidates[0].timeframe, "15m")


from app.smc.profiles import PROFILES as PROFILES_FOR_TEST


if __name__ == "__main__":
    unittest.main()
