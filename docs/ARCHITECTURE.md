# AI Restaurant Manager — Архитектура (Этап 1: проектирование)

Система поддержки принятия решений для менеджера ресторана.
Это **не** сайт ресторана, **не** чат-бот и **не** приложение для заказа еды.

Главная логика системы:

```
Данные ресторана → метрики → AI-анализ → обнаружение проблемы → прогноз
   → объяснение → рекомендация → РЕШЕНИЕ МЕНЕДЖЕРА (человек) → измерение результата
```

---

## 1. Ключевые архитектурные принципы

1. **Человек — единственный исполнитель решений.**
   AI-слой физически не имеет доступа к операциям записи. Любое изменение состояния
   ресторана (перевод сотрудника, изменение статуса заказа, заказ продуктов) происходит
   только через endpoint `POST /api/recommendations/{id}/accept`, который вызывает
   интерфейс менеджера. AI возвращает только текст и структурированные данные.

2. **Разделение «движка метрик» и «AI-слоя».**
   - *Движок метрик* (детерминированный Python-код) считает все числа: загрузку кухни,
     вероятность перегрузки, прогноз спроса на продукты, среднее ожидание.
   - *AI-слой* (OpenAI API) получает уже посчитанный снимок данных и формулирует
     объяснение на человеческом языке, приоритет проблемы и конкретную рекомендацию.

   Зачем так: числа становятся воспроизводимыми и объяснимыми, а модель не может
   «придумать» метрику. В промпте прямо запрещено вводить числа, которых нет во входных данных.

3. **Деградация без AI.** Если ключа OpenAI нет или API недоступен, работает
   `rule_engine` fallback: те же проблемы обнаруживаются по правилам, а объяснения
   берутся из шаблонов. Демонстрация проекта не ломается.

4. **Всё в реальном времени.** Состояние ресторана меняется по тикам (реальным или
   ускоренным в симуляции) и рассылается во фронтенд через WebSocket.

5. **Каждая рекомендация измеряется.** На момент принятия фиксируется baseline метрики,
   сохраняется прогноз, а через окно измерения записывается фактическое значение и вердикт
   (`helped` / `no_effect` / `worse`).

---

## 2. Общая схема компонентов

```
┌──────────────────────────────────────────────────────────────────────┐
│  FRONTEND — React + TypeScript + Tailwind + Recharts                 │
│  Dashboard · Orders · Table Map · AI Insights · Inventory ·          │
│  Reviews · Guest Profile · Simulation Control                        │
└───────────────┬──────────────────────────────────┬───────────────────┘
          REST (запросы/решения)            WebSocket (поток событий)
                │                                  │
┌───────────────▼──────────────────────────────────▼───────────────────┐
│  BACKEND — Python + FastAPI                                          │
│                                                                      │
│  api/routes        — HTTP-слой, валидация, права                     │
│  services/         — ДВИЖОК МЕТРИК (детерминированный)               │
│     metrics · kitchen_load · forecast · inventory_forecast ·         │
│     staff_load · review_analysis · impact                            │
│  ai/               — AI-СЛОЙ (только чтение, только текст)           │
│     analyzer · forecaster · recommender · prompts · fallback         │
│  simulation/       — ускоренное время, сценарий пиковой нагрузки     │
│  realtime/         — WebSocket broadcaster                           │
└───────────────┬──────────────────────────────────┬───────────────────┘
          SQLAlchemy ORM                      HTTPS (chat completions)
                │                                  │
┌───────────────▼────────────────┐   ┌─────────────▼───────────────────┐
│  SQLite (data/restaurant.db)   │   │  OpenAI API                     │
│  операционные + аналитические  │   │  объяснение · приоритет ·       │
│  таблицы + журнал решений      │   │  рекомендация · темы отзывов    │
└────────────────────────────────┘   └─────────────────────────────────┘
```

---

## 3. Структура папок

```
ai-restaurant-manager/
├── README.md
├── docs/
│   ├── ARCHITECTURE.md          # этот документ
│   ├── DATA_MODEL.md            # схема БД (детально)
│   ├── API.md                   # контракт endpoints
│   └── DEMO_SCRIPT.md           # сценарий демонстрации пиковой нагрузки
│
├── backend/
│   ├── requirements.txt
│   ├── .env.example             # OPENAI_API_KEY, OPENAI_MODEL, DB_PATH, AI_ENABLED
│   ├── data/
│   │   └── restaurant.db
│   ├── app/
│   │   ├── main.py              # создание FastAPI, CORS, роутеры, lifespan
│   │   ├── config.py            # настройки через pydantic-settings
│   │   ├── deps.py              # зависимости (сессия БД, текущий менеджер)
│   │   │
│   │   ├── db/
│   │   │   ├── base.py          # declarative base, engine, session factory
│   │   │   ├── models/          # SQLAlchemy модели (по домену)
│   │   │   │   ├── tables.py        # RestaurantTable, Reservation
│   │   │   │   ├── orders.py        # Order, OrderItem
│   │   │   │   ├── menu.py          # MenuItem, RecipeItem
│   │   │   │   ├── staff.py         # Staff, StaffAssignment
│   │   │   │   ├── inventory.py     # InventoryItem, InventoryMovement
│   │   │   │   ├── guests.py        # Guest, GuestVisit, GuestPreference
│   │   │   │   ├── reviews.py       # Review
│   │   │   │   ├── ai.py            # AiInsight, Recommendation, RecommendationOutcome
│   │   │   │   └── ops.py           # MetricsSnapshot, DecisionLog, SimulationRun/Event
│   │   │   ├── seed/
│   │   │   │   ├── seed_base.py     # меню, столики, персонал, продукты, гости
│   │   │   │   └── seed_history.py  # история заказов и отзывов для аналитики
│   │   │   └── migrations/          # alembic (опционально)
│   │   │
│   │   ├── schemas/             # Pydantic DTO для REST и для AI-ответов
│   │   │   ├── dashboard.py
│   │   │   ├── orders.py
│   │   │   ├── tables.py
│   │   │   ├── inventory.py
│   │   │   ├── guests.py
│   │   │   ├── reviews.py
│   │   │   ├── ai.py            # InsightOut, ForecastOut, RecommendationOut, ImpactOut
│   │   │   └── simulation.py
│   │   │
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── dashboard.py
│   │   │       ├── orders.py
│   │   │       ├── tables.py
│   │   │       ├── reservations.py
│   │   │       ├── staff.py
│   │   │       ├── inventory.py
│   │   │       ├── reviews.py
│   │   │       ├── guests.py
│   │   │       ├── ai_insights.py
│   │   │       ├── recommendations.py
│   │   │       └── simulation.py
│   │   │
│   │   ├── services/            # ДВИЖОК МЕТРИК — вся «математика»
│   │   │   ├── snapshot.py          # сбор единого среза состояния ресторана
│   │   │   ├── kitchen_load.py      # загрузка кухни по станциям
│   │   │   ├── orders_service.py    # статусы, задержки, время ожидания
│   │   │   ├── tables_service.py    # занятость, зоны, проблемы обслуживания
│   │   │   ├── staff_load.py        # нагрузка сотрудников
│   │   │   ├── inventory_forecast.py# прогноз расхода продуктов
│   │   │   ├── forecast.py          # прогноз на 30–60 минут, вероятность перегрузки
│   │   │   ├── anomaly_rules.py     # пороговые правила обнаружения проблем
│   │   │   ├── review_analysis.py   # агрегация тем и доли негатива
│   │   │   └── impact.py            # baseline → прогноз → факт → вердикт
│   │   │
│   │   ├── ai/                  # AI-СЛОЙ — только чтение и текст
│   │   │   ├── client.py            # обёртка OpenAI, таймауты, retry, кеш
│   │   │   ├── analyzer.py          # объяснение и приоритизация проблем
│   │   │   ├── forecaster.py        # текстовая интерпретация прогноза
│   │   │   ├── recommender.py       # формулировка рекомендации и ожидаемого эффекта
│   │   │   ├── review_topics.py     # тематизация и сентимент отзывов
│   │   │   ├── fallback.py          # шаблоны при отключённом AI
│   │   │   └── prompts/
│   │   │       ├── analyze.md
│   │   │       ├── forecast.md
│   │   │       ├── recommend.md
│   │   │       └── reviews.md
│   │   │
│   │   ├── simulation/
│   │   │   ├── clock.py             # виртуальное время, speed_factor
│   │   │   ├── engine.py            # тик: генерация заказов, продвижение готовки
│   │   │   ├── scenarios/
│   │   │   │   ├── peak_evening.py  # сценарий 18:50 → 19:30
│   │   │   │   └── shortage.py      # сценарий нехватки продукта
│   │   │   └── what_if.py           # пересчёт метрик при принятой рекомендации
│   │   │
│   │   ├── realtime/
│   │   │   ├── ws.py                # /ws/stream
│   │   │   └── broadcaster.py       # рассылка событий подписчикам
│   │   └── core/
│   │       ├── enums.py
│   │       ├── time_provider.py     # единый источник времени (реальное/симуляция)
│   │       └── logging.py
│   └── tests/
│       ├── test_kitchen_load.py
│       ├── test_forecast.py
│       ├── test_inventory_forecast.py
│       ├── test_impact.py
│       └── test_recommendation_flow.py
│
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tailwind.config.js
    ├── tsconfig.json
    └── src/
        ├── main.tsx
        ├── App.tsx                  # роутинг + layout
        ├── types/                   # TS-типы, зеркалящие Pydantic-схемы
        │   ├── domain.ts
        │   └── ai.ts
        ├── api/
        │   ├── client.ts            # fetch-обёртка, базовый URL
        │   ├── endpoints.ts
        │   └── hooks/               # useDashboard, useOrders, useTables,
        │       │                    # useInsights, useRecommendations, useSimulation
        │       └── useRealtime.ts   # подписка на WebSocket
        ├── pages/
        │   ├── DashboardPage.tsx
        │   ├── OrdersPage.tsx
        │   ├── TableMapPage.tsx
        │   ├── InsightsPage.tsx     # AI-анализ + прогноз + рекомендации
        │   ├── InventoryPage.tsx
        │   ├── ReviewsPage.tsx
        │   ├── GuestPage.tsx        # карточка гостя для официанта
        │   └── SimulationPage.tsx
        ├── components/
        │   ├── layout/              # Sidebar, TopBar, AlertBell, SimClock
        │   ├── kpi/                 # KpiCard, OccupancyCard, KitchenLoadGauge,
        │   │                        # StaffLoadCard, InventoryHealthCard
        │   ├── orders/              # OrderBoard (колонки), OrderCard, WaitTimeBadge,
        │   │                        # DelayedOrdersList
        │   ├── tables/              # TableMapGrid, TableTile, TableStatusLegend,
        │   │                        # TableDetailDrawer
        │   ├── ai/                  # AlertFeed, InsightCard, ForecastCard,
        │   │                        # RecommendationCard (Принять / Отклонить),
        │   │                        # ExplanationBlock, EvidenceList, ImpactPanel,
        │   │                        # DecisionHistoryTable
        │   ├── inventory/           # StockTable, ShortageRiskCard
        │   ├── reviews/             # ReviewTopicsChart, NegativeShareCard, ReviewList
        │   ├── guests/              # GuestProfileCard, PreferencesTags, FavoriteDishes
        │   ├── charts/              # LoadTrendChart, WaitTimeChart, ForecastAreaChart,
        │   │                        # BeforeAfterBarChart, TopicsPieChart  (Recharts)
        │   └── ui/                  # Badge, StatusDot, Drawer, Modal, Skeleton, Toast
        ├── store/                   # Zustand: состояние realtime-снимка и симуляции
        └── lib/                     # formatters, severity-палитра, статус-маппинги
```

---

## 4. Структура базы данных (SQLite)

Группы таблиц: **операционные** (реальная жизнь ресторана), **аналитические**
(снимки и AI-выводы), **журнальные** (решения человека и симуляции).

### 4.1 Столики и бронирования

**`restaurant_tables`**

| поле | тип | описание |
|---|---|---|
| id | INTEGER PK | |
| number | TEXT | номер столика («12», «V1») |
| zone | TEXT | `main` / `terrace` / `vip` / `bar` / `pass` (зона выдачи) |
| seats | INTEGER | мест |
| status | TEXT | `free` / `occupied` / `reserved` / `awaiting_guest` / `service_issue` |
| waiter_id | INTEGER FK → staff.id NULL | |
| pos_x, pos_y | INTEGER | раскладка на карте столиков |
| occupied_since | DATETIME NULL | для расчёта длительности посадки |
| last_service_at | DATETIME NULL | база для признака «проблема с обслуживанием» |
| updated_at | DATETIME | |

**`reservations`**

| поле | тип | описание |
|---|---|---|
| id | INTEGER PK | |
| guest_id | INTEGER FK → guests.id NULL | |
| table_id | INTEGER FK → restaurant_tables.id NULL | |
| guests_count | INTEGER | |
| reserved_for | DATETIME | время ожидаемого прихода (ключ для прогноза) |
| duration_min | INTEGER | плановая длительность |
| status | TEXT | `pending` / `seated` / `late` / `no_show` / `cancelled` |
| source | TEXT | `phone` / `online` / `walk_in` |
| note | TEXT | |
| created_at | DATETIME | |

### 4.2 Меню и рецепты (связь блюдо → продукт)

**`menu_items`**: id, name, category (`hot`/`cold`/`bar`/`dessert`), price,
avg_cook_time_min, station (`grill`/`hot_line`/`cold_line`/`bar`/`pastry`),
complexity (1–5), is_active.

**`recipe_items`**: id, menu_item_id FK, inventory_item_id FK, qty_per_portion, unit.
Нужна, чтобы прогноз спроса на блюда превращался в прогноз расхода продуктов.

### 4.3 Заказы

**`orders`**

| поле | тип | описание |
|---|---|---|
| id | INTEGER PK | |
| table_id | INTEGER FK | |
| waiter_id | INTEGER FK → staff.id | |
| guest_id | INTEGER FK → guests.id NULL | |
| status | TEXT | `new` / `cooking` / `ready` / `served` / `delayed` / `cancelled` |
| created_at | DATETIME | начало отсчёта ожидания |
| cooking_started_at | DATETIME NULL | |
| ready_at | DATETIME NULL | |
| served_at | DATETIME NULL | |
| promised_min | INTEGER | обещанное время — порог для статуса `delayed` |
| guests_count | INTEGER | |
| total_amount | REAL | |
| priority | TEXT | `normal` / `high` |

Производные (не хранятся, считаются в `orders_service`):
`wait_min = now − created_at`, `is_delayed = wait_min > promised_min`,
`eta_min` — остаточное время приготовления.

**`order_items`**: id, order_id FK, menu_item_id FK, qty, station,
status (`queued`/`cooking`/`ready`/`served`), cook_started_at, cook_finished_at.
Станционная разбивка нужна для расчёта загрузки кухни по участкам, а не «в среднем».

### 4.4 Персонал

**`staff`**: id, name, role (`waiter`/`cook`/`host`/`runner`/`bartender`),
station/zone, shift_start, shift_end, status (`active`/`break`/`off`),
capacity_units (сколько параллельной работы выдерживает), hourly_cost.

**`staff_assignments`** — журнал перераспределений: id, staff_id FK, from_zone,
to_zone, changed_at, source (`manual` / `recommendation`), recommendation_id FK NULL.
Именно здесь видно, что перевод сотрудника выполнен человеком по рекомендации.

Нагрузка сотрудника считается на лету: активные столики, активные заказы,
блюда на его станции → `load_pct`.

### 4.5 Запасы

**`inventory_items`**: id, name, unit (`kg`/`pcs`/`l`), qty_on_hand,
portion_size (расход на порцию), par_level, reorder_level, supplier,
lead_time_hours, updated_at.
Производное `portions_on_hand = qty_on_hand / portion_size` — то, что видит менеджер
(«осталось 8 порций курицы»).

**`inventory_movements`**: id, inventory_item_id FK, delta, reason
(`sale`/`waste`/`delivery`/`correction`), order_id FK NULL, created_at.
История расхода даёт скорость потребления для прогноза нехватки.

### 4.6 Гости и персонализация

**`guests`**: id, name, phone, visits_count, avg_check, loyalty_tier,
first_visit_at, last_visit_at, waiter_note.

**`guest_preferences`**: id, guest_id FK, kind (`diet`/`dislike`/`allergy`/`favorite_dish`/`seating`),
value (`vegetarian`, `no_spicy`, `pasta`, `terrace`), confidence, source (`manual`/`derived`).
Отдельная таблица, а не JSON-поле: по предпочтениям нужны фильтры и агрегация.

**`guest_visits`**: id, guest_id FK, order_id FK, visited_at, check_amount, rating,
table_id, dishes JSON (краткий слепок заказа для карточки официанта).

### 4.7 Отзывы

**`reviews`**: id, guest_id FK NULL, source (`google`/`2gis`/`internal`/`qr`),
rating (1–5), text, created_at, sentiment (`positive`/`neutral`/`negative`),
topics JSON (`["wait_time","service"]`), ai_processed_at, insight_id FK NULL.

Темы фиксированы справочником: `wait_time`, `food_quality`, `service`,
`price`, `cleanliness`, `noise`, `order_error`. Фиксированный список позволяет
считать «34% негатива связано с ожиданием» без разъезжающихся формулировок.

### 4.8 Аналитический слой

**`metrics_snapshots`** — срез состояния на момент времени (основа графиков и
baseline для измерения результата):
id, captured_at, sim_time NULL, occupancy_pct, free_tables, occupied_tables,
reserved_tables, active_orders, delayed_orders, avg_wait_min, avg_cook_min,
kitchen_load_pct, station_loads JSON, staff_load_pct, pending_reservations_30m,
inventory_risk_count, raw JSON.

**`ai_insights`** — обнаруженная проблема или прогноз:

| поле | описание |
|---|---|
| id | |
| created_at / sim_time | |
| type | `kitchen_overload` / `wait_time_growth` / `inventory_shortage` / `staff_overload` / `reservation_spike` / `review_pattern` |
| horizon_min | 0 для текущей проблемы, 30/60 для прогноза |
| severity | `info` / `warning` / `critical` |
| probability | REAL 0–1 (например 0.84) |
| title | «Возможна перегрузка кухни через 30 минут» |
| explanation | объяснение причины (текст от AI или шаблона) |
| evidence | JSON: конкретные числа и ссылки на сущности |
| metrics_snapshot_id | FK |
| source | `rule` / `llm` |
| status | `active` / `resolved` / `dismissed` |

**`recommendations`** — предложенное действие (никогда не выполняется автоматически):

| поле | описание |
|---|---|
| id, insight_id FK | |
| action_type | `reassign_staff` / `call_extra_staff` / `throttle_menu_item` / `extend_promise_time` / `reorder_inventory` / `reseat_guest` / `prioritize_order` / `compensate_guest` |
| title | «Временно перевести одного сотрудника на зону выдачи» |
| rationale | почему это должно помочь |
| action_payload | JSON: `{staff_id: 7, to_zone: "pass"}` — параметры для человека |
| expected_effect | JSON: `{metric:"avg_wait_min", before:27, predicted_after:19}` |
| confidence | REAL |
| status | `proposed` / `accepted` / `rejected` / `expired` |
| decided_by, decided_at, decision_note | кто из людей и что решил |

**`recommendation_outcomes`** — измерение результата:
id, recommendation_id FK, metric, baseline_value, predicted_value, actual_value,
window_min, measured_at, verdict (`pending`/`helped`/`no_effect`/`worse`).

### 4.9 Журналы

**`decision_log`**: id, actor (manager/waiter), entity_type, entity_id, action,
payload JSON, created_at — полная трассировка того, что сделал человек.

**`simulation_runs`**: id, scenario, speed_factor, started_at, sim_time, status.
**`simulation_events`**: id, run_id FK, sim_time, kind, description, payload JSON —
лента вида «19:20 — загрузка кухни 72%».

### 4.10 Связи (кратко)

```
guests 1─n guest_visits n─1 orders n─1 restaurant_tables
guests 1─n guest_preferences
guests 1─n reviews
orders 1─n order_items n─1 menu_items 1─n recipe_items n─1 inventory_items
inventory_items 1─n inventory_movements
staff 1─n orders (waiter) ; staff 1─n staff_assignments
metrics_snapshots 1─n ai_insights 1─n recommendations 1─1 recommendation_outcomes
simulation_runs 1─n simulation_events
```

---

## 5. API endpoints (FastAPI)

Все пути с префиксом `/api`. Разделение важное: **GET — чтение, AI и аналитика;
POST/PATCH — только действия человека.**

### Панель менеджера и метрики

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/dashboard/summary` | единый ответ для главной панели: столики, заказы, бронирования, персонал, запасы, загрузка кухни, активные AI-предупреждения |
| GET | `/metrics/timeseries?metric=&minutes=` | ряды для Recharts (`kitchen_load`, `avg_wait`, `active_orders`, `occupancy`) |
| GET | `/metrics/snapshot/latest` | последний срез |

### Заказы

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/orders?status=&zone=` | список с `wait_min`, `eta_min`, `is_delayed` |
| GET | `/orders/board` | сгруппировано по колонкам: новые / готовятся / готовы / задержанные |
| GET | `/orders/{id}` | детали заказа и позиций |
| PATCH | `/orders/{id}/status` | изменение статуса **человеком** |
| PATCH | `/orders/{id}/priority` | приоритизация вручную |

### Столики и бронирования

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/tables` | карта столиков со статусами и зонами |
| GET | `/tables/{id}` | детали: заказ, официант, гость, время посадки |
| PATCH | `/tables/{id}/status` | смена статуса человеком |
| GET | `/reservations?window_min=60` | ожидаемые брони в окне |
| PATCH | `/reservations/{id}/status` | посадили / опоздание / неявка |

### Персонал

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/staff` | смена, роли, зоны, статусы |
| GET | `/staff/load` | нагрузка по сотрудникам и зонам |
| POST | `/staff/{id}/reassign` | перевод сотрудника (вызывается менеджером, в том числе из принятой рекомендации) |

### Запасы

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/inventory` | остатки в порциях и единицах |
| GET | `/inventory/risks` | продукты с риском нехватки: остаток, прогноз спроса, дефицит, время до исчерпания |
| POST | `/inventory/{id}/adjust` | ручная корректировка / приёмка |

### Отзывы

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/reviews?period=week&sentiment=` | список отзывов |
| GET | `/reviews/analysis?period=week` | доли по темам, % негатива, тренд, повторяющиеся проблемы |
| POST | `/reviews/reanalyze` | перезапуск AI-тематизации |

### Гости (для официанта)

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/guests/{id}/profile` | визиты, любимые блюда, предпочтения, средний чек, прошлые заказы |
| GET | `/tables/{id}/guest-context` | та же карточка, но по столику — основной вход для официанта |
| POST | `/guests/{id}/note` | заметка официанта |

### AI: анализ, прогноз, рекомендации

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/ai/insights?status=active` | текущие обнаруженные проблемы с объяснениями |
| GET | `/ai/insights/{id}` | проблема + evidence + связанные рекомендации |
| POST | `/ai/analyze` | принудительный прогон анализа по текущему снимку |
| GET | `/ai/forecast?horizon_min=30` | прогноз на 30/60 минут: вероятность, причина, тренд |
| GET | `/recommendations?status=proposed` | очередь рекомендаций для менеджера |
| **POST** | `/recommendations/{id}/accept` | **решение человека: принять.** Применяет `action_payload`, фиксирует baseline, запускает измерение |
| **POST** | `/recommendations/{id}/reject` | **решение человека: отклонить** (с причиной) |
| GET | `/recommendations/{id}/impact` | «до / прогноз / после» и вердикт |
| GET | `/recommendations/history` | журнал решений и их результативности |

### Симуляция пиковой нагрузки

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/simulation/start` | `{scenario:"peak_evening", speed_factor:60, start_time:"18:50"}` |
| POST | `/simulation/pause` · `/simulation/resume` · `/simulation/reset` | управление |
| POST | `/simulation/step?minutes=10` | шаг вперёд вручную (удобно для демо) |
| GET | `/simulation/state` | текущее виртуальное время, метрики, лента событий |

### Реальное время

| Канал | Назначение |
|---|---|
| WS `/ws/stream` | события: `metrics.update`, `order.changed`, `table.changed`, `insight.created`, `recommendation.created`, `recommendation.decided`, `impact.measured`, `simulation.tick` |

---

## 6. Основные компоненты интерфейса

### 6.1 Главная панель менеджера (`DashboardPage`)
- Полоса KPI: `OccupancyCard` (свободно/занято/забронировано), `KpiCard` активных
  заказов, `KpiCard` ожидаемых броней за 30/60 мин, `KitchenLoadGauge` (%),
  `StaffLoadCard`, `InventoryHealthCard`.
- `AlertFeed` — важные AI-предупреждения, отсортированные по severity, с переходом
  в карточку проблемы.
- `LoadTrendChart` (Recharts) — загрузка кухни и среднее ожидание за последний час,
  с пунктирной проекцией прогноза.
- `ForecastCard` — ближайший прогноз одной фразой + вероятность.

### 6.2 Мониторинг заказов (`OrdersPage`)
`OrderBoard` из четырёх колонок: **новые → готовятся → готовы → задержанные**.
Каждая `OrderCard`: столик, позиции, официант, `WaitTimeBadge` (цвет по порогу
обещанного времени), ETA. Отдельный блок `DelayedOrdersList` с причиной задержки
(станция-узкое место).

### 6.3 Карта столиков (`TableMapPage`)
`TableMapGrid` по зонам, `TableTile` с цветовым статусом:
свободен · занят · забронирован · ожидается клиент · проблема с обслуживанием.
Клик → `TableDetailDrawer`: заказ, официант, время посадки и `GuestProfileCard`
(персонализация для официанта).

### 6.4 AI-центр (`InsightsPage`) — ядро продукта
Для каждой проблемы одна вертикальная цепочка, повторяющая логику системы:
1. `InsightCard` — что обнаружено, severity.
2. `ExplanationBlock` — почему так считает система.
3. `EvidenceList` — конкретные числа и ссылки на заказы/брони/станции.
4. `ForecastAreaChart` — прогноз на 30–60 минут.
5. `RecommendationCard` — предложенное действие, ожидаемый эффект и две кнопки:
   **«Принять»** / **«Отклонить»** (с полем причины). Никакого автозапуска.
6. `ImpactPanel` + `BeforeAfterBarChart` — «до 27 мин → прогноз 19 мин → факт 21 мин»,
   вердикт `helped`.
7. `DecisionHistoryTable` — все прошлые решения менеджера и их результат.

### 6.5 Запасы (`InventoryPage`)
`StockTable` (остаток в порциях, прогноз спроса, время до исчерпания) и
`ShortageRiskCard` для позиций с риском.

### 6.6 Отзывы (`ReviewsPage`)
`NegativeShareCard` (% негатива за неделю), `ReviewTopicsChart` /
`TopicsPieChart` по темам, `ReviewList` с подсветкой повторяющейся проблемы.

### 6.7 Симуляция (`SimulationPage`)
`SimClock` (виртуальное время и множитель скорости), кнопка
**«Симулировать пиковую нагрузку»**, управление пауза/шаг/сброс,
вертикальный `TimelineFeed` событий (18:50 → 19:10 → 19:20 → 19:30 → рекомендация)
и живые графики, меняющиеся в ускоренном времени.

### 6.8 Сквозные элементы
`TopBar` с `AlertBell` и индикатором режима (реальное время / симуляция),
`Sidebar`-навигация, `useRealtime` для WebSocket, Zustand-store с последним
снимком состояния, чтобы все страницы обновлялись синхронно.

---

## 7. Как взаимодействуют frontend, backend, database и AI

### 7.1 Цикл реального времени (каждый тик)

1. **Источник данных.** Движок симуляции (или в реальной жизни — POS/kitchen display)
   меняет операционные таблицы: создаёт заказы, продвигает позиции по станциям,
   сажает гостей, списывает продукты.
2. **Сбор снимка.** `services/snapshot.py` одним проходом по БД собирает срез:
   занятость, активные заказы и их ожидание, загрузка станций кухни, нагрузка
   персонала, остатки, брони в окне 30/60 минут. Срез пишется в `metrics_snapshots`.
3. **Правила.** `anomaly_rules.py` и `forecast.py` детерминированно считают
   проблемы и прогноз. Пример расчёта загрузки кухни: суммарное остаточное время
   приготовления по станции делится на её пропускную способность за горизонт.
   Прогноз добавляет ожидаемые заказы от броней и типовую кривую часа.
   Вероятность перегрузки — это посчитанная величина, а не выдумка модели.
4. **AI-слой.** Если найдена проблема, `ai/analyzer.py` отправляет в OpenAI API
   **только снимок и результаты правил** и просит вернуть строгий JSON:
   `{title, explanation, severity, recommendation:{action_type, title, rationale,
   action_payload, expected_effect, confidence}}`. Ответ валидируется Pydantic;
   при невалидном ответе или недоступном API берётся `ai/fallback.py`.
   AI-слой использует только read-only сессию БД.
5. **Запись выводов.** Результат сохраняется в `ai_insights` + `recommendations`
   со ссылкой на `metrics_snapshot_id` — каждое утверждение привязано к данным,
   на которых оно сделано.
6. **Доставка в UI.** `realtime/broadcaster.py` рассылает по WebSocket события
   `metrics.update` и `insight.created`; фронтенд обновляет store, карточки и графики.

### 7.2 Цикл решения человека

```
Менеджер видит RecommendationCard
        │
        ├── «Отклонить» → POST /recommendations/{id}/reject
        │     status=rejected, причина в decision_log. Состояние не меняется.
        │
        └── «Принять»  → POST /recommendations/{id}/accept
              1. фиксируется baseline метрики из текущего снимка (avg_wait = 27)
              2. применяется action_payload (например POST /staff/{id}/reassign) —
                 но только потому, что это инициировал человек
              3. создаётся recommendation_outcomes со verdict=pending
              4. записывается decision_log (кто, когда, что)
              5. через window_min (реальных или симуляционных) services/impact.py
                 берёт новый снимок, записывает actual_value и вердикт
              6. WebSocket impact.measured → ImpactPanel показывает
                 «было 27 → прогноз 19 → факт 21 → помогло»
```

Критично: ни один путь выполнения, начинающийся в `ai/`, не может изменить
операционные таблицы. Применение действия вызывается только из обработчика
`accept`, то есть всегда после явного решения человека.

### 7.3 Где именно используется OpenAI API

| Задача | Вход | Выход |
|---|---|---|
| Объяснение проблемы | снимок + сработавшие правила | понятный текст причины |
| Приоритизация | список проблем | severity и порядок показа |
| Рекомендация | проблема + доступные ресурсы (персонал, станции, меню) | конкретное действие + ожидаемый эффект |
| Анализ отзывов | пакет отзывов + справочник тем | sentiment, темы, повторяющийся паттерн |
| Карточка гостя | история визитов и заказов | краткая подсказка официанту |

Ограничения промптов: `temperature ≈ 0.2`, ответ строго JSON по схеме,
прямой запрет вводить числа, отсутствующие во входных данных, запрет предлагать
действия вне перечня `action_type`, запрет обращаться к гостю от имени ресторана.

### 7.4 Режим симуляции

`core/time_provider.py` — единственный источник времени для всех сервисов.
В обычном режиме отдаёт реальное время, в симуляции — виртуальное от
`simulation/clock.py` с множителем скорости. Благодаря этому аналитика, прогноз
и измерение результата работают в ускоренном времени без отдельного кода,
а демонстрация (18:50 → 19:30) проходит за полторы минуты.

---

## 8. Порядок разработки по этапам

| Этап | Содержание | Результат, который можно показать |
|---|---|---|
| **1. Архитектура** (этот документ) | структура папок, схема БД, endpoints, компоненты, схема взаимодействия | согласованный план |
| **2. Фундамент данных** | SQLAlchemy-модели, создание SQLite, seed реалистичных данных (столики, меню с рецептами, персонал, запасы, гости, история заказов и отзывов) | наполненная БД и скрипт пересоздания |
| **3. Backend-скелет + движок метрик** | FastAPI, `snapshot`, `kitchen_load`, `orders_service`, `staff_load`; endpoints dashboard / orders / tables / staff / inventory | `/docs` с живыми данными, все числа считаются |
| **4. Frontend-скелет** | Vite + React + TS + Tailwind, layout, типы, api-client; Dashboard, OrdersPage, TableMapPage на реальных данных | работающая панель менеджера без AI |
| **5. Движок правил и прогноза** | `anomaly_rules`, `forecast`, `inventory_forecast`, `review_analysis`; таблицы `ai_insights` / `recommendations`; `AlertFeed`, `ForecastCard`, Recharts-графики | проблемы и прогнозы обнаруживаются по правилам |
| **6. AI-слой (OpenAI)** | `ai/client`, промпты, валидация JSON, `fallback`; объяснения, рекомендации, тематизация отзывов | AI-объяснения и формулировки рекомендаций |
| **7. Контур решения и измерение результата** | `accept` / `reject`, `decision_log`, `impact.py`, `recommendation_outcomes`; `RecommendationCard`, `ImpactPanel`, `BeforeAfterBarChart`, `DecisionHistoryTable` | полная цепочка «проблема → решение человека → измеренный эффект» |
| **8. Реальное время** | WebSocket broadcaster, `useRealtime`, Zustand-store, периодический тик анализа | панель обновляется сама, без перезагрузки |
| **9. Симуляция пиковой нагрузки** | `clock`, `engine`, сценарий `peak_evening`, `what_if`, `SimulationPage`, таймлайн | демо 18:50 → 19:30 с прогнозом и рекомендацией |
| **10. Персонализация гостей** | `guest-context` endpoint, `GuestProfileCard`, `PreferencesTags` в `TableDetailDrawer` | карточка постоянного гостя для официанта |
| **11. Отзывы и аналитика периода** | `ReviewsPage`, темы, доля негатива, тренд | «34% негатива связано с ожиданием» |
| **12. Полировка и демо** | тесты движка метрик, обработка ошибок, пустые состояния, `DEMO_SCRIPT.md`, README с запуском | готовый к показу прототип |

Этапы 2–4 дают «живой каркас» без AI. Этапы 5–7 реализуют главную ценность
продукта (анализ → рекомендация → решение человека → измерение). Этапы 8–9 делают
проект демонстрируемым, 10–12 закрывают оставшиеся функции.

---

## 9. Согласованные параметры

| Параметр | Значение | Где задаётся |
|---|---|---|
| Ресторан | «Терра», 18 столиков, зоны `main`/`terrace`/`vip`/`bar` | `app/db/seed/catalog.py` |
| Смена | 12 человек: 4 официанта, 5 поваров, хостес, раннер, бармен | `catalog.py` |
| Меню | 20 блюд, 26 продуктов, рецепты для всех блюд | `catalog.py` |
| Перегрузка кухни | предупреждение ≥ 70%, критично ≥ 85% | `config.py` |
| Критичное ожидание | предупреждение > 18 мин, критично > 25 мин | `config.py` |
| Перегрузка сотрудника | ≥ 80% | `config.py` |
| Наплыв броней | ≥ 6 броней в окне 30 минут | `config.py` |
| Окно измерения результата | 20 минут | `config.py` |
| Язык интерфейса | русский | `config.py` |
| AI | OpenAI API, модель по умолчанию `gpt-4o-mini`, `temperature 0.2` | `.env` |

Пороги вынесены в настройки, а не зашиты в код: на демонстрации их удобно
менять, чтобы показать, как меняется чувствительность системы.

---

## 10. Уточнения, внесённые при реализации слоя данных

1. **У столика нет поля `current_order_id`.** Циклическая ссылка
   `restaurant_tables ↔ orders` потребовала бы `ALTER TABLE ADD CONSTRAINT`,
   который SQLite не поддерживает. Важнее другое: такое поле создавало бы второй
   источник правды о состоянии столика. Текущий заказ выводится запросом из
   `orders` по `table_id` и активному статусу.

2. **Производные величины не хранятся.** Время ожидания, признак задержки,
   загрузка кухни и нагрузка сотрудника считаются сервисами из `created_at`,
   `promised_min` и позиций заказа. В базе лежат только факты, а не выводы —
   иначе снимки метрик расходились бы с операционными таблицами.

3. **Остаток продукта хранится в единицах, а порции вычисляются.**
   `portions_on_hand = qty_on_hand / portion_size` — свойство модели, потому что
   менеджеру нужны порции, а поставки приходят в килограммах и литрах.

4. **Добавлена зона `pass`** (выдача) — именно туда рекомендация
   `reassign_staff` предлагает временно перевести сотрудника.

5. **`guests.first_visit_at` не пересчитывается по истории.** История покрывает
   14 дней, а знакомство с постоянным гостем произошло раньше; `visits_count` и
   `avg_check` при этом приводятся в соответствие с таблицей визитов, чтобы
   карточка официанта не противоречила данным.
