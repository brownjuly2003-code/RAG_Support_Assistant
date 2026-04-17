# Task 82 — RESILIENCE: Request-level timeout + offload pipeline из event loop

## Goal
Две связанные проблемы в `/api/ask`:

### 1. Блокировка event loop (pre-existing bug)
В `api/app.py:642` вызывается:
```python
result = session.ask(question, trace_id=get_request_id())
```

`ConversationSession.ask` → `run_qa_pipeline` → **синхронный** LangGraph
pipeline с HTTP-вызовами к Ollama через `langchain_community.llms.Ollama`.
Это **блокирует asyncio event loop** на всё время обработки запроса.

Последствия на проде:
- Один запрос с Ollama 8-секундным response time → **все** остальные
  concurrent HTTP-соединения (включая health-probes) ждут 8 секунд.
- `uvicorn --workers 1` (дефолт в Docker) == последовательная обработка.
  FastAPI не даёт concurrency из коробки, когда event loop заблокирован.
- `/api/health/live` начинает отвечать с задержкой → k8s думает, что pod
  умер (liveness timeout обычно 1s) → рестарт под нагрузкой.

### 2. Отсутствие request-level timeout
Даже с task-71 (per-Ollama-call timeout 60s) и task-70 (retry ×3),
пайплайн может делать 4+ LLM-вызова (transform_query, grade_docs,
generate, evaluate) × retry × Self-RAG iterations. Суммарно до
~10 минут в худшем случае. Пользователь UI уже закрыл вкладку.

## Решение
```python
result = await asyncio.wait_for(
    asyncio.to_thread(session.ask, question, trace_id=get_request_id()),
    timeout=settings.request_timeout_sec,
)
```

1. `asyncio.to_thread` выносит blocking sync-вызов в thread pool →
   event loop свободен, concurrency восстановлена.
2. `asyncio.wait_for` ограничивает total wall-time для одного запроса.
3. На `TimeoutError` — 504 + Prometheus counter + лог с `request_id`.

Добавить метрику `rag_request_timeouts_total{endpoint}` — без неё мы
не узнаем, что лимит слишком узкий/широкий.

## Files to change
- `config/settings.py` — `request_timeout_sec`
- `api/app.py::ask` — `asyncio.wait_for(asyncio.to_thread(...))` + 504 handler
- `api/app.py` — (опционально) то же для `/api/ask/stream`, см. §5
- `monitoring/prometheus.py` — counter + helper
- `.env.example`, `README.md`

## Files to create
- `tests/test_request_timeout.py` — 4 теста

---

## 1. `config/settings.py`

Рядом с `shutdown_ready_delay_sec`:

```python
    request_timeout_sec: float = float(
        os.getenv("REQUEST_TIMEOUT_SEC", "30")
    )
```

Дефолт 30 сек — покрывает типичный qwen2.5:7b на CPU с retry'ями, но
не даёт висеть 3+ минуты в худшем случае.

---

## 2. `monitoring/prometheus.py`

В `__all__`:
```python
    "REQUEST_TIMEOUTS",
    "record_request_timeout",
```

В `except ImportError`:
```python
    REQUEST_TIMEOUTS = _NoopMetric()
```

В `else`:
```python
    REQUEST_TIMEOUTS = Counter(
        "rag_request_timeouts_total",
        "Requests exceeding REQUEST_TIMEOUT_SEC wall-time",
        ["endpoint"],
        registry=REGISTRY,
    )
```

Helper:
```python
def record_request_timeout(endpoint: str) -> None:
    REQUEST_TIMEOUTS.labels(endpoint=endpoint).inc()
```

---

## 3. `api/app.py::ask` — ключевая правка

было (упрощённо, см. строка 642):
```python
if hasattr(session, "ask"):
    try:
        result = session.ask(question, trace_id=get_request_id())
        # ... собираем response ...
    except Exception as exc:
        logger.error("Pipeline error in /ask: %s", exc, exc_info=True)
        # ... fallback на human route ...
```

стало:
```python
if hasattr(session, "ask"):
    settings = get_settings()
    timeout = getattr(settings, "request_timeout_sec", 30.0)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(session.ask, question, get_request_id()),
            timeout=timeout,
        )
        # ... собираем response (как раньше) ...
    except asyncio.TimeoutError:
        try:
            from monitoring.prometheus import record_request_timeout
            record_request_timeout("/api/ask")
        except Exception:
            pass
        logger.warning(
            "req_id=%s /api/ask exceeded timeout=%.1fs",
            get_request_id() or "-",
            timeout,
        )
        # Аккуратный 504 — клиенту ясно, что это timeout, а не внутренняя ошибка
        raise HTTPException(
            status_code=504,
            detail=f"Request exceeded {timeout:.0f}s wall-time limit",
        )
    except Exception as exc:
        logger.error("Pipeline error in /ask: %s", exc, exc_info=True)
        # ... существующий fallback на human route ...
```

**Тонкости:**
- `session.ask` принимает `trace_id` как keyword. `asyncio.to_thread`
  принимает `*args, **kwargs`: если вызов именованный — нужно
  `asyncio.to_thread(lambda: session.ask(question, trace_id=get_request_id()))`
  или передать позиционно. В task-79 fixup `ask(question, trace_id=...)` —
  позиционный вариант работает.
- `get_request_id()` **должен** зваться **до** `to_thread`, потому что
  ContextVar — async-local. В thread pool ContextVar не пробрасывается.
  Поэтому в spec выше: `get_request_id()` вычисляется в async-scope,
  передаётся позиционным аргументом в sync-функцию.
- `HTTPException(504)` — FastAPI сам отрендерит JSON `{"detail": "..."}`.
  Request-middleware `_log_requests` запишет строку с req_id=...
  автоматически.

---

## 4. `.env.example` + `README.md`

`.env.example`:
```
# Wall-time лимит на один /api/ask (сек). Превышение → 504.
REQUEST_TIMEOUT_SEC=30
```

`README.md` таблица env vars:
```
| `REQUEST_TIMEOUT_SEC` | `30` | total wall-time limit для /api/ask; 504 при превышении |
```

---

## 5. `/api/ask/stream` (опционально, не обязательно)

SSE-стрим имеет другую природу: клиент может отменить соединение,
и сервер видит это через `await request.is_disconnected()`. Полный
timeout для стрима сломает UX (первый токен через 2с, полный ответ
через 40с — не таймаутить). Пропускаем в этой задаче. Если потребуется,
отдельная задача с heartbeat-пингами.

---

## 6. `tests/test_request_timeout.py`

```python
"""Тесты request-level timeout + thread-offload."""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi.testclient import TestClient


def test_normal_request_passes(mock_pipeline, client: TestClient) -> None:
    """Обычный быстрый вызов не таймаутится."""
    resp = client.post("/api/ask", json={"question": "быстрый вопрос"})
    assert resp.status_code == 200
    assert resp.json()["route"] in ("auto", "human")


def test_slow_pipeline_returns_504(monkeypatch, client: TestClient) -> None:
    """Если session.ask висит дольше timeout'а — 504."""
    # Устанавливаем жёсткий timeout 0.5с
    import config.settings as _s
    monkeypatch.setenv("REQUEST_TIMEOUT_SEC", "0.5")
    _s._settings = None

    # Подменяем pipeline на зависающий
    def _slow_ask(question: str, trace_id=None):
        time.sleep(2.0)  # дольше timeout'а
        return {"answer": "never", "quality_score": 99, "route": "auto"}

    class FakeSession:
        ask = staticmethod(_slow_ask)
        _history: list = []

    monkeypatch.setattr(
        "api.app._get_or_create_session",
        lambda sid: ("test-sid", FakeSession()),
    )

    resp = client.post("/api/ask", json={"question": "медленный вопрос"})
    assert resp.status_code == 504
    assert "30" in resp.json()["detail"] or "0" in resp.json()["detail"]  # timeout value


def test_timeout_counter_increments(monkeypatch, client: TestClient) -> None:
    """504 инкрементит rag_request_timeouts_total."""
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, REQUEST_TIMEOUTS
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    def _get_val(endpoint: str) -> float:
        for m in REQUEST_TIMEOUTS.collect():
            for s in m.samples:
                if s.labels.get("endpoint") == endpoint and s.name.endswith("_total"):
                    return s.value
        return 0.0

    before = _get_val("/api/ask")

    import config.settings as _s
    monkeypatch.setenv("REQUEST_TIMEOUT_SEC", "0.3")
    _s._settings = None

    def _slow_ask(question: str, trace_id=None):
        time.sleep(1.0)
        return {"answer": "x"}

    class FakeSession:
        ask = staticmethod(_slow_ask)
        _history: list = []

    monkeypatch.setattr(
        "api.app._get_or_create_session",
        lambda sid: ("sid", FakeSession()),
    )

    resp = client.post("/api/ask", json={"question": "timeout"})
    assert resp.status_code == 504
    after = _get_val("/api/ask")
    assert after > before, f"counter not incremented: before={before}, after={after}"


def test_event_loop_not_blocked_during_pipeline(monkeypatch, client: TestClient) -> None:
    """Синхронный pipeline должен идти через asyncio.to_thread — event loop жив."""
    # Мокаем session.ask на 0.4с sync sleep
    def _sync_ask(question: str, trace_id=None):
        time.sleep(0.4)
        return {"answer": "ok", "quality_score": 75, "route": "auto"}

    class FakeSession:
        ask = staticmethod(_sync_ask)
        _history: list = []

    monkeypatch.setattr(
        "api.app._get_or_create_session",
        lambda sid: ("sid", FakeSession()),
    )

    # Пока /api/ask идёт 0.4с, /api/health/live должен отвечать < 0.2с
    import threading

    results: dict = {}

    def _worker_ask():
        t0 = time.monotonic()
        r = client.post("/api/ask", json={"question": "q"})
        results["ask_status"] = r.status_code
        results["ask_time"] = time.monotonic() - t0

    def _worker_health():
        time.sleep(0.1)  # начать после /api/ask
        t0 = time.monotonic()
        r = client.get("/api/health/live")
        results["health_status"] = r.status_code
        results["health_time"] = time.monotonic() - t0

    t1 = threading.Thread(target=_worker_ask)
    t2 = threading.Thread(target=_worker_health)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["ask_status"] == 200
    assert results["health_status"] == 200
    # Критерий: health ответил быстрее, чем /api/ask завершился
    # (если event loop заблокирован — health ждал бы 0.3с+)
    assert results["health_time"] < 0.3, (
        f"event loop blocked: health took {results['health_time']:.2f}s"
    )
```

**Замечание:** тест `test_event_loop_not_blocked` проверяет сам факт
offload'а. Если `to_thread` не вставлен — тест упадёт.

TestClient под капотом использует `anyio`, который честно пускает
threadpool для sync-blocking кода только если обработчик — sync.
Для async-handler, который зовёт sync-код напрямую, threadpool НЕ
используется. Поэтому тест надёжно ловит отсутствие `to_thread`.

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **132+ passed** (128 было + 4 новых), 0 regressions.
- `ruff check .` — 0 errors.
- `get_request_id()` зовётся **до** `to_thread` — ContextVar не
  пробрасывается в thread pool.
- Только `/api/ask` (не streaming) — streaming отдельная задача.
- Существующий fallback на human-route при pipeline exception
  **сохраняется** — timeout и pipeline error обрабатываются раздельно.

## DONE WHEN
- [ ] `request_timeout_sec` в `Settings`, `.env.example`, README
- [ ] `api/app.py::ask` использует `asyncio.wait_for(asyncio.to_thread(session.ask, ...), timeout=...)`
- [ ] Timeout → 504 `{"detail": "..."}` + Prometheus counter + warning-log
      с `req_id=`
- [ ] `REQUEST_TIMEOUTS` counter и `record_request_timeout` в
      `monitoring/prometheus.py`
- [ ] Event loop не блокируется — тест `test_event_loop_not_blocked`
      проходит
- [ ] `tests/test_request_timeout.py` — 4 теста, все проходят
- [ ] `pytest tests/ -v` — 132+ passed
- [ ] `ruff check .` — 0 errors
