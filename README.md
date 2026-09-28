# AICFA

**AI for Digital Financial Assets**

AICFA — специализированная AI-система для анализа крипторынка и цифровых финансовых активов.

Цель проекта — создать собственный специализированный AI trading system, который способен анализировать рыночные данные, графики и контекст, сопоставлять их с накопленными знаниями и историческим опытом, самостоятельно определять, какой информации ему не хватает, запрашивать её и формировать обоснованные торговые сценарии.

AICFA не является простым чат-ботом, набором индикаторов, сигнальным ботом или оболочкой вокруг сторонней AI-модели.

---

# Vision

AICFA должен постепенно научиться работать как специализированный цифровой аналитик и торговый мозг рынка.

```text
User
  ↓
AICFA
  ↓
Определение доступной информации
  ↓
Определение недостающей информации
  ↓
Получение дополнительных данных
  ↓
Анализ рынка
  ↓
Сопоставление со знаниями и историческим опытом
  ↓
Формирование сценариев
  ↓
Оценка риска
  ↓
LONG / SHORT / WAIT / NO TRADE
```

AICFA не обязан выдавать торговое решение, если имеющейся информации недостаточно.

**WAIT / NO TRADE — полноценный результат анализа.**

---

# Core Principles

## 1. Own AI

Основное интеллектуальное ядро AICFA должно обучаться и развиваться внутри проекта.

Проект не ставит целью создать интерфейс, который просто передаёт запрос сторонней LLM и возвращает её ответ.

Используемые библиотеки и инструменты могут быть открытыми и сторонними, но специализированные модели и логика AICFA создаются в рамках проекта.

---

## 2. Data before assumptions

AICFA должен опираться на данные рынка и проверяемые исторические результаты.

Основные источники информации:

* OHLCV
* Volume
* Open Interest
* Funding
* Liquidations
* Long/Short data
* Volatility
* Market structure
* Order flow
* Order book data — на более позднем этапе

---

## 3. Multi-timeframe analysis

Рынок рассматривается на разных временных масштабах.

Пример:

```text
1W   → macro context
1D   → higher-timeframe structure
4H   → swing context
1H   → intraday structure
15M  → local structure
5M   → execution context
1M   → scalping / microstructure
```

AICFA не обязан использовать все таймфреймы в каждом анализе.

Он должен определять, какая дополнительная информация действительно необходима.

---

# Trading Modes

AICFA должен поддерживать несколько самостоятельных торговых режимов.

## Scalping

Краткосрочный анализ и торговые сценарии.

Основные особенности:

* 1M
* 5M
* 15M
* micro market structure
* liquidity
* short-term displacement
* volume
* volatility
* Open Interest
* Funding
* Liquidations
* в будущем Order Flow / Order Book

Скальпинг не должен быть просто уменьшенной версией Swing Trading.

Для него требуется отдельное представление рынка и отдельные критерии оценки ситуации.

---

## Intraday

Работа внутри торгового дня.

Основные элементы:

* 5M
* 15M
* 1H
* 4H
* intraday liquidity
* market structure
* volume
* derivatives
* session context
* execution conditions

---

## Swing

Среднесрочные движения.

Основные элементы:

* 1H
* 4H
* 1D
* higher-timeframe structure
* liquidity
* market cycles
* broader price action
* derivatives
* risk/reward

---

## Position

Более долгосрочные сценарии.

Основные элементы:

* 1D
* 1W
* macro structure
* market cycles
* major liquidity zones
* volatility regimes
* broader market context

---

Эти режимы используют общий AICFA Brain, но могут иметь специализированные модели, признаки, правила и критерии принятия решений.

```text
                         AICFA BRAIN
                              │
             ┌────────────────┼────────────────┐
             ↓                ↓                ↓
         SCALPING          INTRADAY          SWING
             │                │                │
       microstructure      local           higher-TF
             │             structure         structure
             └────────────────┼────────────────┘
                              ↓
                         POSITION
```

---

# Smart Money Concepts

Smart Money Concepts (SMC) является отдельным фундаментальным направлением анализа AICFA.

AICFA должен постепенно изучать, распознавать и проверять на исторических данных следующие концепции.

## Market Structure

* Higher High — HH
* Higher Low — HL
* Lower High — LH
* Lower Low — LL
* Break of Structure — BOS
* Change of Character — CHoCH
* Market Structure Shift — MSS
* Trend
* Range
* Expansion
* Consolidation
* Displacement

## Liquidity

* Buy-side Liquidity
* Sell-side Liquidity
* Equal Highs
* Equal Lows
* Previous Highs
* Previous Lows
* Liquidity Pools
* Liquidity Sweep
* Liquidity Grab
* Stop-run behaviour
* Breakout traps

## Imbalances

* Fair Value Gap — FVG
* Inverse Fair Value Gap — IFVG
* Imbalance
* Displacement

## Order Blocks

* Bullish Order Block
* Bearish Order Block
* Breaker
* Mitigation
* Order Block invalidation

## Premium / Discount

* Dealing Range
* Premium
* Discount
* Equilibrium

## Additional SMC Concepts

* Inducement
* Point of Interest — POI
* SMT / Divergence
* Internal / External Liquidity
* Internal / External Structure

SMC concepts должны рассматриваться не как абсолютные торговые правила.

AICFA должен исследовать:

```text
Concept
   ↓
Market Context
   ↓
Historical Occurrences
   ↓
Outcome
   ↓
Statistical Evidence
```

Таким образом, система должна постепенно выяснять, **в каких рыночных условиях конкретная концепция действительно имеет ценность**, а где она даёт ложные сигналы.

---

# Price Action

AICFA должен понимать:

* Support / Resistance
* Breakout
* Retest
* Rejection
* Continuation
* Reversal
* Consolidation
* Expansion
* Compression
* Candle behaviour
* Price reaction at important levels

Price Action анализируется вместе с контекстом, а не как набор отдельных свечных паттернов.

---

# Wyckoff

В систему знаний входят:

* Accumulation
* Distribution
* Spring
* Upthrust
* Markup
* Markdown
* Trading Range
* Sign of Strength
* Sign of Weakness

AICFA должен исследовать связь Wyckoff-контекста с другими рыночными признаками.

---

# Volume

AICFA должен анализировать:

* Volume
* Relative Volume
* Volume Expansion
* Volume Contraction
* Volume at Breakout
* Volume at Rejection
* Volume vs Price
* Volume behaviour around liquidity events

Рост объёма сам по себе не является автоматическим сигналом LONG или SHORT.

---

# Derivatives

Для анализа деривативов:

* Open Interest
* Funding Rate
* Liquidations
* Long/Short Ratio
* Basis
* Derivatives positioning

Позже:

* Order Flow
* Order Book
* Bid/Ask imbalance
* Market depth

Эти данные должны рассматриваться вместе с ценой и рыночным контекстом.

---

# AICFA Brain

Целевая архитектура:

```text
                         AICFA
                           │
             ┌─────────────┼─────────────┐
             │             │             │
          KNOWLEDGE      MARKET DATA   EXPERIENCE
             │             │             │
             └─────────────┼─────────────┘
                           ↓
                     AICFA BRAIN
                           │
          ┌────────────────┼────────────────┐
          ↓                ↓                ↓
      STRUCTURE        LIQUIDITY          VOLUME
      ANALYSIS         ANALYSIS           ANALYSIS
          │                │                │
          └────────────────┼────────────────┘
                           ↓
                 MULTI-TIMEFRAME ANALYSIS
                           ↓
                   SCENARIO ENGINE
                           ↓
                      RISK ENGINE
                           ↓
                    DECISION ENGINE
                           ↓
                LONG / SHORT / WAIT
```

В дальнейшем отдельные специализированные модели могут отвечать за различные части анализа, но все они должны работать в рамках общей архитектуры AICFA.

---

# Active Information Gathering

Одна из ключевых возможностей AICFA — самостоятельно определять, какой информации ему не хватает.

Пример:

```text
User:
Что по BTC?

AICFA:
Пришли BTC/USDT 1H.

User:
[screenshot]

AICFA:
Теперь нужен 4H для определения старшего контекста.

User:
[screenshot]

AICFA:
Структура понятна.
Мне нужны Open Interest и Funding.

User:
[data]

AICFA:
Информации достаточно.
```

После этого система формирует итоговый анализ.

AICFA не должен следовать фиксированному сценарию вроде:

```text
15M → 1H → 4H → 1D
```

Он должен постепенно научиться определять, **какой следующий источник информации наиболее полезен для уменьшения неопределённости**.

---

# Knowledge Base

AICFA будет содержать структурированную базу знаний.

Основные направления:

```text
Market Structure
Smart Money Concepts
Liquidity
Price Action
Wyckoff
Volume
Derivatives
Market Microstructure
Risk Management
Trading Research
Statistics
```

Знания должны постепенно преобразовываться из документов и материалов в структурированные сущности:

```text
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
```

---

# Experience

AICFA должен постепенно накапливать собственный опыт.

Каждая историческая или реальная аналитическая ситуация может сохраняться как структурированная запись:

```text
Situation ID

Asset
Timestamp
Trading Mode
Timeframes

Market State
Structure
Liquidity
Volume
Open Interest
Funding

AICFA Scenario
Entry
Stop
Targets
Invalidation

Actual Market Outcome
```

Это позволит создавать собственную **Experience Database**.

---

# Historical Similarity

AICFA должен уметь искать похожие исторические ситуации.

```text
Current Market
      ↓
Market Representation
      ↓
Historical Similarity Search
      ↓
Similar Situations
      ↓
Observed Outcomes
      ↓
Additional Evidence
      ↓
AICFA Decision
```

Исторические аналоги являются дополнительным источником информации и не гарантируют повторения прошлого.

---

# Decision Engine

AICFA не должен сводиться к предсказанию следующей свечи.

Возможные итоговые состояния:

```text
LONG
SHORT
WAIT
NO TRADE
```

Полный сценарий может содержать:

```text
Market Context

Primary Scenario

Alternative Scenario

Entry

Stop Loss

Take Profit

Invalidation

Required Conditions

Risk Assessment

Reasoning
```

AICFA должен уметь сказать:

> Данных недостаточно.

или:

> Есть несколько противоположных сценариев, поэтому сейчас нет достаточного преимущества для сделки.

---

# Mandatory, Confirming and Blocking Factors

AICFA не должен использовать простую систему:

```text
7 indicators = BUY
```

Факторы должны иметь разные роли:

### Mandatory Factors

Необходимые условия для определённого сценария.

### Confirming Factors

Дополнительные признаки, усиливающие сценарий.

### Blocking Factors

Условия, способные отменить сценарий независимо от количества подтверждений.

Таким образом, решение должно учитывать **структуру взаимодействия факторов**, а не только их количество.

---

# Training

Первая стадия обучения будет основана преимущественно на числовых рыночных данных.

```text
Historical Market Data
        ↓
Data Cleaning
        ↓
Market State Construction
        ↓
Historical Situations
        ↓
Training Dataset
        ↓
Our Model
        ↓
Evaluation
        ↓
Backtesting
        ↓
Paper Trading
        ↓
Experience Database
        ↓
Future Training
```

Все обучающие примеры должны строиться таким образом, чтобы модель не получала информацию из будущего.

Training, validation и test должны разделяться хронологически.

---

# What AICFA Should Learn

Модель должна постепенно решать несколько связанных задач.

## Direction

```text
LONG
SHORT
NEUTRAL
```

## Expected Move

Оценка возможного движения.

## Risk

Вероятность достижения различных уровней риска.

## Volatility

Оценка ожидаемого диапазона движения.

## Time

Оценка временного горизонта сценария.

## False Breakout

Оценка вероятности ложного пробоя.

## Scenario Quality

Оценка статистической поддержки конкретного сценария историческими данными.

AICFA не должен обучаться только задаче «зелёная или красная следующая свеча».

---

# Vision

Анализ скриншотов является отдельным будущим компонентом.

```text
Chart Screenshot
       ↓
AICFA Vision
       ↓
Structured Chart Representation
       ↓
AICFA Brain
       ↓
Analysis
```

Vision должен постепенно научиться извлекать:

* Candles
* Timeframe
* Price levels
* Market structure
* Support / Resistance
* Liquidity zones
* Drawn levels
* Visible indicators
* Volume
* Chart context

Vision является дополнительным каналом восприятия и не заменяет основной Market Brain.

---

# Experience Loop

После появления paper/live анализа система сможет формировать контролируемый цикл:

```text
NEW MARKET DATA
       ↓
AICFA ANALYSIS
       ↓
DECISION
       ↓
REAL MARKET OUTCOME
       ↓
EXPERIENCE DATABASE
       ↓
ERROR ANALYSIS
       ↓
DATASET UPDATE
       ↓
NEW MODEL VERSION
       ↓
BACKTEST
       ↓
VALIDATION
       ↓
PAPER TRADING
```

Новая модель не должна автоматически заменять предыдущую.

Каждая версия должна проходить сравнение и проверку.

---

# Evaluation

AICFA будет оцениваться одновременно как AI-модель и как торговая система.

Возможные ML-метрики:

* Precision
* Recall
* F1
* Directional Accuracy
* Calibration

Торговые метрики:

* Expected Return
* Win Rate
* Profit Factor
* Maximum Drawdown
* Sharpe Ratio
* Sortino Ratio
* Average R
* MAE
* MFE
* False Signal Rate

Тестирование должно учитывать:

* Trading Fees
* Slippage
* Funding
* Execution Assumptions

Backtest results do not guarantee future performance.

---

# Paper Trading

До любого возможного применения реальных средств:

```text
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
```

Paper trading является обязательным этапом проверки системы.

---

# Development Roadmap

## Phase 0 — Foundation

* [x] Create AICFA project
* [x] Register `aicfa.ru`
* [x] Create separate brand repository
* [x] Publish brand declaration
* [x] Publish SHA-256 proof
* [x] Publish `.ots` timestamp proof
* [x] Publish verification instructions
* [x] Create `NYXTRYP/aicfa`

## Phase 1 — Market Data

* [ ] Python project
* [ ] Historical data downloader
* [ ] BTC/USDT dataset
* [ ] 1M / 5M / 15M / 1H / 4H / 1D data
* [ ] Data normalization
* [ ] Dataset storage
* [ ] Historical situation generator
* [ ] Initial scalping dataset
* [ ] Initial intraday dataset
* [ ] Initial swing dataset

## Phase 2 — First Own Model

* [ ] Define first prediction tasks
* [ ] Build training dataset
* [ ] Build first PyTorch model
* [ ] Train
* [ ] Validate
* [ ] Test
* [ ] Document results

## Phase 3 — Market Intelligence

* [ ] Market structure
* [ ] Multi-timeframe structure
* [ ] Liquidity
* [ ] Smart Money Concepts
* [ ] Price Action
* [ ] Volume
* [ ] Volatility
* [ ] Derivatives
* [ ] Risk model
* [ ] Scenario engine
* [ ] Decision engine

## Phase 4 — Trading Modes

* [ ] Scalping engine
* [ ] Intraday engine
* [ ] Swing engine
* [ ] Position engine
* [ ] Mode-specific datasets
* [ ] Mode-specific evaluation

## Phase 5 — Knowledge

* [ ] Knowledge structure
* [ ] SMC concepts
* [ ] Price Action
* [ ] Wyckoff
* [ ] Liquidity
* [ ] Risk Management
* [ ] Derivatives
* [ ] Trading research
* [ ] Historical examples
* [ ] Counterexamples
* [ ] Knowledge retrieval

## Phase 6 — Experience

* [ ] Situation database
* [ ] Historical analogues
* [ ] Outcome tracking
* [ ] Error analysis
* [ ] Experience-based learning

## Phase 7 — Active AI

* [ ] Determine missing information
* [ ] Request additional market data
* [ ] Request screenshots
* [ ] Dynamic multi-step analysis
* [ ] Information-value selection

## Phase 8 — Vision

* [ ] Chart representation
* [ ] Screenshot processing
* [ ] Chart structure extraction
* [ ] SMC visual recognition
* [ ] Liquidity recognition
* [ ] Integration with Market Brain

## Phase 9 — Paper Trading

* [ ] Live market data
* [ ] Virtual positions
* [ ] Real-time decisions
* [ ] Outcome tracking
* [ ] Continuous evaluation

## Phase 10 — AICFA Platform

* [ ] Web interface
* [ ] API
* [ ] User sessions
* [ ] Analysis history
* [ ] Experience memory
* [ ] Visualization
* [ ] Public demo

---

# Project Structure

The repository will gradually evolve toward:

```text
aicfa/
├── data/
│   ├── raw/
│   ├── processed/
│   └── datasets/
│
├── models/
│   ├── market/
│   ├── scalping/
│   ├── structure/
│   ├── risk/
│   └── vision/
│
├── training/
│   ├── datasets/
│   ├── train.py
│   └── evaluate.py
│
├── knowledge/
│   ├── concepts/
│   ├── smc/
│   ├── price_action/
│   ├── wyckoff/
│   ├── rules/
│   └── research/
│
├── experience/
│   ├── situations/
│   └── outcomes/
│
├── analysis/
│   ├── structure/
│   ├── liquidity/
│   ├── smc/
│   ├── volume/
│   ├── derivatives/
│   └── microstructure/
│
├── decision/
│   ├── scenarios/
│   ├── risk/
│   └── engine/
│
├── backtest/
├── api/
├── web/
├── scripts/
├── tests/
└── README.md
```

This is a target architecture. Components will be added when they become necessary.

---

# Technology

Initial stack:

* Python
* PyTorch
* NumPy
* Pandas
* scikit-learn
* CCXT
* PostgreSQL / SQLite
* FastAPI
* Docker
* Git / GitHub

The project is designed to begin with free and open-source tooling.

---

# Repository Separation

AICFA uses separate repositories for different purposes.

## AICFA

`NYXTRYP/aicfa`

Contains:

* AI
* Models
* Training
* Market analysis
* SMC
* Scalping
* Knowledge
* Experience
* Backend
* Interface
* Tests

## AICFA Brand

`NYXTRYP/aicfa-brand`

Contains the historical brand declaration and cryptographic proof associated with the AICFA identity.

The brand repository is intentionally separated from the AI product repository.

---

# Current Status

**Current stage: Foundation / Phase 1**

The initial identity and provenance foundation has been completed.

The technical development now begins with:

```text
BTC/USDT historical data
        ↓
multi-timeframe dataset
        ↓
historical situations
        ↓
first own model
        ↓
first evaluation
```

The system will then progressively expand toward:

```text
Scalping
Intraday
Swing
Position
        ↓
SMC
        ↓
Market Intelligence
        ↓
Knowledge
        ↓
Experience
        ↓
Active Information Gathering
        ↓
Vision
        ↓
Paper Trading
        ↓
AICFA Platform
```

---

# Disclaimer

AICFA is an experimental research and software project.

Market analysis and model outputs are not guarantees of future market performance or financial returns.

Historical and backtested results do not guarantee future results.

The system should initially be developed and evaluated using historical data and paper trading before considering any real-money application.
