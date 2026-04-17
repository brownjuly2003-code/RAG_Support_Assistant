# Task 80 — DEPLOY: Graceful shutdown — readiness flip перед выходом

## Goal
task-77 разделил `/api/health/live` и `/api/health/ready`. Но остался
**deployment race condition** при rolling update в k8s:

Таймлайн SIGTERM → SIGKILL (стандартный k8s, termination grace period 30s):

```
t=0    kubectl set image → k8s шлёт SIGTERM старому pod'у
t=0    pod уходит из Service endpoints списка (event propagation)
t=0..2 Service endpoints ещё обновляются на всех узлах
t=1    новый HTTP request прилетает на старый pod (LB ещё не знал)
t=1    uvicorn начинает graceful shutdown, но readiness у нас всё ещё 200
t=1    request успешно принимается → обработка start'ует
t=2    uvicorn закрывает worker → request падает с Connection reset
```

Canonical fix — **readiness flip**:

```
t=0    SIGTERM → ставим флаг _shutting_down=True
t=0    /api/health/ready начинает возвращать 503
t=0+5s k8s readinessProbe увидел 503, pod ушёл из rotation в LB
t=5s   начинаем реальное закрытие (отмена фоновых задач, cleanup)
t=5s+  uvicorn gracefully завершает in-flight requests
t=30s  SIGKILL (не нужен, уже завершились)
```

5 секунд хватает с запасом: k8s default readinessProbe periodSeconds=10,
failureThreshold=3. Но при failureThreshold=1 (как в нашем task-77 manifest)
— 5 секунд покроет два probe-цикла.

## Files to change
- `api/app.py::_lifespan` — флаг `_shutting_down` + sleep перед cleanup
- `api/app.py::health_readiness` — 503 при `_shutting_down`
- `config/settings.py` — 1 env-флаг
- `.env.example`, `README.md` — документирование
- `tests/test_health_liveness.py` (или создать `test_graceful_shutdown.py`)

## Files to create
- `tests/test_graceful_shutdown.py` — 3 теста (или дополнить liveness)

---

## 1. Settings (`config/settings.py`)

Рядом с `session_ttl_seconds`:

```python
    shutdown_ready_delay_sec: float = float(
        os.getenv("SHUTDOWN_READY_DELAY_SEC", "5")
    )
```

Значение 0 — эффективно отключает задержку (для dev/тестов). В проде
держать ≥ 2 × (k8s readinessProbe periodSeconds).

---

## 2. `api/app.py`: флаг и lifespan

Объявить флаг на модульном уровне (рядом с `_sessions`):

```python
_shutting_down: bool = False
```

Обновить `_lifespan`:

было:
```python
    cleanup_task = asyncio.create_task(_cleanup_sessions())
    logger.info("RAG Support Assistant started")
    yield
    cleanup_task.cancel()
    logger.info("RAG Support Assistant shutting down")
```

стало:
```python
    cleanup_task = asyncio.create_task(_cleanup_sessions())
    logger.info("RAG Support Assistant started")
    try:
        yield
    finally:
        global _shutting_down
        _shutting_down = True
        delay = getattr(settings, "shutdown_ready_delay_sec", 5.0)
        if delay > 0:
            logger.info(
                "Shutdown: flipping readiness to 503, draining for %.1fs",
                delay,
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                # если нас прервали (SIGKILL), выходим без задержки
                pass
        cleanup_task.cancel()
        logger.info("RAG Support Assistant shutting down")
```

**Почему `try/finally`:** если лифспан упадёт или приложение прервётся,
флаг всё равно переключится. `finally` триггерится на SIGTERM
(uvicorn вызывает shutdown при SIGTERM).

---

## 3. `health_readiness` — возвращать 503 при shutdown

Найти endpoint (task-77 добавил):

было:
```python
@router.get("/health/ready")
async def health_readiness() -> JSONResponse:
    return await health_check()
```

стало:
```python
@router.get("/health/ready")
async def health_readiness() -> JSONResponse:
    if _shutting_down:
        return JSONResponse(
            status_code=503,
            content={
                "status": "shutting_down",
                "detail": "process is draining — stop sending traffic",
            },
        )
    return await health_check()
```

**`/api/health/live` не трогаем** — процесс ещё жив, liveness 200.
`/api/health` (alias /ready) унаследует новое поведение.

---

## 4. `.env.example`

```
# Задержка (сек) между SIGTERM и реальной остановкой cleanup'ов.
# Нужна, чтобы k8s LB успел снять pod с rotation до закрытия сокетов.
SHUTDOWN_READY_DELAY_SEC=5
```

## 5. `README.md`

В таблицу env vars:

```
| `SHUTDOWN_READY_DELAY_SEC` | `5` | задержка flip'а readiness→503 при SIGTERM, для drain'а k8s LB |
```

---

## 6. `tests/test_graceful_shutdown.py`

Мокаем `_shutting_down` напрямую (не запускаем реальный SIGTERM в тестах).

```python
"""Тесты readiness-flip при graceful shutdown."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_readiness_returns_503_when_shutting_down(
    monkeypatch, client: TestClient
) -> None:
    monkeypatch.setattr("api.app._shutting_down", True)
    resp = client.get("/api/health/ready")
    assert resp.status_code == 503
    data = resp.json()
    assert data["status"] == "shutting_down"


def test_health_alias_also_flips_when_shutting_down(
    monkeypatch, client: TestClient
) -> None:
    """GET /api/health — alias для /ready, должен тоже 503."""
    monkeypatch.setattr("api.app._shutting_down", True)
    resp = client.get("/api/health")
    assert resp.status_code == 503


def test_liveness_stays_200_during_shutdown(
    monkeypatch, client: TestClient
) -> None:
    """Liveness не зависит от флага — процесс ещё отвечает, рестарт не нужен."""
    monkeypatch.setattr("api.app._shutting_down", True)
    resp = client.get("/api/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"
```

**Замечание:** `monkeypatch.setattr("api.app._shutting_down", True)` — важно
через module path, а не через локальную переменную. После теста monkeypatch
вернёт старое значение.

---

## 7. `deploy/helm/templates/deployment.yaml`

Убедиться, что `terminationGracePeriodSeconds` ≥ `SHUTDOWN_READY_DELAY_SEC`
+ 10s на реальный drain uvicorn'а. Default k8s = 30s, нам хватит.

Опционально добавить `preStop` hook (не обязательно — `finally` в lifespan
покрывает большинство случаев):

```yaml
spec:
  terminationGracePeriodSeconds: 30
```

Этот пункт — только проверка/синхронизация. Создавать ничего нового.

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **125+ passed** (122 было + 3 новых), 0 regressions.
- `ruff check .` — 0 errors.
- `/api/health/live` **никогда** не возвращает 503 из-за shutdown —
  это отдельный инвариант (liveness = процесс жив).
- Флаг читается напрямую из module-level `_shutting_down` (не `app.state`)
  — проще monkeypatch в тестах.
- При `SHUTDOWN_READY_DELAY_SEC=0` drain-задержки нет (dev-режим).

## DONE WHEN
- [ ] `_shutting_down: bool = False` на module level в `api/app.py`
- [ ] `_lifespan` переключает флаг в `finally` и ждёт
      `shutdown_ready_delay_sec` секунд до cleanup
- [ ] `/api/health/ready` возвращает 503 `{status: "shutting_down"}` при
      `_shutting_down=True`
- [ ] `/api/health` (alias) наследует то же поведение
- [ ] `/api/health/live` **остаётся** 200 во время shutdown'а
- [ ] `SHUTDOWN_READY_DELAY_SEC` в `Settings`, `.env.example`, README
- [ ] `tests/test_graceful_shutdown.py` — 3 теста, все проходят
- [ ] `pytest tests/ -v` — 125+ passed
- [ ] `ruff check .` — 0 errors
