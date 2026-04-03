# Task 07 — API key authentication

## Problem
The API is completely open — anyone who can reach port 8000 can call /api/ask.
Need a simple API key guard on write endpoints.

## Changes needed in 2 files

### 1. config/settings.py
Add one field to `Settings` (after `session_ttl_seconds`):

```python
# API key guard. Empty string = auth disabled (dev mode).
api_key: str = os.getenv("API_KEY", "")
```

### 2. api/app.py
Add a dependency function and apply it to protected endpoints.

**Add this function** after the `limiter = Limiter(...)` line:

```python
def _require_api_key(request: Request) -> None:
    """FastAPI dependency — validates X-API-Key header if API_KEY is configured."""
    settings = get_settings()
    expected = getattr(settings, "api_key", "")
    if not expected:
        return  # auth disabled
    provided = request.headers.get("X-API-Key", "")
    if not provided:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    if provided != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")
```

**Update /api/ask endpoint signature** — add `Depends(_require_api_key)`:

Before:
```python
@router.post("/ask", response_model=AskResponse)
@limiter.limit("60/minute")
async def ask(request: Request, body: AskRequest) -> AskResponse:
```

After:
```python
from fastapi import Depends

@router.post("/ask", response_model=AskResponse)
@limiter.limit("60/minute")
async def ask(
    request: Request,
    body: AskRequest,
    _auth: None = Depends(_require_api_key),
) -> AskResponse:
```

**Update /api/upload endpoint signature** the same way:

Before:
```python
@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_document(request: Request, file: UploadFile = File(...)) -> UploadResponse:
```

After:
```python
@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    _auth: None = Depends(_require_api_key),
) -> UploadResponse:
```

### 3. .env.example
Add after `SESSION_TTL_SECONDS`:

```
# API key for protecting /api/ask and /api/upload. Leave empty to disable auth.
API_KEY=
```

## New test — tests/test_api_key_auth.py

```python
from fastapi.testclient import TestClient
import pytest

@pytest.fixture
def client_with_key(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret123")
    # Re-create settings singleton with new env
    import config.settings as _s
    _s._settings = None
    from api.app import app
    return TestClient(app)

def test_ask_without_key_returns_401(client_with_key):
    resp = client_with_key.post("/api/ask", json={"question": "test"})
    assert resp.status_code == 401

def test_ask_with_wrong_key_returns_403(client_with_key):
    resp = client_with_key.post(
        "/api/ask", json={"question": "test"},
        headers={"X-API-Key": "wrong"}
    )
    assert resp.status_code == 403

def test_ask_with_correct_key_passes_auth(client_with_key):
    resp = client_with_key.post(
        "/api/ask", json={"question": "test"},
        headers={"X-API-Key": "secret123"}
    )
    # Auth passed — may return 200 or pipeline error, but NOT 401/403
    assert resp.status_code not in (401, 403)
```

## CONSTRAINTS
- Touch only: config/settings.py, api/app.py, .env.example, tests/test_api_key_auth.py (new)
- `from fastapi import Depends` — add to existing import line in api/app.py, don't duplicate
- When API_KEY="" (default), auth is completely disabled — existing tests must still pass
- ruff check on each modified file → 0 errors

## DONE WHEN
- [ ] `pytest tests/ -v` → 19 passed, 0 failed
- [ ] `curl -X POST http://localhost:8000/api/ask` with `API_KEY=x` set → 401
- [ ] `curl -H "X-API-Key: x" ...` → not 401/403
