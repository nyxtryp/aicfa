import unittest

from app.main import PAGE, index
from app.market_data import ALL_SYMBOLS, TIMEFRAMES
from app.main import LOGIN_PAGE, app


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
        self.assertIn("/api/auth/login", [route.path for route in app.routes])
        self.assertIn("/api/settings/password", [route.path for route in app.routes])
        self.assertIn("/api/setups", [route.path for route in app.routes])
        self.assertIn("/api/active-setups", [route.path for route in app.routes])
        self.assertIn("/api/journal", [route.path for route in app.routes])
        self.assertIn("autocomplete=\"current-password\"", LOGIN_PAGE)
        self.assertIn("AICFA_SETUP_TOKEN", LOGIN_PAGE)
        self.assertNotIn("__AICFA_SYMBOLS__", PAGE)
        self.assertNotIn("__AICFA_TIMEFRAMES__", PAGE)
        for symbol in ALL_SYMBOLS:
            self.assertIn(symbol, PAGE)
        for timeframe in TIMEFRAMES:
            self.assertIn(timeframe, PAGE)
        self.assertNotIn("каркас сайта запущен", PAGE.lower())


if __name__ == "__main__":
    unittest.main()
