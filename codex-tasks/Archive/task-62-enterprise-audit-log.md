# Task 62 — COMP-1: Audit logging

## Goal
Все user/admin/AI actions должны логироваться в immutable audit log.
Нужно для compliance (SOC2, GDPR) и incident investigation.

## Dependencies
- task-43 (SQLAlchemy models)

## Files to create
- `db/audit.py` — audit log helper

## Files to change
- `db/models.py` — добавить AuditLog model
- `api/app.py` — логировать actions

---

## 1. db/models.py — модель AuditLog

```python
class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    actor: Mapped[str] = mapped_column(String(100))  # user_id or "system"
    action: Mapped[str] = mapped_column(String(50))   # "ask", "upload", "login", "escalate", "feedback", "delete_session"
    resource: Mapped[str] = mapped_column(String(200)) # "session:uuid", "document:name", "trace:id"
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON with extra info
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
```

---

## 2. db/audit.py

```python
"""Append-only audit logging."""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def log_audit(
    actor: str,
    action: str,
    resource: str,
    detail: Optional[dict] = None,
    ip_address: Optional[str] = None,
) -> None:
    """Append audit record. Fire-and-forget — never blocks request."""
    try:
        from db.engine import async_session
        from db.models import AuditLog

        async with async_session() as db:
            entry = AuditLog(
                actor=actor,
                action=action,
                resource=resource,
                detail=json.dumps(detail, ensure_ascii=False) if detail else None,
                ip_address=ip_address,
            )
            db.add(entry)
            await db.commit()
    except Exception as exc:
        # Fallback: log to file
        logger.warning(
            "Audit DB write failed, logging to file: %s", exc
        )
        logger.info(
            "AUDIT: actor=%s action=%s resource=%s detail=%s ip=%s",
            actor, action, resource, detail, ip_address,
        )
```

---

## 3. api/app.py — инструментация

В каждом endpoint добавить вызов audit log:

### /api/ask
```python
    await log_audit(
        actor=_user.get("sub", "anonymous"),
        action="ask",
        resource=f"session:{sid}",
        detail={"question_length": len(body.question)},
        ip_address=request.client.host if request.client else None,
    )
```

### /api/upload
```python
    await log_audit(actor=..., action="upload", resource=f"document:{safe_name}")
```

### /api/feedback
```python
    await log_audit(actor=..., action="feedback", resource=f"trace:{body.trace_id}", detail={"rating": body.rating})
```

### /api/auth/login
```python
    await log_audit(actor=body.username, action="login", resource="auth", ip_address=...)
```

### DELETE /api/sessions/{id}
```python
    await log_audit(actor=..., action="delete_session", resource=f"session:{session_id}")
```

---

## CONSTRAINTS
- Audit log append-only: нет UPDATE/DELETE на таблице
- Fire-and-forget: audit failure не блокирует request
- Fallback на logger.info если DB недоступна
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `AuditLog` модель в db/models.py
- [ ] `log_audit()` функция в db/audit.py
- [ ] Все ключевые endpoints логируют audit events
- [ ] DB failure → fallback на structured log (не crash)
- [ ] `pytest tests/ -v` — проходит
