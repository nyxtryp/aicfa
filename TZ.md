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
- Use the nearest real directional liquidity target that meets the existing minimum 1.49R; do not synthesize a 2R target. If no real level meets the RR floor, reject the setup.
- INTRADAY scanner gates are unchanged in this phase. Stop width is not hard-coded to 0.75% or 1% because the historical threshold result varied materially by day; evaluate fee-aware stop rules separately before deployment.
- Acceptance: tests cover missing trigger, pre-trigger sweep, pre-retest 1m confirmation, missing/too-close liquidity, causal retests, and INTRADAY profile behavior. Production deployment requires CI success and offline replay/candidate-count review.

## 2026-10-23 — INTRADAY quality phase (draft, depends on SCALP PR #50)

- Historical results: 171 closed INTRADAY setups, gross -35.17R, fees 6.66R, net -41.83R. FVG LONG -2.79R/67; FVG SHORT -9.83R/45; OB LONG -8.56R/35; OB SHORT -20.65R/24. Do not ban OB SHORT solely on this small sample.
- INTRADAY uses a causal 15m retest of a confirmed 1h OB/FVG after the aligned 15m BOS/CHoCH. A same-direction sweep only counts as a score confluence when it precedes the trigger; it is not a hard gate.
- Existing INTRADAY timeframe/profile, stop buffer, RR threshold, targets, and TTL remain unchanged by this phase.
- Tests cover a valid sweep-trigger-retest, reject a sweep on/after the trigger as score credit, and reject a zone touched only before the 15m trigger.
- Four-snapshot replay: current scanner produced 19 SCALP / 13 INTRADAY candidates; updated dependent branch produced 4 SCALP / 5 INTRADAY candidates. Both profiles remain nonzero, but the drop means more availability validation is required.
- Draft only; do not merge/deploy until CI passes and broader offline replay shows acceptable availability.

## 2026-10-23 — SCALP sequence availability correction (PR #50)

- The first strict implementation accidentally applied causal retest and real-liquidity target rules to INTRADAY as well as SCALP. Corrected the branch so PR #50 scopes the hard causal sequence, 0.75 ATR anti-chase limit, and real-liquidity target policy to SCALP; INTRADAY retains its prior retest and target behavior in this PR.
- SCALP sequence remains mandatory: a same-direction sweep must precede the aligned 5m BOS/CHoCH; a directional OB/FVG must retest after the trigger; aligned 1m structure must close after that retest and trigger.
- Allow a qualifying 5m trigger up to 12 closed candles old only when the sweep remains recent and the later retest and 1m reaction are causal. The 1m reaction may be up to 8 closed candles old, but must still close after the retest and trigger.
- TP1 is the nearest real directional liquidity level that meets the profile's minimum RR (at least 1.49R); no synthetic 2R target is allowed. If no real level qualifies, reject the setup.
- Rolling replay across four consecutive snapshots generated 4 SCALP candidates across 3 symbols and 27 INTRADAY candidates across 12 symbols, versus 43 SCALP and 13 INTRADAY from the current scanner on the same replay run. This is nonzero but a large SCALP reduction; the sample is too short to approve deployment.
- Production remains unchanged during validation. No production database, accepted setups, or journal rows were modified.

## 2026-10-23 — INTRADAY sweep scoring correction

- INTRADAY sweep is optional confluence, not an acceptance gate. Award its score only when a same-direction sweep precedes the aligned 15m BOS/CHoCH; a missing, late, or misaligned sweep does not independently reject a setup.
- SCALP's causal sweep requirement is unchanged by this INTRADAY-only correction.
- A short rolling replay previously showed a material candidate-count reduction when the new causal requirements were combined. Keep PRs in draft until identical-window replay and CI establish acceptable availability and net results after fees.
- Production remains untouched; no production setup, accepted record, candle, or journal data was modified.


## 2026-10-23 — Сохранение INTRADAY retest policy

- После сравнения на одном текущем снимке свечей строгий causal retest давал ноль INTRADAY-кандидатов. Поэтому PR #52 возвращает для INTRADAY прежнюю политику выбора ближайшей зоны и касания в последних 6 свечах; обязательная последовательность sweep → trigger → retest остаётся отдельным SCALP-правилом.
- INTRADAY sweep остаётся дополнительным подтверждением и получает балл только при совпадении направления и появлении до BOS/CHoCH. Само отсутствие sweep не отклоняет сетап.
- Это изменение уменьшает риск остановки потока сетапов, но ещё не доказывает улучшение net R. Проверить CI и одинаковый replay до merge; production не менялся.
