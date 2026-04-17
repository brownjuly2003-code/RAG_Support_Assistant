# Task 68 — Post-review fixes: JWT role, Alembic migration, JWT secret, ruff errors

## Goal
Четыре замечания из code review после выполнения задач 36-67.
Все некритичные, но должны быть исправлены до production.

## Files to change
- `auth/jwt_handler.py` — сохранять role в refresh token
- `api/app.py` — использовать role из refresh token
- `auth/jwt_handler.py` — увеличить default JWT_SECRET до ≥32 байт
- `monitoring/prometheus.py` — убрать unused imports
- `channels/telegram_bot.py` — исправить import order
- `tests/test_jwt_auth.py` — убрать unused `import pytest`

## Files to create
- `alembic/versions/002_add_users_audit_log.py` — миграция для недостающих таблиц

---

## 1. JWT refresh token теряет роль

### auth/jwt_handler.py — create_refresh_token

было:
```python
def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": int(time.time()) + REFRESH_TOKEN_TTL,
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
```

стало:
```python
def create_refresh_token(user_id: str, role: str = "viewer") -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "exp": int(time.time()) + REFRESH_TOKEN_TTL,
        "type": "refresh",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
```

### api/app.py — login endpoint

Везде где вызывается `create_refresh_token`, передать role:

было:
```python
    return TokenResponse(
        access_token=create_access_token("admin", "admin"),
        refresh_token=create_refresh_token("admin"),
    )
```

стало:
```python
    return TokenResponse(
        access_token=create_access_token("admin", "admin"),
        refresh_token=create_refresh_token("admin", "admin"),
    )
```

Аналогично для всех остальных вызовов `create_refresh_token` — передать текущую роль пользователя.

---

## 2. JWT_SECRET default ≥32 байт

### auth/jwt_handler.py

было:
```python
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production")
```

стало:
```python
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-in-production!")
```

Строка `"dev-secret-change-in-production!"` — 32 байта. Убирает `InsecureKeyLengthWarning`.

---

## 3. Alembic миграция 002 — users + audit_log

Создать `alembic/versions/002_add_users_audit_log.py`:

```python
"""add users and audit_log tables

Revision ID: 002
Revises: 001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("resource", sa.String(200), nullable=False),
        sa.Column("detail", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("users")
```

---

## 4. Ruff errors

### monitoring/prometheus.py

Убрать unused imports `CONTENT_TYPE_LATEST` и `generate_latest` из блока try/except.
Они используются только в `api/app.py`, не здесь. Если они импортируются в `api/app.py` напрямую из `prometheus_client` — убрать из `monitoring/prometheus.py`. Если `api/app.py` импортирует их из `monitoring/prometheus.py` — оставить, но добавить `__all__` или re-export.

Проверить откуда `api/app.py` берёт `generate_latest` и `CONTENT_TYPE_LATEST`:
- Если из `prometheus_client` напрямую → убрать из monitoring/prometheus.py
- Если из `monitoring.prometheus` → добавить в `__all__` и оставить

### channels/telegram_bot.py

Перенести `from config.settings import get_settings` выше, до `sys.path.insert`, или обернуть в lazy-import внутри функции.

Простейшее решение — перенести sys.path.insert в начало файла (до всех импортов):

было:
```python
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
```

стало:
```python
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import logging  # noqa: E402

from config.settings import get_settings  # noqa: E402
```

### tests/test_jwt_auth.py

Убрать `import pytest` если он не используется.

---

## CONSTRAINTS
- Минимальные изменения — только то, что указано
- `pytest tests/ -v` — 65 passed, 0 warnings про InsecureKeyLengthWarning
- `ruff check .` — 0 errors
- `alembic upgrade head` (при наличии PostgreSQL) — создаёт 7 таблиц

## DONE WHEN
- [ ] `create_refresh_token` принимает и сохраняет `role`
- [ ] Все вызовы `create_refresh_token` передают роль
- [ ] `JWT_SECRET` default ≥32 байт — нет InsecureKeyLengthWarning
- [ ] `alembic/versions/002_add_users_audit_log.py` создаёт таблицы users и audit_log
- [ ] `ruff check .` — 0 errors
- [ ] `pytest tests/ -v` — 65 passed, 0 warnings
