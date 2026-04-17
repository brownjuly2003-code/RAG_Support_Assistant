"""Async SQLAlchemy engine + session factory."""
from __future__ import annotations

import os
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://rag:rag_dev_password@localhost:5432/rag_assistant",
)

_url = DATABASE_URL
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(_url, echo=False, pool_size=10, max_overflow=20)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def get_pool_stats() -> dict[str, int]:
    try:
        pool = engine.pool
        return {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception:
        return {"size": -1, "checked_out": -1, "overflow": -1}


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency - yields async DB session."""
    async with async_session() as session:
        yield session
