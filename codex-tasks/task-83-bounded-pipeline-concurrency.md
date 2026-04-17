# Task 83 — RESILIENCE: Bounded pipeline concurrency + inflight gauge

## Goal
Codex в конце task-82 прямо отметил лимит текущего фикса:
> «504 завершает HTTP-запрос и освобождает event loop, но уже запущенный
> sync `session.ask` в thread pool не прерывает.»

Это реальная проблема под нагрузкой:
- Python не даёт безопасно убить рабочий поток извне → thread,
  запущенный через `asyncio.to_thread`, крутится до естественного
  завершения, даже если HTTP-ответ 504 уже вернулся.
- Дефолтный `asyncio` threadpool — `min(32, cpu_count+4)` потоков.
  При CPU=4 это 8 потоков.
- Если 8 pipeline'ов «зависли на 5 минут» (Ollama тормозит), **новые
  `/api/ask` блокируются** на acquire слота в пуле. Клиенты видят
  не 504, а просто тишину → гораздо хуже UX.

## Решение
Bounded concurrency через `asyncio.Semaphore` + fail-fast 503 при
saturation + inflight gauge для наблюдаемости.

```
pre-acquire:
  если semaphore.acquire за 0.5с не взял слот → 503 "busy"
  иначе INFLIGHT.inc()
finally:
  INFLIGHT.dec(); semaphore.release()
```

Это **не перегружает** текущий thread pool (мы ограничиваем раньше,
на семафоре), делает `rag_inflight_pipelines` time-series'ом для
Grafana, и закрывает сценарий «504 вернул, но слот занят».

## Files to change
- `config/settings.py` — 2 новых env-флага
- `api/app.py::ask` — semaphore acquire/release вокруг `to_thread`
- `monitoring/prometheus.py` — gauge + counter + helpers
- `.env.example`, `README.md`

## Files to create
- `tests/test_pipeline_concurrency.py` — 4 теста

---

## 1. `config/settings.py`

Рядом с `request_timeout_sec`:

```python
    max_concurrent_pipelines: int = int(
        os.getenv("MAX_CONCURRENT_PIPELINES", "8")
    )
    pipeline_acquire_timeout_sec: float = float(
        os.getenv("PIPELINE_ACQUIRE_TIMEOUT_SEC", "0.5")
    )
```

**Дефолты:**
- `MAX_CONCURRENT_PIPELINES=8` — совпадает с дефолтным размером
  asyncio threadpool (min(32, cpu_count+4) @ 4 CPU = 8). Логика: семафор
  — upper bound, чтобы не упираться в сам пул.
- `PIPELINE_ACQUIRE_TIMEOUT_SEC=0.5` — 500 мс лучше, чем infinity:
  клиент быстро узнаёт о busy и может retry.

---

## 2. `monitoring/prometheus.py`

В `__all__`:
```python
    "INFLIGHT_PIPELINES",
    "PIPELINE_REJECTIONS",
    "record_pipeline_rejection",
```

В `except ImportError`:
```python
    INFLIGHT_PIPELINES = _NoopMetric()
    PIPELINE_REJECTIONS = _NoopMetric()
```

В `else`:
```python
    INFLIGHT_PIPELINES = Gauge(
        "rag_inflight_pipelines",
        "Number of /api/ask pipelines currently running",
        registry=REGISTRY,
    )

    PIPELINE_REJECTIONS = Counter(
        "rag_pipeline_rejections_total",
        "Requests rejected due to pipeline saturation",
        ["reason"],
        registry=REGISTRY,
    )
```

Helper:
```python
def record_pipeline_rejection(reason: str) -> None:
    """reason ∈ {busy}. Сейчас единственный — саъturation."""
    PIPELINE_REJECTIONS.labels(reason=reason).inc()
```

`INFLIGHT_PIPELINES` используется напрямую через `.inc()` / `.dec()` —
без helper'а, чтобы избежать лишней обёртки вокруг gauge.

---

## 3. `api/app.py::ask`

Создать module-level семафор **лениво** (не в module-level — иначе
привязка к случайному event loop'у при импорте):

```python
_pipeline_semaphore: asyncio.Semaphore | None = None


def _get_pipeline_semaphore() -> asyncio.Semaphore:
    """Ленивое создание семафора в текущем event loop'е.

    Вызывается **только** из async-context. Повторные вызовы в том же
    loop'е возвращают тот же объект.
    """
    global _pipeline_semaphore
    if _pipeline_semaphore is None:
        settings = get_settings()
        size = getattr(settings, "max_concurrent_pipelines", 8)
        _pipeline_semaphore = asyncio.Semaphore(size)
    return _pipeline_semaphore
```

**Reset между тестами:** в `conftest.py` уже есть autouse `_reset_settings`.
Добавить рядом или в том же fixture:

```python
# в conftest.py, в _reset_settings (или в отдельной fixture)
import api.app as _app
_app._pipeline_semaphore = None
```

Иначе семафор из прошлого теста привяжется к закрытому loop'у и тесты
упадут с `RuntimeError: Event loop is closed`.

---

Правка `ask()` (после task-82 правки):

было:
```python
if hasattr(session, "ask"):
    settings = get_settings()
    timeout = getattr(settings, "request_timeout_sec", 30.0)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(session.ask, question, get_request_id()),
            timeout=timeout,
        )
        # ... response ...
    except asyncio.TimeoutError:
        # ... 504 ...
```

стало:
```python
if hasattr(session, "ask"):
    from monitoring.prometheus import INFLIGHT_PIPELINES, record_pipeline_rejection
    settings = get_settings()
    timeout = getattr(settings, "request_timeout_sec", 30.0)
    acquire_timeout = getattr(settings, "pipeline_acquire_timeout_sec", 0.5)

    semaphore = _get_pipeline_semaphore()
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=acquire_timeout)
    except asyncio.TimeoutError:
        try:
            record_pipeline_rejection("busy")
        except Exception:
            pass
        logger.warning(
            "req_id=%s /api/ask rejected: pipeline pool saturated",
            get_request_id() or "-",
        )
        raise HTTPException(
            status_code=503,
            detail="Server is busy processing other requests — retry in a moment",
        )

    try:
        INFLIGHT_PIPELINES.inc()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(session.ask, question, get_request_id()),
                timeout=timeout,
            )
            # ... собираем response (как раньше) ...
        except asyncio.TimeoutError:
            # ... существующий 504 ...
        # ... существующий pipeline-error fallback на human route ...
    finally:
        try:
            INFLIGHT_PIPELINES.dec()
        except Exception:
            pass
        semaphore.release()
```

**Инварианты:**
- `semaphore.release()` **всегда** зовётся после успешного `acquire()`,
  даже при 504 или exception'е в pipeline. Это гарантируется `finally`.
- `INFLIGHT_PIPELINES.dec()` — тоже в `finally`, симметрично `.inc()`.
- 503 (saturation) ≠ 504 (wall-time). Разные коды — разные сценарии.

---

## 4. `.env.example`

```
# Максимум одновременно работающих pipeline'ов в /api/ask
MAX_CONCURRENT_PIPELINES=8
# Сколько ждать слот перед 503 (сек)
PIPELINE_ACQUIRE_TIMEOUT_SEC=0.5
```

## 5. `README.md`

В таблицу env vars:
```
| `MAX_CONCURRENT_PIPELINES` | `8` | upper bound на concurrent /api/ask; 503 при saturation |
| `PIPELINE_ACQUIRE_TIMEOUT_SEC` | `0.5` | время ожидания слота до 503 |
```

---

## 6. `tests/test_pipeline_concurrency.py`

```python
"""Тесты bounded concurrency для /api/ask."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient


def _fake_slow_session_factory(sleep_sec: float):
    def _slow_ask(question: str, trace_id=None):
        time.sleep(sleep_sec)
        return {"answer": "ok", "quality_score": 75, "route": "auto"}

    class FakeSession:
        ask = staticmethod(_slow_ask)
        _history: list = []

    return FakeSession


def test_saturated_pool_returns_503(monkeypatch, client: TestClient) -> None:
    """При MAX_CONCURRENT_PIPELINES=1 второй запрос во время первого → 503."""
    import config.settings as _s
    monkeypatch.setenv("MAX_CONCURRENT_PIPELINES", "1")
    monkeypatch.setenv("PIPELINE_ACQUIRE_TIMEOUT_SEC", "0.2")
    _s._settings = None

    import api.app as _app
    _app._pipeline_semaphore = None

    FakeSession = _fake_slow_session_factory(0.8)
    monkeypatch.setattr(
        "api.app._get_or_create_session",
        lambda sid: ("sid", FakeSession()),
    )

    statuses: list[int] = []

    def _worker():
        r = client.post("/api/ask", json={"question": "q"})
        statuses.append(r.status_code)

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    time.sleep(0.05)  # дать первому взять слот
    t2.start()
    t1.join()
    t2.join()

    # один успешный, один 503
    assert 200 in statuses
    assert 503 in statuses
    assert statuses.count(503) == 1


def test_rejection_counter_increments(monkeypatch, client: TestClient) -> None:
    from monitoring.prometheus import PIPELINE_REJECTIONS, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    def _val() -> float:
        for m in PIPELINE_REJECTIONS.collect():
            for s in m.samples:
                if s.labels.get("reason") == "busy" and s.name.endswith("_total"):
                    return s.value
        return 0.0

    before = _val()

    import config.settings as _s
    monkeypatch.setenv("MAX_CONCURRENT_PIPELINES", "1")
    monkeypatch.setenv("PIPELINE_ACQUIRE_TIMEOUT_SEC", "0.1")
    _s._settings = None

    import api.app as _app
    _app._pipeline_semaphore = None

    FakeSession = _fake_slow_session_factory(0.5)
    monkeypatch.setattr(
        "api.app._get_or_create_session",
        lambda sid: ("sid", FakeSession()),
    )

    def _worker():
        client.post("/api/ask", json={"question": "q"})

    threads = [threading.Thread(target=_worker) for _ in range(3)]
    for t in threads: t.start()
    # дать первому взять слот
    time.sleep(0.03)
    # к этому моменту два из трёх должны получить 503
    for t in threads: t.join()

    assert _val() > before


def test_inflight_gauge_decrements_after_success(
    monkeypatch, client: TestClient
) -> None:
    from monitoring.prometheus import INFLIGHT_PIPELINES, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    def _gauge() -> float:
        for m in INFLIGHT_PIPELINES.collect():
            for s in m.samples:
                if s.name == "rag_inflight_pipelines":
                    return s.value
        return 0.0

    # До запроса gauge = 0
    assert _gauge() == 0.0

    FakeSession = _fake_slow_session_factory(0.1)
    monkeypatch.setattr(
        "api.app._get_or_create_session",
        lambda sid: ("sid", FakeSession()),
    )

    resp = client.post("/api/ask", json={"question": "q"})
    assert resp.status_code == 200

    # После запроса gauge снова 0
    assert _gauge() == 0.0


def test_inflight_gauge_decrements_after_timeout(
    monkeypatch, client: TestClient
) -> None:
    """504 должен тоже декрементить gauge (через finally)."""
    from monitoring.prometheus import INFLIGHT_PIPELINES, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    def _gauge() -> float:
        for m in INFLIGHT_PIPELINES.collect():
            for s in m.samples:
                if s.name == "rag_inflight_pipelines":
                    return s.value
        return 0.0

    import config.settings as _s
    monkeypatch.setenv("REQUEST_TIMEOUT_SEC", "0.3")
    _s._settings = None

    import api.app as _app
    _app._pipeline_semaphore = None

    FakeSession = _fake_slow_session_factory(1.0)
    monkeypatch.setattr(
        "api.app._get_or_create_session",
        lambda sid: ("sid", FakeSession()),
    )

    resp = client.post("/api/ask", json={"question": "q"})
    assert resp.status_code == 504

    # После 504 gauge должен обнулиться
    assert _gauge() == 0.0
```

**Важно:** `_app._pipeline_semaphore = None` обязательно перед каждым
тестом, где меняется `MAX_CONCURRENT_PIPELINES`. Иначе семафор из
предыдущего теста переиспользуется с другим size'ом.

Если `conftest.py` добавит автоматический reset — эти строки можно убрать.

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **136+ passed** (132 было + 4 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Семафор создаётся **лениво** в async-context, **сбрасывается**
  между тестами (conftest или явно).
- `semaphore.release()` и `INFLIGHT_PIPELINES.dec()` **всегда** в
  `finally` — никаких leak'ов.
- 503 (busy) и 504 (timeout) — разные семантики, не смешивать.
- Существующий 504 handling из task-82 сохраняется **внутри** успешного
  acquire'а.

## DONE WHEN
- [ ] `max_concurrent_pipelines` и `pipeline_acquire_timeout_sec` в Settings
- [ ] Env vars в `.env.example` и README
- [ ] Lazy-init семафора `_get_pipeline_semaphore()` в `api/app.py`
- [ ] `ask()` обрамляет pipeline в acquire/release; 503 при saturation
- [ ] `INFLIGHT_PIPELINES` gauge инкрементится/декрементится корректно
      включая путь через 504 и pipeline-error fallback
- [ ] `PIPELINE_REJECTIONS{reason="busy"}` инкрементится при 503
- [ ] conftest или fixture сбрасывает `_pipeline_semaphore` между тестами
- [ ] `tests/test_pipeline_concurrency.py` — 4 теста, все проходят
- [ ] `pytest tests/ -v` — 136+ passed
- [ ] `ruff check .` — 0 errors
