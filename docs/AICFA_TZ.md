# AICFA — Техническое задание

**Проект:** AICFA — AI for Digital Financial Assets  
**Репозиторий:** NYXTRYP/aicfa  
**Назначение:** единая техническая спецификация проекта и контрольная точка архитектурных решений.

---

# 1. Цель проекта

Создать собственную специализированную AI-систему для анализа криптовалютного рынка и цифровых финансовых активов.

AICFA должен постепенно стать специализированным Market Brain / Trading Intelligence System, способным:

- собирать и анализировать рыночные данные;
- понимать рыночную структуру;
- анализировать ликвидность;
- учитывать объём и волатильность;
- учитывать деривативы;
- работать с несколькими временными масштабами;
- искать похожие исторические ситуации;
- накапливать собственный опыт;
- формировать и сравнивать торговые сценарии;
- оценивать риск;
- определять, какой информации не хватает;
- запрашивать недостающие данные;
- отказываться от сделки при недостатке преимущества;
- обучаться на исторических результатах и накопленном опыте.

Главная идея:

~~~text
AICFA должен не просто выдавать сигнал,
а строить и проверять гипотезу о текущем состоянии рынка.
~~~

# 2. Собственный AI

AICFA не должен быть простой оболочкой над ChatGPT, Claude, Gemini или другой сторонней LLM.

Сторонние open-source библиотеки допустимы как инструменты инфраструктуры, но специализированное интеллектуальное ядро должно создаваться внутри проекта.

Цепочка:

~~~text
Market Data
  ↓
Features / Market Representation
  ↓
AICFA Models
  ↓
AICFA Brain
  ↓
Scenario Engine
  ↓
Risk Engine
  ↓
Decision Engine
~~~

На ранних этапах допустимы статистические методы, правила и небольшие ML/PyTorch-модели. Не требуется сразу создавать гигантскую нейросеть.

# 3. Общая архитектура

~~~text
                           AICFA
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
      KNOWLEDGE          MARKET DATA        EXPERIENCE
          │                  │                  │
          └──────────────────┼──────────────────┘
                             ↓
                        AICFA BRAIN
                             │
       ┌─────────────────────┼─────────────────────┐
       ↓                     ↓                     ↓
  STRUCTURE              LIQUIDITY              VOLUME
  ANALYSIS               ANALYSIS               ANALYSIS
       │                     │                     │
       └─────────────────────┼─────────────────────┘
                             ↓
                  MULTI-TIMEFRAME ANALYSIS
                             ↓
                     SCENARIO ENGINE
                             ↓
                       RISK ENGINE
                             ↓
                     DECISION ENGINE
                             ↓
               LONG / SHORT / WAIT / NO TRADE
~~~

Основные подсистемы:

- Market Data Engine;
- Feature Engine;
- Label Engine;
- Dataset Builder;
- Training Engine;
- Evaluation Engine;
- Backtest Engine;
- Knowledge Base;
- Experience Database;
- Historical Similarity Engine;
- Active Information Gathering;
- Vision;
- Paper Trading;
- API;
- Web Interface.

# 4. Критическое разделение: обучение и свежий рынок

Это обязательное архитектурное правило.

## 4.1 Исторические данные

История используется для:

- построения признаков;
- генерации исторических ситуаций;
- генерации future labels;
- создания training/validation/test datasets;
- обучения моделей;
- backtesting;
- исследования SMC и других концепций.

Первая стадия использует примерно год исторических данных BTC/USDT. Период должен постепенно расширяться.

## 4.2 Свежие данные

Свежие рыночные данные должны поступать автоматически.

~~~text
Exchange
  ↓
Market Data Engine
  ↓
Incremental Update
  ↓
Raw Market Data
  ↓
Current Features
  ↓
AICFA Brain
  ↓
Current Analysis
~~~

Downloader должен регулярно проверять последние доступные свечи и догружать только отсутствующий участок.

## 4.3 Свежие данные НЕ означают автоматическое переобучение

Новая свеча не должна автоматически запускать переобучение.

Правильный поток:

~~~text
НОВАЯ СВЕЧА
  ↓
обновление market data
  ↓
расчёт текущих features
  ↓
текущий анализ
~~~

А не:

~~~text
НОВАЯ СВЕЧА
  ↓
немедленное переобучение модели
~~~

Свежие данные используются прежде всего для live inference / текущего анализа.

## 4.4 Контролируемое обучение на новых данных

~~~text
NEW MARKET DATA
  ↓
MARKET OUTCOME
  ↓
EXPERIENCE DATABASE
  ↓
DATASET UPDATE
  ↓
TRAIN NEW MODEL VERSION
  ↓
BACKTEST
  ↓
VALIDATION
  ↓
PAPER TRADING
  ↓
COMPARE WITH CURRENT MODEL
  ↓
DEPLOY ONLY IF VALIDATED
~~~

Новая модель не должна автоматически заменять текущую.

Каждая версия должна иметь:

- version ID;
- dataset version;
- training configuration;
- metrics;
- backtest results;
- validation results;
- timestamp;
- статус;
- возможность возврата к предыдущей рабочей модели.

# 5. Market Data Engine

AICFA должен проектироваться сразу с расчётом на большое количество цифровых активов. BTC/USDT является первым эталонным активом для разработки, а не архитектурным ограничением.

## 5.1 Universe of Assets

Market Data Engine должен поддерживать:

- множество symbols;
- spot и futures markets;
- индивидуальную доступность таймфреймов и derivatives data;
- метаданные актива;
- market type;
- exchange;
- base/quote asset;
- listing/delisting periods;
- liquidity/volume context.

Нельзя считать, что каждый актив имеет одинаковый набор данных. Отсутствующие источники явно маркируются как unavailable и не заменяются выдуманными значениями.

Первая стадия:

- BTC/USDT;
- затем другие ликвидные криптоактивы.

Базовые таймфреймы:

- 1m;
- 5m;
- 15m;
- 1h;
- 4h;
- 1d;
- 1w;
- 1M.

Это базовый набор из 8 таймфреймов.

3m, 30m, 8h и 12h не добавляются автоматически. Они могут появиться позже только после статистического доказательства полезности.

## OHLCV

- timestamp;
- open;
- high;
- low;
- close;
- volume.

Внутреннее время — UTC. Источники с Unix milliseconds должны обрабатываться как миллисекунды.

## Дополнительные данные

Постепенно:

- Open Interest;
- Funding Rate;
- Liquidations;
- Long/Short Ratio;
- Basis;
- derivatives positioning.

Позднее:

- Order Flow;
- Order Book;
- Bid/Ask imbalance;
- Market depth.

## Incremental updates

Downloader должен:

1. определить последний локальный timestamp;
2. запросить более новые данные;
3. добавить только отсутствующие свечи;
4. обработать дубли;
5. сохранить данные;
6. проверить целостность;
7. безопасно работать при повторном запуске.

# 6. Хранение данных

Целевая логика:

~~~text
data/
├── raw/
│   └── SYMBOL/
│       ├── 1m.csv
│       ├── 5m.csv
│       ├── 15m.csv
│       ├── 1h.csv
│       ├── 4h.csv
│       ├── 1d.csv
│       ├── 1w.csv
│       └── 1M.csv
├── processed/
└── dataset/
~~~

Raw, processed и training datasets не должны смешиваться.

# 7. Feature Engine

Feature Engine использует только информацию, доступную на соответствующий момент.

~~~text
timestamp T
  ↓
данные <= T
  ↓
features(T)
~~~

Feature Engine должен быть универсальным для большого количества активов. Символ, тип рынка, ликвидность и доступность источников данных являются частью контекста.

## 7.1 Price

- returns;
- log returns;
- candle body;
- upper/lower wick;
- candle range;
- body/range;
- gap;
- close position inside candle;
- candle sequences;
- impulse;
- compression;
- rolling highs/lows;
- distance to important levels;
- distance to recent extremes;
- reaction after level interaction.

## 7.2 Volatility

- rolling volatility;
- ATR-подобные признаки;
- range relative to average;
- volatility expansion/contraction;
- volatility regime;
- extreme moves;
- volatility persistence;
- volatility compression;
- volatility shock.

## 7.3 Market Structure

- HH;
- HL;
- LH;
- LL;
- swing highs/lows;
- internal structure;
- external structure;
- BOS;
- CHoCH;
- MSS;
- trend;
- range;
- consolidation;
- structure strength;
- displacement;
- structural persistence;
- structural break quality.

Каждое понятие должно иметь формальное алгоритмическое определение и воспроизводимые параметры.

## 7.4 Liquidity

- previous high/low;
- equal highs/lows;
- local liquidity pools;
- internal liquidity;
- external liquidity;
- distance to nearest liquidity;
- liquidity sweep/grab;
- rejection after sweep;
- breakout;
- failed breakout;
- breakout trap;
- stop-run behaviour;
- reaction after liquidity event.

## 7.5 SMC

- FVG;
- IFVG;
- imbalance;
- displacement;
- order-block candidates;
- bullish/bearish order blocks;
- breaker candidates;
- breaker;
- mitigation;
- invalidation;
- premium;
- discount;
- equilibrium;
- dealing range;
- inducement;
- POI;
- SMT/divergence;
- internal/external liquidity;
- internal/external structure.

SMC не является встроенной истиной. Каждый концепт превращается в измеримый признак или событие и проходит историческую статистическую проверку.

## 7.6 Volume

- raw volume;
- volume change;
- volume SMA/EMA;
- relative volume;
- volume anomaly;
- price/volume divergence;
- volume on expansion;
- volume on rejection;
- volume persistence;
- abnormal volume events.

## 7.7 Market Regime

- trend;
- range;
- expansion;
- compression;
- high-volatility regime;
- low-volatility regime;
- directional strength;
- persistence;
- mean-reversion tendency;
- transition between regimes.

## 7.8 Multi-Timeframe Representation

Базовый набор:

- 1m;
- 5m;
- 15m;
- 1h;
- 4h;
- 1d;
- 1w;
- 1M.

AICFA должен уметь связывать:

~~~text
HTF trend
↓
HTF liquidity
↓
HTF structure
↓
LTF structure
↓
LTF liquidity event
↓
entry context
~~~

Не требуется использовать все таймфреймы в каждом решении.

## 7.9 Derivatives Features

По мере доступности:

- Open Interest;
- OI change;
- Funding;
- Liquidations;
- Long/Short Ratio;
- Basis;
- Futures Volume;
- Spot/Futures divergence;
- derivatives positioning.

## 7.10 Order Flow / Market Microstructure

Первая реализация начинается с taker flow как наиболее формализуемого слоя order flow.

Текущий source contract:

- `taker_buy_volume`;
- `taker_sell_volume` либо `total_volume`, из которого sell volume может быть выведен;
- `timestamp` означает **время доступности полностью завершённого интервала**, а не его open time;
- для exchange kline с open/close timestamps в feature layer должен использоваться close/availability timestamp, чтобы не допустить look-ahead.

Первый feature layer:

- taker buy volume;
- taker sell volume;
- taker net volume = buy - sell;
- taker imbalance = net / (buy + sell);
- taker buy share;
- taker sell share;
- delta;
- change%;
- z-score against strictly past observations.

Causal rule:

~~~text
completed interval
      ↓
availability / close timestamp
      ↓
features(T)
      ↓
base candle at T or later
~~~

Нельзя использовать полный объём завершённого интервала на его open timestamp.

Для Binance futures официальная документация указывает taker buy volume в kline/continuous-kline данных и отдельный taker buy/sell volume endpoint; отдельный taker buy/sell volume endpoint ограничен последними 30 днями, поэтому он не должен быть единственным историческим источником для годового training dataset. Для исторического слоя предпочтителен источник, позволяющий получить completed kline data с корректным availability timestamp.

Пока не реализуются:

- CVD;
- absorption;
- liquidity walls;
- order-book changes;
- market depth.

Они требуют отдельного source contract и проверки исторической доступности.


Позднее, при наличии исторических источников:

- Order Book;
- Market Depth;
- Bid/Ask imbalance;
- aggressive buying/selling;
- absorption;
- delta;
- CVD;
- liquidity walls;
- order-book changes.

## 7.11 Feature Provenance

Для каждого feature желательно сохранять:

- feature name;
- definition;
- calculation parameters;
- source data;
- timestamp;
- timeframe;
- symbol;
- causal availability;
- feature version.

Это необходимо для воспроизводимости, исследований и объяснения решений модели.

# 8. SMC как исследовательская система

SMC не считается абсолютной истиной.

Для каждого концепта:

~~~text
Concept
  ↓
Formal Definition
  ↓
Detection Algorithm
  ↓
Historical Occurrences
  ↓
Market Context
  ↓
Outcome
  ↓
Statistical Evaluation
~~~

Нужно выяснять:

- где концепция работает;
- где не работает;
- при каких режимах работает лучше;
- какие подтверждения полезны;
- какие факторы блокируют сценарий;
- частоту ложных сигналов;
- распределение outcome.

AICFA не должен принимать решение только потому, что найден FVG, Order Block или другой SMC-паттерн.

# 9. Price Action

AICFA должен анализировать:

- Support / Resistance;
- Breakout;
- Retest;
- Rejection;
- Continuation;
- Reversal;
- Consolidation;
- Expansion;
- Compression;
- Candle behaviour;
- реакцию цены на важные уровни.

Свечные паттерны не должны рассматриваться вне контекста.

# 9.1 Price Action

AICFA uses a deterministic Price Action layer to formalize candle behaviour
and interactions with previously observed price levels.

Required source fields:
- `timestamp` — availability time of the completed candle;
- `open`;
- `high`;
- `low`;
- `close`.

The layer provides descriptive features for:
- candle body and wick proportions;
- close location;
- bullish/bearish rejection classifications;
- prior support/resistance levels;
- breakouts and failed breakouts;
- breakout retests;
- short candle-sequence continuation/reversal;
- range expansion/compression;
- consolidation.

Prior levels are calculated strictly from candles before the current observation.
No future candle may alter an earlier Price Action result.

These features are descriptive hypotheses, not trade signals. Their thresholds
must be historically evaluated before any predictive interpretation.

Price Action complements SMC, liquidity, structure, volume, derivatives and
market microstructure; it does not replace them.

# 10. Wyckoff

Учитывать:

- Accumulation;
- Distribution;
- Spring;
- Upthrust;
- Markup;
- Markdown;
- Trading Range;
- Sign of Strength;
- Sign of Weakness.

Исследовать совместно с volume, structure, liquidity и price action.

# 11. Derivatives

Постепенно учитывать:

- Open Interest;
- Funding;
- Liquidations;
- Long/Short Ratio;
- Basis;
- derivatives positioning.

Позднее:

~~~text
Order Book
+
Order Flow
+
Bid/Ask imbalance
+
Market Depth
~~~

# 12. Trading Modes

AICFA должен иметь самостоятельные режимы:

- Scalping;
- Intraday;
- Swing;
- Position.

## Scalping

Основные TF:

- 1m;
- 5m;
- 15m.

Фокус:

- microstructure;
- short-term liquidity;
- displacement;
- volume;
- volatility;
- OI;
- funding;
- liquidations;
- позднее order flow/order book.

Scalping не является уменьшенным Swing.

## Intraday

Основные TF:

- 5m;
- 15m;
- 1h;
- 4h.

Фокус:

- intraday structure;
- local liquidity;
- volume;
- derivatives;
- session context;
- execution conditions.

## Swing

Основные TF:

- 1h;
- 4h;
- 1d.

Фокус:

- higher-timeframe structure;
- liquidity;
- market cycles;
- price action;
- derivatives;
- risk/reward.

## Position

Основные TF:

- 1d;
- 1w.

Macro context:

- 1M.

Фокус:

- macro structure;
- cycles;
- major liquidity;
- volatility regimes;
- broader context.

# 13. Multi-Timeframe Engine

AICFA не обязан использовать все таймфреймы в каждом анализе.

Базовые шаблоны:

~~~text
Scalping:
1m → 5m → 15m

Swing:
1h → 4h → 1d

Position:
1d → 1w → 1M
~~~

Но в дальнейшем AICFA должен самостоятельно определять, какая информация необходима для уменьшения неопределённости.

# 14. Active Information Gathering

Одна из ключевых функций.

~~~text
USER
 ↓
AICFA
 ↓
WHAT DO I KNOW?
 ↓
WHAT IS MISSING?
 ↓
WHAT WOULD REDUCE UNCERTAINTY?
 ↓
REQUEST DATA
 ↓
NEW INFORMATION
 ↓
REANALYZE
~~~

Пример:

~~~text
User: Что по BTC?

AICFA: Нужен BTC/USDT 1H.

User: [screenshot]

AICFA: Нужен 4H для старшего контекста.

User: [screenshot]

AICFA: Нужны Open Interest и Funding.

User: [data]

AICFA: Информации достаточно.
~~~

AICFA не должен всегда проходить фиксированную последовательность 15M → 1H → 4H → 1D.

Он должен постепенно научиться выбирать следующий наиболее полезный источник информации.

# 15. Information Value

В будущем выбор следующего источника может формализоваться через ожидаемое уменьшение неопределённости:

~~~text
Candidate Information
  ↓
Expected Information Gain
  ↓
Cost / Availability
  ↓
Priority
  ↓
Request
~~~

# 16. Knowledge Base

Структура знаний:

~~~text
Concept
  ↓
Definition
  ↓
Conditions
  ↓
Examples
  ↓
Counterexamples
  ↓
Relations
  ↓
Historical Evidence
~~~

Разделы:

- Market Structure;
- SMC;
- Liquidity;
- Price Action;
- Wyckoff;
- Volume;
- Derivatives;
- Market Microstructure;
- Risk Management;
- Statistics;
- Trading Research.

Knowledge Base должна постепенно становиться структурированным источником для Brain, а не просто папкой документов.

# 17. Experience Database

Каждая аналитическая ситуация по возможности сохраняется с:

- Situation ID;
- asset;
- timestamp;
- mode;
- timeframes;
- market state;
- structure;
- liquidity;
- volume;
- OI;
- funding;
- scenario;
- entry;
- stop;
- targets;
- invalidation;
- required conditions;
- actual outcome;
- error/reason.

Цель:

~~~text
Historical Market
  ↓
AICFA Analysis
  ↓
Outcome
  ↓
Experience
~~~

# 18. Historical Similarity

~~~text
Current Market
  ↓
Structured Market Representation
  ↓
Similarity Search
  ↓
Historical Situations
  ↓
Observed Outcomes
  ↓
Additional Evidence
~~~

Сравниваться могут:

- structure;
- liquidity;
- volatility;
- volume;
- derivatives;
- market regime;
- timeframe context;
- trend/range;
- SMC state.

Исторический аналог не является гарантией повторения прошлого.

# 19. Labels

Возможные targets:

- future return;
- future MFE;
- future MAE;
- TP hit;
- SL hit;
- triple barrier outcome;
- volatility outcome;
- time to target;
- false breakout;
- scenario outcome.

Критическое правило:

~~~text
features(T) = только прошлое и настоящее
labels(T)   = могут использовать будущее
~~~

Future labels никогда не должны попадать во входные признаки.

# 20. Training Dataset

~~~text
Raw OHLCV
  ↓
Causal Features
  ↓
Future Labels
  ↓
Leak-Safe Dataset
  ↓
Chronological Split
  ↓
Training
~~~

Проверки:

- duplicate timestamps;
- UTC normalization;
- millisecond parsing;
- NaN handling;
- feature/label alignment;
- отсутствие future leakage;
- корректное временное разделение.

# 21. Chronological Validation

Для временного ряда основной split:

~~~text
PAST ------------------------------> FUTURE

TRAIN | VALIDATION | TEST
~~~

При расширении — walk-forward evaluation.

# 22. First Own Model

Первая модель должна быть CPU-friendly.

Допустимо:

- PyTorch;
- scikit-learn baseline;
- NumPy;
- Pandas.

Сначала нужно доказать корректность dataset, labels, features и out-of-sample результата, а уже затем увеличивать сложность.

# 23. Что AICFA должен учиться предсказывать

Не только цвет следующей свечи.

Задачи:

### Direction
- LONG;
- SHORT;
- NEUTRAL.

### Expected Move
Ожидаемое движение.

### Volatility
Ожидаемая волатильность.

### Risk
Вероятности достижения уровней.

### Time
Временной горизонт.

### False Breakout
Вероятность ложного пробоя.

### Scenario Quality
Статистическая поддержка сценария.

В дальнейшем возможна multi-task модель.

# 24. AICFA Brain

Brain объединяет:

- market data;
- features;
- knowledge;
- experience;
- model predictions;
- historical analogues;
- current market state.

~~~text
MARKET DATA
    ↓
FEATURES
    ↓
STRUCTURE ─┐
LIQUIDITY ─┤
VOLUME ────┤
DERIVATIVES┤
SMC ───────┤
MTF ───────┤
HISTORY ───┤
KNOWLEDGE ─┤
EXPERIENCE ┘
    ↓
SCENARIOS
    ↓
RISK
    ↓
DECISION
~~~

# 25. Scenario Engine

Система должна уметь строить:

- primary scenario;
- alternative scenario;
- invalidation;
- required conditions;
- blockers.

Пример:

~~~text
Primary:
liquidity sweep → displacement → continuation

Alternative:
breakdown → retest → continuation down

Invalidation:
price closes beyond X
~~~

# 26. Mandatory / Confirming / Blocking Factors

Нельзя использовать схему:

~~~text
7 indicators = BUY
~~~

Факторы делятся на:

### Mandatory
Необходимые условия.

### Confirming
Усиливают сценарий.

### Blocking
Могут отменить сценарий независимо от количества подтверждений.

Таким образом, решение основано на структуре факторов, а не на их количестве.

# 27. Decision Engine

Возможные состояния:

- LONG;
- SHORT;
- WAIT;
- NO TRADE.

WAIT и NO TRADE являются полноценными результатами.

AICFA должен уметь сказать:

- «Данных недостаточно»;
- «Есть несколько противоположных сценариев»;
- «Статистического преимущества недостаточно».

Результат анализа может содержать:

~~~text
Market Context
Current State
Primary Scenario
Alternative Scenario
Decision
Entry
Stop Loss
Take Profit
Invalidation
Required Conditions
Risk Assessment
Reasoning
Confidence / Calibration
~~~

# 28. Risk Engine

Учитывать:

- stop distance;
- expected reward;
- volatility;
- position sizing;
- fees;
- slippage;
- funding;
- invalidation;
- maximum risk;
- drawdown context.

# 29. Backtesting

Backtest должен учитывать:

- fees;
- slippage;
- funding;
- execution assumptions;
- latency assumptions, если релевантно.

Нельзя использовать future information.

Backtest должен быть воспроизводимым.

# 30. Evaluation

ML metrics:

- Precision;
- Recall;
- F1;
- Directional Accuracy;
- Calibration.

Trading metrics:

- Expected Return;
- Win Rate;
- Profit Factor;
- Maximum Drawdown;
- Sharpe;
- Sortino;
- Average R;
- MAE;
- MFE;
- False Signal Rate.

Нельзя оценивать систему только по win rate.

# 31. Paper Trading

До реального использования:

~~~text
LIVE MARKET
     ↓
AICFA
     ↓
VIRTUAL POSITION
     ↓
ENTRY / SL / TP
     ↓
REAL MARKET OUTCOME
     ↓
EXPERIENCE
~~~

Paper trading проверяет не только модель, но и всю цепочку live data → features → decision → risk → outcome.

# 32. Experience Loop

~~~text
NEW DATA
  ↓
ANALYSIS
  ↓
DECISION
  ↓
MARKET OUTCOME
  ↓
EXPERIENCE
  ↓
ERROR ANALYSIS
  ↓
DATASET UPDATE
  ↓
NEW MODEL
  ↓
BACKTEST
  ↓
VALIDATION
  ↓
PAPER TRADING
~~~

Это не должно превращаться в бесконтрольное online learning.

# 33. Model Versioning

Каждая модель получает version ID.

Например:

~~~text
AICFA-model-001
AICFA-model-002
AICFA-model-003
~~~

Для каждой версии сохранять:

- model weights;
- architecture;
- feature version;
- dataset version;
- label version;
- training configuration;
- training period;
- validation period;
- test period;
- metrics;
- backtest metrics;
- creation timestamp.

Старая рабочая модель не удаляется при появлении новой.

# 34. Vision

~~~text
Chart Screenshot
       ↓
AICFA Vision
       ↓
Structured Chart Representation
       ↓
AICFA Brain
       ↓
Analysis
~~~

Извлекать:

- candles;
- timeframe;
- price levels;
- structure;
- support/resistance;
- liquidity zones;
- drawn levels;
- visible indicators;
- volume;
- chart context.

Vision является дополнительным каналом и не заменяет точные market data.

# 35. Data Quality

Проверять:

- timestamps;
- gaps;
- duplicates;
- invalid OHLC;
- impossible prices;
- zero/invalid volume;
- timezone;
- symbol consistency;
- timeframe consistency.

Ошибки должны обнаруживаться тестами.

# 36. Tests

Критические компоненты должны иметь тесты:

- downloader;
- timestamp parsing;
- feature engine;
- label engine;
- dataset builder;
- leakage checks;
- data validation;
- model training;
- evaluation;
- backtest;
- decision engine.

# 37. Technology Stack

Начальный стек:

- Python;
- PyTorch;
- NumPy;
- Pandas;
- scikit-learn;
- CCXT;
- PostgreSQL / SQLite;
- FastAPI;
- Docker;
- Git;
- GitHub.

Начальная стратегия — бесплатные/open-source инструменты.

# 38. Инфраструктура

AICFA должен развиваться CPU-first.

При нехватке ресурсов:

- оптимизировать dataset;
- batch processing;
- уменьшать модель;
- кэшировать features;
- разделять ingestion и training;
- запускать тяжёлые задачи отдельно.

GPU добавляется только при доказанной необходимости.

# 39. Freim/Frostdeploy

Текущая концепция:

~~~text
GitHub
  ↓
Freim/Frostdeploy
  ↓
AICFA worker
  ↓
Persistent shared data
~~~

Код находится в Git.

Рабочие данные находятся в persistent storage.

Release directory не должен считаться постоянным хранилищем market data.

# 40. Текущая реализация

Уже реализованы/частично реализованы:

- Python project;
- package structure;
- OHLCV downloader;
- persistent configurable data storage;
- weekly/monthly timeframes;
- causal feature engine;
- feature builder;
- feature validation;
- causal future-outcome label engine;
- label dataset builder;
- leak-safe dataset builder;
- timestamp parsing fixes;
- tests;
- Freim deployment;
- persistent shared data.

BTC/USDT поддерживает базовые 8 таймфреймов:

~~~text
1m
5m
15m
1h
4h
1d
1w
1M
~~~

# 41. Текущее состояние данных

Первая рабочая историческая выборка построена примерно на год данных BTC/USDT.

Ориентировочный объём:

~~~text
1m  → ~525,600
5m  → ~105,120
15m → ~35,040
1h  → ~8,760
4h  → ~2,190
1d  → ~365
1w  → ~53
1M  → ~12
~~~

Количество строк зависит от фактического диапазона.

1M на первой стадии полезен главным образом как macro context, поскольку наблюдений мало.

# 42. Следующая техническая задача

После базовой инфраструктуры:

1. расширить и проверить исторические данные;
2. сформировать feature datasets;
3. сформировать labels;
4. проверить dataset;
5. определить первые prediction targets;
6. создать baseline;
7. создать первую собственную PyTorch model;
8. обучить;
9. провести chronological validation;
10. провести out-of-sample test;
11. сделать первый backtest;
12. зафиксировать результаты;
13. затем расширять Brain.

Отдельно необходимо реализовать автоматическое непрерывное получение свежих данных для live analysis.

# 43. Приоритет разработки

~~~text
DATA
 ↓
FEATURES
 ↓
LABELS
 ↓
LEAK-SAFE DATASET
 ↓
BASELINE
 ↓
FIRST OWN MODEL
 ↓
EVALUATION
 ↓
BACKTEST
 ↓
MARKET BRAIN
 ↓
SMC / LIQUIDITY / VOLUME
 ↓
DERIVATIVES
 ↓
EXPERIENCE
 ↓
ACTIVE INFORMATION
 ↓
VISION
 ↓
PAPER TRADING
 ↓
PLATFORM
~~~

Не строить всё одновременно.

# 44. Целевая система

~~~text
                    LIVE MARKET
                         ↓
                  MARKET DATA ENGINE
                         ↓
                 CURRENT MARKET STATE
                         ↓
       ┌─────────────────┼─────────────────┐
       ↓                 ↓                 ↓
   STRUCTURE          LIQUIDITY          VOLUME
       ↓                 ↓                 ↓
       └─────────────────┼─────────────────┘
                         ↓
                  DERIVATIVES
                         ↓
                 MULTI-TIMEFRAME
                         ↓
                    KNOWLEDGE
                         ↓
                   EXPERIENCE
                         ↓
              HISTORICAL SIMILARITY
                         ↓
                  AICFA BRAIN
                         ↓
                SCENARIO ENGINE
                         ↓
                   RISK ENGINE
                         ↓
                 DECISION ENGINE
                         ↓
            LONG / SHORT / WAIT / NO TRADE
                         ↓
                  PAPER TRADING
                         ↓
                    OUTCOME
                         ↓
               EXPERIENCE DATABASE
                         ↓
             CONTROLLED RETRAINING
                         ↓
                VALIDATED MODEL
~~~

AICFA должен иметь возможность остановиться на любом этапе и сказать:

~~~text
INSUFFICIENT INFORMATION
~~~

или:

~~~text
NO STATISTICAL ADVANTAGE
~~~

Это правильное поведение системы, а не ошибка.

# 45. Запреты

Не допускается:

- превращать AICFA в wrapper сторонней LLM;
- использовать future data в features;
- смешивать train и test;
- считать backtest гарантией будущей доходности;
- принимать решение только по количеству индикаторов;
- считать SMC-концепт гарантированно рабочим;
- автоматически переобучать модель на каждой новой свече;
- автоматически заменять проверенную модель непроверенной;
- хранить production data только в release directory;
- добавлять таймфреймы без доказанной необходимости;
- усложнять систему до проверки базового решения.

# 46. Главный архитектурный принцип

AICFA использует историю для обучения, текущий рынок — для текущего анализа, а накопленный новый опыт — для контролируемого улучшения модели.

Три потока должны оставаться различными:

~~~text
1. TRAINING

Historical Data
  ↓
Dataset
  ↓
Model


2. LIVE INFERENCE

Fresh Market Data
  ↓
Current Features
  ↓
Current AICFA Model
  ↓
Decision


3. LEARNING LOOP

New Outcomes
  ↓
Experience
  ↓
New Dataset
  ↓
Retraining
  ↓
Validation
  ↓
New Model Version
~~~

Это обязательное архитектурное правило AICFA.


# Order Book / Market Depth source contract — 2026-09-29

The first market-microstructure implementation uses a causal snapshot contract.

Required source fields:
- `timestamp` — order-book snapshot availability timestamp;
- `bid_price` — best bid price;
- `ask_price` — best ask price;
- `bid_size` — best bid size;
- `ask_size` — best ask size.

Optional source fields:
- `bid_depth_volume`;
- `ask_depth_volume`.

Optional depth fields must represent a clearly defined aggregate depth region supplied by the source. They are not interpreted as individual liquidity walls.

Derived descriptive features:
- mid price;
- spread and spread percentage;
- microprice;
- top-of-book Bid/Ask imbalance;
- bid/ask size deltas and changes;
- spread and mid-price changes;
- optional aggregate depth total and depth imbalance.

Causality:
- a base observation at time T may use only an order-book snapshot whose availability timestamp is <= T;
- snapshots are aligned with backward as-of semantics;
- source snapshots are ordered by their own observation timestamps before deltas are calculated;
- no future snapshot may alter an already available historical result.

This stage does not yet implement:
- level-by-level liquidity walls;
- order-book cancellation/addition flow;
- absorption;
- CVD.

Those require explicit source contracts and historical availability semantics before implementation.


# Level-by-level Order Book / Liquidity Walls — 2026-09-29

For deeper market-microstructure analysis, AICFA accepts complete order-book
snapshots normalized into one row per visible level:

- timestamp — availability time of the complete snapshot;
- side — bid or ask;
- price — level price;
- size — displayed quantity at that level.

Derived level-change fields:
- previous size;
- size delta;
- added size;
- cancelled size;
- level added;
- level removed.

A level disappearing from a complete snapshot is treated as a displayed
cancellation/removal for descriptive accounting. This does not assert why the
level disappeared economically.

Liquidity-wall detection is deliberately conservative:
- compare displayed size with the same-side visible levels in the same snapshot;
- require persistence across a configurable number of consecutive snapshots;
- expose wall status and size multiple only;
- never convert a wall into a LONG/SHORT signal.

This layer does not yet claim that a large displayed level will be executed.
Displayed liquidity can be added, reduced, cancelled or replaced.

Absorption remains deferred. A defensible absorption feature requires synchronized
trade/taker flow, book-level changes and a defined price-response interval.


## Absorption — causal source contract

Absorption is implemented as a descriptive **candidate event**, not a trading signal.

Required synchronized inputs:
- completed price observations: `timestamp, open, high, low, close`;
- completed taker flow: `timestamp, taker_buy_volume, taker_sell_volume`;
- complete level-by-level book snapshots: `timestamp, side, price, size`.

All timestamps represent source availability time. For event time T the
configured observation window is strictly backward: `(T-W, T]`. No source
observation after T may affect the result.

A candidate requires:
- dominant aggressive taker flow;
- nearby opposing-side displayed liquidity;
- relative size of the candidate level versus the visible same-side book;
- persistence of the candidate level;
- displayed replenishment relative to cancellations;
- limited contemporaneous close-to-open price response and directional
efficiency.

The result is explicitly descriptive. A displayed level does not prove that
an execution occurred there. Without synchronized trade-price-level data and
matching-engine execution information, the implementation must not claim
economic absorption as fact.

Future price movement is not part of the live feature. If later research
evaluates whether absorption candidates predict subsequent movement, that
forward movement belongs to a separate outcome/label dataset.

Exchange-source note: Binance documents futures market streams including
`aggTrade` and `depth`, and futures order-book data exposes price/quantity
levels. The collector must preserve source event/availability timestamps
before synchronization.


# CVD / Cumulative Taker Delta — 2026-09-29

CVD is implemented as a descriptive cumulative taker-delta feature.

Required source fields:
- `timestamp` — availability time of the completed flow interval;
- `taker_buy_volume`;
- `taker_sell_volume`.

Optional `reset` explicitly starts a new cumulative segment. The implementation does
not infer resets from arbitrary calendar boundaries. Without documented reset semantics,
CVD is cumulative over the supplied source sequence.

For each completed interval:
- `taker_delta = taker_buy_volume - taker_sell_volume`;
- CVD is the cumulative sum within the current source segment.

Causality:
- source timestamps are availability timestamps;
- base observations use only source intervals with timestamp <= T;
- backward as-of alignment carries only the latest already-known CVD state;
- future flow observations cannot change earlier CVD values.

Scope limitation: this does not claim to reconstruct an exchange-native lifetime/session
CVD unless the source explicitly defines that scope. Chunked historical data requires an
explicit continuity contract. CVD remains descriptive and is not a standalone trade signal.


## 10.1 Causal Wyckoff Representation

AICFA includes a deterministic Wyckoff-inspired representation layer.

Source contract:
- required: `timestamp`, `open`, `high`, `low`, `close`;
- optional: `volume`;
- `timestamp` is the availability time of the completed candle;
- trading-range boundaries use only strictly prior candles.

The layer provides descriptive features/events for:
- trading-range boundaries and range position;
- breakout and failed breakout;
- Spring candidate;
- Upthrust candidate;
- Sign of Strength;
- Sign of Weakness;
- range expansion/compression;
- optional relative volume and volume expansion;
- deterministic Wyckoff state context;
- explicit Accumulation/Distribution proxy fields.

The Accumulation/Distribution fields are proxies, not claims about hidden
participant intent and not ground-truth labels. AICFA must statistically
evaluate these concepts historically before predictive use.

Wyckoff is asset-agnostic and timeframe-agnostic. The same definitions can be
applied across supported symbols and timeframes. If optional volume is
unavailable, volume-derived fields are omitted rather than fabricated.

Order Book / Market Depth is not a prerequisite for Wyckoff and is not a
prerequisite for the core AICFA market representation. If microstructure data
is unavailable, the remaining causal layers continue to operate.

No Wyckoff feature is a standalone LONG/SHORT decision or trade signal.
