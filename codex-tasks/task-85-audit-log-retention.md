# Task 85 — OPS: audit_log retention (Postgres)

## Goal
task-84 поставил retention для SQLite traces. Симметричная дыра — `audit_log`
таблица в **Postgres** (task-62). Проверил grep'ом по `api/app.py`: `log_audit`
пишется на **каждом `/api/ask`** (строки 809, 853), не только на админ-действиях.

Расчёт роста:
- 1000 req/day × `action="ask"` = 1000 rows/day
- Плюс upload, feedback, auth_login, admin-actions ≈ +10%
- **~400K rows/год**, средний размер строки с JSON `detail` ≈ 400 bytes =
  ~160 MB/год.

Что ломается без retention:
- Postgres не деградирует как SQLite (B-tree индексы), но:
  - Любой `SELECT * FROM audit_log WHERE ts > ...` становится медленнее
  - Если появится admin UI для просмотра audit — pagination замучается
  - Disk inflation → unplanned alerts / outages через 2-3 года

**Решение — зеркало task-84:**
1. Функция `purge_old_audit(days)` в `db/audit.py`
2. Background task в `_lifespan` рядом с trace-purge
3. Admin endpoint `DELETE /api/admin/audit-log?older_than_days=N`
4. Metric `rag_audit_purged_total`
5. Env var `AUDIT_RETENTION_DAYS=180` (audit долгоживущее — compliance)

**Почему 180 дней а не 90:** audit традиционно важнее trace (compliance,
security investigations). GDPR допускает хранение до 6 мес без специальных
обоснований. Если проекту нужно дольше — env var поднимется.

## Files to change
- `db/audit.py` — `purge_old_audit(days)` функция
- `api/app.py` — admin endpoint + background task в `_lifespan`
- `config/settings.py` — 2 env-флага
- `monitoring/prometheus.py` — counter + helper
- `.env.example`, `README.md`

## Files to create
- `tests/test_audit_retention.py` — 4 теста

---

## 1. `config/settings.py`

Рядом с `trace_retention_days`:

```python
    audit_retention_days: int = field(
        default_factory=lambda: int(os.getenv("AUDIT_RETENTION_DAYS", "180"))
    )
    audit_purge_interval_sec: int = field(
        default_factory=lambda: int(os.getenv("AUDIT_PURGE_INTERVAL_SEC", "86400"))
    )
```

**`default_factory`** обязателен — как в task-71 для `ollama_request_timeout_sec`,
чтобы env var перечитывался при каждом `Settings()` (для тестов с monkeypatch).

---

## 2. `db/audit.py::purge_old_audit`

Добавить async-функцию (audit использует async_session):

```python
async def purge_old_audit(retention_days: int) -> int:
    """Удалить audit_log entries старше retention_days. Возвращает кол-во."""
    if retention_days <= 0:
        return 0

    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    try:
        from db.engine import async_session
        from db.models import AuditLog
        from sqlalchemy import delete

        async with async_session() as db:
            result = await db.execute(
                delete(AuditLog).where(AuditLog.ts < cutoff)
            )
            await db.commit()
            return result.rowcount or 0
    except Exception as exc:
        logger.warning("Audit purge failed: %s", exc)
        return 0
```

**Замечания:**
- Возвращает **int**, не dict (в audit одна таблица, нет cascade).
- Использует SQLAlchemy `delete()` construct — не raw SQL (не все БД
  одинаково парсят).
- Ловим Exception внутри — background task не должен падать на одиночной
  ошибке. Логируем.
- Индекс `audit_log(ts)` — проверить, есть ли в миграции 002
  (`alembic/versions/002_add_users_audit_log.py` из task-68): там
  `sa.Column("ts", ..., index=True)`. Если индекса нет — добавить в
  миграцию 003 (или обновить 002 если она ещё не в проде). Если в проекте
  миграции уже запускались где-либо в проде — создать новую миграцию 003:

```python
# alembic/versions/003_audit_log_ts_index.py (только если 002 уже в проде)
"""add index on audit_log.ts for retention scans."""
from alembic import op

revision = "003"
down_revision = "002"


def upgrade() -> None:
    op.create_index("idx_audit_log_ts", "audit_log", ["ts"], if_not_exists=True)


def downgrade() -> None:
    op.drop_index("idx_audit_log_ts", table_name="audit_log")
```

Если миграция 002 всё ещё не задеплоена (dev-проект) — просто убедиться,
что там `sa.Column("ts", ..., index=True)` — иначе добавить туда.

---

## 3. `monitoring/prometheus.py`

В `__all__`:
```python
    "AUDIT_PURGED",
    "record_audit_purged",
```

В `except ImportError`:
```python
    AUDIT_PURGED = _NoopMetric()
```

В `else`:
```python
    AUDIT_PURGED = Counter(
        "rag_audit_purged_total",
        "audit_log rows deleted by retention purge",
        registry=REGISTRY,
    )
```

(Без label'а — одна таблица.)

Helper:
```python
def record_audit_purged(count: int) -> None:
    if count > 0:
        AUDIT_PURGED.inc(count)
```

---

## 4. `api/app.py::_lifespan` — второй background task

В _lifespan, рядом с `_purge_old_traces_periodically` (task-84), добавить:

```python
    async def _purge_old_audit_periodically() -> None:
        settings = get_settings()
        interval = max(60, getattr(settings, "audit_purge_interval_sec", 86400))
        retention = getattr(settings, "audit_retention_days", 180)
        if retention <= 0:
            logger.info("Audit retention disabled (AUDIT_RETENTION_DAYS=0)")
            return
        while True:
            await asyncio.sleep(interval)
            try:
                from db.audit import purge_old_audit
                deleted = await purge_old_audit(retention)
                if deleted:
                    try:
                        prometheus_metrics.record_audit_purged(deleted)
                    except Exception:
                        pass
                    logger.info("Audit retention purge: %d rows", deleted)
            except Exception as exc:
                logger.warning("Audit retention purge failed: %s", exc)

    audit_purge_task = asyncio.create_task(_purge_old_audit_periodically())
```

В `finally` lifespan'а добавить отмену:
```python
        audit_purge_task.cancel()
```

---

## 5. Admin endpoint

Рядом с `/api/admin/traces` (task-84):

```python
@router.delete("/admin/audit-log")
async def admin_purge_audit(
    request: Request,
    older_than_days: int = 90,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    """Удалить audit_log entries старше N дней."""
    if older_than_days < 0 or older_than_days > 3650:
        raise HTTPException(
            status_code=400,
            detail="older_than_days must be in [0, 3650]",
        )

    from db.audit import log_audit, purge_old_audit
    deleted = await purge_old_audit(older_than_days)
    try:
        prometheus_metrics.record_audit_purged(deleted)
    except Exception:
        pass

    # ВАЖНО: audit записываем ПОСЛЕ purge'а, чтобы наша же запись
    # не попала под удаление.
    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="audit_purge",
        resource=f"audit_log/older_than={older_than_days}d",
        detail={"deleted": deleted},
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(status_code=200, content={"deleted": deleted})
```

**Тонкость:** `log_audit` зовётся **после** `purge_old_audit`. Если сначала
записать, а потом удалить — свой же audit под нож при `older_than_days=0`.

---

## 6. `.env.example`

```
# Retention для audit_log (дней). 0 — не чистить.
AUDIT_RETENTION_DAYS=180
AUDIT_PURGE_INTERVAL_SEC=86400
```

## 7. `README.md`

В таблицу env vars:
```
| `AUDIT_RETENTION_DAYS` | `180` | retention audit_log; 0 = не чистить |
| `AUDIT_PURGE_INTERVAL_SEC` | `86400` | интервал фоновой очистки audit_log |
```

В таблицу API:
```
| DELETE | `/api/admin/audit-log?older_than_days=N` | ручная очистка audit_log (admin) |
```

---

## 8. `tests/test_audit_retention.py`

Audit использует SQLAlchemy async — тесты потребуют либо real Postgres,
либо мок. Идём по пути мока (как в других db-related тестах): подменяем
`purge_old_audit` и проверяем, что endpoint зовёт её корректно.

```python
"""Тесты audit_log retention + admin purge endpoint."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient


def test_purge_with_zero_retention_is_noop() -> None:
    """retention_days <= 0 должен вернуть 0 без обращения к БД."""
    import asyncio
    from db.audit import purge_old_audit

    result = asyncio.run(purge_old_audit(0))
    assert result == 0


def test_purge_with_negative_returns_zero() -> None:
    import asyncio
    from db.audit import purge_old_audit

    result = asyncio.run(purge_old_audit(-10))
    assert result == 0


def test_admin_purge_endpoint_calls_purge(monkeypatch, client: TestClient) -> None:
    """Admin endpoint делегирует в purge_old_audit с правильным параметром."""
    from auth.jwt_handler import create_access_token

    called_with = {}

    async def _fake_purge(days: int) -> int:
        called_with["days"] = days
        return 42

    async def _fake_log_audit(**kwargs) -> None:
        called_with.setdefault("audit_calls", []).append(kwargs)

    monkeypatch.setattr("db.audit.purge_old_audit", _fake_purge)
    monkeypatch.setattr("api.app.log_audit", _fake_log_audit)

    token = create_access_token("admin", "admin")
    resp = client.request(
        "DELETE",
        "/api/admin/audit-log?older_than_days=90",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"deleted": 42}
    assert called_with["days"] == 90
    # audit о самой операции записан
    assert any(
        c.get("action") == "audit_purge"
        for c in called_with.get("audit_calls", [])
    )


def test_admin_purge_rejects_non_admin(client: TestClient) -> None:
    from auth.jwt_handler import create_access_token
    token = create_access_token("viewer-user", "viewer")

    resp = client.request(
        "DELETE",
        "/api/admin/audit-log?older_than_days=90",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_admin_purge_validates_bounds(client: TestClient) -> None:
    from auth.jwt_handler import create_access_token
    token = create_access_token("admin", "admin")

    for bad in (-1, 4000):
        resp = client.request(
            "DELETE",
            f"/api/admin/audit-log?older_than_days={bad}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400, f"expected 400 for {bad}"
```

**Замечание:** `monkeypatch.setattr("db.audit.purge_old_audit", _fake_purge)`
— патчим в `db.audit` module. Если endpoint импортирует `from db.audit
import purge_old_audit` локально (внутри функции), такой патч работает.
Если импорт на top-level — нужно патчить `api.app.purge_old_audit`.
Посмотреть по факту и адаптировать.

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **146+ passed** (141 было + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- `purge_old_audit` использует SQLAlchemy async, ошибки ловятся
  локально (background task не должен падать на одиночной проблеме БД).
- Endpoint пишет audit **после** purge'а (собственная запись не под нож).
- Index на `audit_log(ts)` — проверить в миграции 002; создать 003
  только если 002 уже запущена где-то.
- `AUDIT_RETENTION_DAYS=0` отключает auto-purge.
- 400 на невалидный `older_than_days` (вне [0, 3650]).

## DONE WHEN
- [ ] `purge_old_audit(days)` в `db/audit.py` — async, возвращает int
- [ ] Background task в `_lifespan` запускается и корректно отменяется
- [ ] `DELETE /api/admin/audit-log?older_than_days=N` — admin only,
      audit-записывается **после** purge'а
- [ ] `rag_audit_purged_total` counter инкрементится на каждом покусанном
      row'е
- [ ] 2 env-флага в Settings (через `default_factory`), .env.example, README
- [ ] Index `audit_log(ts)` существует (в 002 или 003)
- [ ] `tests/test_audit_retention.py` — 5 тестов, все проходят
- [ ] `pytest tests/ -v` — 146+ passed
- [ ] `ruff check .` — 0 errors
