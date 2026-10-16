import unittest

from scripts.research_smc import grid_report


class BacktestCliTests(unittest.TestCase):
    def test_grid_report_refuses_to_rank_too_little_history(self):
        report = grid_report("BTCUSDT", {"5m": tuple()}, "scalp")
        self.assertEqual(report["status"], "insufficient_history_for_grid")
        self.assertEqual(report["trigger_candles"], 0)


if __name__ == "__main__":
    unittest.main()
