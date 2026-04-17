# Task 91 — MULTI-TENANCY Phase 1: `tenant_id` в схеме (без enforcement)

## Goal
Проект пока single-tenant: весь vector store, traces, audit_log — общие для
всех пользователей. Это блокирует B2B-use-case (компании не могут делить
инстанс). rec.md §2.2 классифицирует multi-tenancy как **HIGH** приоритет.

Multi-tenancy — большая тема, делаем в **4 фазы** под отдельные задачи:
- **91 (эта)**: добавить `tenant_id` column в schema + Pydantic + state,
  **без enforcement**. Безопасно: все строки получают `tenant_id="default"`.
- 93: propagation из JWT claim в request/graph/audit
- 95: query enforcement (все SELECT WHERE tenant_id = current_tenant_id)
- 96: per-tenant ChromaDB collections

**Phase 1 — no-risk**: добавляем поля, дефолтом заполняем, ничего не
ломается. Deploy можно без миграции бизнес-логики.

## Files to change
- `db/models.py` — `tenant_id` column в `AuditLog`, `Session` (и другие tenant-bound таблицы)
- `state.py` — `tenant_id` в `GraphState`
- `api/app.py` — `tenant_id: str = "default"` в релевантных Pydantic моделях
- `sqlite_trace.py` — `tenant_id` column в `traces` таблице

## Files to create
- `alembic/versions/003_add_tenant_id.py` — миграция Postgres
- `tests/test_tenant_id_schema.py` — 4 теста

---

## 1. `db/models.py`

В каждую tenant-bound модель:

```python
class AuditLog(Base):
    # ... existing fields ...
    tenant_id: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="default", index=True
    )


class Session(Base):  # если таблица sessions создана в task-48
    # ... existing fields ...
    tenant_id: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="default", index=True
    )
```

`User` модель **не** трогаем — один пользователь может обслуживать
несколько tenants (опционально). Связь user↔tenant — отдельная таблица
(будет в Phase 2-3, если вообще понадобится).

`server_default="default"` гарантирует, что существующие строки
при применении миграции получат `tenant_id="default"` без NULL'ов.

---

## 2. `alembic/versions/003_add_tenant_id.py`

```python
"""add tenant_id columns

Revision ID: 003
Revises: 002
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"


TENANT_TABLES = ["audit_log", "sessions"]  # обновить под реальный набор


def upgrade() -> None:
    for table in TENANT_TABLES:
        op.add_column(
            table,
            sa.Column(
                "tenant_id",
                sa.String(50),
                nullable=False,
                server_default="default",
            ),
        )
        op.create_index(
            f"idx_{table}_tenant_id",
            table,
            ["tenant_id"],
            if_not_exists=True,
        )


def downgrade() -> None:
    for table in TENANT_TABLES:
        op.drop_index(f"idx_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")
```

Если в `db/models.py` нет таблицы `sessions` (persistent sessions не
дошли в прод) — убрать из `TENANT_TABLES`. Сверить по реальным
`alembic/versions/*`.

---

## 3. `state.py`

```python
class GraphState(TypedDict, total=False):
    # ... existing fields ...
    tenant_id: str  # default "default", заполняется в create_initial_state


def create_initial_state(
    question: str,
    trace_id: str,
    tenant_id: str = "default",
    # ... other args ...
) -> GraphState:
    return GraphState(
        question=question,
        trace_id=trace_id,
        tenant_id=tenant_id,
        # ...
    )
```

Обновить все вызовы `create_initial_state` в `api/app.py` и `graph.py` —
пока все передают `tenant_id="default"`.

---

## 4. `api/app.py` — Pydantic

В моделях, которые связаны с tenant (upload, ask, session create):

```python
class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=100)
    tenant_id: str = Field(default="default", max_length=50, pattern=r"^[a-zA-Z0-9_\-]+$")
```

**НЕ** удаляем default — в Phase 1 клиент может не передавать
`tenant_id`, получает "default". Pattern валидирует формат
(только alphanum+dash+underscore, макс 50 символов).

Аналогично в `UploadResponse`, `HistoryResponse` — поле `tenant_id`
в **ответе**, чтобы клиент видел, в каком tenant'е он находится.

---

## 5. `sqlite_trace.py`

В `CREATE TABLE traces`:
```sql
CREATE TABLE IF NOT EXISTS traces (
    trace_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    tenant_id TEXT NOT NULL DEFAULT 'default'
);
CREATE INDEX IF NOT EXISTS idx_traces_tenant_id ON traces(tenant_id);
```

Обновить `start_trace`:
```python
def start_trace(trace_id: str | None = None, tenant_id: str = "default") -> str:
    if trace_id is None:
        trace_id = str(uuid.uuid4())
    with _get_connection() as conn:
        conn.execute(
            "INSERT INTO traces (trace_id, started_at, tenant_id) VALUES (?, ?, ?)",
            (trace_id, _now_iso(), tenant_id),
        )
        conn.commit()
    return trace_id
```

SQLite автоматически подставит `default` через column DEFAULT, если
существующий код зовёт `INSERT INTO traces (trace_id, started_at)` без
tenant_id — **важно**: старый код не ломаем.

---

## 6. `tests/test_tenant_id_schema.py`

```python
"""Phase 1 — schema-level tests (no enforcement)."""
from __future__ import annotations

import pytest


def test_graph_state_accepts_tenant_id() -> None:
    from state import GraphState, create_initial_state

    s = create_initial_state(question="x", trace_id="t1", tenant_id="acme-corp")
    assert s["tenant_id"] == "acme-corp"


def test_graph_state_defaults_to_default_tenant() -> None:
    from state import create_initial_state

    s = create_initial_state(question="x", trace_id="t1")
    assert s["tenant_id"] == "default"


def test_ask_request_accepts_tenant_id(mock_pipeline, client) -> None:
    resp = client.post(
        "/api/ask",
        json={"question": "hi", "tenant_id": "customer-42"},
    )
    assert resp.status_code == 200


def test_ask_request_rejects_malformed_tenant_id(client) -> None:
    resp = client.post(
        "/api/ask",
        json={"question": "hi", "tenant_id": "bad tenant; DROP"},
    )
    assert resp.status_code == 422  # Pydantic validation


def test_sqlite_trace_accepts_tenant_id(tmp_path, monkeypatch) -> None:
    """start_trace пишет tenant_id в новую строку."""
    import sqlite3
    import sqlite_trace

    db = tmp_path / "t.db"
    monkeypatch.setenv("TRACING_DB_PATH", str(db))
    # Если _DB_PATH / _ensure_tables имеют другие имена — адаптировать
    sqlite_trace._DB_PATH = str(db)
    sqlite_trace._ensure_tables()

    tid = sqlite_trace.start_trace(tenant_id="megacorp")
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT tenant_id FROM traces WHERE trace_id=?", (tid,)
    ).fetchone()
    conn.close()
    assert row[0] == "megacorp"
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- **`pytest tests/ -v` — 165+ passed** (161 + 4 новых). 
- `ruff check .` — 0 errors.
- Существующий код, НЕ передающий `tenant_id`, продолжает работать —
  default `"default"` на всех уровнях (SQL, Python, Pydantic).
- Alembic миграция 003 проходит `alembic upgrade head` без ошибок
  при наличии Postgres.
- **НИКАКОГО enforcement** в этой фазе — queries пока не фильтруются по
  `tenant_id`. Это Phase 3 (task-95).

## DONE WHEN
- [ ] `tenant_id` column в `AuditLog` + sessions, с `server_default="default"`
- [ ] Alembic миграция 003 создана и корректна
- [ ] `GraphState` имеет `tenant_id`; `create_initial_state` принимает
      параметр с default
- [ ] Все Pydantic-модели, релевантные для tenant, имеют `tenant_id`
      с валидацией regex
- [ ] `sqlite_trace.traces` имеет column `tenant_id` + index; `start_trace`
      принимает параметр
- [ ] Старые вызовы `INSERT INTO traces (trace_id, started_at)` продолжают
      работать (SQL-level DEFAULT)
- [ ] 4 теста в `tests/test_tenant_id_schema.py` проходят
- [ ] `pytest tests/ -v` — 165+ passed
- [ ] `ruff check .` — 0 errors
