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


### PAC accepted-tracking regression (2026-10-17)
- Every eligible PAC scanner setup in SCALP or INTRADAY must enter `ACCEPTED` paper tracking, just like eligible legacy SMC setups. Do not leave the active PAC path in `CANDIDATE` solely because live exchange execution is disabled.
- `ACCEPTED` means monitored by AICFA only; it must not submit exchange orders or enable live execution.
- Regression tests must prove that a newly eligible `:PAC:` setup is persisted as `ACCEPTED` and emits `SETUP_ACCEPTED`. Old `CANDIDATE` rows must not be promoted during startup: the first deployment of accepted-source synchronization clears the legacy unsynchronized candidates/events/journal once, then future startups preserve new records. There is no global active-setup cap or implicit row truncation; preserve the symbol/profile duplicate guard and zone cooldown. Strategy Results remain restricted to setups that were accepted and then closed.


## Синхронизация панелей SCALP / INTRADAY, Accepted и Strategy Results

- Текущие панели SCALP и INTRADAY и блок Accepted используют один и тот же набор ключей активных принятых сетапов. Нельзя отдельно дедуплицировать входящие сигналы по символу/профилю так, чтобы Accepted продолжал показывать скрытые записи.
- В Accepted разрешено любое количество допустимых сетапов: фиксированного общего или профильного cap нет.
- Перезапуск приложения не имеет права автоматически повышать старый CANDIDATE до ACCEPTED. При первой установке этого правила старые несинхронизированные записи и старые результаты очищаются однократно; после этого метка миграции предотвращает повторную очистку при обычных рестартах.
- Мониторинг и завершённые результаты учитывают только реально принятые сетапы профилей SCALP/INTRADAY. Финальный результат создаётся ровно один раз при завершении жизненного цикла. Достижение TP1 закрывает весь сетап.
- Регрессия: API панелей и Accepted возвращают идентичные упорядоченные ключи; более 100 отдельных активных сетапов не блокируются общим лимитом; legacy записи до миграции не появляются после старта.


### Accepted setup lifecycle — no premature invalidation (2026-10-18)
- После перехода в `ACCEPTED` сетап не закрывается из-за выхода цены за границу OB/FVG-зоны или противоположного CHoCH.
- Принятый paper-сетап завершается по фактическому SL, достижению TP1 (закрывает весь сетап) либо сроку жизни профиля; зона остаётся доказательством исходного входа, а не дополнительным стопом.
- Противоположный CHoCH может инвалидировать только ещё не принятый `CANDIDATE`; новые критерии сканера и RR не меняются.
- Regression: выход за границу зоны и противоположный CHoCH не снимают `ACCEPTED`; SL/TP/EXPIRED по-прежнему завершают жизненный цикл.


### Fee-aware stop and journal integrity (2026-10-18)
- PAC acceptance requires stop distance >= max(0.5 × ATR, entry × 8 × configured per-side commission rate). This bounds estimated round-trip fees relative to initial risk; never widen a stop artificially to force acceptance.
- Strategy summary excludes records with commission above 0.75R or with final status SL and positive gross R. These legacy records remain visible in the journal with an anomaly warning; they are not deleted or silently rewritten.
- Regression tests cover the stricter cost floor and anomaly classification.


## PAC entry trigger structure requirement (2026-10-18)
- A PAC candidate must have a recent BOS/CHoCH in the profile's confirmation timeframe, aligned with the higher-timeframe direction and no older than three closed candles.
- Higher-timeframe bias plus a nearby/retested OB/FVG and valid risk/reward is not sufficient by itself to create an ACCEPTED setup.
- Liquidity sweep, Premium/Discount, internal structure, and extra-timeframe alignment remain confluences, not universal hard gates.
- Regression: PAC scanner rejects a setup when no recent aligned confirmation-timeframe structure break exists and accepts the aligned-trigger case.


## 2026-10-19 — Revert mandatory recent PAC trigger gate (70c016c)
- The confirmation-timeframe BOS/CHoCH is restored as a scored confluence rather than a universal hard rejection. A valid directional zone and a retest after zone confirmation remain required; when a directional trigger exists, retesting must still occur after it.
- Score base reduced from four to three mandatory gates to avoid implicitly retaining the reverted trigger requirement. Profile score thresholds, 1m scalp confirmation, fee-aware stop, nearest-liquidity TP1, RR floor, anti-chase, and causal retest checks remain enabled.
- Added regression coverage that a candidate can qualify without a recent confirmation-timeframe trigger when the remaining confluences satisfy the profile score. No production deployment implied; run CI and verify live rejection counters after deploy.


## 2026-10-19 — Roll back fee-aware stop tightening (d67ced8)
- Restore the prior PAC minimum stop-distance fee multiplier from 8× to 4× the configured per-side commission rate; the 8× floor was an additional acceptance gate and can reduce SCALP/INTRADAY candidates.
- Restore the prior journal metrics anomaly threshold of commission <= 5R; this rollback does not alter historical journal rows or setup records.
- This change does not bypass the other PAC quality filters. Production deployment still needs verification.


## 2026-10-19 — Revert PAC minimum stop-distance gate (2d8ce31)
- Remove the additional PAC acceptance gate requiring stop distance >= 0.5 × ATR. Keep positive risk, RR >= 1.49, correct-side target, valid tick size, freshness, causal retest, profile score, scalp 1m confirmation, and the other existing PAC quality filters.
- This restores prior candidate eligibility; it does not widen stops or disable unrelated filters. Review candidate quality and stop-distance distribution after deployment.

### PAC scanner zone-selection regression — 2026-10-20

- For each symbol/profile, determine causal post-trigger retests for all active, direction-aligned OB/FVG zones before selecting the entry zone.
- Select the nearest zone only from those with a confirmed post-zone-confirmation and post-directional-BOS/CHoCH retest in the recent trigger-candle window.
- An untouched nearer zone must not suppress a farther valid retested zone. Keep the existing six-candle lookback, anti-chase limit, nearest confirmed liquidity TP1, minimum 1.49R, closed-candle-only processing, and profile score requirements.
- Regression: nearest zone untouched + second zone retested => choose second zone; pre-trigger-only touch => reject; no retested zones => reject. Validate with unit tests and offline replay before production deployment.

## 2026-10-23 — SCALP causal entry sequence correction (PR under review)

- SCALP only: require a recent aligned 5m BOS/CHoCH and a same-direction liquidity sweep that occurred before that structure break.
- Choose the nearest active directional OB/FVG among zones with a confirmed retest after zone confirmation and the 5m trigger; reject chased entries beyond 0.75 ATR.
- Require the aligned 1m structure reaction to close after the qualifying 5m retest and after the 5m trigger. A stale/pre-retest 1m event cannot confirm the entry.
- Require a real nearest directional liquidity target and the existing minimum 1.49R; do not synthesize a 2R target when real liquidity is absent or skip a nearer target that fails RR.
- INTRADAY scanner gates are unchanged in this phase. Stop width is not hard-coded to 0.75% or 1% because the historical threshold result varied materially by day; evaluate fee-aware stop rules separately before deployment.
- Acceptance: tests cover missing trigger, pre-trigger sweep, pre-retest 1m confirmation, missing/too-close liquidity, causal retests, and INTRADAY profile behavior. Production deployment requires CI success and offline replay/candidate-count review.

## 2026-10-23 — INTRADAY quality phase (draft, depends on SCALP PR #50)

- Historical results: 171 closed INTRADAY setups, gross -35.17R, fees 6.66R, net -41.83R. FVG LONG -2.79R/67; FVG SHORT -9.83R/45; OB LONG -8.56R/35; OB SHORT -20.65R/24. Do not ban OB SHORT solely on this small sample.
- INTRADAY now requires the causal sequence on its own cadence: a same-direction sweep before the aligned 15m BOS/CHoCH, followed by a closed 15m retest of the confirmed 1h OB/FVG after the trigger. The PR #50 base already supplies causal zone selection; this phase adds the INTRADAY sweep gate.
- Existing INTRADAY timeframe/profile, stop buffer, RR threshold, targets, and TTL remain unchanged by this phase.
- Tests cover a valid sweep-trigger-retest and reject a sweep on/after the trigger. Draft only; do not merge/deploy until CI passes and offline replay/candidate counts show acceptable availability.
