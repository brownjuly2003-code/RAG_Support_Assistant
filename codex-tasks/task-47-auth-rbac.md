# Task 47 — AUTH-2: RBAC — роли admin, agent, viewer

## Goal
Добавить Role-Based Access Control. Три роли:
- **admin** — полный доступ (все endpoints + /api/sessions)
- **agent** — /api/ask, /api/upload, /api/feedback, /api/sessions
- **viewer** — только /api/ask (read-only)

## Dependencies
- task-46 (JWT auth + `require_role` dependency)

## Files to change
- `api/app.py` — применить `require_role()` на endpoints
- `auth/dependencies.py` — если нужны правки

---

## api/app.py

Импорт:
```python
from auth.dependencies import get_current_user, require_role
```

Применить роли на endpoints:

### /api/ask — viewer, agent, admin
```python
@router.post("/ask", response_model=AskResponse)
@limiter.limit("60/minute")
async def ask(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
) -> AskResponse:
```

### /api/ask/stream — viewer, agent, admin
```python
@router.post("/ask/stream")
@limiter.limit("60/minute")
async def ask_stream(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
):
```

### /api/upload — agent, admin
```python
@router.post("/upload", response_model=UploadResponse)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    _user: dict = Depends(require_role("agent", "admin")),
) -> UploadResponse:
```

### /api/feedback — viewer, agent, admin (все могут давать feedback)
```python
async def submit_feedback(
    request: Request,
    body: FeedbackRequest,
    _user: dict = Depends(get_current_user),
):
```

### /api/sessions (list) — agent, admin
```python
async def list_sessions(
    _user: dict = Depends(require_role("agent", "admin")),
):
```

### /api/metrics — admin
```python
async def get_metrics(
    _user: dict = Depends(require_role("admin")),
):
```

### /api/health — без auth (публичный)
Оставить без изменений.

Убрать старый `_require_api_key` dependency из всех endpoints — его заменяет `get_current_user`.

---

## CONSTRAINTS
- Изменить только `api/app.py`
- Удалить `_require_api_key` function и все `Depends(_require_api_key)`
- `/api/health` остаётся без auth
- `/api/auth/login` и `/api/auth/refresh` — без auth
- viewer получает 403 на /api/upload
- `pytest tests/ -v` — проходит (обновить test_api_key_auth.py если нужно)

## DONE WHEN
- [ ] `_require_api_key` удалён из api/app.py
- [ ] Все protected endpoints используют `get_current_user` или `require_role`
- [ ] viewer → POST /api/upload → 403
- [ ] admin → POST /api/upload → не 403
- [ ] `/api/health` доступен без auth
- [ ] `pytest tests/ -v` — проходит
