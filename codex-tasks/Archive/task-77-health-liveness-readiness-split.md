# Task 77 — HEALTH: Разделить `/api/health` на liveness и readiness

## Goal
Сейчас `/api/health` возвращает 503, когда Ollama или ChromaDB недоступны.
В k8s это означает, что **та же проверка** нагружена на обе probe:
`livenessProbe` и `readinessProbe`. Последствия:

- Ollama мигнула на 40 секунд → `/api/health` → 503 →
  **livenessProbe** помечает pod нездоровым → k8s перезапускает pod.
  Но перезапуск ничего не лечит: Ollama всё ещё моргает, новый pod
  запустится и снова станет 503. **Restart-loop на проблеме, которая
  вообще не в нашем процессе.**
- То же самое для Postgres/ChromaDB/любой внешней зависимости.

Правильная k8s-семантика (из docs.kubernetes.io/docs/tasks/configure-pod-container/
configure-liveness-readiness-startup-probes):

| Probe | Смысл | Failure action |
|---|---|---|
| **liveness** | процесс жив и не зависший | перезапуск pod |
| **readiness** | готов принимать трафик прямо сейчас | убрать из LB, **без** рестарта |

Liveness должен падать **только** если **наш** процесс сам сломан
(deadlock, OOM, event loop завис). Внешние зависимости ≠ liveness.

## Files to change
- `api/app.py` — новые endpoint'ы `GET /api/health/live` и
  `GET /api/health/ready`. Существующий `GET /api/health` остаётся
  как alias для readiness (backwards compat)
- `docs/` — если есть runbook/operational doc — одна строка про
  liveness/readiness (опционально, без фанатизма)
- `README.md` — описание двух новых endpoint'ов в таблице API

## Files to create
- `tests/test_health_liveness.py` — 3 теста для `/live`
- (readiness уже покрыт существующими `test_health.py` + `test_health_postgres_redis.py`)

---

## 1. Endpoint'ы в `api/app.py`

Рядом с существующим `health_check()`:

```python
@router.get("/health/live")
async def health_liveness() -> JSONResponse:
    """Liveness probe: процесс жив, event loop не завис.

    НЕ проверяет внешние зависимости (Ollama, DB, Redis) — их падение
    не должно триггерить рестарт pod'а, только eviction из LB через
    readiness. Возвращает 200 всегда, если процесс способен ответить.
    """
    return JSONResponse(
        status_code=200,
        content={"status": "alive", "service": "rag-support-assistant"},
    )


@router.get("/health/ready")
async def health_readiness() -> JSONResponse:
    """Readiness probe: готов принимать трафик.

    Делегирует в существующий health_check() — сохраняет текущую
    семантику 503/degraded/ok с проверкой всех зависимостей.
    """
    return await health_check()


# Существующий /health оставить как alias для /health/ready (backwards compat).
# НЕ удалять, чтобы не ломать внешних потребителей.
```

**Важно:**
- `/health/live` **никогда** не вызывает probe-функции. Это должен быть
  constant-time 200. Нужен deadlock-canary — даже без asyncio-проверки,
  если FastAPI смог отрендерить JSON и asyncio event loop крутится,
  процесс жив.
- `/health/ready` — тонкая обёртка над `health_check`. Не дублировать
  логику.
- Регистрация endpoint'ов должна быть в том же `router`, что и остальные
  `/api/*`.

---

## 2. `README.md`

В таблицу API добавить две строки:

```
| GET | `/api/health/live` | liveness probe (k8s): 200 всегда, пока процесс отвечает |
| GET | `/api/health/ready` | readiness probe (k8s): полная проверка зависимостей, 503 при падении Ollama/ChromaDB |
```

Существующую строку `GET /api/health` оставить (alias).

---

## 3. `deploy/` k8s манифесты (если есть)

Если в `deploy/` есть `Deployment.yaml` или `values.yaml` (task-64), обновить
probe-пути:

```yaml
livenessProbe:
  httpGet:
    path: /api/health/live
    port: 8000
  initialDelaySeconds: 30
  periodSeconds: 10
  failureThreshold: 3
readinessProbe:
  httpGet:
    path: /api/health/ready
    port: 8000
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 2
```

Если таких файлов нет — пропустить этот пункт, не создавать новые.

---

## 4. `tests/test_health_liveness.py`

```python
"""Тесты для liveness probe — НЕ должна зависеть от внешних probe-функций."""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_liveness_returns_200_and_alive(client: TestClient) -> None:
    resp = client.get("/api/health/live")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "alive"


def test_liveness_does_not_call_probes(monkeypatch, client: TestClient) -> None:
    """Liveness не должна триггерить пробы внешних зависимостей."""
    calls: list[str] = []

    async def _spy_probe(*args, **kwargs):
        calls.append("called")
        from api.app import ComponentStatus
        return ComponentStatus(status="ok", detail=None)

    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        monkeypatch.setattr(f"api.app._probe_{name}", _spy_probe)

    resp = client.get("/api/health/live")
    assert resp.status_code == 200
    assert calls == [], "liveness must not invoke any probe"


def test_liveness_stays_200_when_dependencies_are_down(
    monkeypatch, client: TestClient
) -> None:
    """Ollama/Postgres/Redis down → readiness 503/degraded, liveness всё равно 200."""
    from api.app import ComponentStatus

    async def _fail(*args, **kwargs):
        return ComponentStatus(status="error", detail="down")

    for name in ("ollama", "chromadb", "sqlite", "postgres", "redis"):
        monkeypatch.setattr(f"api.app._probe_{name}", _fail)

    live = client.get("/api/health/live")
    ready = client.get("/api/health/ready")

    assert live.status_code == 200  # не перезапускаем процесс из-за внешних
    assert ready.status_code == 503  # но из LB убираем
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **113+ passed** (110 было + 3 новых), 0 regressions.
- `ruff check .` — 0 errors.
- `/api/health` **остаётся** работать (alias readiness) — не ломаем
  существующих потребителей, docker healthcheck'и и т.д.
- `/api/health/live` **никогда** не вызывает `_probe_*` — строгий инвариант.
- Новые endpoint'ы **без** rate-limit и **без** require_role — должны
  отвечать даже когда auth сломан.

## DONE WHEN
- [ ] `GET /api/health/live` возвращает 200 + `{"status": "alive", ...}`
- [ ] `GET /api/health/ready` делегирует в `health_check()`
- [ ] `GET /api/health` работает как раньше (backwards compat)
- [ ] `/live` не вызывает ни одну probe-функцию (тест это проверяет)
- [ ] `/live` возвращает 200 даже когда все зависимости down
- [ ] README обновлён (две новых строки в таблице API)
- [ ] k8s манифесты в `deploy/` указывают на `/live` и `/ready`
      (если эти файлы существуют)
- [ ] `tests/test_health_liveness.py` — 3 теста, все проходят
- [ ] `pytest tests/ -v` — 113+ passed
- [ ] `ruff check .` — 0 errors
