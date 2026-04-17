# Task 43 — DB-1: SQLAlchemy модели + подключение к PostgreSQL

## Goal
Создать слой доступа к БД: SQLAlchemy модели для sessions, messages, traces, trace_steps, feedback.
Это заменит in-memory `_sessions` и SQLite `traces.db`.

## Files to create
- `db/__init__.py`
- `db/engine.py` — async engine + session factory
- `db/models.py` — SQLAlchemy ORM модели

## Files to change
- `requirements.txt` — добавить sqlalchemy, asyncpg, psycopg2-binary

---

## 1. requirements.txt

Добавить:
```
sqlalchemy[asyncio]>=2.0.0
asyncpg>=0.29.0
psycopg2-binary>=2.9.0
```

---

## 2. db/__init__.py

```python
"""Database layer — SQLAlchemy models and engine."""
```

---

## 3. db/engine.py

```python
"""Async SQLAlchemy engine + session factory."""
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://rag:rag_dev_password@localhost:5432/rag_assistant",
)

# Для asyncpg нужен postgresql+asyncpg:// prefix
_url = DATABASE_URL
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(_url, echo=False, pool_size=10, max_overflow=20)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields async DB session."""
    async with async_session() as session:
        yield session
```

---

## 4. db/models.py

```python
"""SQLAlchemy ORM модели для RAG Support Assistant."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_access: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    messages: Mapped[list["Message"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    session: Mapped["Session"] = relationship(back_populates="messages")


class Trace(Base):
    __tablename__ = "traces"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # trace_id (UUID string)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_route: Mapped[str | None] = mapped_column(String(30), nullable=True)
    final_quality: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_relevance: Mapped[float | None] = mapped_column(Float, nullable=True)

    steps: Mapped[list["TraceStep"]] = relationship(back_populates="trace", cascade="all, delete-orphan")
    feedbacks: Mapped[list["Feedback"]] = relationship(back_populates="trace", cascade="all, delete-orphan")


class TraceStep(Base):
    __tablename__ = "trace_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), ForeignKey("traces.id", ondelete="CASCADE"))
    step_order: Mapped[int] = mapped_column(Integer)
    node_name: Mapped[str] = mapped_column(String(50))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    state_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    trace: Mapped["Trace"] = relationship(back_populates="steps")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(64), ForeignKey("traces.id", ondelete="CASCADE"))
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rating: Mapped[str] = mapped_column(String(10))  # "up" | "down"
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    trace: Mapped["Trace"] = relationship(back_populates="feedbacks")
```

---

## CONSTRAINTS
- Создать только `db/` пакет и обновить `requirements.txt`
- НЕ мигрировать существующий код — только создать модели
- Модели должны соответствовать текущей структуре SQLite (traces, trace_steps, feedback) + новые (sessions, messages)
- `python -c "from db.models import Base, Session, Message, Trace, TraceStep, Feedback"` — работает
- `pytest tests/ -v` — проходит (новый код не ломает существующий)

## DONE WHEN
- [ ] `db/__init__.py`, `db/engine.py`, `db/models.py` созданы
- [ ] 5 моделей: Session, Message, Trace, TraceStep, Feedback
- [ ] `requirements.txt` содержит sqlalchemy, asyncpg, psycopg2-binary
- [ ] Import работает: `from db.models import Base`
- [ ] `pytest tests/ -v` — проходит
