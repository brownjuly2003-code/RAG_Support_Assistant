# Task 75 — HEALTH: Пробы Postgres и Redis в /api/health

## Goal
`/api/health` пробит `ollama`, `chromadb`, `sqlite` — но после task-42/45
в проект приехали **Postgres** (auth, audit_log, persistent sessions) и
**Redis** (cache, с fallback на in-memory dict). Их **нет в health-check**.

Сценарии, которые мы сейчас не увидим:
- Postgres умер → `/api/auth/login` падает 500, audit-log перестаёт писаться
  в БД (fallback на file logger). `/api/health` возвращает **200 ok** —
  мониторинг молчит, хотя полсистемы на бок.
- Redis умер → cache полностью в in-memory dict (hit rate обвалится,
  эффективное кол-во работающих воркеров уменьшится). `/api/health`
  возвращает **200 ok**.

Добавить две пробы по существующему паттерну `_probe_*`.

**Семантика статусов (важно не раздуть 503):**
- `ollama` или `chromadb` down → **503 unhealthy** (основной read-path, без них RAG мёртв)
- `sqlite` down → 200 **degraded** (уже так)
- `postgres` down → 200 **degraded** (JWT login сломан, но `/api/ask` с API-key работает)
- `redis` down → 200 **degraded** (cache падает на fallback, сервис работает)

То есть Postgres и Redis **не** делают сервис 503 — это важно, чтобы
балансировщики/k8s не выкидывали pod из ротации из-за упавшего кеша.

## Files to change
- `api/app.py` — 2 новые probe-функции, 2 новых компонента в `HealthResponse`,
  обновление `health_check()`

## Files to create
- `tests/test_health_postgres_redis.py` — 4 теста

---

## 1. Probe-функции в `api/app.py`

Разместить рядом с существующими `_probe_ollama / _probe_chromadb / _probe_sqlite`
(строка ~448).

```python
async def _probe_postgres() -> ComponentStatus:
    """Проверить доступность Postgres через SELECT 1.

    Импортируем `db.engine` лениво — если в окружении `asyncpg`/`sqlalchemy`
    не установлены (dev без Docker), возвращаем `status="unavailable"`
    и не падаем.
    """
    try:
        from db.engine import async_session
        from sqlalchemy import text

        async with async_session() as db:
            await asyncio.wait_for(db.execute(text("SELECT 1")), timeout=1.0)
        return ComponentStatus(status="ok", detail=None)
    except ImportError as exc:
        return ComponentStatus(status="unavailable", detail=f"driver missing: {exc}")
    except Exception as exc:
        return ComponentStatus(status="error", detail=str(exc))


async def _probe_redis() -> ComponentStatus:
    """PING Redis. Fallback на in-memory dict — не ошибка, но помечаем как error."""
    try:
        import redis

        from config.settings import get_settings

        settings = get_settings()
        client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        # redis-py синхронный — оборачиваем в to_thread
        ok = await asyncio.wait_for(
            asyncio.to_thread(client.ping), timeout=1.5
        )
        if ok:
            return ComponentStatus(status="ok", detail=None)
        return ComponentStatus(status="error", detail="PING returned falsy")
    except ImportError as exc:
        return ComponentStatus(status="unavailable", detail=f"redis lib missing: {exc}")
    except Exception as exc:
        return ComponentStatus(status="error", detail=str(exc))
```

**Замечания:**
- `status="unavailable"` (новое значение!) — для сценариев, когда модуль
  не установлен. Не error — сервис умышленно запущен без БД/кеша
  (например, минимальный Dockerfile для CI).
- Timeout 1-1.5 сек — health-check не должен висеть. Если Postgres отвечает
  дольше секунды, это уже degraded.
- `asyncio.to_thread(client.ping)` — `redis-py` синхронный, чтобы не
  блокировать event loop.

Если в проекте уже определён тип `ComponentStatus` с литералом статусов,
расширить его значением `"unavailable"` (искать определение в `api/app.py`
рядом с `HealthResponse`).

---

## 2. Обновление `health_check()`

было:
```python
    ollama_status, chroma_status, sqlite_status = (
        await _probe_ollama(settings.ollama_base_url),
        await _probe_chromadb(settings.vectordb_chroma_dir),
        await _probe_sqlite(settings.tracing_db_path),
    )

    critical_down = ollama_status.status == "error" or chroma_status.status == "error"
    overall = "unhealthy" if critical_down else (
        "degraded" if sqlite_status.status == "error" else "ok"
    )

    response = HealthResponse(
        status=overall,
        components={
            "ollama": ollama_status,
            "chromadb": chroma_status,
            "sqlite": sqlite_status,
        },
        ...
    )
```

стало:
```python
    ollama_status, chroma_status, sqlite_status, postgres_status, redis_status = (
        await _probe_ollama(settings.ollama_base_url),
        await _probe_chromadb(settings.vectordb_chroma_dir),
        await _probe_sqlite(settings.tracing_db_path),
        await _probe_postgres(),
        await _probe_redis(),
    )

    critical_down = ollama_status.status == "error" or chroma_status.status == "error"
    non_critical_error = (
        sqlite_status.status == "error"
        or postgres_status.status == "error"
        or redis_status.status == "error"
    )
    overall = (
        "unhealthy" if critical_down
        else "degraded" if non_critical_error
        else "ok"
    )

    response = HealthResponse(
        status=overall,
        components={
            "ollama": ollama_status,
            "chromadb": chroma_status,
            "sqlite": sqlite_status,
            "postgres": postgres_status,
            "redis": redis_status,
        },
        ...
    )
```

**`status="unavailable"` не считается ошибкой** — `overall` остаётся `ok`.

---

## 3. Параллельный запуск проб (опционально, но желательно)

5 sequential probes × 1-1.5с = до 7с на health-check. Запускать параллельно:

```python
    results = await asyncio.gather(
        _probe_ollama(settings.ollama_base_url),
        _probe_chromadb(settings.vectordb_chroma_dir),
        _probe_sqlite(settings.tracing_db_path),
        _probe_postgres(),
        _probe_redis(),
        return_exceptions=False,
    )
    ollama_status, chroma_status, sqlite_status, postgres_status, redis_status = results
```

---

## 4. `tests/test_health_postgres_redis.py`

```python
"""Тесты health-check для Postgres и Redis."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def _mock_critical_probes_ok(monkeypatch):
    """Мокаем ollama/chromadb/sqlite как OK, чтобы изолировать postgres/redis."""
    from api.app import ComponentStatus

    async def _ok(*args, **kwargs):
        return ComponentStatus(status="ok", detail=None)

    monkeypatch.setattr("api.app._probe_ollama", _ok)
    monkeypatch.setattr("api.app._probe_chromadb", _ok)
    monkeypatch.setattr("api.app._probe_sqlite", _ok)


def test_health_returns_200_when_postgres_and_redis_ok(
    client: TestClient, _mock_critical_probes_ok, monkeypatch
):
    from api.app import ComponentStatus

    async def _ok(*args, **kwargs):
        return ComponentStatus(status="ok", detail=None)

    monkeypatch.setattr("api.app._probe_postgres", _ok)
    monkeypatch.setattr("api.app._probe_redis", _ok)

    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "postgres" in data["components"]
    assert "redis" in data["components"]
    assert data["components"]["postgres"]["status"] == "ok"
    assert data["components"]["redis"]["status"] == "ok"


def test_health_returns_degraded_when_postgres_down(
    client: TestClient, _mock_critical_probes_ok, monkeypatch
):
    from api.app import ComponentStatus

    async def _ok(*args, **kwargs):
        return ComponentStatus(status="ok", detail=None)

    async def _fail(*args, **kwargs):
        return ComponentStatus(status="error", detail="connection refused")

    monkeypatch.setattr("api.app._probe_postgres", _fail)
    monkeypatch.setattr("api.app._probe_redis", _ok)

    resp = client.get("/api/health")
    # degraded — не 503, сервис частично работоспособен (API-key path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["components"]["postgres"]["status"] == "error"


def test_health_returns_degraded_when_redis_down(
    client: TestClient, _mock_critical_probes_ok, monkeypatch
):
    from api.app import ComponentStatus

    async def _ok(*args, **kwargs):
        return ComponentStatus(status="ok", detail=None)

    async def _fail(*args, **kwargs):
        return ComponentStatus(status="error", detail="connection refused")

    monkeypatch.setattr("api.app._probe_postgres", _ok)
    monkeypatch.setattr("api.app._probe_redis", _fail)

    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["components"]["redis"]["status"] == "error"


def test_health_unavailable_is_not_error(
    client: TestClient, _mock_critical_probes_ok, monkeypatch
):
    """При отсутствии asyncpg/redis-lib (минимальное CI-окружение) статус=ok."""
    from api.app import ComponentStatus

    async def _unavailable(*args, **kwargs):
        return ComponentStatus(status="unavailable", detail="driver missing")

    monkeypatch.setattr("api.app._probe_postgres", _unavailable)
    monkeypatch.setattr("api.app._probe_redis", _unavailable)

    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    # unavailable не делает health degraded — это сознательный отказ от компонента
    assert data["status"] == "ok"
    assert data["components"]["postgres"]["status"] == "unavailable"
    assert data["components"]["redis"]["status"] == "unavailable"
```

**Замечание:** используется fixture `client` из `tests/conftest.py` (task-65).

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **106+ passed** (102 было + 4 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Health-check **не** становится 503 при падении Postgres/Redis —
  только `degraded`. Это критично для k8s readiness/liveness probe
  семантики.
- Probe-timeout 1-1.5с — health никогда не висит дольше 2с даже при
  недоступности всех БД.
- `status="unavailable"` (driver не установлен) ≠ ошибка в смысле
  мониторинга.
- Существующие health-тесты (`tests/test_health.py`) должны продолжать
  работать без изменений.

## DONE WHEN
- [ ] `_probe_postgres()` возвращает `ComponentStatus` с ok/error/unavailable
- [ ] `_probe_redis()` возвращает `ComponentStatus` с ok/error/unavailable
- [ ] `/api/health` содержит `postgres` и `redis` в `components`
- [ ] При error Postgres или Redis: `overall = "degraded"`, status code 200
- [ ] При error Ollama или ChromaDB: status code 503 (без изменений)
- [ ] Пробы запускаются параллельно через `asyncio.gather`
- [ ] `tests/test_health_postgres_redis.py` — 4 теста, все проходят
- [ ] `pytest tests/ -v` — 106+ passed
- [ ] `ruff check .` — 0 errors
