import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.smc.pac_scanner import scan_symbol


def candle(index, timeframe_minutes=5, close=100.0):
    return SimpleNamespace(
        open_time_ms=1_800_000_000_000 + index * 60_000,
        close_time_ms=1_800_000_000_000 + (index + 1) * 60_000 - 1,
        open=close, high=close + 1.0, low=close - 1.0, close=close, volume=100.0,
    )


def fake_analysis(timeframe):
    bias_break = SimpleNamespace(direction="bullish", candle_index=35, swing_index=30)
    block = SimpleNamespace(direction="bullish", lower=98.0, upper=101.0,
                            candle_index=25, confirmation_index=30)
    return SimpleNamespace(
        structure_breaks=(bias_break,) if timeframe in {"1h", "15m"} else (),
        swings=(), as_of_index=39, order_blocks=(block,),
        order_block_mitigation=(SimpleNamespace(mitigated=False),),
        fvg=(), fvg_fill=(), atr=(1.0,) * 40,
        liquidity_levels=(SimpleNamespace(price=104.0),),
        sweeps=(), average_volume=(100.0,) * 40,
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

    def test_pac_path_generates_candidate_without_sweep_or_pd_gate(self):
        def analysis(candles, profile, timeframe):
            return fake_analysis(timeframe)

        with patch("app.smc.pac_scanner._analysis", side_effect=analysis):
            candidates = scan_symbol("BTCUSDT", self.series, trigger_timeframe="5m")

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].status, "CANDIDATE")
        self.assertEqual(candidates[0].direction, "long")
        self.assertIn(":PAC:", candidates[0].key)

    def test_scanner_enforces_rr_floor_149(self):
        source = (Path(__file__).resolve().parents[1] / "app" / "smc" / "pac_scanner.py").read_text()
        self.assertIn("abs(p-entry) >= 1.49*risk", source)
        self.assertIn("if rr < 1.49:", source)

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


if __name__ == "__main__":
    unittest.main()
