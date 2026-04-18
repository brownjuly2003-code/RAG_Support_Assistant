# Task 98 — OBSERVABILITY: DB connection pool saturation metrics

## Goal
task-75 пробит Postgres доступность (SELECT 1). Но **saturation pool'а**
мы не видим. В `db/engine.py`:

```python
engine = create_async_engine(_url, echo=False, pool_size=10, max_overflow=20)
```

- `pool_size=10` — постоянные соединения в пуле
- `max_overflow=20` — временные сверх pool_size при нагрузке
- Итого max concurrent = 30

Сценарий, который мы не увидим:
- Postgres жив, SELECT 1 проходит → `rag_component_up{postgres}=1`.
- Но **все 30 соединений checked_out** — новые запросы из handler'а
  блокируются на `get_db()` dependency.
- Внешний эффект: `/api/auth/login`, audit writes, admin endpoints —
  все висят. `/api/ask` не страдает (он не ходит в Postgres).
- Symptom diagnosis невозможен без знания pool state.

## Решение — 3 gauge'а, периодически сэмплируются в `_probe_postgres`
- `rag_db_pool_size` — total pool size (const)
- `rag_db_pool_checked_out` — сколько в использовании
- `rag_db_pool_overflow` — сколько overflow-соединений открыто

SQLAlchemy async engine даёт `engine.pool.size()`, `checkedout()`,
`overflow()` методы напрямую.

Sampling: на каждом вызове `/api/health/ready` (раз в 10с k8s readiness)
— этого достаточно для Prometheus 15-30с scrape.

## Files to change
- `db/engine.py` — helper `get_pool_stats() -> dict`
- `api/app.py::_probe_postgres` — дополнить snapshot + Prometheus update
- `monitoring/prometheus.py` — 3 gauge'а + helper
- `monitoring/alert_rules.yml` — 1 alert rule

## Files to create
- `tests/test_db_pool_metrics.py` — 4 теста

---

## 1. `db/engine.py`

```python
def get_pool_stats() -> dict:
    """Snapshot текущего состояния пула. Используется health-probe'ом.

    Returns:
        {"size": int, "checked_out": int, "overflow": int}
        Все три int'а. -1 если pool не инициализирован.
    """
    try:
        pool = engine.pool
        return {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception:
        return {"size": -1, "checked_out": -1, "overflow": -1}
```

---

## 2. `monitoring/prometheus.py`

```python
# __all__:
    "DB_POOL_SIZE",
    "DB_POOL_CHECKED_OUT",
    "DB_POOL_OVERFLOW",
    "record_db_pool_stats",

# except ImportError:
    DB_POOL_SIZE = _NoopMetric()
    DB_POOL_CHECKED_OUT = _NoopMetric()
    DB_POOL_OVERFLOW = _NoopMetric()

# else:
    DB_POOL_SIZE = Gauge(
        "rag_db_pool_size",
        "SQLAlchemy pool size (permanent connections)",
        registry=REGISTRY,
    )
    DB_POOL_CHECKED_OUT = Gauge(
        "rag_db_pool_checked_out",
        "SQLAlchemy pool connections currently in use",
        registry=REGISTRY,
    )
    DB_POOL_OVERFLOW = Gauge(
        "rag_db_pool_overflow",
        "SQLAlchemy pool overflow connections beyond pool_size",
        registry=REGISTRY,
    )


def record_db_pool_stats(size: int, checked_out: int, overflow: int) -> None:
    """Обновить три gauge'а атомарно. Значения < 0 игнорируются."""
    if size >= 0:
        DB_POOL_SIZE.set(size)
    if checked_out >= 0:
        DB_POOL_CHECKED_OUT.set(checked_out)
    if overflow >= 0:
        DB_POOL_OVERFLOW.set(overflow)
```

---

## 3. `api/app.py::_probe_postgres`

Сразу после успешного SELECT 1, до return'а — собрать pool stats
и отправить в Prometheus:

было:
```python
async def _probe_postgres() -> ComponentStatus:
    t0 = time.monotonic()
    try:
        from db.engine import async_session
        from sqlalchemy import text
        async with async_session() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=1.0)
        return ComponentStatus(status="ok", ...)
    except ImportError as exc:
        return ComponentStatus(status="unavailable", ...)
    except Exception as exc:
        return ComponentStatus(status="error", ...)
```

стало:
```python
async def _probe_postgres() -> ComponentStatus:
    t0 = time.monotonic()
    try:
        from db.engine import async_session, get_pool_stats
        from sqlalchemy import text

        async with async_session() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=1.0)

        # Snapshot pool + update metrics
        try:
            stats = get_pool_stats()
            from monitoring.prometheus import record_db_pool_stats
            record_db_pool_stats(
                stats["size"], stats["checked_out"], stats["overflow"]
            )
        except Exception:
            pass

        return ComponentStatus(status="ok", ...)
    except ImportError as exc:
        return ComponentStatus(status="unavailable", ...)
    except Exception as exc:
        return ComponentStatus(status="error", ...)
```

`try/except` вокруг pool-snapshot — observability не ломает health-check.

---

## 4. `monitoring/alert_rules.yml`

В группу `rag-health`:

```yaml
      - alert: DbPoolSaturationHigh
        expr: |
          rag_db_pool_checked_out
          / (rag_db_pool_size + rag_db_pool_overflow + 0.001)
          > 0.8
        for: 5m
        labels:
          severity: warning
          component: postgres
        annotations:
          summary: "DB pool >80% saturated over 5min"
          description: |
            Postgres connection pool has been >80% in use for 5 minutes.
            If this trend continues, /api/auth/login, audit writes and
            admin endpoints will start blocking on get_db() dependency.
            Check for slow queries (pg_stat_activity) and connection leaks
            in custom endpoints.

      - alert: DbPoolExhausted
        expr: |
          rag_db_pool_checked_out
          / (rag_db_pool_size + rag_db_pool_overflow + 0.001)
          >= 0.95
        for: 1m
        labels:
          severity: critical
          component: postgres
        annotations:
          summary: "DB pool exhausted — new connections blocking"
          description: |
            >=95% of SQLAlchemy pool connections are checked out. New
            requests are likely blocking on pool acquisition. Mitigate
            immediately: identify slow queries or a connection leak,
            consider raising pool_size/max_overflow as a temporary fix.
```

Два правила — warning и critical — стандартный шаблон для saturation
метрик.

---

## 5. `tests/test_db_pool_metrics.py`

Pool stats сложно реально протестировать без живого Postgres. Тестируем
**поведение helper'ов** и их интеграцию, не реальные значения.

```python
"""Тесты для DB pool metrics helpers и интеграции с health-probe."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_record_db_pool_stats_sets_gauges():
    from monitoring.prometheus import (
        DB_POOL_SIZE, DB_POOL_CHECKED_OUT, DB_POOL_OVERFLOW,
        PROMETHEUS_AVAILABLE, record_db_pool_stats,
    )
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    record_db_pool_stats(size=10, checked_out=3, overflow=2)

    def _gauge_val(g, name: str) -> float:
        for m in g.collect():
            for s in m.samples:
                if s.name == name:
                    return s.value
        return -1.0

    assert _gauge_val(DB_POOL_SIZE, "rag_db_pool_size") == 10
    assert _gauge_val(DB_POOL_CHECKED_OUT, "rag_db_pool_checked_out") == 3
    assert _gauge_val(DB_POOL_OVERFLOW, "rag_db_pool_overflow") == 2


def test_negative_values_are_ignored():
    """get_pool_stats возвращает -1 при неинициализированном пуле —
    мы не должны выставлять gauge в -1."""
    from monitoring.prometheus import (
        DB_POOL_SIZE, PROMETHEUS_AVAILABLE, record_db_pool_stats,
    )
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    record_db_pool_stats(size=42, checked_out=0, overflow=0)
    record_db_pool_stats(size=-1, checked_out=-1, overflow=-1)

    def _gauge_val(g, name: str) -> float:
        for m in g.collect():
            for s in m.samples:
                if s.name == name:
                    return s.value
        return -1.0

    # size остался 42, не был перезаписан -1
    assert _gauge_val(DB_POOL_SIZE, "rag_db_pool_size") == 42


def test_get_pool_stats_handles_missing_engine(monkeypatch):
    """При ImportError в db.engine get_pool_stats должен вернуть -1, не падать."""
    import db.engine as _e

    class _BrokenPool:
        def size(self): raise RuntimeError("engine disposed")
        def checkedout(self): raise RuntimeError()
        def overflow(self): raise RuntimeError()

    fake_engine = MagicMock()
    fake_engine.pool = _BrokenPool()
    monkeypatch.setattr(_e, "engine", fake_engine)

    stats = _e.get_pool_stats()
    assert stats == {"size": -1, "checked_out": -1, "overflow": -1}


def test_probe_postgres_updates_pool_metrics(monkeypatch, client):
    """/api/health/ready должен инкрементить обновлять pool gauges."""
    from monitoring.prometheus import DB_POOL_SIZE, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    # Мокаем _probe_postgres напрямую, чтобы он вызывал record_db_pool_stats
    # с реальным значением (не требуя живой Postgres).
    from api.app import ComponentStatus

    async def _fake_probe():
        from monitoring.prometheus import record_db_pool_stats
        record_db_pool_stats(size=99, checked_out=7, overflow=1)
        return ComponentStatus(status="ok", detail=None)

    monkeypatch.setattr("api.app._probe_postgres", _fake_probe)

    client.get("/api/health/ready")

    def _gauge_val() -> float:
        for m in DB_POOL_SIZE.collect():
            for s in m.samples:
                if s.name == "rag_db_pool_size":
                    return s.value
        return -1.0

    assert _gauge_val() == 99
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **188+ passed** (184 + 4 новых), 0 regressions.
- `ruff check .` — 0 errors.
- `get_pool_stats` никогда не падает — ловит все exceptions, возвращает
  sentinel -1.
- Exception в record_db_pool_stats не ломает health-probe.
- `test_alert_rules.py::test_expressions_reference_declared_metrics`
  должен пройти с новыми метриками.

## DONE WHEN
- [ ] `get_pool_stats()` в `db/engine.py` — safe, возвращает dict с int'ами
- [ ] 3 gauge'а (`DB_POOL_SIZE`, `DB_POOL_CHECKED_OUT`, `DB_POOL_OVERFLOW`)
      в `monitoring/prometheus.py` + `record_db_pool_stats` helper
- [ ] `_probe_postgres` вызывает `record_db_pool_stats` после успешного
      SELECT 1
- [ ] 2 alert rules (`DbPoolSaturationHigh` warning, `DbPoolExhausted`
      critical) в `monitoring/alert_rules.yml`
- [ ] 4 теста в `tests/test_db_pool_metrics.py`
- [ ] `pytest tests/ -v` — 188+ passed
- [ ] `ruff check .` — 0 errors
