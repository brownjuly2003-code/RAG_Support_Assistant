# Task 90 — ADMIN: View endpoints для audit_log и traces

## Goal
task-74/84/85 добавили админские **действия** (reset breaker, purge).
Но для **investigation** — нет способа **просмотреть** данные через HTTP:
- Audit_log читается только прямым SQL'ем в Postgres
- Traces — только прямым SQLite в `traces.db`
- Support получает «trace_id: abc123» от пользователя и должен лезть в БД

Нужны read-only endpoint'ы:
1. `GET /api/admin/audit?limit=50&actor=...&action=...` — последние audit
2. `GET /api/admin/traces?limit=50` — список недавних traces (без state_json)
3. `GET /api/admin/traces/{trace_id}` — полный trace с шагами + feedback

RBAC: admin или agent (support оператор — agent-роль). Audit-lог само
чтение не записываем (иначе каждый просмотр админа = audit-запись, шум).

## Files to change
- `api/app.py` — 3 новых endpoint'а рядом с `/api/admin/*`
- `sqlite_trace.py` — 2 helper'а: `list_recent_traces`, `get_trace_detail`

## Files to create
- `tests/test_admin_view.py` — 6 тестов

---

## 1. `sqlite_trace.py` helpers

```python
def list_recent_traces(limit: int = 50) -> list[dict]:
    """Последние N traces, без state_json (лёгкий list view)."""
    limit = max(1, min(500, limit))
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT trace_id, started_at, finished_at
            FROM traces
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {"trace_id": r[0], "started_at": r[1], "finished_at": r[2]}
            for r in cur.fetchall()
        ]


def get_trace_detail(trace_id: str) -> dict | None:
    """Один trace со всеми шагами + feedback. None если не найден."""
    with _get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT trace_id, started_at, finished_at FROM traces WHERE trace_id = ?",
            (trace_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        cur.execute(
            """
            SELECT step_order, node_name, state_json, ts
            FROM trace_steps
            WHERE trace_id = ?
            ORDER BY step_order
            """,
            (trace_id,),
        )
        steps = [
            {
                "order": s[0],
                "node": s[1],
                "state": json.loads(s[2]) if s[2] else None,
                "ts": s[3],
            }
            for s in cur.fetchall()
        ]

        cur.execute(
            "SELECT rating, ts FROM feedback WHERE trace_id = ?",
            (trace_id,),
        )
        feedback = [{"rating": f[0], "ts": f[1]} for f in cur.fetchall()]

        return {
            "trace_id": row[0],
            "started_at": row[1],
            "finished_at": row[2],
            "steps": steps,
            "feedback": feedback,
        }
```

Импорт `json` уже есть в файле.

---

## 2. `api/app.py` — 3 endpoint'а

Рядом с `/api/admin/traces DELETE` (task-84):

```python
@router.get("/admin/audit")
async def admin_list_audit(
    limit: int = 50,
    actor: str | None = None,
    action: str | None = None,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    """Последние N audit_log entries с опциональными фильтрами."""
    limit = max(1, min(500, limit))

    try:
        from db.engine import async_session
        from db.models import AuditLog
        from sqlalchemy import select

        async with async_session() as db:
            stmt = select(AuditLog).order_by(AuditLog.ts.desc()).limit(limit)
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
        "entries": [
            {
                "id": r.id,
                "ts": r.ts.isoformat() if r.ts else None,
                "actor": r.actor,
                "action": r.action,
                "resource": r.resource,
                "detail": r.detail,
                "ip_address": r.ip_address,
            }
            for r in rows
        ],
    })


@router.get("/admin/traces")
async def admin_list_traces(
    limit: int = 50,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from sqlite_trace import list_recent_traces
    traces = await asyncio.to_thread(list_recent_traces, limit)
    return JSONResponse(content={"traces": traces})


@router.get("/admin/traces/{trace_id}")
async def admin_get_trace(
    trace_id: str,
    _user: dict = Depends(require_role("agent", "admin")),
) -> JSONResponse:
    from sqlite_trace import get_trace_detail

    # Валидация: trace_id — UUID4 hex (из task-79) или UUID с дефисами.
    # Отклоняем что-то слишком длинное/с недопустимыми символами —
    # защита от SQL-injection (хоть параметризованный запрос и так
    # защищает).
    import re
    if not re.fullmatch(r"[A-Za-z0-9\-]{8,64}", trace_id):
        raise HTTPException(status_code=400, detail="invalid trace_id format")

    trace = await asyncio.to_thread(get_trace_detail, trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return JSONResponse(content=trace)
```

---

## 3. `tests/test_admin_view.py`

```python
"""Тесты admin view endpoints."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


def _admin(): return {"Authorization": f"Bearer {create_access_token('admin', 'admin')}"}
def _agent(): return {"Authorization": f"Bearer {create_access_token('op1', 'agent')}"}
def _viewer(): return {"Authorization": f"Bearer {create_access_token('v1', 'viewer')}"}


def test_audit_list_requires_role(client: TestClient) -> None:
    resp = client.get("/api/admin/audit", headers=_viewer())
    assert resp.status_code == 403


def test_audit_list_admin_ok(monkeypatch, client: TestClient) -> None:
    # Мокаем db-вызов — иначе тест требует живой Postgres
    class _Row:
        id, ts, actor, action, resource, detail, ip_address = 1, None, "a", "b", "c", "{}", None

    async def _fake_execute(*a, **kw):
        class _R:
            def scalars(self):
                class _S:
                    def all(self_inner): return [_Row()]
                return _S()
        return _R()

    class _Session:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def execute(self, *a, **kw): return await _fake_execute()

    def _fake_session(): return _Session()
    monkeypatch.setattr("db.engine.async_session", _fake_session)

    resp = client.get("/api/admin/audit?limit=10", headers=_admin())
    assert resp.status_code == 200
    assert "entries" in resp.json()


def test_traces_list_agent_ok(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr(
        "sqlite_trace.list_recent_traces",
        lambda limit: [{"trace_id": "abc", "started_at": "2026-04-17T00:00:00Z", "finished_at": None}],
    )
    resp = client.get("/api/admin/traces?limit=5", headers=_agent())
    assert resp.status_code == 200
    assert len(resp.json()["traces"]) == 1


def test_trace_detail_not_found(monkeypatch, client: TestClient) -> None:
    monkeypatch.setattr("sqlite_trace.get_trace_detail", lambda tid: None)
    resp = client.get(
        "/api/admin/traces/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        headers=_admin(),
    )
    assert resp.status_code == 404


def test_trace_detail_invalid_id_rejected(client: TestClient) -> None:
    resp = client.get(
        "/api/admin/traces/'; DROP TABLE traces--",
        headers=_admin(),
    )
    assert resp.status_code in (400, 404)  # FastAPI может до нас не довести path-валидацию


def test_trace_detail_returns_steps(monkeypatch, client: TestClient) -> None:
    fake = {
        "trace_id": "abc123",
        "started_at": "2026-04-17T00:00:00Z",
        "finished_at": "2026-04-17T00:00:02Z",
        "steps": [{"order": 0, "node": "transform_query", "state": {}, "ts": "2026-04-17T00:00:00Z"}],
        "feedback": [],
    }
    monkeypatch.setattr("sqlite_trace.get_trace_detail", lambda tid: fake)
    resp = client.get("/api/admin/traces/abc123", headers=_admin())
    assert resp.status_code == 200
    data = resp.json()
    assert data["trace_id"] == "abc123"
    assert len(data["steps"]) == 1
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **167+ passed** (161 было + 6 новых), 0 regressions.
- `ruff check .` — 0 errors.
- RBAC: `require_role("agent", "admin")` — support-оператору тоже нужно.
- Audit **не** записывается для read-endpoint'ов (иначе шум).
- `limit` clamp в [1, 500] — anti-DoS через `?limit=999999999`.
- trace_id whitelist regex — защита от injection.

## DONE WHEN
- [ ] `list_recent_traces(limit)` и `get_trace_detail(trace_id)` в `sqlite_trace.py`
- [ ] `GET /api/admin/audit` с фильтрами actor/action/limit
- [ ] `GET /api/admin/traces` со списком (без state_json)
- [ ] `GET /api/admin/traces/{trace_id}` с полной детализацией + feedback
- [ ] Валидация trace_id regex'ем и limit clamp'ом
- [ ] `tests/test_admin_view.py` — 6 тестов проходят
- [ ] `pytest tests/ -v` — 167+ passed
- [ ] `ruff check .` — 0 errors
