import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from app.market_data import ClosedCandle, TIMEFRAMES
from app.smc.scanner import SetupCandidate, scan_symbol


class AutomaticScannerTests(unittest.TestCase):
    def candles(self, symbol="BTCUSDT", timeframe="5m", count=20, close=Decimal("100")):
        # Keep each timeframe's real candle duration and align the newest
        # close across series so the scanner's no-look-ahead snapshot has
        # sufficient historical 1m candles at the 5m confirmation time.
        step = {
            "1m": 60_000,
            "5m": 300_000,
            "15m": 900_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
        }[timeframe]
        common_close_ms = 1_800_000_000_000
        first_open_ms = common_close_ms - count * step + 1
        return tuple(
            ClosedCandle(
                symbol=symbol, timeframe=timeframe,
                open_time_ms=first_open_ms + i * step,
                close_time_ms=first_open_ms + (i + 1) * step - 1,
                open=Decimal("100"), high=Decimal("101"),
                low=Decimal("99"), close=close,
                volume=Decimal("10"),
            )
            for i in range(count)
        )

    def test_insufficient_windows_never_emit_a_setup(self):
        series = {tf: self.candles(timeframe=tf) for tf in TIMEFRAMES}
        self.assertEqual(scan_symbol("BTCUSDT", series, trigger_timeframe="5m"), [])
        self.assertEqual(scan_symbol("BTCUSDT", series, trigger_timeframe="15m"), [])

    def test_only_profile_confirmation_timeframes_trigger_scans(self):
        series = {tf: self.candles(timeframe=tf, count=60) for tf in TIMEFRAMES}
        self.assertEqual(scan_symbol("BTCUSDT", series, trigger_timeframe="1m"), [])
        self.assertEqual(scan_symbol("BTCUSDT", series, trigger_timeframe="4h"), [])


    def test_emits_candidate_when_multitimeframe_smc_rules_align(self):
        series = {tf: self.candles(timeframe=tf, count=60, close=Decimal("99") if tf == "1h" else Decimal("100")) for tf in TIMEFRAMES}
        block = SimpleNamespace(direction="bullish", lower=99.0, upper=101.0, confirmation_index=10)
        block_state = SimpleNamespace(mitigated=False)
        gap = SimpleNamespace(direction="bullish", lower=99.5, upper=100.5, confirmation_index=12)
        gap_fill = SimpleNamespace(fully_filled=False)

        def analysis_for(candles, profile, timeframe):
            last = len(candles) - 1
            base = dict(
                as_of_index=last, structure_breaks=(), swings=(), order_blocks=(),
                order_block_mitigation=(), fvg=(), fvg_fill=(), sweeps=(),
                liquidity_levels=(), dealing_range=None, premium_discount=None,
                atr=tuple([1.0] * len(candles)),
                average_volume=tuple([100.0] * len(candles)),
            )
            if timeframe == "1h":
                base["structure_breaks"] = (SimpleNamespace(direction="bullish", candle_index=last - 2),)
                base["swings"] = (
                    SimpleNamespace(kind="low", index=20, confirmation_index=22, price=97.0),
                    SimpleNamespace(kind="high", index=30, confirmation_index=32, price=103.0),
                )
                base["premium_discount"] = "discount"
            elif timeframe == "15m":
                base.update(
                    structure_breaks=(SimpleNamespace(direction="bullish", candle_index=last - 2),),
                    swings=(
                        SimpleNamespace(kind="low", index=20, confirmation_index=22, price=97.0),
                        SimpleNamespace(kind="high", index=30, confirmation_index=32, price=103.0),
                    ),
                    order_blocks=(block,), order_block_mitigation=(block_state,),
                    fvg=(gap,), fvg_fill=(gap_fill,),
                    dealing_range=SimpleNamespace(ote_lower=99.0, ote_upper=101.0),
                    premium_discount="discount",
                )
            elif timeframe == "5m":
                base.update(
                    structure_breaks=(SimpleNamespace(direction="bullish", candle_index=last),),
                    sweeps=(SimpleNamespace(direction="bullish", candle_index=last - 1),),
                    liquidity_levels=tuple(SimpleNamespace(price=p) for p in (110.0, 120.0, 130.0)),
                )
            elif timeframe == "1m":
                base["structure_breaks"] = (SimpleNamespace(direction="bullish", candle_index=last),)
            return SimpleNamespace(**base)

        with patch("app.smc.scanner._analysis", side_effect=analysis_for):
            candidates = scan_symbol("BTCUSDT", series, trigger_timeframe="5m")
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].profile, "scalp")
        self.assertEqual(candidates[0].direction, "long")
        self.assertEqual(len(candidates[0].targets), 3)
        self.assertTrue(candidates[0].evidence["order_block_fvg_overlap"])

    def test_candidate_serialization_is_json_ready(self):
        candidate = SetupCandidate(
            key="BTCUSDT:scalp:long:OB:1:2", symbol="BTCUSDT",
            profile="scalp", direction="long", status="CANDIDATE",
            confirmation_time_ms=2, confirmation_price=100.0, stop_price=95.0,
            targets=(110.0, 115.0), score=7, reasons=("sweep",),
            zone=(98.0, 101.0), timeframe="5m",
        )
        payload = candidate.as_dict()
        self.assertEqual(payload["targets"], [110.0, 115.0])
        self.assertEqual(payload["zone"], [98.0, 101.0])
        self.assertEqual(payload["status"], "CANDIDATE")


if __name__ == "__main__":
    unittest.main()
