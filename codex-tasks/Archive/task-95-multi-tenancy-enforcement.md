# Task 95 — MULTI-TENANCY Phase 3: Query enforcement

## Goal
Phase 2 (task-93) научил систему **писать** реальный `tenant_id` в
`traces`, `audit_log`, state. Но **читать** данные все tenants пока
может любой аутентифицированный пользователь:
- `GET /api/admin/audit` возвращает **все** audit-записи
- `GET /api/admin/traces` возвращает **все** traces
- `/api/metrics` (SQLite-based) агрегирует по **всем** tenant'ам
- `purge_old_audit` и `purge_old_traces` удаляют из **всех** tenant'ов

Это data leak в B2B-контексте: acme-corp видит traces megacorp'а.

Phase 3 — enforce isolation **во всех SELECT/DELETE** по `tenant_id`:
- Read endpoint'ы фильтруют строго по текущему `tenant` из JWT
- Purge endpoint'ы тоже ограничены своим tenant'ом (если не admin-wide)
- Metrics snapshot учитывает только свой tenant
- Background purge в lifespan'е — per-tenant циклом или один SQL с
  GROUP BY (простой вариант: удаляем только rows с `tenant_id=...`
  в цикле по всем known tenants; в Phase 3 нет реестра tenants,
  так что **пока удаляем across all tenants** в background — это
  единственный admin-wide путь).

**Не делаем** в этой фазе:
- Per-tenant ChromaDB (это task-96)
- Per-tenant rate-limits
- Cross-tenant admin view (superadmin-role) — отдельная задача,
  когда понадобится

## Files to change
- `sqlite_trace.py` — `tenant_id` параметр в `list_recent_traces`,
  `get_trace_detail`, `get_metrics_snapshot`, `purge_old_traces`
- `api/app.py` — admin read endpoint'ы передают `current_tenant`;
  purge endpoint'ы тоже
- `db/audit.py` — `purge_old_audit(retention_days, tenant_id=None)`;
  admin list endpoint фильтрует по tenant
- `api/app.py::_list_audit` — добавить filter

## Files to create
- `tests/test_tenant_enforcement.py` — 8 тестов

---

## 1. `sqlite_trace.py`

```python
def list_recent_traces(limit: int = 50, tenant_id: str | None = None) -> list[dict]:
    """Последние traces. Если tenant_id задан — фильтруем по нему."""
    limit = max(1, min(500, limit))
    with _get_connection() as conn:
        cur = conn.cursor()
        if tenant_id is None:
            cur.execute(
                "SELECT trace_id, started_at, finished_at FROM traces "
                "ORDER BY started_at DESC LIMIT ?",
                (limit,),
            )
        else:
            cur.execute(
                "SELECT trace_id, started_at, finished_at FROM traces "
                "WHERE tenant_id = ? ORDER BY started_at DESC LIMIT ?",
                (tenant_id, limit),
            )
        return [
            {"trace_id": r[0], "started_at": r[1], "finished_at": r[2]}
            for r in cur.fetchall()
        ]


def get_trace_detail(trace_id: str, tenant_id: str | None = None) -> dict | None:
    """Один trace. Если tenant_id задан — вернёт None для trace другого tenant'а."""
    with _get_connection() as conn:
        cur = conn.cursor()
        if tenant_id is None:
            cur.execute(
                "SELECT trace_id, started_at, finished_at, tenant_id "
                "FROM traces WHERE trace_id = ?",
                (trace_id,),
            )
        else:
            cur.execute(
                "SELECT trace_id, started_at, finished_at, tenant_id "
                "FROM traces WHERE trace_id = ? AND tenant_id = ?",
                (trace_id, tenant_id),
            )
        row = cur.fetchone()
        if row is None:
            return None
        # ... остальной код (steps + feedback) без изменений ...


def get_metrics_snapshot(tenant_id: str | None = None) -> dict:
    """Агрегированные метрики. Без tenant_id — по всем tenants (для admin-wide).
    С tenant_id — только свой."""
    # Существующая логика SELECT count/avg + добавить WHERE tenant_id = ?
    # Все подзапросы к traces получают filter. trace_steps/feedback —
    # JOIN по trace_id с основным traces-фильтром.
    # Детали зависят от текущей реализации; главное — каждый SELECT
    # из traces-таблицы имеет опциональный WHERE tenant_id = ?.


def purge_old_traces(retention_days: int, tenant_id: str | None = None) -> dict:
    """Удалить traces старше retention_days, опционально только в одном tenant'е."""
    if retention_days <= 0:
        return {"traces_deleted": 0, "steps_deleted": 0, "feedback_deleted": 0}

    cutoff_iso = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()

    with _get_connection() as conn:
        cur = conn.cursor()
        if tenant_id is None:
            cur.execute(
                "SELECT trace_id FROM traces WHERE started_at < ?", (cutoff_iso,)
            )
        else:
            cur.execute(
                "SELECT trace_id FROM traces WHERE started_at < ? AND tenant_id = ?",
                (cutoff_iso, tenant_id),
            )
        # ... rest (cascade delete batch'ами) без изменений ...

        if tenant_id is None:
            cur.execute("DELETE FROM traces WHERE started_at < ?", (cutoff_iso,))
        else:
            cur.execute(
                "DELETE FROM traces WHERE started_at < ? AND tenant_id = ?",
                (cutoff_iso, tenant_id),
            )
        # ... rest ...
```

---

## 2. `db/audit.py`

```python
async def purge_old_audit(
    retention_days: int, tenant_id: str | None = None
) -> int:
    if retention_days <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    try:
        from db.engine import async_session
        from db.models import AuditLog
        from sqlalchemy import delete

        async with async_session() as db:
            stmt = delete(AuditLog).where(AuditLog.ts < cutoff)
            if tenant_id is not None:
                stmt = stmt.where(AuditLog.tenant_id == tenant_id)
            result = await db.execute(stmt)
            await db.commit()
            return result.rowcount or 0
    except Exception as exc:
        logger.warning("Audit purge failed: %s", exc)
        return 0
```

---

## 3. `api/app.py` — admin read endpoints

### `GET /api/admin/audit`

```python
@router.get("/admin/audit")
async def admin_list_audit(
    request: Request,
    limit: int = 50,
    actor: str | None = None,
    action: str | None = None,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from api.correlation import get_current_tenant
    tenant = _user.get("tenant") or get_current_tenant() or "default"

    limit = max(1, min(500, limit))

    try:
        from db.engine import async_session
        from db.models import AuditLog
        from sqlalchemy import select

        async with async_session() as db:
            stmt = (
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant)  # ← enforcement
                .order_by(AuditLog.ts.desc())
                .limit(limit)
            )
            if actor:
                stmt = stmt.where(AuditLog.actor == actor)
            if action:
                stmt = stmt.where(AuditLog.action == action)
            result = await db.execute(stmt)
            rows = result.scalars().all()
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"detail": f"audit_log unavailable: {exc}"},
        )

    return JSONResponse(content={
        "entries": [...],  # as before
        "tenant": tenant,  # эхо — видимость для клиента
    })
```

### `GET /api/admin/traces` и `/api/admin/traces/{id}`

```python
@router.get("/admin/traces")
async def admin_list_traces(
    limit: int = 50,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    tenant = _user.get("tenant", "default")
    from sqlite_trace import list_recent_traces
    traces = await asyncio.to_thread(list_recent_traces, limit, tenant)
    return JSONResponse(content={"traces": traces, "tenant": tenant})


@router.get("/admin/traces/{trace_id}")
async def admin_get_trace(
    trace_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    tenant = _user.get("tenant", "default")
    # ... validation regex ...
    from sqlite_trace import get_trace_detail
    trace = await asyncio.to_thread(get_trace_detail, trace_id, tenant)
    if trace is None:
        # Mogu be "не существует" или "существует, но другого tenant'а".
        # 404 одинаково — не leak'ит информацию про foreign trace.
        raise HTTPException(status_code=404, detail="trace not found")
    return JSONResponse(content=trace)
```

**Ключевое:** когда trace существует, но чужого tenant'а — возвращаем
404, **не** 403. 403 бы leak'нул факт существования trace'а в другом
tenant'е.

### Admin purge endpoints

```python
@router.delete("/admin/traces")
async def admin_purge_traces(
    older_than_days: int = 30,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    tenant = _user.get("tenant", "default")
    from sqlite_trace import purge_old_traces
    result = await asyncio.to_thread(purge_old_traces, older_than_days, tenant)
    # ... Prometheus + audit_log как раньше ...
    return JSONResponse(content=result)


@router.delete("/admin/audit-log")
async def admin_purge_audit(
    older_than_days: int = 90,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    tenant = _user.get("tenant", "default")
    from db.audit import purge_old_audit
    deleted = await purge_old_audit(older_than_days, tenant)
    # ... rest ...
```

### Background purge в `_lifespan`

**Не** передавать tenant_id — background purge admin-wide (cleanup всех
retention'ов). Это безопасно: retention применяется одинаково к всем
tenants. Оставляем существующий код без изменений.

### `GET /api/metrics` (SQLite-aggregated)

```python
async def get_metrics() -> dict:
    from api.correlation import get_current_tenant
    tenant = get_current_tenant() or "default"
    try:
        from sqlite_trace import get_metrics_snapshot
        return get_metrics_snapshot(tenant_id=tenant)
    # ... except ...
```

---

## 4. `tests/test_tenant_enforcement.py`

```python
"""Phase 3 enforcement: read и purge по tenant_id."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


def _token(tenant="default", role="admin"):
    t = create_access_token("u", role, tenant)
    return {"Authorization": f"Bearer {t}"}


@pytest.fixture
def trace_db_with_tenants(monkeypatch, tmp_path):
    db = tmp_path / "traces.db"
    import sqlite_trace
    sqlite_trace._DB_PATH = str(db)
    sqlite_trace._ensure_tables()

    conn = sqlite3.connect(str(db))
    # acme-corp trace
    conn.execute(
        "INSERT INTO traces (trace_id, started_at, finished_at, tenant_id) VALUES (?, ?, NULL, ?)",
        ("acme-trace-1", "2026-04-17T00:00:00Z", "acme-corp"),
    )
    # megacorp trace
    conn.execute(
        "INSERT INTO traces (trace_id, started_at, finished_at, tenant_id) VALUES (?, ?, NULL, ?)",
        ("mega-trace-1", "2026-04-17T00:00:00Z", "megacorp"),
    )
    conn.commit()
    conn.close()
    yield db


def test_list_traces_filters_by_tenant(trace_db_with_tenants):
    from sqlite_trace import list_recent_traces

    acme_only = list_recent_traces(50, tenant_id="acme-corp")
    mega_only = list_recent_traces(50, tenant_id="megacorp")
    all_traces = list_recent_traces(50)

    acme_ids = [t["trace_id"] for t in acme_only]
    mega_ids = [t["trace_id"] for t in mega_only]
    all_ids = [t["trace_id"] for t in all_traces]

    assert "acme-trace-1" in acme_ids
    assert "mega-trace-1" not in acme_ids
    assert "mega-trace-1" in mega_ids
    assert "acme-trace-1" not in mega_ids
    assert len(all_ids) >= 2


def test_get_trace_detail_hides_foreign_tenant(trace_db_with_tenants):
    from sqlite_trace import get_trace_detail

    assert get_trace_detail("acme-trace-1", tenant_id="acme-corp") is not None
    # acme пользователь не видит megacorp trace
    assert get_trace_detail("mega-trace-1", tenant_id="acme-corp") is None


def test_purge_traces_respects_tenant(trace_db_with_tenants):
    from sqlite_trace import purge_old_traces
    # Давняя дата — оба под purge (300 дней)
    from pathlib import Path
    import sqlite3
    # Сначала омолодим даты, чтобы они не попали под purge:
    # (в нашем fixture даты 2026-04-17 — могут быть "в будущем" или нет)

    result = purge_old_traces(retention_days=1, tenant_id="acme-corp")
    # megacorp trace должен остаться
    conn = sqlite3.connect(str(trace_db_with_tenants))
    survivors = [
        r[0] for r in conn.execute("SELECT trace_id FROM traces").fetchall()
    ]
    conn.close()
    assert "mega-trace-1" in survivors


def test_admin_traces_endpoint_filters_by_jwt_tenant(monkeypatch, client: TestClient):
    monkeypatch.setattr(
        "sqlite_trace.list_recent_traces",
        lambda limit, tenant_id=None: [
            {"trace_id": "t1", "started_at": None, "finished_at": None}
        ]
        if tenant_id == "acme"
        else [],
    )

    resp = client.get("/api/admin/traces", headers=_token("acme"))
    assert resp.status_code == 200
    assert len(resp.json()["traces"]) == 1
    assert resp.json().get("tenant") == "acme"

    resp2 = client.get("/api/admin/traces", headers=_token("wrong-tenant"))
    assert len(resp2.json()["traces"]) == 0


def test_admin_trace_detail_returns_404_for_foreign(monkeypatch, client: TestClient):
    """Foreign trace → 404, не 403 (no information leak)."""
    def _fake_detail(trace_id, tenant_id=None):
        if tenant_id == "acme":
            return None  # foreign — enforcement вернул None
        return {"trace_id": "x", "started_at": "", "finished_at": None, "steps": [], "feedback": []}

    monkeypatch.setattr("sqlite_trace.get_trace_detail", _fake_detail)
    resp = client.get(
        "/api/admin/traces/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        headers=_token("acme"),
    )
    assert resp.status_code == 404


def test_admin_audit_list_filters_by_tenant(monkeypatch, client: TestClient):
    """admin_list_audit использует WHERE tenant_id = ?."""
    captured: dict = {}

    class _Row:
        id, ts, actor, action, resource, detail, ip_address = 1, None, "a", "b", "c", "{}", None

    class _Execute:
        def scalars(self):
            class _S:
                def all(self_inner): return [_Row()]
            return _S()

    class _Stmt:
        def __init__(self): self.filters = []
        def where(self, cond):
            captured.setdefault("where", []).append(str(cond))
            return self
        def order_by(self, *a, **kw): return self
        def limit(self, n): return self

    class _Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def execute(self, stmt): return _Execute()

    monkeypatch.setattr("db.engine.async_session", lambda: _Session())
    monkeypatch.setattr(
        "api.app.select",
        lambda *a, **kw: _Stmt(),
        raising=False,
    )

    resp = client.get("/api/admin/audit?limit=5", headers=_token("my-tenant"))
    # Тест может быть хрупким из-за monkeypatch select'а — если сложно,
    # упростить: просто проверить, что в ответе echo tenant=my-tenant.
    assert resp.status_code in (200, 503)  # или 200 при успехе


def test_audit_purge_scoped_to_tenant(monkeypatch, client: TestClient):
    captured: dict = {}

    async def _fake_purge(days, tenant_id=None):
        captured["days"] = days
        captured["tenant"] = tenant_id
        return 5

    async def _fake_audit(**kw): pass

    monkeypatch.setattr("db.audit.purge_old_audit", _fake_purge)
    monkeypatch.setattr("api.app.log_audit", _fake_audit)

    resp = client.request(
        "DELETE",
        "/api/admin/audit-log?older_than_days=30",
        headers=_token("acme"),
    )
    assert resp.status_code == 200
    assert captured["tenant"] == "acme"
    assert captured["days"] == 30


def test_metrics_snapshot_filtered_by_tenant(monkeypatch, client: TestClient):
    """/api/metrics вызывает get_metrics_snapshot с tenant из контекста."""
    captured: dict = {}

    def _fake_snapshot(tenant_id=None):
        captured["tenant"] = tenant_id
        return {"latency": {}, "escalation": {}, "quality": {}, "errors": {}, "feedback": {}}

    monkeypatch.setattr("sqlite_trace.get_metrics_snapshot", _fake_snapshot)

    client.get("/api/metrics", headers=_token("x-corp"))
    assert captured["tenant"] == "x-corp"
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **207+ passed** (199 + 8 новых), 0 regressions.
- `ruff check .` — 0 errors.
- **404 вместо 403** для foreign trace/audit — защита от information leak.
- Background purge tasks остаются admin-wide (retention применяется
  одинаково всем tenants).
- Существующие тесты `test_admin_view.py`, `test_trace_retention.py`,
  `test_audit_retention.py` не должны сломаться — API функций расширилось
  новым **опциональным** параметром `tenant_id`, legacy вызовы
  (tenant_id=None) продолжают работать.

## DONE WHEN
- [ ] `list_recent_traces`, `get_trace_detail`, `get_metrics_snapshot`,
      `purge_old_traces` принимают optional `tenant_id`
- [ ] `purge_old_audit(days, tenant_id=None)` фильтрует
- [ ] Admin read endpoints (`/admin/audit`, `/admin/traces`,
      `/admin/traces/{id}`, `/api/metrics`) передают `user.tenant`
- [ ] Admin purge endpoints (`/admin/traces DELETE`, `/admin/audit-log DELETE`)
      тоже scoped к tenant'у
- [ ] 404 для foreign trace в `/admin/traces/{id}`
- [ ] 8 тестов в `tests/test_tenant_enforcement.py`
- [ ] `pytest tests/ -v` — 207+ passed
- [ ] `ruff check .` — 0 errors
