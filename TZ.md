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
        self.assertIn('item["expires_at_ms"]', inspect.getsource(main_module))
        self.assertIn("срок до", PAGE)
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
        self.assertIn(".metric,.panel{background:linear-gradient(145deg,#111b2b,#0d1523);border:1px solid #202e43;border-radius:4.5px;padding:3px 4.5px}", PAGE)
        self.assertIn(".metric .value{font-size:.47rem;line-height:.575;font-weight:750;margin-top:1px;overflow-wrap:anywhere}", PAGE)
        self.assertIn(".metric .label{font-size:.32rem;line-height:.575;color:#8fa0b8}", PAGE)
        self.assertIn(".metric .hint{font-size:.295rem;line-height:.575;color:#70839f;margin-top:.5px}", PAGE)
        self.assertIn(".grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:3px;margin-bottom:4px}", PAGE)
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


## Dashboard redesign — compact spacing and consistent layout (2026-10-17)
- Preserve checkpoint `d5948de043547264bf496e595c353c12ca002b26` as the rollback point before the full redesign.
- Replace the half-size status cards that made text effectively unreadable with compact but legible cards; use consistent spacing, type scale, borders, and panel padding throughout the dashboard.
- Use a restrained dark terminal palette, tighter headers and controls, balanced 3-column desktop layout, responsive tablet/mobile stacking, compact setup cards, and readable chart/journal panels.
- Keep all scanner functionality, chart annotations, auth controls, and API behavior unchanged. CSS should be formatted with consistent indentation; no functionality removed to make layout easier.
- Acceptance: dashboard regression tests and CI pass; visual layout should be checked at desktop, tablet, and mobile widths. Production deployment is tracked separately.


## Modern MVP visual system — acceptance requirements (2026-10-17)
- Apply one consistent modern dark terminal visual language across dashboard and password login: restrained teal accent, subtle layered backgrounds, readable contrast, consistent radii/borders, compact status strip, clear hierarchy and visible keyboard focus.
- Four top market status cards remain deliberately slim: desktop padding 4×7px, 5px grid gap, readable compact labels/values/hints; mobile remains a 2-column grid with further compact overrides.
- Dashboard must adapt from 3-column desktop to 2-column tablet and stacked mobile; setup lists scroll independently; chart and journal remain legible without horizontal page overflow.
- Add reduced-motion support and focus-visible styling. Preserve all API routes, authentication behavior, scanner criteria, candidate lifecycle, chart drawing/SMC annotations and shadow-only operation.
- Acceptance: automated dashboard/auth regression tests and CI pass. Production is not considered updated until deployment and browser checks confirm it.


## Interactive dashboard reconstruction (2026-10-17)
- Replace minor polish with a clearly distinct terminal visual system and responsive panel hierarchy.
- INTRADAY and SCALP headers are keyboard-accessible accordion controls; opening one collapses the other and the open panel can collapse.
- Preserve scanner rules, chart/SMC, journal, auth, APIs, and shadow mode.


## Realized journal analytics (2026-10-17)
- Replace the raw realized-trade dump with strategy KPIs: net R, win rate, Profit Factor, and maximum drawdown.
- Add All / SCALP / INTRADAY filters; individual trades remain clickable to open their chart/details.
- Flag implausible or invalid commission/result records and exclude them from aggregate metrics rather than silently letting extreme fee values distort the statistics.
- Acceptance: dashboard tests pass; calculations are derived from closed journal records; abnormal fees remain visible for audit and are not represented as trusted performance.


## Journal/setup source integrity (2026-10-17)
- Incoming SCALP and INTRADAY panels must display every persisted valid setup, not only the newest setup per symbol/profile. Deduplication by symbol/profile hides setups that can later appear in the realized journal.
- The realized journal API must join journal rows to their persisted setup candidate by the exact `setup_key`, and allow only `scalp` and `intraday` profiles on both records.
- Preserve Binance candle history, auth, settings, scanner criteria, and shadow mode. Acceptance requires regression tests showing every journal row has a matching persisted setup and no unsupported profile is returned.


### Journal lifecycle rule (2026-10-17)

- Eligible SCALP and INTRADAY setups are automatically tracked in Accepted as paper setups; this does not enable exchange execution.
- A setup is added to Strategy Results only after it was accepted/tracked and then reaches a final close status. Candidate-only/legacy simulation closures must not be counted.
- Strategy statistics are computed only from these accepted-and-closed setup records.
