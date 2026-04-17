# Task 76 — OBSERVABILITY: Prometheus gauge для состояния компонентов из /api/health

## Goal
task-75 привела Postgres и Redis в `/api/health`. Но **Prometheus про них
ничего не знает** — мониторинг зависит от того, вызовет ли кто-то
`/api/health`. Alertmanager и Grafana читают Prometheus, а не health-endpoint.

Сценарии, которые сейчас не закрыты:
- Postgres упал в 3:00, k8s readiness-probe дёргает `/api/health` → пишет
  `status=degraded`. Но это в **ответе endpoint'а**, а не в метриках.
  Alertmanager молчит до тех пор, пока кто-то не добавит blackbox-exporter
  на `/api/health`.
- Нет истории доступности — нельзя построить SLO graph «uptime Postgres
  за 30 дней», потому что нет time-series.

Нужен один общий gauge `rag_component_up{component}` (1=ok, 0=error),
который обновляется на каждом `/api/health`. Поскольку k8s readiness
дёргает health каждые 10с, Prometheus scrape каждые 15-30с гарантированно
будет получать свежие значения.

**Семантика "unavailable" (драйвер не установлен):** gauge **не эмитится**.
Отсутствие gauge'а — «компонент не сконфигурирован», это не алерт. Alertmanager
использует `rag_component_up == 0 for 2m` — для намеренно выключенного
компонента алерта не будет.

## Files to change
- `monitoring/prometheus.py` — новый gauge + helper
- `api/app.py::health_check` — вызывать helper после сбора проб

## Files to create
- `tests/test_component_health_metrics.py` — 4 теста

---

## 1. `monitoring/prometheus.py`

В `__all__`:
```python
    "COMPONENT_UP",
    "record_component_health",
```

В блоке `except ImportError`:
```python
    COMPONENT_UP = _NoopMetric()
```

В `else`:
```python
    COMPONENT_UP = Gauge(
        "rag_component_up",
        "Health status of a dependency component: 1=ok, 0=error. "
        "Absent when the component is not configured/installed (unavailable).",
        ["component"],
        registry=REGISTRY,
    )
```

Helper:
```python
def record_component_health(component: str, status: str) -> None:
    """Обновить gauge для компонента.

    - status="ok"           → COMPONENT_UP{component}=1
    - status="error"        → COMPONENT_UP{component}=0
    - status="unavailable"  → НЕ эмитим (gauge остаётся отсутствующим)
    - иное                  → считаем error, ставим 0

    Именование компонента (ollama, chromadb, sqlite, postgres, redis) —
    должно совпадать с ключами components в HealthResponse.
    """
    if status == "unavailable":
        # Никаких .remove() здесь — лейбл просто не создаётся.
        # Если компонент перешёл из ok в unavailable между scrape'ами, gauge
        # «замрёт» на последнем значении до рестарта процесса. Это ОК —
        # unavailable в рантайме практически не случается (оно определяется
        # ImportError на старте, т.е. на всю жизнь процесса).
        return
    value = 1 if status == "ok" else 0
    COMPONENT_UP.labels(component=component).set(value)
```

---

## 2. `api/app.py::health_check`

После получения результатов всех проб добавить обновление метрик:

```python
    ollama_status, chroma_status, sqlite_status, postgres_status, redis_status = await asyncio.gather(
        _probe_ollama(settings.ollama_base_url),
        _probe_chromadb(settings.vectordb_chroma_dir),
        _probe_sqlite(settings.tracing_db_path),
        _probe_postgres(),
        _probe_redis(),
    )

    # NEW: обновить Prometheus gauge
    try:
        from monitoring.prometheus import record_component_health
        record_component_health("ollama", ollama_status.status)
        record_component_health("chromadb", chroma_status.status)
        record_component_health("sqlite", sqlite_status.status)
        record_component_health("postgres", postgres_status.status)
        record_component_health("redis", redis_status.status)
    except Exception:
        pass  # observability не должна ломать health-check

    # ... остальная логика overall/response без изменений ...
```

**Защитный `try/except Exception`** — симметрично тому, как это сделано в
task-72 для breaker-хука: если prometheus_client внезапно упал, health
продолжает отвечать.

---

## 3. `tests/test_component_health_metrics.py`

```python
"""Тесты для Prometheus gauge rag_component_up."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _get_gauge_value(component: str) -> float | None:
    """Прочитать текущее значение rag_component_up{component=...}."""
    from monitoring.prometheus import COMPONENT_UP, PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        return None
    # prometheus_client: collect() возвращает Iterable[Metric]
    for metric in COMPONENT_UP.collect():
        for sample in metric.samples:
            if sample.labels.get("component") == component:
                return sample.value
    return None


@pytest.fixture
def _mock_all_probes_ok(monkeypatch):
    from api.app import ComponentStatus

    async def _ok(*args, **kwargs):
        return ComponentStatus(status="ok", detail=None)

    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        monkeypatch.setattr(f"api.app._probe_{name}", _ok)


def test_record_component_health_sets_one_for_ok():
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, record_component_health

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    record_component_health("ollama", "ok")
    assert _get_gauge_value("ollama") == 1.0


def test_record_component_health_sets_zero_for_error():
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, record_component_health

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    record_component_health("postgres", "error")
    assert _get_gauge_value("postgres") == 0.0


def test_record_component_health_skips_unavailable():
    from monitoring.prometheus import PROMETHEUS_AVAILABLE, record_component_health

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    # эксклюзивное имя, чтобы не пересекаться с другими тестами
    record_component_health("new_unavailable_component", "unavailable")
    assert _get_gauge_value("new_unavailable_component") is None


def test_health_endpoint_updates_component_gauges(
    client: TestClient, _mock_all_probes_ok
):
    from monitoring.prometheus import PROMETHEUS_AVAILABLE

    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    resp = client.get("/api/health")
    assert resp.status_code == 200

    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        assert _get_gauge_value(name) == 1.0, f"{name} gauge not updated"
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **110+ passed** (106 было + 4 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Gauge не эмитится для `status="unavailable"` — критично для Alertmanager
  семантики (absent != alert).
- Помимо ожидаемого: задача тривиально расширяется под добавление
  `rag_circuit_breaker_state` в `/api/metrics` сопутствующих dashboards,
  но это вне scope этой задачи.
- Существующие тесты health/metrics должны продолжать проходить.

## DONE WHEN
- [ ] `monitoring/prometheus.py` экспортирует `COMPONENT_UP` и
      `record_component_health`
- [ ] `health_check()` вызывает `record_component_health` для всех 5
      компонент после `asyncio.gather`
- [ ] При `status="ok"` gauge=1, при `status="error"` gauge=0, при
      `status="unavailable"` gauge не создаётся
- [ ] Исключение в prometheus-хуке не ломает health-check
- [ ] `tests/test_component_health_metrics.py` — 4 теста, все проходят
- [ ] `pytest tests/ -v` — 110+ passed
- [ ] `ruff check .` — 0 errors
- [ ] Ручная проверка: `curl /api/health` → `curl /api/metrics | grep
      rag_component_up` показывает 5 строк (по одной на компонент)
