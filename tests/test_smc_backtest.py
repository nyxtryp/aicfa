import unittest
from decimal import Decimal

from app.market_data import ClosedCandle
from app.smc.backtest import BacktestConfig, _simulate, summarize
from app.smc.profiles import PROFILES
from app.smc.scanner import SetupCandidate


def candle(index, *, open_=100, high=100, low=100, close=100, timeframe="5m"):
    return ClosedCandle(
        symbol="BTCUSDT",
        timeframe=timeframe,
        open_time_ms=1_800_000_000_000 + index * 300_000,
        close_time_ms=1_800_000_299_999 + index * 300_000,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal("100"),
    )


def candidate(targets=(103.0,), stop=98.0):
    return SetupCandidate(
        key="test-key", symbol="BTCUSDT", profile="scalp", direction="long",
        status="CANDIDATE", confirmation_time_ms=1_800_000_299_999,
        confirmation_price=100.0, stop_price=stop, targets=targets, score=8,
        reasons=(), zone=(99.0, 101.0), timeframe="5m", atr=1.0,
    )


class BacktestTests(unittest.TestCase):
    def config(self):
        return BacktestConfig(
            margin_usd=5, leverage=10, fee_rate_per_side=0,
            slippage_bps_per_side=0,
        )

    def test_fixed_five_dollar_margin_and_ten_x_leverage(self):
        rows = [candle(i) for i in range(41)]
        rows.append(candle(41, open_=100, high=106, low=99, close=105))
        result = _simulate(candidate(), rows, 40, PROFILES["scalp"], self.config(), 41)
        self.assertIsNotNone(result)
        self.assertTrue(result.complete)
        self.assertEqual(result.exit_reason, "TP1")
        self.assertAlmostEqual(result.gross_pnl_usd, 1.5, places=6)
        self.assertAlmostEqual(result.margin_return_pct, 30.0, places=6)

    def test_stop_wins_when_stop_and_target_touch_same_bar(self):
        rows = [candle(i) for i in range(41)]
        rows.append(candle(41, open_=100, high=104, low=97, close=103))
        result = _simulate(candidate(), rows, 40, PROFILES["scalp"], self.config(), 41)
        self.assertIsNotNone(result)
        self.assertEqual(result.exit_reason, "SL")
        self.assertAlmostEqual(result.gross_pnl_usd, -1.0, places=6)

    def test_three_targets_use_half_thirty_twenty_distribution(self):
        rows = [candle(i) for i in range(41)]
        rows.append(candle(41, open_=100, high=104, low=99, close=103))
        result = _simulate(
            candidate(targets=(103.0, 104.0, 105.0)),
            rows, 40, PROFILES["scalp"], self.config(), 41,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.exit_reason, "TP3")
        self.assertAlmostEqual(result.gross_pnl_usd, 1.3, places=6)

    def test_fees_are_charged_on_entry_and_exits(self):
        rows = [candle(i) for i in range(41)]
        rows.append(candle(41, open_=100, high=103, low=99, close=102))
        config = BacktestConfig(margin_usd=5, leverage=10, fee_rate_per_side=0.0005,
                                slippage_bps_per_side=0)
        result = _simulate(candidate(), rows, 40, PROFILES["scalp"], config, 41)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.fees_usd, 0.05, places=6)
        self.assertAlmostEqual(result.net_pnl_usd, 1.45, places=6)

    def test_summary_reports_win_rate_and_margin_return(self):
        rows = [candle(i) for i in range(41)]
        rows.append(candle(41, open_=100, high=103, low=99, close=102))
        result = _simulate(candidate(), rows, 40, PROFILES["scalp"], self.config(), 41)
        metrics = summarize([result], margin_usd=5)
        self.assertEqual(metrics["trades"], 1)
        self.assertEqual(metrics["win_rate_pct"], 100)
        self.assertEqual(metrics["margin_return_pct"], 30)


if __name__ == "__main__":
    unittest.main()
