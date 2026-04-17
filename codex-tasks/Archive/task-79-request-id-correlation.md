# Task 79 — OBSERVABILITY: X-Request-Id header + correlation ID в логах

## Goal
Support-кейс: пользователь пишет «дал неправильный ответ 5 минут назад».
Чтобы найти этот запрос в трейсах, нам нужно:
1. Попросить пользователя скопировать что-нибудь идентифицирующее из UI.
2. Сейчас **идентифицировать нечем** — у UI нет заголовка с request-id,
   у ответа нет поля с request-id, в логах есть trace_id только для
   `/api/ask` (генерируется внутри LangGraph-пайплайна).

Что теряем без correlation ID:
- `/api/upload`, `/api/feedback`, `/api/auth/*` — в логах есть путь и
  статус, но нет способа связать строку лога с конкретным пользовательским
  инцидентом. «500 на login в 14:23» — у кого? которого из сотни?
- Даже для `/api/ask` trace_id **внутри** пайплайна (из `graph.state`),
  но не попадает в middleware-лог `GET /api/ask -> 200`. Две логические
  записи, нет связи.

Решение — **request-scoped correlation ID**:
1. Middleware на каждый request: либо берёт `X-Request-Id` из заголовков
   клиента (если валидный), либо генерирует UUID4.
2. Значение кладётся в `ContextVar` — доступно из любого места обработки.
3. Устанавливается в response-header `X-Request-Id`.
4. Включается в строку middleware-лога.
5. Для `/api/ask` — прокидывается в `graph.state.trace_id`, если тот пуст.

Стандарт X-Request-Id: https://http.dev/x-request-id
(индустриально-общепринятый, не W3C traceparent — тот для distributed
tracing, это отдельная task если появится).

## Files to create
- `api/correlation.py` — ContextVar + helper'ы
- `tests/test_request_id.py` — 5 тестов

## Files to change
- `api/app.py` — новый middleware `_request_id` перед `_log_requests`,
  существующий `_log_requests` использует request_id в формате лога,
  `/api/ask` передаёт request_id в graph

---

## 1. `api/correlation.py`

```python
"""Request-scoped correlation ID для логов и ответов."""
from __future__ import annotations

import re
import uuid
from contextvars import ContextVar
from typing import Optional

# Формат совместим с W3C tracestate value: ASCII visible, без запятых,
# макс 128 символов. Не принимаем произвольные user-controlled значения,
# чтобы избежать log-injection.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9_\-:.]{1,128}$")

_current_request_id: ContextVar[Optional[str]] = ContextVar(
    "request_id", default=None
)


def generate_request_id() -> str:
    """UUID4 без дефисов — компактнее в логах."""
    return uuid.uuid4().hex


def sanitize_request_id(raw: Optional[str]) -> Optional[str]:
    """Валидировать значение из заголовка клиента.

    Возвращает значение, если оно проходит whitelist regexp, иначе None.
    """
    if not raw:
        return None
    if not _VALID_REQUEST_ID.match(raw):
        return None
    return raw


def get_request_id() -> Optional[str]:
    """Текущий request ID или None вне request-scope."""
    return _current_request_id.get()


def set_request_id(value: Optional[str]) -> None:
    """Только для middleware. В бизнес-коде использовать get_request_id."""
    _current_request_id.set(value)
```

**Инварианты:**
- User-controlled `X-Request-Id` проходит strict whitelist → защита от
  log-injection (например `\n` + fake log line).
- ContextVar — не глобальная переменная; корректно работает в asyncio.
- Генерируем hex (32 символа), без дефисов — короче в grep'е.

---

## 2. `api/app.py`: новый middleware

**Порядок важен:** `_request_id` должен стоять **перед** `_log_requests`,
иначе лог-строка не увидит ID.

```python
@app.middleware("http")
async def _request_id(request: Request, call_next: Any) -> Any:
    from api.correlation import (
        generate_request_id,
        sanitize_request_id,
        set_request_id,
    )

    incoming = sanitize_request_id(request.headers.get("X-Request-Id"))
    req_id = incoming or generate_request_id()
    set_request_id(req_id)

    response = await call_next(request)
    response.headers["X-Request-Id"] = req_id
    return response
```

Расширить существующий `_log_requests`:

было:
```python
    logger.info(
        "%s %s -> %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
```

стало:
```python
    from api.correlation import get_request_id
    logger.info(
        "req_id=%s %s %s -> %d (%.1fms)",
        get_request_id() or "-",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
```

**Регистрация middleware в FastAPI** — `@app.middleware("http")` стекают
в обратном порядке. Чтобы `_request_id` отрабатывал **раньше**
`_log_requests`, он должен быть объявлен **ПОЗЖЕ** в коде (последний
зарегистрированный — первый вызывается). Сверить по тесту
`test_request_id_present_in_log_line`.

---

## 3. `/api/ask` — передать request_id в пайплайн

В `api/app.py::_run_qa_pipeline` (или где вызывается graph) найти точку,
где создаётся начальный `GraphState`, и заинжектить:

```python
    from api.correlation import get_request_id

    initial_state = create_initial_state(
        question=question,
        # ... остальное ...
    )
    if not initial_state.get("trace_id"):
        initial_state["trace_id"] = get_request_id() or ""
```

Если код выглядит иначе — адаптировать, сохраняя инвариант: внешний
`trace_id` из graph'а может перезаписать request_id только если
уже установлен; иначе наследуется request_id.

---

## 4. `tests/test_request_id.py`

```python
"""Тесты correlation ID: генерация, preservation, sanitize, в логах."""
from __future__ import annotations

import logging
import re
import uuid

import pytest
from fastapi.testclient import TestClient


def test_request_id_generated_when_header_absent(client: TestClient) -> None:
    resp = client.get("/api/health/live")
    assert "X-Request-Id" in resp.headers
    value = resp.headers["X-Request-Id"]
    # UUID4 hex (32 символа)
    assert re.fullmatch(r"[0-9a-f]{32}", value), value


def test_request_id_preserved_from_header(client: TestClient) -> None:
    incoming = "test-req-id-abc123"
    resp = client.get(
        "/api/health/live", headers={"X-Request-Id": incoming}
    )
    assert resp.headers["X-Request-Id"] == incoming


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    # \n — попытка log-injection
    bad = "evil\nFAKE LOG LINE"
    resp = client.get("/api/health/live", headers={"X-Request-Id": bad})
    assert resp.headers["X-Request-Id"] != bad
    assert re.fullmatch(r"[0-9a-f]{32}", resp.headers["X-Request-Id"])


def test_too_long_request_id_is_replaced(client: TestClient) -> None:
    bad = "a" * 200  # > 128 chars
    resp = client.get("/api/health/live", headers={"X-Request-Id": bad})
    assert resp.headers["X-Request-Id"] != bad


def test_request_id_appears_in_log_line(client: TestClient, caplog) -> None:
    caplog.set_level(logging.INFO, logger="api.app")
    incoming = "corr-0001"
    client.get("/api/health/live", headers={"X-Request-Id": incoming})

    matching = [r for r in caplog.records if incoming in r.getMessage()]
    assert matching, (
        f"expected log line to contain req_id={incoming}, "
        f"got:\n" + "\n".join(r.getMessage() for r in caplog.records)
    )
```

**Замечания:**
- `caplog.set_level(logging.INFO, logger="api.app")` — фикстура стандартная,
  не требует добавлений в conftest.
- Если logger в проекте называется иначе — поправить logger name.

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **122+ passed** (117 было + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Строгий whitelist для `X-Request-Id` — **обязательно** (log-injection).
- `X-Request-Id` **всегда** появляется в response headers (даже на 4xx/5xx).
- ContextVar — не global. Proof-test не требуется, но убедиться, что
  `set_request_id` зовётся **внутри** middleware, не на модульном уровне.

## DONE WHEN
- [ ] `api/correlation.py` с ContextVar и helper'ами
- [ ] `_request_id` middleware зарегистрирован и отрабатывает перед
      `_log_requests` (по порядку вызова)
- [ ] `X-Request-Id` в ответе всегда присутствует
- [ ] Невалидные значения (regexp не прошёл, > 128 chars) заменяются
      на сгенерированный
- [ ] `_log_requests` пишет `req_id=...` в строку лога
- [ ] `/api/ask` передаёт request_id в graph как fallback для `trace_id`
- [ ] `tests/test_request_id.py` — 5 тестов, все проходят
- [ ] `pytest tests/ -v` — 122+ passed
- [ ] `ruff check .` — 0 errors
