# Анализ ответов LLM и архитектура PoC RAG-ассистента

## 1. Какой LLM мог выдать какой ответ (гипотезы) и разбор

Важно: это **чистая угадайка** по стилю, уверенность низкая.

### Ответ 1

**Гипотеза по модели**

Очень “классический” стиль:  
- аккуратное дерево директорий,  
- короткие комментарии,  
- кусочек кода в конце, хотя просили “без кода” — типичный “я знаю лучше требований” 😅  

Похоже на ChatGPT (GPT-4/4.1) или другой “общий” LLM без сильной оптимизации под следование инструкциям.

**Что хорошо**

- Структура читаемая и компактная.
- Пояснения по папкам/файлам есть, без излишней воды.
- Есть явный указатель, где живёт трейс: `tracing/langgraph_tracer.py` + SQLite.
- Видна связь модулей: `agent` зависит от `vectordb`, `integrations`, `tracing`, `api` – от `agent` и т. д.

**Что не очень**

- Нарушение требования “не писать код” (кусок с `graph.with_config(...)`).
- Нет отдельного `data/` для артефактов (вектора, БД трейсинга, inbox).
- Нет `config/` (всё свалено в `config.py` в корне).
- Трейс описан достаточно поверхностно (нет явного разделения на schema/ writer/ reader).

**Оценка**:  
Структура норм, но поверхностная и с нарушением условий. Я бы дал **7/10**.

---

### Ответ 2

**Гипотеза по модели**

Очень многословно, много перефразирования, “мета-объяснений” (“эта архитектура модульная…”, “ниже приведена полная структура…”). Это сильно похоже на Claude-стиль (Opus/Sonnet) или на GPT в режиме “максимально объясни всё”.

**Что хорошо**

- Очень подробно расписаны зависимости между папками.
- Чётко описано, где trace: `tracing/tracer.py` → `traces.db`.
- Есть осмысленный `config.py`, упоминание `traces.db` как артефакта.
- Даёт понятный high-level поток: api → agent → vectordb / integrations → tracing.

**Что не очень**

- Много “воды”: повторение одной и той же мысли несколькими формулировками.
- Структура чуть менее аккуратна, чем у Ответа 3: нет отдельного `data/`, нет разнесения tracing на schema / writer / reader.
- Немного смешаны уровни детализации: где-то очень детально, где-то общо.

**Оценка**:  
Содержательно хорошо, но можно намного компактнее. **8/10** за содержание, **6/10** за лаконичность.

---

### Ответ 3

**Гипотеза по модели**

Очень “инженерный” ответ:

- Есть `data/` для артефактов.
- Ясное разделение tracing: `schema`, `sqlite_client`, `trace_writer`, `trace_reader`, `context`.
- Интеграции разнесены на подпакеты `bitrix/` и `inbox/`.
- Чётко описано, где и как создаётся run / steps.

Это прям стиль человека, который много пишет архитектурные доки — или хорошо настроенного GPT-4.1 / “thinking”-модели.

**Что хорошо**

- **Самая сильная часть — tracing**:
  - `tracing/schema.py`
  - `tracing/sqlite_client.py`
  - `tracing/trace_writer.py`
  - `tracing/trace_reader.py`
  - `tracing/context.py`
- Понятное разделение кода и данных: `data/vectordb`, `data/tracing/traces.db`, `data/inbox`.
- Логичная декомпозиция `agent/nodes/*` с отдельными узлами для каждого шага графа.
- Хорошо расписаны реальные зависимости:
  - кто кого вызывает,
  - кто создаёт run,
  - как узлы логируют шаги.

**Что слабее**

- Ответ длинный (хотя менее “водянистый”, чем Ответ 2).
- Немного перегружено деталями для PoC (но тебе как раз это, по ощущениям, и нужно 😉).

**Оценка**:  
Структурно – лучший из четырёх. **9/10**.

---

### Ответ 4

Текст обрывается на середине `vectordb/storage.py`, поэтому:

**Что видно**

- Аккуратное дерево на верхнем уровне.
- Логика похожа на Ответ 1, но с чуть более структурированными секциями (“1. Папка ingestion…”).

**Что можно сказать**

- По тому, что показано, это хороший, но менее подробный вариант.
- До tracing и API мы не дочитали, поэтому оценка неполная.

**Оценка (по обрывку)**:  
Где-то **7/10**, но мало данных.

---

## 2. Мой вариант архитектуры (собираю лучшее из ответов)

Я возьму базу из **Ответа 3** (config + data + тщательный tracing), комбинирую с минимализмом **Ответа 1**, и аккуратно подчёркну, где и как именно пишется trace в SQLite.

### Корневая структура проекта

```text
rag-support-assistant/
├── main.py                # Локальный вход для dev/demo (запуск API/агента)
├── pyproject.toml / requirements.txt
├── README.md
├── .env.example           # Пример локальных переменных окружения (без токенов)
│
├── config/                # Конфигурация проекта
├── data/                  # Локальные артефакты (БД, индексы, mock-инбокс)
│   ├── vectordb/
│   ├── tracing/
│   │   └── traces.db      # SQLite с трейcами графа (мини-LangSmith)
│   └── inbox/
│       └── inbox.db       # SQLite/mock-инбокс
│
├── ingestion/             # Работа с документами
├── vectordb/              # Векторная БД и retrieval
├── agent/                 # LangGraph: состояние, узлы, граф, LLM
├── integrations/          # Bitrix и mock-инбокс
├── tracing/               # Локальный LangSmith-подобный трейсинг
├── api/                   # FastAPI-обёртка над агентом и трейсингом
├── tests/                 # Юнит-тесты
└── demo/                  # Демо-документы (гарантия, возвраты, ошибки E10–E30)
```

---

### config/ — конфигурация

```text
config/
├── __init__.py            # get_settings() и удобные хелперы
├── settings.py            # Pydantic Settings или аналог
└── logging.yaml           # Конфиг логгера
```

**Назначение**

- `settings.py`:
  - путь к `data/tracing/traces.db`;
  - корни `data/vectordb/`, `data/inbox/`;
  - настройки Ollama (host/port, модель по умолчанию — `mistral`);
  - флаг: использовать Bitrix или только mock-инбокс;
  - пути к `demo/`.
- Используется в: `ingestion`, `vectordb`, `agent`, `integrations`, `tracing`, `api`.

---

### data/ — артефакты

```text
data/
├── vectordb/              # Индексы векторного хранилища
├── tracing/
│   └── traces.db          # SQLite для трейсинга шагов графа
└── inbox/
    └── inbox.db           # SQLite/mock-инбокс (эскалации)
```

**Назначение**

- Чётко отделить код (`rag-support-assistant/`) от генерируемых данных.
- Все записи трейса → **строго сюда** (`tracing` пишет только сюда).

---

### ingestion/ — работа с документами

```text
ingestion/
├── __init__.py            # Экспорт публичных функций (run_ingestion и др.)
├── loaders.py             # Загрузка документов из demo/
├── preprocessors.py       # Очистка и нормализация текста
├── splitters.py           # Нарезка на чанки
└── pipeline.py            # Оркестрация ingestion-процесса
```

**Назначение файлов**

- `loaders.py`  
  - Читает документы из `demo/` (md, txt, pdf).
  - Возвращает список Document-объектов.
- `preprocessors.py`  
  - Чистит текст, нормализует формат.
- `splitters.py`  
  - Делит документы на чанки (по размеру, по заголовкам).
- `pipeline.py`  
  - Склеивает всё: загрузка → препроцессинг → чанки.
  - Отдаёт чанки в `vectordb` для индексации.

**Зависимости**

- Использует: `config.settings`, `demo/`.
- Вызывается: утилитами, скриптом или API-эндпоинтом для первичного наполнения БД.

---

### vectordb/ — векторная БД и retrieval

```text
vectordb/
├── __init__.py            # Экспорт фабрик indexer/retriever
├── schema.py              # Модель документа/чанка для индексации
├── embeddings.py          # Обёртка над локальными эмбеддингами
├── store.py               # Работа с конкретным движком (Chroma/FAISS/и т.п.)
└── retriever.py           # Высокоуровневый retriever для RAG
```

**Назначение**

- `schema.py` — описывает структуру: id, текст, метаданные, вектор.
- `embeddings.py` — использует локальную модель эмбеддингов (без внешних API; может быть отдельный локальный сервис или LLM).
- `store.py` — хранение и поиск по векторам, артефакты лежат в `data/vectordb/`.
- `retriever.py` — интерфейс `retrieve(query, filters) → [chunks]`.

**Зависимости**

- Использует: `config.settings`, результат из `ingestion.pipeline`.
- Используется: `agent/nodes/retrieval_node.py`, тесты.

---

### agent/ — LangGraph: состояние, узлы, граф

```text
agent/
├── __init__.py                # build_support_agent_graph(), фабрики
├── state.py                   # Структура состояния графа
├── llm_client.py              # Обёртка над локальной LLM через Ollama
├── prompts.py                 # Шаблоны промптов
├── tools.py                   # Утилиты (форматирование, подготовка payload)
├── nodes/
│   ├── __init__.py
│   ├── retrieval_node.py      # Достаёт контекст из vectordb
│   ├── classification_node.py # Решает, нужна ли эскалация
│   ├── answer_node.py         # Генерирует ответ пользователю
│   ├── escalation_decision_node.py
│   ├── bitrix_escalation_node.py
│   └── inbox_escalation_node.py
└── graph.py                   # Конфигурация LangGraph, сборка всего графа
```

**Назначение**

- `state.py` — описывает поля:
  - запрос пользователя;
  - retrieved context;
  - история диалога;
  - флаги эскалации (тип и необходимость);
  - id текущего run/step для трейсинга (если прокидываем явно).
- `llm_client.py` — обёртка над Ollama:
  - умеет генерировать текст;
  - интерфейс спроектирован так, чтобы легко заменить модель (меняем реализацию или конфиг).
- `prompts.py` — шаблоны для:
  - RAG-ответа;
  - решения об эскалации;
  - резюме для тикета.
- `tools.py` — вспомогательные функции (сборка payload для Bitrix/inbox и т.п.).

**Узлы (`nodes/*`)**

- `retrieval_node.py`  
  - Берёт state.question, вызывает `vectordb.retriever`, кладёт контекст в state.
  - Логирует шаг через `tracing.trace_writer`.
- `classification_node.py`  
  - Решает, достаточно ли знаний БЗ, нужна ли эскалация и куда.
  - Выставляет флаги в state.
  - Логирует шаг.
- `answer_node.py`  
  - Генерирует финальный ответ пользователю (если эскалация не нужна).
  - Логирует вход/выход.
- `escalation_decision_node.py`  
  - Разруливает ветку после classification:
    - Bitrix → `bitrix_escalation_node`;
    - inbox → `inbox_escalation_node`;
    - иначе → финальный ответ.
- `bitrix_escalation_node.py`  
  - Формирует payload, вызывает `integrations.bitrix.client`.
  - Логирует результат (id тикета и т.п.).
- `inbox_escalation_node.py`  
  - То же самое, но через `integrations.inbox.store` (запись в локальный inbox.db).

**graph.py**

- Собирает LangGraph из узлов.
- Здесь же **подключает трейсинг**:
  - при старте диалога создаёт новый run в `tracing.trace_writer`;
  - оборачивает выполнение каждом узла вызовами `start_step/ end_step`.

**Зависимости**

- Использует: `vectordb`, `integrations`, `tracing`, `config`.
- Используется: `api` (для обработки запросов), `tests/test_agent_nodes.py`.

---

### integrations/ — Bitrix и mock-инбокс

```text
integrations/
├── __init__.py
├── bitrix/
│   ├── __init__.py
│   ├── client.py         # Stub-клиент Bitrix (без реальных токенов)
│   └── mappers.py        # Маппинг state → структура тикета Bitrix
└── inbox/
    ├── __init__.py
    ├── models.py         # Модель письма/тикета для inbox
    └── store.py          # Работа с data/inbox/inbox.db
```

**Назначение**

- `bitrix/client.py` — stub-интерфейс: либо логирует в файл, либо пишет в локальную БД, но **не** требует токенов/внешних API.
- `bitrix/mappers.py` — как превратить состояние агента в структуру тикета.
- `inbox/models.py` — описание локального тикета.
- `inbox/store.py` — примитивный DAO поверх `data/inbox/inbox.db`.

**Зависимости**

- Использует: `config.settings`.
- Используется: `agent/nodes/bitrix_escalation_node.py`, `agent/nodes/inbox_escalation_node.py`.

---

### tracing/ — “мини-LangSmith” на SQLite

```text
tracing/
├── __init__.py           # Экспорт TraceWriter, TraceReader
├── schema.py             # Схема таблиц runs/steps/events (описательно)
├── sqlite_client.py      # Низкоуровневый клиент к SQLite
├── trace_writer.py       # Основная логика записи трейсов
├── trace_reader.py       # Чтение трейсов для UI/API
└── context.py            # Хранение текущего run_id/step_id (contextvars)
```

**Ключевой момент: где пишется trace**

- **Физическое место хранения**:  
  `data/tracing/traces.db` (путь берётся из `config.settings`).
- **Файл, который пишет**:  
  `tracing/trace_writer.py`.

**Роли файлов**

- `schema.py`  
  - Описывает структуру таблиц:
    - `runs` — один диалог/запрос;
    - `steps` — один шаг графа (узел);
    - опционально `events` для мелких событий.
- `sqlite_client.py`  
  - Создаёт БД и таблицы при старте (если их нет).
  - Даёт простые методы insert/select.
- `trace_writer.py`  
  - High-level API:
    - `start_run(metadata) → run_id`
    - `end_run(run_id, status, error?)`
    - `start_step(run_id, node_name, input_state) → step_id`
    - `end_step(step_id, output_state, status, error?)`
  - Вызывается из:
    - `agent/graph.py` (обёртка каждого узла),
    - при необходимости — из отдельных `nodes/*`.
- `trace_reader.py`  
  - Методы:
    - `list_runs(filters)`,
    - `get_run_steps(run_id)`.
  - Используется API-слоем для просмотра трасс.
- `context.py`  
  - Хранит текущий `run_id` и, при необходимости, `step_id` в контексте запроса (чтобы узлам не надо было таскать их по аргументам).

**Зависимости**

- Использует: `config.settings`.
- Используется: `agent.graph`, `agent.nodes`, `api/routers/tracing.py`, `tests`.

---

### api/ — FastAPI-обёртка

```text
api/
├── __init__.py            # create_app() или app
├── main.py                # Точка входа для Uvicorn/Hypercorn
├── deps.py                # Depends: агент, трейсинг, настройки
└── routers/
    ├── __init__.py
    ├── chat.py            # /chat — диалог с ассистентом
    ├── traces.py          # /traces, /traces/{run_id} — просмотр трейсов
    └── health.py          # /health — проверки (LLM, БД и т.п.)
```

**Назначение**

- `chat.py`:
  - принимает запрос пользователя;
  - создаёт новый `run` через `TraceWriter`;
  - вызывает граф из `agent/graph.py`;
  - возвращает ответ + `run_id`.
- `traces.py`:
  - отдаёт список `runs` и шаги по `run_id` (через `trace_reader`).
- `health.py`:
  - проверяет доступность SQLite, наличие модели Ollama и т.п.

**Зависимости**

- Использует: `agent`, `tracing`, `config`.
- Tочка входа `main.py` используется `main.py` в корне.

---

### tests/ — юнит-тесты

```text
tests/
├── conftest.py             # Фикстуры для temp SQLite, temp vectordb
├── test_ingestion.py
├── test_retriever.py
├── test_agent_nodes.py
├── test_tracing.py
└── test_api.py
```

---

### demo/ — демо-документы

```text
demo/
├── docs/
│   ├── warranty.md            # Гарантия
│   ├── returns_policy.md      # Возвраты
│   └── errors_e10_e30.md      # Ошибки E10–E30
└── conversations/
    └── sample_tickets.json    # Примеры обращений
```

---

### Итог: где “мини-LangSmith”

Если коротко:

- **Файл БД**:  
  `data/tracing/traces.db`.
- **Модуль, который реально пишет**:  
  `tracing/trace_writer.py` (через `sqlite_client.py` и `schema.py`).
- **Кто вызывает writer**:
  - `agent/graph.py` при запуске каждого запроса и при переходах между узлами;
  - опционально сами `nodes/*` для более детального логирования.

То есть **аналог LangSmith** — это вся папка `tracing/` + привязка к графу в `agent/graph.py`.
