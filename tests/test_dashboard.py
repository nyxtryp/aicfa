import unittest

from app.main import PAGE, index


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_serves_scanner_dashboard_not_placeholder(self):
        response = await index()
        self.assertEqual(response.status_code, 200)
        self.assertIn("SMC Scanner", response.body.decode())
        self.assertIn("/api/smc-analysis/", PAGE)
        self.assertIn("canvas", PAGE)
        self.assertIn("zone((ann.order_blocks||[])", PAGE)
        self.assertIn("zone((ann.fvg||[])", PAGE)
        self.assertIn("for(const e of ann.structure_breaks||[])", PAGE)
        self.assertIn("for(const e of ann.sweeps||[])", PAGE)
        self.assertIn("__AICFA_SYMBOLS__", PAGE)
        self.assertIn("__AICFA_TIMEFRAMES__", PAGE)
        self.assertNotIn("каркас сайта запущен", PAGE.lower())


if __name__ == "__main__":
    unittest.main()
