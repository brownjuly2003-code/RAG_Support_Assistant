# Task 84 — OPS: SQLite trace retention + admin purge endpoint

## Goal
В `sqlite_trace.py` нет retention-политики: таблицы `traces`, `trace_steps`,
`feedback` растут **вечно**. Это sleeper-баг, который бьёт через 3-6 месяцев
uptime:

- При 1000 req/day и ~6 узлах пайплайна на запрос → **6000+ trace_steps**/день.
- За год накапливается ~2M rows, база ~100-300 MB (state_json'ы крупные).
- SQLite тянет, но:
  - `VACUUM` редко зовётся → фактический disk-use больше logical size.
  - `/api/metrics` (task-28) делает `SELECT ... WHERE started_at > ...` —
    без индекса на старте скан всех строк, задержка растёт.
  - Alert checker (task-29) бежит каждые 5 минут — та же деградация.

Нужно:
1. **Автоматический retention** — фоновая задача в lifespan раз в 24ч
   удаляет traces старше `TRACE_RETENTION_DAYS` (default 90).
2. **Admin endpoint** — `DELETE /api/admin/traces` с параметром
   `older_than_days` для ручного purge (RBAC: admin, audit log).
3. Observability: counter удалённых rows на каждый прогон.

**Не добавляем:** partition-стратегии, VACUUM, перенос в Postgres —
это отдельные задачи. Здесь минимальный фикс под реальный disk-fill
риск.

## Files to change
- `sqlite_trace.py` — функция `purge_old_traces(days)` + индекс на
  `traces(started_at)`
- `api/app.py` — новый admin endpoint + background task в `_lifespan`
- `config/settings.py` — 2 новых env-флага
- `monitoring/prometheus.py` — counter
- `.env.example`, `README.md`

## Files to create
- `tests/test_trace_retention.py` — 5 тестов

---

## 1. `config/settings.py`

Рядом с `session_ttl_seconds`:

```python
    trace_retention_days: int = int(
        os.getenv("TRACE_RETENTION_DAYS", "90")
    )
    trace_purge_interval_sec: int = int(
        os.getenv("TRACE_PURGE_INTERVAL_SEC", "86400")  # 24h
    )
```

`TRACE_RETENTION_DAYS=0` — отключает автоматический purge (для dev).

---

## 2. `sqlite_trace.py::purge_old_traces`

Добавить функцию:

```python
def purge_old_traces(retention_days: int) -> dict:
    """Удалить traces старше `retention_days`. Каскадно удаляет trace_steps
    и feedback для этих trace_id (через ON DELETE CASCADE, либо вручную).

    Args:
        retention_days: сколько дней хранить. 0 — ничего не удалять (no-op).

    Returns:
        {"traces_deleted": N, "steps_deleted": M, "feedback_deleted": K}
    """
    if retention_days <= 0:
        return {"traces_deleted": 0, "steps_deleted": 0, "feedback_deleted": 0}

    cutoff_iso = (
        datetime.now(timezone.utc) - timedelta(days=retention_days)
    ).isoformat()

    with _get_connection() as conn:
        cur = conn.cursor()

        # 1. Какие trace_id попадают под purge
        cur.execute(
            "SELECT trace_id FROM traces WHERE started_at < ?",
            (cutoff_iso,),
        )
        old_trace_ids = [row[0] for row in cur.fetchall()]

        if not old_trace_ids:
            return {"traces_deleted": 0, "steps_deleted": 0, "feedback_deleted": 0}

        # 2. Удалить зависимые строки. SQLite не даёт ON DELETE CASCADE
        # по умолчанию — делаем явно. Батчами по 500 чтобы не взрывать
        # SQL `IN (...)` лимитом.
        def _batch(seq, size=500):
            for i in range(0, len(seq), size):
                yield seq[i : i + size]

        steps_deleted = 0
        feedback_deleted = 0
        for batch in _batch(old_trace_ids):
            placeholders = ",".join("?" for _ in batch)
            cur.execute(
                f"DELETE FROM trace_steps WHERE trace_id IN ({placeholders})",
                batch,
            )
            steps_deleted += cur.rowcount
            cur.execute(
                f"DELETE FROM feedback WHERE trace_id IN ({placeholders})",
                batch,
            )
            feedback_deleted += cur.rowcount

        # 3. Удалить сами traces
        cur.execute("DELETE FROM traces WHERE started_at < ?", (cutoff_iso,))
        traces_deleted = cur.rowcount
        conn.commit()

    return {
        "traces_deleted": traces_deleted,
        "steps_deleted": steps_deleted,
        "feedback_deleted": feedback_deleted,
    }
```

**Индекс на `traces(started_at)`** — добавить в `_ensure_tables()` или где
создаются таблицы:

```python
            CREATE INDEX IF NOT EXISTS idx_traces_started_at
            ON traces(started_at);
```

Без индекса `DELETE WHERE started_at < ?` делает full table scan.

**Импорты в начале файла:**
```python
from datetime import datetime, timedelta, timezone
```

(уже должны быть, если `_now_iso()` использует `datetime`).

---

## 3. `monitoring/prometheus.py`

В `__all__`:
```python
    "TRACES_PURGED",
    "record_traces_purged",
```

В `except ImportError`:
```python
    TRACES_PURGED = _NoopMetric()
```

В `else`:
```python
    TRACES_PURGED = Counter(
        "rag_traces_purged_total",
        "SQLite rows deleted by retention purge",
        ["table"],
        registry=REGISTRY,
    )
```

Helper:
```python
def record_traces_purged(table: str, count: int) -> None:
    if count > 0:
        TRACES_PURGED.labels(table=table).inc(count)
```

---

## 4. `api/app.py::_lifespan` — background task

Найти блок, где создаётся `_cleanup_sessions` task (task-16), и рядом
добавить второй:

```python
    async def _purge_old_traces_periodically() -> None:
        settings = get_settings()
        interval = max(60, getattr(settings, "trace_purge_interval_sec", 86400))
        retention = getattr(settings, "trace_retention_days", 90)
        if retention <= 0:
            logger.info("Trace retention disabled (TRACE_RETENTION_DAYS=0)")
            return
        while True:
            await asyncio.sleep(interval)
            try:
                from sqlite_trace import purge_old_traces
                from monitoring.prometheus import record_traces_purged

                result = await asyncio.to_thread(purge_old_traces, retention)
                for table, count in (
                    ("traces", result["traces_deleted"]),
                    ("trace_steps", result["steps_deleted"]),
                    ("feedback", result["feedback_deleted"]),
                ):
                    record_traces_purged(table, count)
                if result["traces_deleted"]:
                    logger.info(
                        "Trace retention purge: traces=%d steps=%d feedback=%d",
                        result["traces_deleted"],
                        result["steps_deleted"],
                        result["feedback_deleted"],
                    )
            except Exception as exc:
                logger.warning("Trace retention purge failed: %s", exc)

    cleanup_task = asyncio.create_task(_cleanup_sessions())
    purge_task = asyncio.create_task(_purge_old_traces_periodically())
```

И в `finally`:
```python
        cleanup_task.cancel()
        purge_task.cancel()
```

**Важно:** `asyncio.to_thread(purge_old_traces, ...)` — purge синхронный
(SQLite sync), нельзя блокировать event loop.

---

## 5. Admin endpoint

Рядом с `/api/admin/circuit-breaker/reset` (task-74):

```python
@router.delete("/admin/traces")
async def admin_purge_traces(
    request: Request,
    older_than_days: int = 30,
    _user: dict = Depends(require_role("admin")),
) -> JSONResponse:
    """Удалить traces старше N дней. Синхронная операция, возвращает
    счётчики удалённых строк."""
    from monitoring.prometheus import record_traces_purged
    from sqlite_trace import purge_old_traces

    if older_than_days < 0 or older_than_days > 3650:
        raise HTTPException(
            status_code=400,
            detail="older_than_days must be in [0, 3650]",
        )

    result = await asyncio.to_thread(purge_old_traces, older_than_days)

    for table, count in (
        ("traces", result["traces_deleted"]),
        ("trace_steps", result["steps_deleted"]),
        ("feedback", result["feedback_deleted"]),
    ):
        record_traces_purged(table, count)

    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="trace_purge",
        resource=f"traces/older_than={older_than_days}d",
        detail=result,
        ip_address=request.client.host if request.client else None,
    )

    return JSONResponse(status_code=200, content=result)
```

---

## 6. `.env.example`

```
# Retention для SQLite traces (дней). 0 — не чистить.
TRACE_RETENTION_DAYS=90
TRACE_PURGE_INTERVAL_SEC=86400
```

## 7. `README.md`

В таблицу env vars:
```
| `TRACE_RETENTION_DAYS` | `90` | retention SQLite traces; 0 = не чистить |
| `TRACE_PURGE_INTERVAL_SEC` | `86400` | интервал фоновой очистки traces |
```

В таблицу API:
```
| DELETE | `/api/admin/traces?older_than_days=N` | ручная очистка старых traces (admin) |
```

---

## 8. `tests/test_trace_retention.py`

```python
"""Тесты retention + admin purge endpoint."""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def temp_trace_db(monkeypatch, tmp_path):
    """Отдельная SQLite для теста."""
    db = tmp_path / "traces.db"
    monkeypatch.setenv("TRACING_DB_PATH", str(db))
    import config.settings as _s
    _s._settings = None

    # Пересоздать таблицы в новой БД
    import sqlite_trace
    sqlite_trace._DB_PATH = str(db)  # если есть module-level константа
    sqlite_trace._ensure_tables() if hasattr(sqlite_trace, "_ensure_tables") else None
    # Если _ensure_tables не экспортирован, тупо создаём:
    conn = sqlite3.connect(str(db))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS traces (
            trace_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            finished_at TEXT
        );
        CREATE TABLE IF NOT EXISTS trace_steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT,
            step_order INTEGER,
            node_name TEXT,
            state_json TEXT,
            ts TEXT
        );
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT,
            rating TEXT,
            ts TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_traces_started_at ON traces(started_at);
    """)
    conn.commit()
    conn.close()
    yield db


def _insert_trace(db: Path, trace_id: str, days_ago: int):
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn = sqlite3.connect(str(db))
    conn.execute("INSERT INTO traces VALUES (?, ?, NULL)", (trace_id, ts))
    conn.execute(
        "INSERT INTO trace_steps (trace_id, step_order, node_name, state_json, ts) VALUES (?, 0, 'x', '{}', ?)",
        (trace_id, ts),
    )
    conn.execute(
        "INSERT INTO feedback (trace_id, rating, ts) VALUES (?, 'up', ?)",
        (trace_id, ts),
    )
    conn.commit()
    conn.close()


def test_purge_deletes_old_and_keeps_new(temp_trace_db):
    from sqlite_trace import purge_old_traces

    _insert_trace(temp_trace_db, "old-1", days_ago=100)
    _insert_trace(temp_trace_db, "old-2", days_ago=95)
    _insert_trace(temp_trace_db, "new-1", days_ago=10)

    result = purge_old_traces(retention_days=90)

    assert result["traces_deleted"] == 2
    assert result["steps_deleted"] == 2
    assert result["feedback_deleted"] == 2

    conn = sqlite3.connect(str(temp_trace_db))
    remaining = [r[0] for r in conn.execute("SELECT trace_id FROM traces")]
    assert remaining == ["new-1"]
    conn.close()


def test_purge_with_zero_retention_is_noop(temp_trace_db):
    from sqlite_trace import purge_old_traces

    _insert_trace(temp_trace_db, "old-1", days_ago=365)
    result = purge_old_traces(retention_days=0)

    assert result["traces_deleted"] == 0
    conn = sqlite3.connect(str(temp_trace_db))
    count = conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0]
    assert count == 1
    conn.close()


def test_purge_handles_empty_table(temp_trace_db):
    from sqlite_trace import purge_old_traces
    result = purge_old_traces(retention_days=30)
    assert result == {"traces_deleted": 0, "steps_deleted": 0, "feedback_deleted": 0}


def test_admin_purge_endpoint_returns_counts(client, temp_trace_db):
    from auth.jwt_handler import create_access_token

    _insert_trace(temp_trace_db, "ancient", days_ago=200)
    token = create_access_token("admin", "admin")

    resp = client.request(
        "DELETE",
        "/api/admin/traces?older_than_days=30",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["traces_deleted"] >= 1


def test_admin_purge_rejects_non_admin(client, temp_trace_db):
    from auth.jwt_handler import create_access_token
    token = create_access_token("viewer-user", "viewer")

    resp = client.request(
        "DELETE",
        "/api/admin/traces?older_than_days=30",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
```

**Замечания:**
- `client.request("DELETE", ...)` — потому что TestClient не имеет
  `.delete()` с query params + headers в одном call'е в некоторых версиях.
  Если `client.delete(...)` работает — использовать.
- Fixture `temp_trace_db` пересоздаёт таблицы в temp-пути. Это изолирует
  тест от глобальной БД.
- Если `sqlite_trace._DB_PATH` / `_ensure_tables` называются иначе —
  посмотреть в коде и адаптировать.

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **141+ passed** (136 было + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Purge использует `asyncio.to_thread` — не блокирует event loop.
- Индекс на `traces(started_at)` — обязателен (без него O(n) на каждом
  purge'е).
- Admin endpoint пишет audit-запись через существующий `log_audit`.
- Background task корректно отменяется в `finally` lifespan'а.

## DONE WHEN
- [ ] `purge_old_traces(days)` в `sqlite_trace.py` удаляет traces, steps,
      feedback каскадно; возвращает dict счётчиков
- [ ] Индекс `idx_traces_started_at` создаётся при инициализации
- [ ] Background task в `_lifespan` запускается раз в `TRACE_PURGE_INTERVAL_SEC`
- [ ] `DELETE /api/admin/traces?older_than_days=N` — admin only, audit,
      400 при невалидных значениях
- [ ] `rag_traces_purged_total{table}` counter инкрементится после каждого
      purge'а
- [ ] 2 env-флага в Settings, .env.example, README
- [ ] `tests/test_trace_retention.py` — 5 тестов, все проходят
- [ ] `pytest tests/ -v` — 141+ passed
- [ ] `ruff check .` — 0 errors
