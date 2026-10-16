import inspect
import unittest

import app.main as main_module
from app.main import PAGE, SCANNER_LIVE_ENABLED, index
from app.market_data import ALL_SYMBOLS, TIMEFRAMES
from app.main import LOGIN_PAGE, app


class DashboardTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_serves_scanner_dashboard_not_placeholder(self):
        response = await index()
        self.assertEqual(response.status_code, 200)
        self.assertIn("SMC Scanner", response.body.decode())
        self.assertIn("Автосканер · все инструменты · scalp / intraday", PAGE)
        self.assertIn('id="intradaySetups"', PAGE)
        self.assertIn('id="scalpSetups"', PAGE)
        self.assertIn("grid-template-rows:repeat(2,minmax(0,1fr))", PAGE)
        self.assertIn("overflow:hidden;position:static", PAGE)
        self.assertIn("flex:1 1 auto;min-height:0;max-height:none", PAGE)
        self.assertIn("grid-template-rows:repeat(2,minmax(0,42vh))", PAGE)
        self.assertIn("rr < 1.49 or not target_on_correct_side", inspect.getsource(main_module))
        self.assertIn("list_monitored()", inspect.getsource(main_module))
        self.assertIn('candidate_mode = payload.get("status") == "CANDIDATE"', inspect.getsource(main_module))
        self.assertIn('rr_below_minimum_or_unverifiable_legacy', inspect.getsource(__import__("app.smc.setup_store", fromlist=["SetupStore"])))
        self.assertIn("def list_monitored", inspect.getsource(__import__("app.smc.setup_store", fromlist=["SetupStore"]).SetupStore))
        self.assertIn("const key=[item.symbol,item.profile].join('|')", PAGE)
        self.assertIn('id="activeSetups"', PAGE)
        self.assertIn('id="realizedJournal"', PAGE)
        self.assertNotIn('id="rejectedSetups"', PAGE)
        self.assertNotIn('id="rejectedCount"', PAGE)
        self.assertNotIn("data.rejected_candidates", PAGE)
        self.assertNotIn("selectSetupTab", PAGE)
        self.assertNotIn('id="showRejected"', PAGE)
        self.assertIn("uniqueCandidates", PAGE)
        self.assertIn("host.querySelectorAll('.setup-card').length", PAGE)
        self.assertIn("Could not render setup card", PAGE)
        self.assertNotIn("String(incoming.length)+' актуальных'", PAGE)
        self.assertIn('id="marketHoursStatus"', PAGE)
        self.assertIn("Режим: shadow", PAGE)
        self.assertFalse(SCANNER_LIVE_ENABLED)
        self.assertNotIn("$('refresh').addEventListener", PAGE)
        self.assertNotIn("setInterval(", PAGE)
        self.assertIn("let selectedSetup=null", PAGE)
        self.assertIn("activeSetup.stop_price", PAGE)
        self.assertIn("activeSetup.targets", PAGE)
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
        self.assertIn('autocomplete="current-password"', LOGIN_PAGE)
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
