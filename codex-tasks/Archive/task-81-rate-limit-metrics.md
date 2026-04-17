# Task 81 — OBSERVABILITY: Prometheus-счётчик для rate-limit rejections

## Goal
`slowapi` стоит на `/api/ask` (60/min) и `/api/upload` (10/min). Если кто-то
долбится в rate-limit — возвращаем 429. Но **мы это никак не считаем**:
- Нет метрики → невозможно построить alert «кто-то пробивает лимит 500
  раз за 10 минут» (DoS-probe, clicker-bot, bug в клиенте).
- Нет метрики → невозможно заметить, что настроенные лимиты реально
  несрабатывают на обычном трафике (= лимит слишком узкий).
- Весь остальной observability-стек task-72..78 ссылается на Prometheus,
  а эта дырка единственная нецелая.

Добавить один counter `rag_rate_limit_rejections_total{endpoint}` +
инкремент в handler'е.

Это самая маленькая observability-задача в текущем спринте, но она
замыкает цикл: сейчас у нас есть метрики на retry, breaker, health,
request duration, quality, feedback, escalation — и не было **одной**,
именно про ограничение трафика.

## Files to change
- `monitoring/prometheus.py` — counter + helper
- `api/app.py::_rate_limit_exceeded_handler` — инкремент при каждом 429

## Files to create
- `tests/test_rate_limit_metrics.py` — 3 теста

---

## 1. `monitoring/prometheus.py`

В `__all__`:
```python
    "RATE_LIMIT_REJECTIONS",
    "record_rate_limit_rejection",
```

В `except ImportError`:
```python
    RATE_LIMIT_REJECTIONS = _NoopMetric()
```

В `else`:
```python
    RATE_LIMIT_REJECTIONS = Counter(
        "rag_rate_limit_rejections_total",
        "Requests rejected by slowapi rate limiter",
        ["endpoint"],
        registry=REGISTRY,
    )
```

Helper:
```python
def record_rate_limit_rejection(endpoint: str) -> None:
    """Инкремент при 429. `endpoint` — request.url.path."""
    RATE_LIMIT_REJECTIONS.labels(endpoint=endpoint).inc()
```

---

## 2. `api/app.py`: хук в handler

Существующий handler (строка ~56):

было (примерно):
```python
    def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
        )
```

стало:
```python
    def _rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
        try:
            from monitoring.prometheus import record_rate_limit_rejection
            record_rate_limit_rejection(request.url.path)
        except Exception:
            pass  # observability не должна ломать 429
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded"},
        )
```

**Важно:** `try/except Exception` — симметрично breaker/retry хукам.
Falsy prometheus_client не должен ломать handler.

Если в проекте есть и **slowapi-импортированный** `_rate_limit_exceeded_handler`
(из `slowapi` directly), а не локальный — заменить регистрацию в
`app.add_exception_handler(RateLimitExceeded, ...)` на нашу обёртку:

```python
def _rate_limit_rejected(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    try:
        from monitoring.prometheus import record_rate_limit_rejection
        record_rate_limit_rejection(request.url.path)
    except Exception:
        pass
    # Делегируем в стандартный slowapi handler (или возвращаем 429 сами)
    from slowapi import _rate_limit_exceeded_handler as _slowapi_handler
    return _slowapi_handler(request, exc)

app.add_exception_handler(RateLimitExceeded, _rate_limit_rejected)
```

Выбрать вариант в зависимости от того, что сейчас в коде (локальный
stub или slowapi-импорт). Имена `_rate_limit_exceeded_handler` и
`_rate_limit_rejected` — на усмотрение.

---

## 3. `tests/test_rate_limit_metrics.py`

Переиспользуем существующий `test_rate_limiting.py`-подход: дёргаем
`/api/ask` пока не получим 429, проверяем counter.

```python
"""Тесты Prometheus-метрики для rate-limit rejections."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _get_counter_value(endpoint: str) -> float | None:
    from monitoring.prometheus import (
        PROMETHEUS_AVAILABLE,
        RATE_LIMIT_REJECTIONS,
    )
    if not PROMETHEUS_AVAILABLE:
        return None
    for metric in RATE_LIMIT_REJECTIONS.collect():
        for sample in metric.samples:
            if sample.labels.get("endpoint") == endpoint:
                # _total suffix добавляется автоматически prometheus_client
                if sample.name.endswith("_total"):
                    return sample.value
    return None


def test_rejection_counter_increments_on_429(
    mock_pipeline, client: TestClient
):
    from monitoring.prometheus import PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    before = _get_counter_value("/api/ask") or 0.0

    # Пробиваем 60/min дефолтный лимит
    last_status = None
    for _ in range(65):
        resp = client.post("/api/ask", json={"question": "что?"})
        last_status = resp.status_code
        if last_status == 429:
            break

    assert last_status == 429, "expected to hit 429 within 65 requests"

    after = _get_counter_value("/api/ask") or 0.0
    assert after > before, f"counter did not increment: before={before}, after={after}"


def test_counter_labeled_by_endpoint(mock_pipeline, client: TestClient):
    """Разные endpoints имеют разные counter'ы с разным label'ом."""
    from monitoring.prometheus import PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    # /api/ask label после предыдущего теста уже может быть > 0 — это ОК,
    # проверяем независимость через отсутствие /foo label
    assert _get_counter_value("/api/nonexistent-endpoint") in (None, 0.0)


def test_handler_does_not_crash_when_prometheus_unavailable(
    monkeypatch, mock_pipeline, client: TestClient
):
    """Если import prometheus упадёт — handler всё равно вернёт 429."""
    def _boom(endpoint):
        raise RuntimeError("prometheus dead")

    monkeypatch.setattr(
        "monitoring.prometheus.record_rate_limit_rejection", _boom
    )

    for _ in range(65):
        resp = client.post("/api/ask", json={"question": "тест"})
        if resp.status_code == 429:
            assert resp.json()["detail"] == "Rate limit exceeded" or "limit" in resp.json()["detail"].lower()
            return

    pytest.fail("never hit 429")
```

**Fixture `mock_pipeline`** — из `conftest.py` (task-65).

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **128+ passed** (125 было + 3 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Handler `try/except Exception` — observability не ломает 429.
- Label `endpoint` = `request.url.path` (без query string, без host).
  Если в будущем потребуется per-user label — отдельная задача.

## DONE WHEN
- [ ] `RATE_LIMIT_REJECTIONS` counter и `record_rate_limit_rejection`
      экспортируются из `monitoring/prometheus.py`
- [ ] 429-handler инкрементит counter с label'ом `endpoint`
- [ ] Исключение из prometheus-хука не ломает 429-response
- [ ] `tests/test_rate_limit_metrics.py` — 3 теста, все проходят
- [ ] `pytest tests/ -v` — 128+ passed
- [ ] `ruff check .` — 0 errors
- [ ] Ручная проверка: `curl /api/metrics | grep rag_rate_limit_rejections_total` —
      появляется строка после первого 429
