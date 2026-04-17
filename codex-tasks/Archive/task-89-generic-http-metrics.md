# Task 89 — OBSERVABILITY: Generic HTTP metrics (method × endpoint × status)

## Goal
Сейчас `REQUEST_COUNT` и `REQUEST_DURATION` инкрементятся только в `ask`
handler'е (`api/app.py:842-845`):

```python
prometheus_metrics.REQUEST_DURATION.observe(duration)
prometheus_metrics.REQUEST_COUNT.labels(route=response.route).inc()
```

Label `route` = auto/human/retry/error — это **бизнес-семантика** `/api/ask`.
Полезная, оставляем как есть.

Но для остальных endpoint'ов (`/api/upload`, `/api/feedback`, `/api/sessions/*`,
`/api/auth/*`, `/api/admin/*`) нет **никакой** HTTP-метрики. Последствия:
- Нельзя алертиться на «спайк 500 на /api/upload»
- Нельзя сравнить RPS `/api/feedback` vs `/api/ask`
- SLO-графики невозможны без базового `{method, endpoint, status}`
  counter'а — это стандарт индустрии (starlette-prometheus, fastapi-prom,
  RED method).

**Решение:** универсальный middleware `_http_metrics`, который считает
**все** HTTP-запросы через существующую пару counter+histogram с разумными
label'ами.

## Ключевая деталь — cardinality
Если label `endpoint` = `request.url.path`, то для `/api/sessions/{id}/history`
получим 10000+ уникальных label-комбинаций при росте трафика. Это съест
память Prometheus и сломает все запросы.

**Правильный подход:** `request.scope["route"].path_format` — FastAPI route
template (`/api/sessions/{session_id}/history`), а не развёрнутый path.
Fall back на `"unknown"` для 404/middleware'd путей — чтобы не взрывать
cardinality от сканеров, пробующих `/wp-admin/login.php`.

## Files to change
- `monitoring/prometheus.py` — 2 новые метрики + helper
- `api/app.py` — новый middleware `_http_metrics`
- `monitoring/alert_rules.yml` — alert на 5xx rate

## Files to create
- `tests/test_http_metrics.py` — 5 тестов

---

## 1. `monitoring/prometheus.py`

В `__all__`:
```python
    "HTTP_REQUESTS",
    "HTTP_REQUEST_DURATION",
    "record_http_request",
```

В `except ImportError`:
```python
    HTTP_REQUESTS = _NoopMetric()
    HTTP_REQUEST_DURATION = _NoopMetric()
```

В `else`:
```python
    HTTP_REQUESTS = Counter(
        "rag_http_requests_total",
        "HTTP requests by method, endpoint, status (all routes, not just /api/ask)",
        ["method", "endpoint", "status"],
        registry=REGISTRY,
    )
    HTTP_REQUEST_DURATION = Histogram(
        "rag_http_request_duration_seconds",
        "HTTP request duration by method and endpoint",
        ["method", "endpoint"],
        buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
        registry=REGISTRY,
    )
```

Helper:
```python
def record_http_request(method: str, endpoint: str, status: int, duration_sec: float) -> None:
    """Один HTTP-запрос → обновить оба метрика.

    `endpoint` должен быть route template (`/api/sessions/{id}/history`),
    а НЕ реальный path, иначе cardinality взорвётся.
    """
    HTTP_REQUESTS.labels(
        method=method, endpoint=endpoint, status=str(status)
    ).inc()
    HTTP_REQUEST_DURATION.labels(
        method=method, endpoint=endpoint
    ).observe(duration_sec)
```

**Выбор бакетов для histogram:** 10ms..30s — покрывает быстрые (health-probes)
и медленные (`/api/ask` с retry) endpoint'ы одновременно. Не увеличивай
без необходимости — каждый bucket = ещё одна time-series.

---

## 2. `api/app.py` — middleware `_http_metrics`

Расположить **после** `_log_requests` (т.е. **раньше** по порядку вызова),
чтобы observability уложилась до любой возможной ошибки в других
middleware'ах.

```python
@app.middleware("http")
async def _http_metrics(request: Request, call_next: Any) -> Any:
    import time as _time

    t0 = _time.monotonic()
    try:
        response = await call_next(request)
        status = response.status_code
    except Exception:
        # Неперехваченный exception — считаем как 500 в метрике, но
        # исключение пробрасываем дальше, чтобы не съесть ошибку.
        try:
            endpoint = _extract_route_template(request)
            from monitoring.prometheus import record_http_request
            record_http_request(
                request.method, endpoint, 500, _time.monotonic() - t0
            )
        except Exception:
            pass
        raise

    try:
        endpoint = _extract_route_template(request)
        from monitoring.prometheus import record_http_request
        record_http_request(
            request.method,
            endpoint,
            status,
            _time.monotonic() - t0,
        )
    except Exception:
        pass  # observability не ломает ответ

    return response


def _extract_route_template(request: Request) -> str:
    """Route template (`/api/sessions/{id}`) вместо реального path.

    Fall back на 'unknown' для 404 и middleware'd запросов, чтобы
    cardinality метрики не взорвалась от скан-трафика.
    """
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return route.path
    return "unknown"
```

**Замечание:** `request.scope["route"]` устанавливается Starlette **после**
матчинга роута. Middleware в FastAPI отрабатывают в следующем порядке:
`request → middleware stack → routing → handler → response ← middleware stack`.
К моменту вызова `record_http_request` на выходном пути route уже есть.
Для exception-пути (не дошли до handler'а) `scope["route"]` может быть
None → fall back на "unknown".

---

## 3. `monitoring/alert_rules.yml`

Добавить в группу `rag-latency`:

```yaml
      - alert: High5xxErrorRate
        expr: |
          sum(rate(rag_http_requests_total{status=~"5.."}[5m]))
          / sum(rate(rag_http_requests_total[5m]))
          > 0.05
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "5xx error rate >5% over 10min"
          description: |
            More than 5% of HTTP responses are 5xx server errors. Check
            application logs for unhandled exceptions and the recent
            deploys. Correlate with rag_circuit_breaker_state and
            rag_component_up.
```

---

## 4. `tests/test_http_metrics.py`

```python
"""Тесты universal HTTP metrics middleware."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _counter_sum(endpoint_filter: str | None = None) -> float:
    from monitoring.prometheus import HTTP_REQUESTS, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        return 0.0
    total = 0.0
    for m in HTTP_REQUESTS.collect():
        for s in m.samples:
            if not s.name.endswith("_total"):
                continue
            if endpoint_filter and s.labels.get("endpoint") != endpoint_filter:
                continue
            total += s.value
    return total


def test_counter_increments_on_any_endpoint(client: TestClient) -> None:
    from monitoring.prometheus import PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    before = _counter_sum("/api/health/live")
    client.get("/api/health/live")
    after = _counter_sum("/api/health/live")
    assert after > before


def test_labels_include_method_and_status(client: TestClient) -> None:
    from monitoring.prometheus import HTTP_REQUESTS, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    client.get("/api/health/live")
    # Ищем конкретный label-комбо
    found = False
    for m in HTTP_REQUESTS.collect():
        for s in m.samples:
            if (
                s.name.endswith("_total")
                and s.labels.get("method") == "GET"
                and s.labels.get("endpoint") == "/api/health/live"
                and s.labels.get("status") == "200"
            ):
                found = True
                break
    assert found, "GET /api/health/live -> 200 не попал в метрики"


def test_endpoint_uses_route_template_not_actual_path(client: TestClient) -> None:
    """Для /api/sessions/{session_id}/history label должен быть template."""
    from monitoring.prometheus import HTTP_REQUESTS, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    # Session history endpoint требует session_id path-parameter.
    # Пробуем несуществующий — endpoint должен либо вернуть 404, либо
    # отработать normal path, но в метриках endpoint = template.
    resp = client.get("/api/sessions/random-id-42/history")
    # что бы ни вернулось (200/404), метрика должна быть по template
    _ = resp.status_code

    seen_endpoints: set[str] = set()
    for m in HTTP_REQUESTS.collect():
        for s in m.samples:
            if s.name.endswith("_total"):
                ep = s.labels.get("endpoint", "")
                if "sessions" in ep:
                    seen_endpoints.add(ep)

    # «random-id-42» НЕ должен появиться ни в одном label'е
    for ep in seen_endpoints:
        assert "random-id-42" not in ep, (
            f"реальный path попал в label: {ep} (cardinality leak)"
        )


def test_unknown_route_labeled_unknown(client: TestClient) -> None:
    from monitoring.prometheus import HTTP_REQUESTS, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    # Scan-like запрос на несуществующий путь
    resp = client.get("/wp-admin/login.php")
    assert resp.status_code == 404

    # endpoint должен быть "unknown", не "/wp-admin/login.php"
    for m in HTTP_REQUESTS.collect():
        for s in m.samples:
            if s.name.endswith("_total"):
                ep = s.labels.get("endpoint", "")
                assert "wp-admin" not in ep, (
                    f"scan-трафик попал в label: {ep}"
                )


def test_duration_histogram_observed(client: TestClient) -> None:
    from monitoring.prometheus import HTTP_REQUEST_DURATION, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    client.get("/api/health/live")

    # Histogram expose _count и _sum
    found_count = False
    for m in HTTP_REQUEST_DURATION.collect():
        for s in m.samples:
            if (
                s.name.endswith("_count")
                and s.labels.get("endpoint") == "/api/health/live"
                and s.value > 0
            ):
                found_count = True
                break
    assert found_count, "histogram count не инкрементировался"
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **166+ passed** (161 было + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Cardinality: label `endpoint` = route template, не реальный path.
  Это проверяется `test_endpoint_uses_route_template_not_actual_path`
  и `test_unknown_route_labeled_unknown`.
- Exception из prometheus не ломает ответ.
- Unhandled exception в handler → считаем как status=500 в метрике,
  пробрасываем дальше.
- Alert rule новой метрики должен пройти `test_alert_rules.py` проверки
  (метрика объявлена в prometheus.py).

## DONE WHEN
- [ ] `HTTP_REQUESTS` counter (method × endpoint × status) и
      `HTTP_REQUEST_DURATION` histogram (method × endpoint) экспортированы
- [ ] `record_http_request(method, endpoint, status, duration)` helper
- [ ] Middleware `_http_metrics` считает все запросы; endpoint = route template
- [ ] Unknown path → label `endpoint="unknown"` (защита от cardinality leak)
- [ ] Alert `High5xxErrorRate` в `monitoring/alert_rules.yml`
- [ ] `tests/test_http_metrics.py` — 5 тестов, все проходят
- [ ] `pytest tests/ -v` — 166+ passed
- [ ] `ruff check .` — 0 errors
