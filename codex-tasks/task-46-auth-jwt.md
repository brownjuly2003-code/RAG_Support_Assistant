# Task 46 — AUTH-1: JWT-based authentication

## Goal
Заменить простой API key на JWT tokens с access + refresh.
Новые endpoints: `/api/auth/login`, `/api/auth/refresh`.
Существующий X-API-Key auth остаётся как fallback для обратной совместимости.

## Dependencies
- task-43 (SQLAlchemy модели — таблица users)

## Files to create
- `auth/__init__.py`
- `auth/jwt_handler.py` — create/verify JWT
- `auth/dependencies.py` — FastAPI dependencies
- `db/models.py` — добавить модель User
- `tests/test_jwt_auth.py`

## Files to change
- `requirements.txt` — добавить PyJWT, passlib[bcrypt]
- `api/app.py` — новые auth endpoints, обновить `_require_api_key`

---

## 1. requirements.txt

Добавить:
```
PyJWT>=2.8.0
passlib[bcrypt]>=1.7.4
```

---

## 2. auth/__init__.py

```python
"""Authentication — JWT tokens + legacy API key."""
```

---

## 3. auth/jwt_handler.py

```python
"""JWT token creation and verification."""
from __future__ import annotations

import os
import time
from typing import Optional

import jwt

JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = int(os.getenv("JWT_ACCESS_TTL", "3600"))       # 1 hour
REFRESH_TOKEN_TTL = int(os.getenv("JWT_REFRESH_TTL", "604800"))   # 7 days


def create_access_token(user_id: str, role: str = "viewer") -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int(time.time()) + ACCESS_TOKEN_TTL,
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + REFRESH_TOKEN_TTL,
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str, expected_type: str = "access") -> Optional[dict]:
    """Verify and decode JWT. Returns payload dict or None."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        if payload.get("type") != expected_type:
            return None
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
```

---

## 4. auth/dependencies.py

```python
"""FastAPI dependencies for authentication."""
from __future__ import annotations

import hmac
from typing import Optional

from fastapi import HTTPException, Request

from auth.jwt_handler import verify_token


def get_current_user(request: Request) -> dict:
    """Authenticate via Bearer JWT or legacy X-API-Key.

    Returns dict with keys: sub, role.
    """
    # Try JWT first
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = verify_token(token, expected_type="access")
        if payload is None:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        return {"sub": payload["sub"], "role": payload.get("role", "viewer")}

    # Fallback: legacy X-API-Key
    from config.settings import get_settings
    settings = get_settings()
    expected = getattr(settings, "api_key", "")
    if not expected:
        return {"sub": "anonymous", "role": "admin"}  # auth disabled in dev

    provided = request.headers.get("X-API-Key", "")
    if not provided:
        raise HTTPException(status_code=401, detail="Authorization required")
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return {"sub": "api-key-user", "role": "admin"}


def require_role(*roles: str):
    """Dependency factory — require specific role(s)."""
    def dependency(request: Request) -> dict:
        user = get_current_user(request)
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"Role '{user['role']}' not authorized")
        return user
    return dependency
```

---

## 5. db/models.py — добавить User

Добавить модель после `Session`:

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="viewer")  # admin | agent | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
```

---

## 6. api/app.py — auth endpoints

Добавить после существующих endpoints:

```python
from pydantic import BaseModel

class LoginRequest(BaseModel):
    username: str = Field(..., max_length=100)
    password: str = Field(..., max_length=200)

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Authenticate and return JWT tokens."""
    from auth.jwt_handler import create_access_token, create_refresh_token
    from passlib.hash import bcrypt

    # TODO: task-47 подключит реальную БД. Пока — env-based single user.
    import os
    admin_user = os.getenv("ADMIN_USERNAME", "admin")
    admin_hash = os.getenv("ADMIN_PASSWORD_HASH", "")

    if not admin_hash:
        # Dev mode: accept admin/admin
        if body.username == "admin" and body.password == "admin":
            return TokenResponse(
                access_token=create_access_token("admin", "admin"),
                refresh_token=create_refresh_token("admin"),
            )
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if body.username != admin_user or not bcrypt.verify(body.password, admin_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return TokenResponse(
        access_token=create_access_token(body.username, "admin"),
        refresh_token=create_refresh_token(body.username),
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest):
    """Refresh access token."""
    from auth.jwt_handler import create_access_token, create_refresh_token, verify_token

    payload = verify_token(body.refresh_token, expected_type="refresh")
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    return TokenResponse(
        access_token=create_access_token(payload["sub"], payload.get("role", "viewer")),
        refresh_token=create_refresh_token(payload["sub"]),
    )
```

---

## 7. tests/test_jwt_auth.py

```python
"""JWT authentication tests."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    import config.settings as _s
    _s._settings = None
    from api.app import app
    return TestClient(app)


def test_login_dev_mode(client):
    """В dev mode (без ADMIN_PASSWORD_HASH) admin/admin работает."""
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password(client):
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_refresh_token(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    tokens = login.json()

    resp = client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_protected_endpoint_with_jwt(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    token = login.json()["access_token"]

    resp = client.post(
        "/api/ask",
        json={"question": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code not in (401, 403)
```

---

## CONSTRAINTS
- Создать `auth/` пакет
- JWT + legacy X-API-Key оба работают
- Dev mode: admin/admin логин (без env vars)
- `JWT_SECRET` через env var (ОБЯЗАТЕЛЬНО менять в production)
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `POST /api/auth/login` → access + refresh tokens
- [ ] `POST /api/auth/refresh` → новый access token
- [ ] `Authorization: Bearer <token>` работает на protected endpoints
- [ ] `X-API-Key` по-прежнему работает (обратная совместимость)
- [ ] `pytest tests/ -v` — проходит
