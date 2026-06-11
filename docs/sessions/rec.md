# RAG Support Assistant: Комплексная оценка проекта

> Дата: 2026-04-04 | Версия: 1.0

---

## Содержание

1. [Общая оценка](#1-общая-оценка)
2. [Продукт](#2-продукт)
3. [Дизайн](#3-дизайн)
4. [UX/UI](#4-uxui)
5. [Код](#5-код)
6. [Рекомендации по улучшению](#6-рекомендации-по-улучшению)

---

## 1. Общая оценка

| Аспект | Оценка | Комментарий |
|--------|--------|-------------|
| **Продукт** | 8.0/10 | Полный RAG-пайплайн, мониторинг, эскалация. Не хватает multi-tenancy и персистентных сессий |
| **Дизайн** | 6.5/10 | Функциональный, но без дизайн-системы. Несогласованность между страницами |
| **UX/UI** | 6.0/10 | Основной флоу работает, но accessibility провален, мобильная версия слабая |
| **Код** | 7.0/10 | Хорошая архитектура, но есть уязвимости безопасности и code smells |
| **Итого** | **6.9/10** | Крепкий MVP, но до production-ready нужна работа по безопасности, UX и коду |

---

## 2. Продукт

### 2.1 Что проект делает хорошо

**Полнота RAG-пайплайна** — реализованы все ключевые уровни:
- Level 1: базовый retrieve + generate
- Level 2: hybrid search (BM25 + vector + RRF), cross-encoder reranking, semantic chunking
- Level 3: Self-RAG (retry loop), Corrective RAG (grade_docs), HyDE, parent-child chunking

**Observability** — продуманная система наблюдаемости:
- SQLite tracing с trace_id на каждый запрос
- JSON structured logging через config/logging_config.py
- Metrics dashboard (/api/metrics, /static/metrics.html)
- Alert checker (scripts/check_alerts.py) с hysteresis и webhook-уведомлениями

**Гибкая конфигурация** — 26+ переменных окружения, .env.example с документацией, sensible defaults

**Escalation workflow** — абстракция SupportSink (mock-inbox / Bitrix24) для маршрутизации сложных вопросов

**Документация** — README, runbook, 7 research-документов, 35 task-спецификаций

### 2.2 Что не хватает

| Фича | Важность | Описание |
|------|----------|----------|
| Персистентные сессии | CRITICAL | In-memory сессии теряются при рестарте. Нужен PostgreSQL/Redis |
| Multi-tenancy | HIGH | Общий vector store и traces для всех. Нет изоляции по tenant_id |
| Message queue | HIGH | Синхронная загрузка документов блокирует. Нужен Celery/RQ |
| RBAC | MEDIUM | Только binary API key. Нет ролей (admin/agent/user) |
| Circuit breaker | MEDIUM | Нет fallback если Ollama зависает — просто ждёт |
| Feature flags | MEDIUM | Нельзя переключать RAG-стратегии без перезапуска |
| Distributed tracing | MEDIUM | SQLite local only. Нет OpenTelemetry/Jaeger интеграции |
| Prometheus /metrics | MEDIUM | Кастомный JSON-эндпоинт вместо стандартного Prometheus формата |
| Automated backups | LOW | Нет скриптов для backup/restore ChromaDB и traces.db |
| Fact verification | LOW | Нет проверки фактов в сгенерированном ответе |

### 2.3 Масштабируемость

**Текущий потолок:** ~1000 req/day (2 uvicorn workers, single-node SQLite + ChromaDB)

**Для 10K+ req/day нужно:**
- PostgreSQL вместо SQLite для трейсинга
- Redis для сессий и кеширования
- Qdrant cluster вместо одиночного ChromaDB
- Load balancer + 4-8 workers
- Async task queue для тяжёлых операций

---

## 3. Дизайн

### 3.1 Визуальный стиль

**Цветовая палитра:**
- Light: белые фоны, `#4a90d9` accent, `#1a1a2e` текст
- Dark: deep blue `#1a1a2e`/`#16213e`, `#5b9ee6` accent, `#e0e0e0` текст

**Проблемы:**

1. **Недостаточный контраст (WCAG AA fail)**
   - Dark mode: `--text-secondary: #a0a4b8` на `--bg-chat: #0f1729` — **не проходит** WCAG AA (4.5:1)
   - Light mode: `--text-secondary: #555770` на `#f0f2f5` — **пограничный** контраст

2. **Несогласованность между страницами**
   - chat.html, help.html, metrics.html — каждый файл переопределяет свою палитру CSS-переменных
   - `--radius: 12px` в chat.html vs `--radius: 16px` в help.html
   - Разные line-height: 1.5 (chat) vs 1.6 (help)

3. **Нет дизайн-системы**
   - Все CSS вложены в `<style>` каждого файла (673 строки CSS в chat.html)
   - Нет общего CSS-файла, shared tokens, или design system
   - Spacing: хаотичный набор 4/8/12/16/20px без единой шкалы

### 3.2 Типографика

**Шрифты:** системные (`-apple-system, BlinkMacSystemFont, 'Segoe UI'...`) — хорошо для performance

**Проблемы:**
- Нет typographic scale (font-size: 13px, 14px, 15px, 18px, 20px, 32px разбросаны хаотично)
- Нет единого heading hierarchy
- Timestamps в чате не отображаются (нет времени отправки сообщения)

### 3.3 Иконография

- SVG-иконки inline — хорошо для performance
- Непоследовательная стилизация: некоторые SVG имеют `title`, другие — нет
- Feedback кнопки — emoji (👍👎) вместо SVG-иконок — стилистическое несоответствие

---

## 4. UX/UI

### 4.1 Accessibility (Доступность) — CRITICAL

**Провалы WCAG 2.1 AA:**

| Проблема | Файл | Строка | Серьёзность |
|----------|------|--------|-------------|
| Нет `<label for="">` у form inputs | index.html | 72-76 | HIGH |
| Textarea без `<label>` — только placeholder | chat.html | 749-754 | HIGH |
| Нет `<form>` вокруг chat input | chat.html | 743 | HIGH |
| Dropzone не доступен с клавиатуры | chat.html | 779, 1235 | HIGH |
| Нет visible focus indicators | chat.html | все | HIGH |
| Нет viewport meta в templates | templates/*.html | 1-5 | HIGH |
| SVG-кнопки без aria-label | chat.html | 708-716 | MEDIUM |
| Таблицы без `scope` на headers | templates/*.html | все | MEDIUM |
| Нет keyboard shortcuts | chat.html | все | MEDIUM |
| Нет focus trap в upload overlay | chat.html | 1231 | MEDIUM |

### 4.2 Мобильная адаптация — WEAK

**Текущее состояние:**
- chat.html: 1 breakpoint (600px) — sidebar скрывается, и всё
- help.html: 1 breakpoint (640px) — таблица трансформируется в block
- metrics.html: 1 breakpoint (640px) — grid перестраивается
- templates/*.html: **вообще нет responsive**, нет viewport meta

**Отсутствует:**
- Tablet breakpoint (768-1024px)
- Mobile-first подход (всё desktop-first)
- Touch-friendly sizing (кнопки < 44px tap target)
- Safe area для notch-устройств

### 4.3 UX-паттерны — GOOD с оговорками

**Что работает:**
- SSE streaming для real-time ответов
- Dark/light theme toggle
- Typing indicator (анимированные точки)
- Session management с UUID
- Welcome message при пустом чате
- Feedback кнопки (👍👎) на каждом ответе

**Что не работает:**

1. **Потеря сессии без предупреждения** — кнопка "New session" удаляет текущую без confirmation dialog
2. **Нет copy-to-clipboard** на ответах бота
3. **Нет retry** для упавших сообщений
4. **Нет message search** в истории
5. **Нет timestamp** на сообщениях
6. **Generic error messages** — "Ошибка: [text]" без guidance что делать
7. **Silent failures** — feedback submission, session load молча проглатывают ошибки (`catch (_) {}`)
8. **Upload без прогресса** — нет progress bar, только статус-текст

### 4.4 Loading/Error/Empty States

| State | Реализация | Качество |
|-------|-----------|----------|
| Loading (chat) | Typing indicator + disabled send | OK |
| Loading (metrics) | Нет индикатора | BAD |
| Loading (page) | Нет skeleton/spinner | BAD |
| Error (API) | Generic "Ошибка: ..." | WEAK |
| Error (stream) | "Streaming error" (на английском) | WEAK |
| Error (upload) | Показывает API error | OK |
| Empty (chat) | Welcome message | GOOD |
| Empty (sessions) | "No sessions" (на английском!) | BAD |

---

## 5. Код

### 5.1 Архитектура — GOOD

**Сильные стороны:**
- Чёткое разделение: api/ → agent/ → vectordb/ → config/ → tracing/
- LangGraph node-factory pattern для RAG-пайплайна
- TypedDict для GraphState (прозрачное управление состоянием)
- SupportSink абстракция для эскалации (mock vs Bitrix24)
- Settings singleton с валидацией

**Слабости:**
- Дублирование модулей: `graph.py` (root) vs `agent/graph.py`, `state.py` (root) vs `agent/state.py`
- Нарушение SRP: api/app.py (923 строки) мешает routing, бизнес-логику и инициализацию vector store
- Нарушение DIP: прямые import конкретных реализаций вместо DI

### 5.2 Безопасность — CRITICAL issues

| # | Проблема | Файл:строка | Серьёзность |
|---|----------|-------------|-------------|
| 1 | **Path traversal в file upload** — `file.filename` используется напрямую в path | api/app.py:772 | CRITICAL |
| 2 | **Timing attack на API key** — string `!=` вместо `hmac.compare_digest` | api/app.py:116 | CRITICAL |
| 3 | **Auth отключается при пустом API_KEY** — если env var не задан, auth disabled | api/app.py:110 | HIGH |
| 4 | **Нет input length validation** — пользовательский вопрос не ограничен по длине | graph.py:212 | HIGH |
| 5 | **LLM prompt injection** — user question вставляется в промпт без санитизации | graph.py:212-235 | HIGH |
| 6 | **XSS risk в feedback UI** — `innerHTML` для кнопок feedback | chat.html:1159 | MEDIUM |
| 7 | **Нет CORS** — нет конфигурации CORS headers | api/app.py | MEDIUM |
| 8 | **Session IDs exposed** — `/sessions` endpoint доступен без auth | api/app.py:818 | MEDIUM |

### 5.3 Error Handling — WEAK

**Bare exception handlers (debug-кошмар):**
```python
# graph.py:75, 124, 149
try:
    from mock_inbox import get_support_sink
except Exception:
    pass  # Молчаливый провал — ничего не логируется
```
Встречается в 10+ местах. Делает отладку в production невозможной.

**Непоследовательные HTTP status codes:**
- `/api/ask` возвращает HTTP 200 даже при ошибке (ошибка в теле ответа как `route: "human"`)
- Должен быть 400/500/503 в зависимости от типа ошибки

**print() вместо logger:**
- ingestion/loader.py:107-109 — 2 print()
- scripts/chunking_eval.py:268-344 — 20+ print()
- Не попадают в structured logging pipeline

### 5.4 Performance — MODERATE concerns

| Проблема | Файл | Импакт |
|----------|------|--------|
| SQLite: новое соединение на каждую операцию (нет connection pool) | sqlite_trace.py:107-119 | File descriptor exhaustion, +5-10ms latency |
| Embedding model в global state без thread safety | manager.py:80-119 | Race conditions при concurrent requests |
| In-memory sessions без лимита | api/app.py:276 | Unbounded memory growth |
| Sync document retrieval в async context | api/app.py:547-550 | Блокирует thread pool |
| Нет кэширования идентичных запросов | graph.py | Дублирование LLM-вызовов |

### 5.5 Тестирование — MODERATE

**Покрытие:**
- Тестируется: auth, health, rate limiting, metrics, alerts, state
- НЕ тестируется: core RAG pipeline (retrieve, grade, generate, evaluate), end-to-end flow, concurrent sessions, streaming, document upload → retrieval

**Проблемы:**
- Каждый тест-файл переизобретает stub-инфраструктуру (100+ строк бойлерплейта). Нужен `conftest.py`
- Нет integration tests
- Нет performance tests
- Нет coverage reporting

### 5.6 Code Smells

1. **Magic numbers** — `rrf_k=60`, `quality >= 70`, `200` chars для RRF doc key, `chunk_size=800` (hardcoded в 3 местах)
2. **Глобальное мутабельное состояние** — `_sessions`, `_session_last_access`, `_vector_store` в api/app.py (thread-unsafe)
3. **Повторяющиеся if-else chains** — `hasattr(session, "_history") / hasattr(session, "history") / isinstance(session, dict)` в 3+ местах
4. **40+ `# type: ignore`** — маскирует проблемы с типами LangChain
5. **Inconsistent naming** — `_sessions` vs `_retriever`, `node` vs `_node`

### 5.7 Frontend JS — Memory Leaks

**CRITICAL:**
```javascript
// chat.html:1163-1179
// Каждый addMessage() добавляет новые event listeners на кнопки feedback
// За 100+ сообщений — 200+ listeners, never cleaned up
fbDiv.querySelectorAll('.btn-feedback').forEach(btn => {
    btn.addEventListener('click', async () => { ... });
});
```

**Другие проблемы JS:**
- `setInterval` (health check, metrics refresh) никогда не очищается
- Textarea resize на каждый `input` event без debounce
- Множественные `catch (_) {}` — silent error swallowing
- Race condition: multiple `sendMessage()` при быстром нажатии

---

## 6. Рекомендации по улучшению

### Phase 1: CRITICAL — Безопасность и стабильность (1-2 недели)

#### SEC-1: Исправить path traversal в upload
```python
# api/app.py:772
import os
safe_filename = os.path.basename(file.filename)
if not safe_filename or safe_filename.startswith('.'):
    raise HTTPException(status_code=400, detail="Invalid filename")
file_path = upload_dir / safe_filename
```

#### SEC-2: Timing-safe сравнение API key
```python
# api/app.py:116
import hmac
if not hmac.compare_digest(provided, expected):
    raise HTTPException(status_code=403, detail="Invalid API key")
```

#### SEC-3: Обязательный API_KEY в production
```python
# api/app.py:110
if not expected:
    if os.getenv("ENVIRONMENT") == "production":
        raise HTTPException(status_code=500, detail="API auth not configured")
    return  # Allow in dev mode
```

#### SEC-4: Input length validation
```python
# Pydantic model для /api/ask
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    entity_id: str = Field(..., max_length=100)
```

#### BUG-1: Заменить bare except на specific handlers
Все `except Exception: pass` в graph.py:75,124,149 заменить на:
```python
except ImportError as e:
    logger.debug("Module not available: %s", e)
```

#### BUG-2: Fix memory leak в chat.html
Использовать event delegation вместо listener на каждую кнопку:
```javascript
chatContainer.addEventListener('click', (e) => {
    const btn = e.target.closest('.btn-feedback');
    if (!btn) return;
    submitFeedback(btn.dataset.traceId, btn.dataset.rating);
});
```

### Phase 2: HIGH — UX и качество кода (2-4 недели)

#### UX-1: Accessibility fixes
- Добавить `<label for="">` ко всем form inputs
- Добавить viewport meta в templates
- Добавить `aria-label` на SVG-кнопки
- Сделать upload dropzone focusable (`tabindex="0"`, keyboard events)
- Добавить visible focus indicators (`:focus-visible` стили)

#### UX-2: Мобильная адаптация
- Добавить breakpoints: 480px (phone), 768px (tablet), 1024px (desktop)
- Увеличить tap targets до минимум 44x44px
- Добавить viewport meta ко всем template-файлам

#### UX-3: Error handling в UI
- Заменить generic "Ошибка" на контекстные сообщения с guidance
- Добавить retry кнопку на failed messages
- Убрать все `catch (_) {}` — логировать и показывать пользователю
- Перевести "No sessions" → "Нет сессий"

#### CODE-1: Вынести CSS в общий файл
Создать `static/styles/shared.css` с CSS variables, reset, typography scale

#### CODE-2: Исправить HTTP status codes
```python
# api/app.py — для ошибок пайплайна
raise HTTPException(status_code=500, detail="Pipeline error")
# Для validation errors
raise HTTPException(status_code=400, detail="Question too long")
```

#### CODE-3: Заменить print() на logger
Все `print()` в ingestion/loader.py, scripts/chunking_eval.py → `logger.warning()`/`logger.info()`

#### CODE-4: SQLite connection pooling
```python
# sqlite_trace.py
import threading
_local = threading.local()

def _get_connection():
    if not hasattr(_local, 'conn'):
        _local.conn = sqlite3.connect(_get_db_path(), check_same_thread=False)
    return _local.conn
```

#### CODE-5: conftest.py для тестов
Вынести общие stubs/fixtures в `tests/conftest.py` — убрать 100+ строк бойлерплейта из каждого тест-файла

### Phase 3: MEDIUM — Product и масштабирование (1-2 месяца)

#### PROD-1: Персистентные сессии
Заменить in-memory `_sessions` на PostgreSQL/Redis backend. Сессии должны переживать рестарт.

#### PROD-2: Async document processing
Добавить task queue (Celery + Redis) для загрузки и индексации документов. Endpoint `/api/upload` возвращает task_id, клиент poll-ит статус.

#### PROD-3: Дизайн-система
- Создать единую CSS-библиотеку: tokens (colors, spacing, typography), components (buttons, cards, badges)
- Мигрировать все страницы на общую систему
- Добавить consistent spacing scale (4px base: 4/8/12/16/24/32/48)

#### PROD-4: Integration tests
Покрыть тестами:
- Document upload → indexing → retrieval → answer (end-to-end)
- Multi-turn conversations
- Streaming endpoint
- Concurrent sessions
- Error escalation flow

#### PROD-5: CORS и security headers
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["X-API-Key", "Content-Type"],
)
```

#### PROD-6: Prometheus metrics
Добавить `/metrics` endpoint в Prometheus формате для интеграции с Grafana:
```
rag_request_duration_seconds{quantile="0.5"} 2.1
rag_request_duration_seconds{quantile="0.95"} 8.3
rag_escalation_rate 0.12
rag_quality_score_avg 74.2
```

### Phase 4: LOW — Polish (ongoing)

#### POLISH-1: UX improvements
- Copy-to-clipboard на ответах бота
- Timestamps на сообщениях
- Search в истории сессий
- Confirmation dialog на "New session"
- Progress bar для upload

#### POLISH-2: Cleanup code duplication
- Объединить root-level модули с их copies в подпапках (graph.py, state.py, etc.)
- Вынести magic numbers в config/settings.py
- Убрать `# type: ignore` — создать type stubs для LangChain

#### POLISH-3: Advanced RAG features
- Multi-query retrieval (уже закомментирован)
- Contextual retrieval (header injection)
- Few-shot prompting (dynamic examples)
- Fact verification (entity cross-reference)

#### POLISH-4: Observability upgrade
- OpenTelemetry integration
- Distributed tracing (Jaeger)
- Log aggregation (ELK stack)
- Anomaly detection на метриках

---

## Приложение: Карта файлов проекта

```
RAG_Support_Assistant/
├── api/app.py              (923 строк) REST API endpoints
├── agent/graph.py          (702 строк) LangGraph RAG pipeline
├── agent/state.py          (129 строк) GraphState TypedDict
├── agent/prompts.py        (397 строк) LLM prompt templates
├── config/settings.py      (194 строк) Configuration singleton
├── config/logging_config.py                Structured JSON logging
├── vectordb/manager.py     (883 строк) ChromaDB + BM25 + reranking
├── tracing/sqlite_trace.py (504 строк) SQLite tracing
├── ingestion/loader.py     (294 строк) Document loading
├── ingestion/pipeline.py                   Ingestion workflow
├── scripts/check_alerts.py                 Alert checker (cron)
├── static/chat.html        (48 KB)     Chat interface
├── static/help.html        (12 KB)     Help page
├── static/metrics.html     (10 KB)     Metrics dashboard
├── templates/              (5 файлов)  Legacy Jinja2 templates
├── tests/                  (10 файлов) Unit tests
├── docs/runbook.md                     Operational runbook
├── docs/research/          (7 документов) Research & benchmarks
├── Dockerfile + docker-compose.yml     Docker deployment
├── requirements.txt        (52 пакета) Python dependencies
└── .env.example            (46 переменных) Configuration template
```
