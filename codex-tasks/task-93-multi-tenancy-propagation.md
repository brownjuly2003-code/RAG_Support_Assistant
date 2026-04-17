# Task 93 — MULTI-TENANCY Phase 2: propagation из JWT в pipeline

## Goal
Phase 1 (task-91) добавил **поле** `tenant_id` в schema/state/Pydantic
с дефолтом `"default"`. Но сейчас никто не заполняет его: все пользователи
всегда получают `tenant_id="default"`.

Phase 2 — научить систему **реально различать tenants**:

1. **JWT claim**: access-token несёт `tenant` в payload.
2. **Dependency**: `get_current_user` возвращает `{"sub", "role", "tenant"}`.
3. **Request-scoped ContextVar**: параллельно с `request_id` (task-79),
   добавить `current_tenant`.
4. **Propagation**: `run_qa_pipeline` и `ConversationSession.ask` принимают
   `tenant_id`, прокидывают в `create_initial_state`, `start_trace`,
   `log_audit`.
5. **НЕ** добавляем query enforcement (это Phase 3 / task-95).

После этой задачи: трейсы в SQLite и audit entries в Postgres получают
**реальный** `tenant_id` из JWT, но SELECT'ы пока возвращают данные всех
tenants — т.е. разделения данных между tenants **нет**. Это безопасно
для единственного tenant'а ("default") и подготавливает почву для Phase 3.

## Files to change
- `auth/jwt_handler.py` — `tenant` в payload access + refresh tokens
- `auth/dependencies.py` — return `tenant` в user-dict
- `api/correlation.py` — добавить `current_tenant` ContextVar + helper'ы
- `api/app.py::_request_id` middleware — выставлять tenant в ContextVar
- `api/app.py::ask` — брать tenant, передавать в `session.ask(..., tenant_id=...)`
- `graph.py::run_qa_pipeline` и `ConversationSession.ask` — параметр
  `tenant_id`, передача в `create_initial_state` и `start_trace`
- `sqlite_trace.py::log_step` — использовать tenant из state

## Files to create
- `tests/test_tenant_propagation.py` — 6 тестов

---

## 1. JWT

### `auth/jwt_handler.py`

```python
def create_access_token(
    user_id: str, role: str = "viewer", tenant: str = "default"
) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "tenant": tenant,
        "exp": int(time.time()) + ACCESS_TOKEN_TTL,
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(
    user_id: str, role: str = "viewer", tenant: str = "default"
) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "tenant": tenant,
        "exp": int(time.time()) + REFRESH_TOKEN_TTL,
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
```

### `auth/dependencies.py`

```python
def get_current_user(request: Request, settings: object | None = None) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        from auth.jwt_handler import verify_token

        token = auth_header[7:]
        payload = verify_token(token, expected_type="access")
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return {
            "sub": payload["sub"],
            "role": payload.get("role", "viewer"),
            "tenant": payload.get("tenant", "default"),
        }
    # ... API-key branch — возвращаем default tenant:
    # {"sub": ..., "role": ..., "tenant": "default"}
```

### `api/app.py::login` и `refresh_token`

Все вызовы `create_access_token(..., ...)` и `create_refresh_token(..., ...)`
должны передавать tenant третьим аргументом. В dev-ветке (ADMIN_PASSWORD_HASH
отсутствует) tenant = "default". В prod-ветке — брать из ENV
`ADMIN_DEFAULT_TENANT` (default "default").

---

## 2. ContextVar для tenant

### `api/correlation.py`

Добавить:

```python
_current_tenant: ContextVar[Optional[str]] = ContextVar(
    "current_tenant", default=None
)


def set_current_tenant(value: Optional[str]) -> None:
    _current_tenant.set(value)


def get_current_tenant() -> Optional[str]:
    return _current_tenant.get()
```

### `api/app.py::_request_id` middleware — НЕ менять

`_request_id` не знает про tenant (tenant приходит из JWT, middleware
работает **до** auth-dependency). Правильное место — внутри handler'а,
сразу после `get_current_user`. Но это 7+ endpoint'ов.

**Лучше**: добавить **второй** middleware `_tenant_context`, который:
- Пробует extract tenant из Authorization header (как делает
  `get_current_user`, но без raise на invalid).
- Если получилось — `set_current_tenant(...)`.
- Если нет (нет header, невалидный токен, API-key) — `set_current_tenant("default")`.

```python
@app.middleware("http")
async def _tenant_context(request: Request, call_next: Any) -> Any:
    from api.correlation import set_current_tenant

    tenant = "default"
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from auth.jwt_handler import verify_token

            token = auth_header[7:]
            payload = verify_token(token, expected_type="access")
            if payload is not None:
                tenant = payload.get("tenant", "default")
        except Exception:
            pass  # silent fallback — auth-dependency сама отдаст 401

    set_current_tenant(tenant)
    return await call_next(request)
```

**Порядок middleware'ов в `api/app.py`** (напомним, FastAPI стек
**reversed**, последний зарегистрированный — первый вызванный):

```
# file top → bottom:
@app.middleware("http")
async def _http_metrics(...):     # innermost (вызывается последним на пути in)
    ...

@app.middleware("http")
async def _log_requests(...):
    ...

@app.middleware("http")
async def _request_id(...):
    ...

@app.middleware("http")
async def _tenant_context(...):   # outermost (вызывается первым на пути in)
    ...
```

`_tenant_context` должен быть **последним зарегистрированным**, чтобы
`get_current_tenant()` в handler'ах уже работал.

---

## 3. Pipeline propagation

### `graph.py::run_qa_pipeline`

```python
def run_qa_pipeline(
    question: str,
    retriever: Any,
    llm: SupportsInvoke | None = None,
    max_iterations: int = 2,
    chat_history: List[Dict[str, str]] | None = None,
    trace_id: str | None = None,
    tenant_id: str = "default",
) -> GraphState:
    trace_id = start_trace(trace_id=trace_id, tenant_id=tenant_id)
    initial_state = create_initial_state(
        question=question, trace_id=trace_id, tenant_id=tenant_id
    )
    # ... rest unchanged ...
```

### `ConversationSession.ask`

```python
def ask(
    self, question: str, trace_id: Optional[str] = None, tenant_id: str = "default"
) -> GraphState:
    result = run_qa_pipeline(
        question=question,
        retriever=self._retriever,
        llm=self._llm,
        max_iterations=self._max_iterations,
        chat_history=self._history,
        trace_id=trace_id,
        tenant_id=tenant_id,
    )
    # ... rest unchanged ...
```

### `api/app.py::ask` handler

```python
from api.correlation import get_current_tenant

# В месте вызова session.ask:
tenant = get_current_tenant() or "default"
result = await asyncio.wait_for(
    asyncio.to_thread(session.ask, question, get_request_id(), tenant),
    timeout=timeout,
)
```

Позиционный порядок `session.ask(question, trace_id, tenant_id)` —
совпадает с сигнатурой выше.

---

## 4. Audit и trace_log

### `api/app.py` везде, где зовётся `log_audit`

Добавить `tenant` в `detail` или отдельным полем. Проще всего — в detail:

```python
await log_audit(
    actor=_user.get("sub", "anonymous"),
    action="ask",
    resource="rag",
    detail={"tenant": _user.get("tenant", "default"), ...},
    ip_address=...,
)
```

Это не требует миграции schema (tenant_id у audit_log уже есть из task-91,
но для упрощения Phase 2 пишем в detail; Phase 3 перенесёт в column).

### `sqlite_trace.py::log_step`

Пробрасывать `tenant_id` из state в INSERT:

```python
def log_step(trace_id: str, node_name: str, state: Any) -> None:
    tenant = (
        state.get("tenant_id", "default") if isinstance(state, dict) else "default"
    )
    # ... существующая логика INSERT в trace_steps, но tenant пишем
    # в traces table, не в каждую строку trace_steps (в traces уже есть column).
```

На самом деле `traces.tenant_id` заполняется при `start_trace(tenant_id=...)`
— этого достаточно. `trace_steps` наследуют tenant через JOIN по trace_id.
Ничего дополнительного.

---

## 5. `tests/test_tenant_propagation.py`

```python
"""Тесты propagation tenant из JWT в pipeline."""
from __future__ import annotations

from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token


def _token(tenant: str = "default", role: str = "admin") -> dict:
    t = create_access_token("u1", role, tenant)
    return {"Authorization": f"Bearer {t}"}


def test_jwt_access_token_encodes_tenant() -> None:
    from auth.jwt_handler import verify_token
    t = create_access_token("u1", "admin", "acme-corp")
    payload = verify_token(t, expected_type="access")
    assert payload["tenant"] == "acme-corp"


def test_get_current_user_extracts_tenant(client: TestClient) -> None:
    """Прокси-тест через любой protected endpoint — если он принимает
    request, user['tenant'] будет доступен. Проверяем через /api/sessions."""
    resp = client.get("/api/sessions", headers=_token("megacorp", "admin"))
    # любой 2xx — главное не 401/403 на наш валидный токен
    assert resp.status_code < 400


def test_context_var_set_by_middleware(monkeypatch, client: TestClient) -> None:
    """После middleware get_current_tenant() возвращает tenant из JWT."""
    captured: dict = {}

    # Хук в handler. Монкипатчим любой лёгкий endpoint.
    from api.correlation import get_current_tenant

    original = client.app.router  # noqa: F841 — нужен только для type-hint
    from fastapi import APIRouter
    debug_router = APIRouter()

    @debug_router.get("/_test_tenant")
    async def _test_endpoint():
        captured["tenant"] = get_current_tenant()
        return {"ok": True}

    client.app.include_router(debug_router)

    resp = client.get("/_test_tenant", headers=_token("tenant-x"))
    assert resp.status_code == 200
    assert captured["tenant"] == "tenant-x"


def test_no_auth_defaults_to_default_tenant(client: TestClient) -> None:
    """Без Bearer — tenant = default."""
    from api.correlation import get_current_tenant
    captured: dict = {}

    from fastapi import APIRouter
    debug_router = APIRouter()

    @debug_router.get("/_test_tenant_default")
    async def _test():
        captured["tenant"] = get_current_tenant()
        return {"ok": True}

    client.app.include_router(debug_router)

    resp = client.get("/_test_tenant_default")
    assert resp.status_code == 200
    assert captured["tenant"] == "default"


def test_run_qa_pipeline_writes_tenant_to_trace(tmp_path, monkeypatch) -> None:
    """start_trace должен записать tenant_id из аргумента."""
    import sqlite3
    import sqlite_trace

    db = tmp_path / "t.db"
    sqlite_trace._DB_PATH = str(db)
    sqlite_trace._ensure_tables()

    tid = sqlite_trace.start_trace(tenant_id="acme")
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT tenant_id FROM traces WHERE trace_id=?", (tid,)
    ).fetchone()
    conn.close()
    assert row[0] == "acme"


def test_ask_endpoint_propagates_tenant_to_graph(
    monkeypatch, mock_pipeline, client: TestClient
) -> None:
    """/api/ask с tenant-JWT → session.ask(..., tenant_id='acme')."""
    seen: dict = {}

    def _spy_ask(question, trace_id=None, tenant_id="default"):
        seen["tenant_id"] = tenant_id
        return {"answer": "ok", "quality_score": 90, "route": "auto", "trace_id": trace_id}

    class FakeSession:
        ask = staticmethod(_spy_ask)
        _history: list = []

    monkeypatch.setattr(
        "api.app._get_or_create_session",
        lambda sid: ("sid", FakeSession()),
    )

    resp = client.post(
        "/api/ask",
        json={"question": "?"},
        headers=_token("acme-corp"),
    )
    assert resp.status_code == 200
    assert seen["tenant_id"] == "acme-corp"
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **190+ passed** (184 + 6 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Существующий код без tenant-awareness продолжает работать (defaults
  `"default"` везде).
- JWT payload теперь содержит `tenant` — **старые токены** с существующим
  payload (без tenant) должны parseить'ся через `payload.get("tenant", "default")`.
- **Никакого query enforcement** в этой фазе — только propagation.
- Существующие тесты (audit, jwt_auth, admin) **не** должны потребовать
  правок.

## DONE WHEN
- [ ] JWT access + refresh tokens содержат `tenant` claim
- [ ] `get_current_user` возвращает dict с `tenant` key
- [ ] `api/correlation.py` экспортирует `get_current_tenant` и
      `set_current_tenant`
- [ ] Middleware `_tenant_context` заполняет ContextVar из JWT, default "default"
- [ ] `run_qa_pipeline`, `ConversationSession.ask`, `start_trace`
      принимают `tenant_id`
- [ ] `api/app.py::ask` передаёт `get_current_tenant()` в pipeline
- [ ] SQLite `traces.tenant_id` содержит реальное значение из JWT,
      не всегда "default"
- [ ] 6 тестов в `tests/test_tenant_propagation.py` проходят
- [ ] `pytest tests/ -v` — 190+ passed
- [ ] `ruff check .` — 0 errors
