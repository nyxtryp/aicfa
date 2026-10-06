## 2026-10-03 — TASK 9 — RR ↔ OUTCOME ANALYSIS GREEN / FULL REGRESSION VERIFIED

- Added causal RR ↔ outcome analysis in production commit `3118e99fee3381d01598544e60f80edbfb614e72` — `feat: add RR outcome analysis`.
- RR is derived directly from structural Entry/SL/TP geometry; it is not used as a setup-validity filter.
- Analysis preserves the observed outcome for every setup: TP, SL, TIMEOUT, or AMBIGUOUS.
- Aggregate `mean_rr` is calculated only across resolved TP/SL outcomes; unresolved TIMEOUT/AMBIGUOUS outcomes remain visible and are excluded from that resolved aggregate.
- Mismatched setup/evaluation counts are rejected explicitly.
- Added fold-local RR ↔ outcome analysis in production commit `6a35228f43b328801c7a5b86fc0ed725b4fac913` — `feat: analyze RR outcomes across folds`.
- Fold analysis keeps chronological validation boundaries separate; observations from one fold are not mixed into another.
- Added two fold-analysis contract tests in `431946f8dca0ea6f63e0a9eca3c68f6d72f0e67e` — `test: define RR analysis across chronological folds`.
- Server focused validation after fold analysis: `tests/test_evaluation.py` = **19 passed in 0.50s**.
- Server full regression after the fold-analysis layer: **421 passed in 81.74s (0:01:21)**.
- Result: **0 failed, 0 skipped**.
- No hit-rate, profitability, confidence, predictive-performance, or trading-performance claim is made from this analysis.

### Current Task 9 status

- Conservative single-setup evaluator: GREEN.
- Batch evaluation/statistics: GREEN.
- Causal label purging: GREEN.
- Chronological purged validation folds: GREEN.
- RR ↔ outcome analysis: GREEN.
- RR ↔ outcome analysis across chronological folds: GREEN.
- Fold outcome statistics by chronological folds: GREEN.
- Full regression: **GREEN — 423/423**.
- Task 9 remains ACTIVE.

### 2026-10-03 — FOLD OUTCOME STATISTICS GREEN / FULL REGRESSION VERIFIED

- Added fold-local outcome statistics in production commit `d0b29625fa5abfcd3f1bf8d0d9654567a5c6a110` — `feat: add fold outcome statistics`.
- Added contract coverage in test commit `21e2e7e8c2a2a82df0c5de0c51a1543989713a1e` — `test: define fold outcome statistics contract`.
- Corrected test construction to use the real `BatchEvaluation` contract, including required `results`, in commits `afb3968a1efb64497c922fcf1954990b8089aad7`, `bc9b2c9a056d5b740432e35c6789d6676d890562`, and `781fb414ee590efd8502984044c4a0197430db7a`.
- Fold statistics preserve each fold independently: TP/SL/TIMEOUT/AMBIGUOUS counts, resolved count, TP rate among resolved outcomes, and mean gross return among resolved outcomes.
- Focused server validation: `tests/test_evaluation.py` = **21 passed in 0.54s**.
- Full server regression: **423 passed in 79.60s (0:01:19)**.
- Result: **0 failed, 0 skipped**.
- Task 9 remains ACTIVE.

### Next exact action

Continue Task 9 from the existing chronological purged-fold foundation with the next evaluation/statistics layer defined by the project plan, preserving strict causal boundaries and avoiding fixed RR filters, confidence scores, arbitrary thresholds, or unsupported performance claims.


### 2026-10-03 — SETUP OUTCOME JOURNAL GREEN / FULL REGRESSION VERIFIED

- Added historical per-setup outcome journal in production commit `6190b3817e46eb9fb4ed4cf6b28d61e5613f1e0a` — `feat: add historical setup outcome journal`.
- Added contract coverage in test commit `9507961cff3652a6a8fa5df1ef8191cdbc4402ef` — `test: define setup outcome journal contract`.
- Each journal record preserves setup timestamp, direction, Entry/SL/TP, derived RR, causal outcome, outcome offset, exit price, and gross return.
- TP, SL, TIMEOUT, and AMBIGUOUS remain explicit; unresolved outcomes do not receive fabricated exit prices or returns.
- The journal pairs already-defined setups with already-computed causal evaluations; it does not create or modify Entry/SL/TP.
- Focused server validation: `tests/test_evaluation.py` = **26 passed**.
- Full regression after this layer: **426 passed in 82.05s (0:01:22)**.
- Result: **0 failed, 0 skipped**.
- Task 9 remains ACTIVE.


### 2026-10-03 — DIRECTIONAL OUTCOME STATISTICS FOCUSED GREEN

- Added directional historical setup outcome statistics in production commit `0a0c1232773942cef9dffddb614be957020f86b9` — `feat: add directional setup outcome statistics`.
- Added contract coverage in test commit `459d9d9b3f7e843540d2950827003e937adaaea1` — `test: define directional setup outcome statistics contract`.
- Statistics keep Long/Short outcomes separated; TP/SL/TIMEOUT/AMBIGUOUS remain visible and resolved metrics exclude unresolved outcomes.
- Server focused validation: `tests/test_evaluation.py` = **28 passed in 0.58s**.
- Full regression is not yet rerun after this layer.
- Task 9 remains ACTIVE.

### 2026-10-03 — AICFA PRODUCT DIRECTION: THREE CORE HORIZONS + AUTONOMOUS MARKET SCANNER

- Product direction is now fixed around **three main trading horizons** in the primary AICFA system:
  - **Intraday** — 5m–1h, minutes to hours.
  - **Swing** — 1h–1d, hours to days.
  - **Position** — 4h–1w, days to weeks.
- **Scalping is explicitly separated from the primary AICFA system.** It will be implemented later as a dedicated website window with its own faster/microstructure logic and approximately minute-level updates. Scalping must not distort or replace the causal architecture of the three primary horizons.
- The three horizons are contexts of the shared Setup Engine, not three independent engines.
- The primary system must not remain request-driven ("analyze BTC when the user asks"). The target product behavior is an **autonomous market scanner**.
- The scanner must reuse the existing AICFA architecture and prefer no signal over a fabricated one.
- Scalping remains a later, separate product surface and implementation task.

### 2026-10-04 — ACTIVE PLAN: MARKET ROTATION ENGINE / PRODUCTION SCANNER DIAGNOSTIC

**This is the active implementation plan. Reuse the existing analytical core and do not create a parallel scanner.**

- Primary horizons: **Intraday, Swing, Position**.
- Scalping remains isolated.
- One market is processed as one analytical unit.
- Shared primary MTF context: **1w / 1d / 4h / 1h / 15m / 5m**.
- OHLCV/MTF is the structural core; futures enrichment is best-effort.
- Preserve every independently valid setup; no fixed signal counts, confidence score, or fixed RR filter.
- Deterministic queue, bounded market execution, observable diagnostics and lifecycle are required before continuous operation.

### 2026-10-05 — STEP 10 — PERSISTENT AUTONOMOUS SCAN JOURNAL

- Added append-only JSONL persistent journal in `src/aicfa/persistent_journal.py`.
- Journal path can be configured with `AICFA_JOURNAL_PATH`; otherwise production uses `AICFA_DATA_DIR/journal/events.jsonl`.
- `AutonomousScanEngine` persists completed scan snapshots and rotation-cycle summaries.
- Journal records preserve structured diagnostics, explainable setups, lifecycle results and rotation metrics.
- Focused journal/lifecycle validation on the VDS: **9 passed in 0.51s**.
- Real production `AutonomousScanEngine` scan verified persistence: **completed**, a real production setup reached lifecycle **active**, and a real `events.jsonl` record was written.
- The diagnostic-only pipeline runner does not write the journal; persistence belongs to `AutonomousScanEngine`, as intended.

### 2026-10-05 — STEP 10 — READ-ONLY JOURNAL FEED API

- Added `src/aicfa/journal_feed.py`.
- Added `scripts/journal_feed.py` runner.
- The feed is strictly read-only and does not invoke analysis or mutate lifecycle state.
- Endpoints:
  - `GET /api/health`
  - `GET /api/journal/events?limit=N`
  - `GET /api/journal/scans?limit=N`
  - `GET /api/journal/setups?limit=N`
- Responses are JSON, capped to the latest 500 requested events, with CORS read access for the future website.
- POST/PUT/DELETE return 405.
- Added focused HTTP contract tests in `tests/test_journal_feed.py`.
- Commits:
  - `ffefb583656d150fe487e23d3cc2a593b15abd2b` — `feat: add read-only journal feed API`
  - `5b959e03c6a86639161767b4a384ac64272a0a3b` — `test: add read-only journal feed API contract`
  - `038a445704f843eecf9a06cae308064f825c194d` — `feat: add journal feed runner`

# 2026-10-05 — CONSOLIDATED MASTER STATUS / ROADMAP

This section is the current source of truth and supersedes stale historical "next exact action" notes above.

## 1. ORIGINAL PRODUCT VISION — PRESERVED

AICFA remains a specialized AI / Market Brain for digital financial assets, not a wrapper around ChatGPT/Claude/Gemini or another third-party LLM.

Final target:
```
MARKET DATA
→ CAUSAL MARKET REPRESENTATION
→ MARKET STATE
→ SETUP / SCENARIO DETECTION
→ HISTORICAL OUTCOME + VALIDATION
→ AICFA OWN MODELS / BRAIN
→ RISK / DECISION
→ PAPER TRADING
→ EXPERIENCE
→ CONTROLLED MODEL IMPROVEMENT
```

The system must be able to return WAIT / NO TRADE / INSUFFICIENT INFORMATION. SMC is evidence and a measurable research hypothesis, not truth.

## 2. EVERYTHING COMPLETED SO FAR

### 2.1 Data foundation — GREEN
- Python project/package structure.
- OHLCV acquisition/downloader.
- Persistent `AICFA_DATA_DIR` storage outside release directories.
- Historical/live-data separation.
- 1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M timeframe support.
- Causal timestamp handling.
- Future-outcome label engine.
- Dataset/label infrastructure.
- Leak-safe dataset construction.
- Data-contract and timestamp hardening.

### 2.2 Causal market representation — GREEN
- Price.
- Volatility.
- Market structure.
- Confirmed swings.
- HH/HL/LH/LL.
- Causal BOS / CHoCH / MSS provenance.
- Liquidity and liquidity reaction.
- SMC role-aware analysis.
- Premium/discount context.
- Volume evidence.
- Market regime/context.
- MTF representation.
- Feature provenance.
- Deterministic chart/structure representation.

### 2.3 SMC / zone lifecycle — GREEN
The intended internal chain is implemented:
```
Confirmed Swing
→ causal BOS/CHoCH/MSS
→ Liquidity
→ Order Block lifecycle
→ FVG lifecycle
→ Zone Reaction
→ Volume Evidence
→ Structural Entry / SL / TP
```
Implemented:
- causal Order Block lifecycle;
- causal FVG lifecycle;
- unified zone reaction;
- active/broken zone states;
- zone indexing/performance optimizations;
- structural entry conditions;
- structural invalidation;
- structural targets;
- fixed RR validity gate removed.

### 2.4 Derivatives / order flow / microstructure — GREEN AS OPTIONAL ENRICHMENT
Seven canonical data kinds are supported:
1. OHLCV
2. TRADES
3. ORDER_BOOK
4. FUNDING
5. OPEN_INTEREST
6. LIQUIDATIONS
7. MARK_PRICE

Implemented where available:
- funding;
- open interest;
- mark price;
- liquidations;
- trades;
- order book;
- order-book history;
- level-by-level depth/liquidity;
- absorption context;
- trade-level CVD / taker delta;
- live microstructure context;
- provider provenance.

Missing optional derivatives/microstructure data does not structurally block OHLCV/MTF analysis.

### 2.5 Multi-exchange routing — GREEN
Implemented:
- generic CCXT adapter;
- capability-aware source factory;
- venue-aware symbol resolution;
- multi-source fallback;
- explicit venue mappings;
- independent derivative-source fallback;
- bounded fallback attempts;
- provider provenance;
- partial-source handling;
- market-aware auxiliary feed routing;
- production multi-provider chain.

### 2.6 Three primary horizons — GREEN
Primary system:
- Intraday: 5m–1h.
- Swing: 1h–1d.
- Position: 4h–1w.

Shared primary MTF:
`1w / 1d / 4h / 1h / 15m / 5m`.

Profiles:
- Intraday: 4h → 1h → 15m → 5m.
- Swing: 1d → 4h → 1h.
- Position: 1w → 1d → 4h.

The horizons share one analytical core.

Scalping is intentionally separate and deferred:
- 15m / 5m / 1m;
- low-latency/microstructure logic;
- separate website surface;
- future streaming/WebSocket requirement.

### 2.7 Explainable setup contract — GREEN
Setup preserves:
- asset/market/horizon/direction;
- scenario;
- Entry zone;
- structural SL/invalidation;
- TP levels;
- geometry-derived RR;
- structure/liquidity evidence;
- OB/FVG evidence;
- zone location/reaction;
- volume evidence;
- entry/invalidation conditions;
- source/confirmation timeframes;
- timestamp/freshness;
- lifecycle status.

No fixed setup count, confidence score or fixed RR filter.

### 2.8 Historical evaluation — GREEN
Implemented:
- conservative causal single-setup evaluator;
- batch evaluation;
- causal label purging;
- chronological purged folds;
- TP/SL/TIMEOUT/AMBIGUOUS;
- RR ↔ outcome analysis;
- fold-local statistics;
- fold-local RR analysis;
- cost-adjusted fold returns;
- historical per-setup outcome journal;
- Long/Short directional statistics.

Unresolved outcomes remain explicit. No unsupported profitability/predictive-performance claim is made.

### 2.9 Autonomous scanner — GREEN
Implemented:
- autonomous market scanner;
- configurable market universe;
- one-market analytical unit;
- shared six-TF snapshot;
- shared feature computation per market;
- Intraday + Swing + Position in one scan;
- preservation of all independent setups;
- deterministic finite rotations;
- bounded whole-market execution;
- observable diagnostics;
- recurring scan state;
- setup lifecycle integration;
- independent setup identities/horizons;
- WAIT does not destroy a still-valid active setup;
- duplicate suppression;
- TP1/TP2/invalidation/expiration lifecycle.

### 2.10 Production diagnostics/performance — GREEN
Implemented:
- single-market pipeline diagnostics;
- MTF/horizon/block timings;
- seven-block coverage diagnostics;
- compact production diagnostics;
- rotation progress;
- hard timeout preservation;
- shared MTF/features;
- derivatives/provider reuse;
- parallel optional acquisition;
- order-book history reuse;
- feature profiler;
- extensive zone/liquidity indexing and performance work.

The current design intentionally accepts multi-second market analysis instead of speculative over-optimization.

### 2.11 Market universe — GREEN / MAINTENANCE
Implemented:
- durable configurable universe;
- crypto + selected TradFi perpetual targets;
- venue mappings;
- live routing verification;
- cleanup/removal of failing or low-priority markets.

Universe remains configuration, not scanner logic.

### 2.12 Persistent scan journal — GREEN
Implemented:
- append-only JSONL journal;
- scan records;
- rotation-cycle records;
- diagnostics;
- setups;
- lifecycle results;
- configurable journal path.

Production VDS verification succeeded with a real production setup persisted with lifecycle ACTIVE.

### 2.13 Read-only journal feed — CODE/TEST GREEN
Implemented:
- `src/aicfa/journal_feed.py`;
- `scripts/journal_feed.py`;
- `/api/health`;
- `/api/journal/events`;
- `/api/journal/scans`;
- `/api/journal/setups`;
- read-only HTTP contract;
- CORS read access;
- 500-event cap;
- POST/PUT/DELETE → 405.

VDS verification succeeded against the real journal.

### 2.14 Feed productionization — GREEN
- Created systemd unit `aicfa-journal-feed.service`.
- Service uses `User=fd-aicfa`, `WorkingDirectory=/srv/frostdeploy/aicfa/current`, `AICFA_DATA_DIR=/srv/frostdeploy/aicfa/shared/data`, `PYTHONPATH=/srv/frostdeploy/aicfa/current/src`.
- `Restart=always`, `RestartSec=3`.
- Enabled at boot.
- Manual `nohup` process was removed after the port conflict.
- Final VDS state verified: **active (running)**, API health **ok**, listening on `127.0.0.1:8090`.
- This establishes the feed as a persistent local service.

## 3. ORIGINAL VISION ITEMS NOT YET FINISHED

These were in the original technical specification and must remain in the plan:

- first own predictive ML/PyTorch model;
- learned AICFA Brain;
- Scenario/Risk/Decision layer above deterministic setup detection;
- Historical Similarity Engine;
- Knowledge Base as a maintained machine-readable system;
- Experience Database distinct from raw event journal;
- Active Information Gathering;
- Information Value / value-of-information logic;
- Vision / screenshot analysis;
- full product-level backtesting/research environment;
- paper trading;
- controlled retraining;
- model promotion/rollback;
- model/data/version lineage;
- event subscriptions and alerts;
- user watchlists/monitoring;
- centralized multi-user architecture;
- production web/API platform;
- data-quality/source-health monitoring;
- separate low-latency Scalping module;
- optional validated execution adapter, strictly separated from analysis.

## 4. NEW MASTER ROADMAP

### STEP 11 — Productionize the live feed — GREEN / DONE
Completed:
1. Replace manual `nohup` with systemd — **DONE**.
2. Auto-start/restart after reboot/failure — **DONE**.
3. Load production environment including `AICFA_DATA_DIR` — **DONE**.
4. Verify permissions and ownership — **DONE**.
5. Expose the AICFA platform through FrostDeploy/Caddy — **DONE**.
6. Define production project/domain routing under the `aicfa.ru` platform domain — **DONE**.
7. Verify external read-only access — **DONE**.
8. Keep scanner and feed processes separated — **DONE**.

### STEP 11.1 — Caddy/FrostDeploy integration — GREEN / SUPERSEDED
- Inspected the live VDS Caddy installation and configuration.
- Current config file: `/etc/caddy/Caddyfile`.
- The earlier standalone `/etc/caddy/Caddyfile` reverse-proxy approach is no longer the production architecture.
- FrostDeploy owns the public project routing/TLS layer for the `aicfa.ru` platform domain.
- The Journal Feed remains a local read-only service and is consumed through the platform architecture rather than by exposing a separate ad-hoc Caddy hostname.
- Do not expose write methods; the journal feed remains read-only.

### 2026-10-06 — STEP 11.2 — НОВАЯ ПЛАТФОРМЕННАЯ АРХИТЕКТУРА: aicfa.ru КАК ДОМЕН FROSTDEPLOY

Архитектура публичных адресов AICFA изменена и зафиксирована. Предыдущая схема с `aicfa.nyxtryp.ru` как production Feed hostname **отменена**.

#### Новая основа

- Базовый домен установки FrostDeploy должен быть изменён с **nyxtryp.ru** на **aicfa.ru**.
- `aicfa.ru` становится **доменом самой AICFA/FrostDeploy-платформы**, а не отдельным custom domain только для AICFA Web.
- DNS платформы должен использовать:
  - **A @ → IP AICFA VDS**;
  - **A * → IP AICFA VDS** (wildcard для поддоменов проектов).
- FrostDeploy должен самостоятельно обслуживать HTTPS и сертификаты для проектных hostname в рамках платформенной схемы.
- Домен каждому проекту задаётся отдельно через его настройки «Домен» и может быть не только поддоменом платформы.
- Сам корневой **aicfa.ru** также может быть назначен конкретному проекту, поэтому после перевода платформы на `aicfa.ru` его можно назначить AICFA Web или другому выбранному проекту.
- Не создаём отдельный внешний `feed.aicfa.ru` reverse-proxy как обходной путь. Feed/API должен быть подключён через штатную платформенную архитектуру FrostDeploy.
- `aicfa.nyxtryp.ru` больше не является целевым публичным Feed URL.

#### Целевая схема

```
aicfa.ru
↓
FrostDeploy / AICFA platform
↓
проекты и сервисы AICFA
```

Пример:

```
aicfa.ru          → AICFA Web / основной сайт
app.aicfa.ru      → AICFA application
feed.aicfa.ru     → AICFA Feed/API, если Feed оформлен отдельным FrostDeploy-сервисом
*.aicfa.ru        → другие проекты/сервисы
```

Конкретные имена поддоменов назначаются после проверки соответствующего проекта/сервиса.

#### Текущий DNS и миграция

Сейчас платформа FrostDeploy использует:

```
nyxtryp.ru
A @ → 195.209.221.72
A * → 195.209.221.72
```

Цель:

```
aicfa.ru
A @ → IP AICFA VDS
A * → IP AICFA VDS
```

Перед переключением `aicfa.ru` необходимо отвязать текущий AICFA Web custom-domain от старой схемы.

Порядок:

1. Сохранить текущую рабочую конфигурацию AICFA Web.
2. Отвязать `aicfa.ru` от текущего AICFA Web custom-domain.
3. Изменить Platform Domain FrostDeploy с `nyxtryp.ru` на `aicfa.ru`.
4. Настроить DNS `A @` и `A *` на IP AICFA VDS.
5. Проверить панель FrostDeploy и автоматическую выдачу HTTPS.
6. Назначить `aicfa.ru` обратно проекту AICFA Web (или создать/назначить другой нужный проект).
7. Назначить отдельные поддомены остальным AICFA-сервисам.
8. После этого подключить production Feed к сайту.
9. Проверить, что пользовательский браузер остаётся на `aicfa.ru`.

#### Что делать с текущим aicfa.nyxtryp.ru

- Сейчас это платформенный адрес FrostDeploy Worker-сервиса `app` без HTTP-порта.
- Он **не является корректным публичным Journal Feed endpoint**.
- Не использовать его как Feed URL.
- Не удалять и не менять его до завершения миграции.
- После перехода Platform Domain на `aicfa.ru` его дальнейшая судьба определяется отдельно.

#### Что остаётся обязательным

- `aicfa.ru` — основной пользовательский адрес.
- FrostDeploy/Caddy остаётся штатным владельцем TLS и маршрутизации.
- Journal Feed остаётся read-only.
- Scanner не запускается сайтом.
- Архитектура остаётся:
  `AICFA Scanner → Journal / Feed → AICFA Website → Users`.
- Все инфраструктурные изменения фиксируются в этом плане до перехода к следующему этапу.

### 2026-10-06 — STEP 12 STARTED — AICFA MONITORING WEB UI

- Began the production web implementation in the existing `nyxtryp/aicfa` repository under `web/`.
- Added `web/index.html`: first real monitoring UI shell with live setup feed, horizon filters, system status, journal events, future AI query surface and sound control.
- Added `web/styles.css`: responsive production-oriented visual system for desktop/mobile.
- Added `web/app.js`: read-only feed consumption, 15-second refresh, setup normalization, lifecycle/evidence display, filtering and browser-safe notification sound.
- Added `web/server.py`: static web server plus same-origin read-only `/api/*` proxy to the local Journal Feed at `127.0.0.1:8090`. The web process does **not** run the scanner.
- This establishes the intended flow:
  `AICFA Scanner → Journal/Feed → AICFA Web UI → Users`.
- The next infrastructure action is to create/deploy the dedicated AICFA Web project in FrostDeploy using the `web/server.py` entry point, then bind the public project domain to `aicfa.ru`.
- Do not change the existing AICFA worker or Journal Feed service for this web deployment.

### STEP 12 — ПЕРВЫЙ НАСТОЯЩИЙ САЙТ МОНИТОРИНГА AICFA — РАБОЧЕЕ ПРИЛОЖЕНИЕ `aicfa.aicfa.ru`

Создать полноценный, качественно оформленный пользовательский интерфейс AICFA поверх централизованного Scanner/Feed.

Это должен быть **настоящий production-grade проект**, а не техническая страница или простая API-витрина. Нужны профессиональные визуальная иерархия, навигация, типографика, карточки сетапов, живая лента, состояния, поиск и понятная работа на мобильных и десктопных экранах.

### Публичный адрес

- Пользователь открывает **aicfa.aicfa.ru** после успешной регистрации/авторизации и работает в самом AICFA.
- `aicfa-web.aicfa.ru` — презентационная поверхность.
- `aicfa.aicfa.ru` — пользовательский URL самого рабочего AICFA.
- Технические Feed/Scanner hostname не должны становиться пользовательскими адресами.

### Основные элементы сайта

1. **Строка поиска / запроса для будущего ИИ**
   - заметное поле для будущего взаимодействия с AICFA AI;
   - на первом этапе это может быть подготовленный интерфейсный элемент без незавершённой AI-логики;
   - поиск не должен запускать полный market scan на каждый пользовательский запрос.

2. **Живая лента сетапов**
   - новые найденные сетапы автоматически появляются;
   - сетапы показываются последовательно, друг за другом;
   - пользователь не запускает сканирование вручную;
   - лента обновляется по мере появления новых центральных результатов.

3. **Активные сетапы**
   - текущие живые сетапы;
   - lifecycle;
   - направление;
   - горизонт;
   - актуальность.

4. **Основные горизонты**
   - Intraday;
   - Swing;
   - Position.

5. **Состояния / направление**
   - LONG;
   - SHORT;
   - WAIT;
   - NO TRADE.

6. **Торговая геометрия**
   - Entry;
   - SL;
   - TP;
   - RR.

7. **Доказательная часть сетапа**
   - market structure;
   - liquidity;
   - OB;
   - FVG;
   - volume evidence.

8. **Свежесть данных**
   - timestamp;
   - возраст результата;
   - актуальность данных.

9. **Lifecycle сетапа**
   - создан;
   - активен;
   - усилен/обновлён;
   - TP1;
   - TP2/completed;
   - invalidated;
   - expired;
   - outcome recorded.

10. **Покрытие данных**
    - доступные timeframe;
    - доступность источников;
    - состояние необходимых данных;
    - отсутствие обязательной информации должно быть явно видно.

11. **Диагностика**
    - релевантные production diagnostics;
    - состояние источников;
    - scan/processing timing;
    - проблемы качества данных, если они есть.

12. **Исторические события**
    - предыдущие сетапы;
    - lifecycle events;
    - результаты;
    - история отдельно от текущей живой ленты.

13. **WAIT / NO TRADE**
    - полноценные видимые результаты AICFA;
    - отсутствие сделки не должно выглядеть ошибкой или пустым экраном.

### Автоматическая выдача сетапов и звук

- Сетапы поступают **автоматически друг за другом** из центрального AICFA Scanner/Feed.
- Пользователь не запускает полный анализ рынка вручную для каждого нового сетапа.
- При обнаружении нового релевантного сетапа сайт должен выдавать **звуковое уведомление**.
- Звук привязан к появлению нового события/сетапа, а не к постоянному обновлению страницы.
- Необходимо учитывать browser autoplay restrictions: если браузер запрещает автоматический звук до первого взаимодействия пользователя, интерфейс должен предложить включить звук/уведомления и после разрешения воспроизводить сигнал.
- Для одного и того же события/сетапа должна быть защита от повторного звука.

### Главное архитектурное правило

Сайт **не должен запускать полный рыночный анализ для каждого пользователя**.

Центральный поток:

```
AICFA Scanner
      ↓
Journal / Feed
      ↓
AICFA Website
      ↓
Пользователи
```

Один централизованный Scanner анализирует рынок, сохраняет результаты в Journal, Feed отдаёт уже рассчитанные результаты, а сайт только отображает и распространяет их пользователям.

### Требование к публичному URL

Публичные пользовательские поверхности разделены:

```
aicfa-web.aicfa.ru
   ↓
Open AICFA
   ↓
регистрация / авторизация
   ↓
aicfa.aicfa.ru
   ↓
AICFA Web UI
   ↓
центральный Feed
   ↓
Journal / Feed service
```

При этом технические hostname Feed/Scanner не должны становиться адресом страницы в браузере. Рабочая пользовательская поверхность — **aicfa.aicfa.ru**.

### Следующий этап

После завершения production-grade сайта перейти к **STEP 13 — СТАБИЛЬНАЯ МОДЕЛЬ СОБЫТИЙ**.



### 2026-10-06 — STEP 12 — PUBLIC WEBSITE / AICFA APPLICATION ARCHITECTURE — FINAL / FIXED

Зафиксирована окончательная и обязательная архитектура пользовательских адресов AICFA. **Это правило проекта и не должно трактоваться иначе.**

- **`aicfa-web.aicfa.ru` = ПРЕЗЕНТАЦИОННЫЙ САЙТ AICFA.**
  - описание AICFA и его возможностей;
  - информация о системе;
  - регистрация / вход;
  - кнопка **Open AICFA**.
  - Это НЕ рабочее приложение AICFA.

- **`aicfa.aicfa.ru` = САМ AICFA, рабочее приложение.**
  - monitoring UI;
  - live setup feed;
  - Intraday / Swing / Position;
  - lifecycle / evidence / status;
  - будущий AI-интерфейс;
  - все дальнейшие рабочие функции продукта.

- Пользовательский путь строго:
  **`aicfa-web.aicfa.ru` → Open AICFA → регистрация / авторизация → `aicfa.aicfa.ru`**

- **Регистрация и авторизация — отдельный этап продукта.**
  - Кнопка **Open AICFA** ведёт пользователя в отдельную форму входа / регистрации.
  - После успешной регистрации или авторизации пользователь открывает **`aicfa.aicfa.ru` — сам рабочий AICFA**.
  - Регистрацию / авторизацию не считать частью аналитического ядра AICFA; это отдельный продуктовый и инфраструктурный этап.

- **`aicfa.ru` НЕ является ни презентационным сайтом, ни рабочим URL AICFA.** Это базовый Platform Domain FrostDeploy.

- В FrostDeploy уже существует проект **`aicfa`** с platform URL **`aicfa.aicfa.ru`**, Project ID **`b328b84e6d5940a2`**. Новый проект для рабочего AICFA создавать не требуется.

- Рабочее приложение `aicfa.aicfa.ru` должно развиваться внутри существующего проекта AICFA и использовать production entry point `web/server.py` с сохранением существующих Scanner и Journal Feed.

- **Никогда не смешивать роли адресов:**
  `aicfa-web.aicfa.ru` = presentation/marketing surface;
  `aicfa.aicfa.ru` = actual AICFA application.

- Существующие AICFA Scanner и Journal Feed при настройке Web-приложения не изменять.

### STEP 13 — Stable event model
Add explicit:
- setup created;
- setup updated/strengthened;
- setup invalidated;
- setup expired;
- TP1;
- TP2/completed;
- outcome recorded;
- data degraded/recovered.
Add stable event/setup IDs, ordering, deduplication, replay/history and consumer cursors.

### STEP 14 — Live setup → historical outcome loop
```
LIVE SETUP
→ immutable setup record
→ future candles
→ causal outcome
→ TP/SL/TIMEOUT/AMBIGUOUS
→ historical statistics
→ experience dataset
```
Original Entry/SL/TP geometry must never be rewritten.

### STEP 15 — Research/backtest platform
Turn current evaluation primitives into repeatable experiments:
- historical setup generation;
- market/horizon/direction segmentation;
- regime segmentation;
- costs/slippage;
- chronological walk-forward;
- baselines/benchmarks;
- reproducible dataset/experiment IDs;
- stored results;
- leakage audit;
- out-of-sample reporting.

### STEP 16 — Experience Database
Separate long-lived learning memory from raw journal.
Store:
- setup context;
- canonical market state;
- data coverage;
- scenario/SMC evidence;
- derivatives/microstructure;
- regime;
- outcome;
- timing;
- model/software metadata.

### STEP 17 — Historical Similarity
Retrieve causal historical situations by:
- structure;
- liquidity;
- volatility/regime;
- setup family;
- MTF context;
- historical outcomes.
Similarity is context, not a guarantee.

### STEP 18 — First own AICFA model
Start with transparent statistical baselines, then compact ML/PyTorch models.
Initial targets:
- direction;
- expected move;
- volatility;
- risk;
- time-to-outcome;
- false breakout;
- setup/scenario quality.
Use chronological train/validation/test and evaluate by horizon/regime. Models augment the causal representation; they do not replace it blindly.

### STEP 19 — AICFA Brain / Scenario / Risk / Decision
```
Market State
→ Setup Candidates
→ Historical Similarity / Experience
→ Own Models
→ Scenario Engine
→ Risk Engine
→ Decision Engine
→ LONG / SHORT / WAIT / NO TRADE
```

### STEP 20 — Active Information Gathering
AICFA should determine:
- what information is missing;
- what is available but unnecessary;
- what additional information has enough expected value to acquire.
Possible sources:
- another timeframe;
- another exchange;
- order-book history;
- derivatives field;
- trade flow;
- higher/lower timeframe context.

### STEP 21 — Vision / screenshot analysis
Chart screenshot becomes another input modality to the same canonical AICFA representation.
AICFA should:
- identify asset/timeframe when possible;
- extract visible structure;
- request additional screenshots/timeframes when needed;
- map visual evidence into the same Market State/Setup representation.
No disconnected vision-only logic.

### STEP 22 — Paper Trading
Implement:
- virtual positions;
- real-time setup tracking;
- fees/slippage;
- position sizing;
- stop/target handling;
- portfolio risk;
- audit trail;
- comparison with historical expectations.

### STEP 23 — Scalping
Separate module:
- 15m/5m/1m;
- streaming/WebSocket-capable data;
- microstructure/order flow;
- fast updates;
- independent performance budget/evaluation;
- no contamination of primary Intraday/Swing/Position logic.

### STEP 24 — Alerts / personal monitoring
Add:
- watchlists;
- horizon/setup subscriptions;
- lifecycle alerts;
- deduplication;
- cooldown/rate limits;
- delivery history.

### STEP 25 — Optional execution boundary
Only after paper trading/validation:
- explicit opt-in;
- authentication;
- duplicate-order protection;
- balance/position verification;
- risk limits;
- order reconciliation;
- emergency stop;
- audit log.
Execution is never required for the analytical product.

### STEP 26 — Versioning / lineage
Version:
- market data;
- feature schema;
- labels;
- datasets;
- models;
- configuration;
- scanner;
- experiments;
- deployment.
Every important result must be traceable to its inputs/version.

### STEP 27 — Reliability / data quality
Monitor:
- stale candles;
- missing TFs;
- exchange outages;
- provider degradation;
- mapping failures;
- timestamp anomalies;
- duplicates/gaps;
- derivative inconsistencies;
- scan latency;
- journal/feed health.

### STEP 28 — Multi-user product
Only after intelligence is validated:
- centralized computation;
- accounts;
- watchlists;
- personalized monitoring;
- API;
- web interface;
- usage limits;
- optional commercial layer.

## 5. CURRENT PRIORITY

```
NOW
 ↓
11  Persistent feed + Caddy
 ↓
12  Live AICFA website
 ↓
13  Stable event/setup IDs
 ↓
14  Live → historical outcomes
 ↓
15  Research/backtest platform
 ↓
16  Experience Database
 ↓
17  Historical Similarity
 ↓
18  First Own Model
 ↓
19  AICFA Brain / Risk / Decision
 ↓
20  Active Information Gathering
 ↓
21  Vision
 ↓
22  Paper Trading
 ↓
23  Scalping
 ↓
24  Alerts / personal monitoring
 ↓
25  Optional execution
 ↓
26  Versioning/lineage
 ↓
27  Reliability/data quality
 ↓
28  Multi-user platform
```

## 6. CURRENT STATUS

- Foundation: GREEN.
- Causal market representation: GREEN.
- SMC/zone lifecycle: GREEN.
- Derivatives/microstructure enrichment: GREEN.
- Multi-source routing: GREEN.
- Three primary horizons: GREEN.
- Explainable setup contract: GREEN.
- Historical causal evaluation: GREEN.
- Autonomous scanner: GREEN.
- Setup lifecycle: GREEN.
- Persistent journal: GREEN.
- Read-only feed code/tests: GREEN.
- Feed systemd productionization: **GREEN / DONE**.
- Caddy/FrostDeploy platform routing: **GREEN / DONE**.
- User-facing website: **NEXT — STEP 12 implementation**.
- Experience loop: ARCHITECTURE DEFINED; needs live outcome accumulation.
- Own ML model: NOT YET PRODUCTION.
- Vision: PLANNED.
- Paper trading: PLANNED.
- Scalping: PLANNED / INTENTIONALLY SEPARATE.
- Live execution: OUTSIDE CURRENT CORE.

## 7. XMR CORRECTNESS ISSUE — CLOSED — 2026-10-06

The previously observed XMRUSDT production setup with invalid second TP geometry (`TP2 = 0.0`) is **closed as a production-universe issue**.

Actions completed:
- Removed `XMR/USDT` from `config/market_universe.json`.
- The autonomous scanner will no longer select XMR from the configured production market universe.
- The XMR-specific correctness issue is removed from the active blocker list.
- The persistent journal/feed architecture was not identified as the root cause; the issue was isolated to the affected market/setup data.
- No other market was changed as part of this closure.

This closure does not claim that the underlying generic TP-generation/data-validation logic is globally fixed; that remains a separate engineering concern if similar invalid geometry is ever observed for another market.

## 8. RULES THAT MUST NOT BE LOST

- AICFA is not a third-party LLM wrapper.
- No future data in causal features.
- No forced signals.
- No fixed signal count.
- No fixed RR validity gate.
- No arbitrary confidence score.
- SMC is evidence/hypothesis, not truth.
- Missing optional derivatives/microstructure data does not block the structural core.
- All primary horizons share one causal architecture.
- Scalping stays isolated.
- Analyze each market centrally once; users consume results.
- Setup geometry is immutable after creation.
- Lifecycle is separate from setup creation.
- Journal is immutable event history; Experience is learning memory.
- New models require controlled validation before promotion.
- Execution remains separate from analysis.
- Production data stays in persistent storage.
- Infrastructure changes must be recorded in this plan before moving to the next stage.


### 2026-10-06 — STEP 12 — TECHNICAL WEB CARCASS DEPLOYED / FINAL DESIGN DEFERRED

- The AICFA Web application has now been deployed successfully in FrostDeploy as a **Web** application using `web/server.py`.
- Production deployment verified on commit `60c073e`.
- The application is publicly available at **`aicfa.aicfa.ru`**.
- FrostDeploy allocated the application port dynamically; healthcheck passed and deployment completed successfully.
- Current UI is intentionally treated as a **technical/functional carcass**, not the final product design.
- Current carcass already contains the main future surfaces: AICFA status, AI query placeholder, autonomous horizons, Live Feed, Current Setups, and Immutable Journal.
- The visible `DATA UNAVAILABLE` / empty feed state is expected at this stage and is not treated as the final user experience.
- **Final visual redesign is deliberately deferred** until the real Journal/Feed data is connected and the actual information architecture, states and user flows are verified.
- Do not spend the next implementation step on cosmetic redesign. First connect and verify the real central Feed data in the existing UI.

### Current stopping point — 2026-10-06

**We are here:**
```
STEP 12
  ├─ Web application: DEPLOYED / GREEN
  ├─ Technical UI carcass: PRESENT
  ├─ Final visual design: DEFERRED
  └─ Real Journal/Feed data in UI: NEXT
```

### Next exact implementation action

Continue **STEP 12** by connecting the deployed AICFA Web UI to the existing read-only Journal Feed and verifying real production data end-to-end:

```
AICFA Scanner
    ↓
Persistent Journal
    ↓
Journal Feed :8090
    ↓
web/server.py /api proxy
    ↓
aicfa.aicfa.ru
    ↓
Live Feed / Current Setups / Events
```

Verify actual setup/event rendering, lifecycle states, timestamps/freshness, horizon filtering and empty/degraded-data states. Only after this functional layer is stable should the final production-grade visual redesign be performed.

**Do not mark STEP 12 complete yet.**


### 2026-10-06 — STEP 12 — JOURNAL FEED CONNECTION BUG FIXED

- During live integration verification, identified the exact cause of the Web UI showing `OFFLINE / DATA UNAVAILABLE`.
- `web/server.py` was incorrectly stripping the `/api` prefix before proxying requests to the Journal Feed.
- The Journal Feed itself expects the full paths `/api/health`, `/api/journal/events`, `/api/journal/scans`, and `/api/journal/setups`.
- Fixed the Web proxy to preserve the complete API path when forwarding to `127.0.0.1:8090`.
- Commit: `abb2395` — `fix: preserve journal feed api path in web proxy`.
- FrostDeploy autodeploy should publish this fix from `main`.
- **Next verification:** confirm `aicfa.aicfa.ru` changes from OFFLINE/DATA UNAVAILABLE to LIVE/HEALTHY and that real journal setups/events render.
