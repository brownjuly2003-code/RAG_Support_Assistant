# Task 48 — DB-1+: Персистентные сессии в PostgreSQL

## Goal
Заменить in-memory `_sessions` dict на PostgreSQL.
Сессии должны переживать рестарт приложения.

## Dependencies
- task-43 (SQLAlchemy модели Session, Message)
- task-44 (Alembic миграции)

## Files to change
- `api/app.py` — заменить `_sessions` dict на DB queries
- `db/engine.py` — если нужны правки

---

## api/app.py

### Удалить global state

Удалить:
```python
_sessions: Dict[str, Any] = {}
_session_last_access: Dict[str, float] = {}
```

### Обновить _get_or_create_session

было (in-memory):
```python
def _get_or_create_session(session_id: Optional[str]) -> tuple:
    global _retriever, _llm
    ...
```

стало (DB-backed с in-memory fallback для LLM state):

```python
# In-memory LLM state (retriever/llm не хранятся в БД)
_session_llm_state: Dict[str, Any] = {}

async def _get_or_create_session(session_id: Optional[str]) -> tuple:
    """Get or create session. Persists to DB, LLM state in memory."""
    global _retriever, _llm

    if session_id is None:
        session_id = str(uuid.uuid4())

    # Ensure session exists in DB
    try:
        from db.engine import async_session
        from db.models import Session as DBSession
        from sqlalchemy import select
        from datetime import datetime, timezone

        async with async_session() as db:
            result = await db.execute(select(DBSession).where(DBSession.id == uuid.UUID(session_id)))
            db_session = result.scalar_one_or_none()
            if db_session is None:
                db_session = DBSession(id=uuid.UUID(session_id))
                db.add(db_session)
                await db.commit()
            else:
                db_session.last_access = datetime.now(timezone.utc)
                await db.commit()
    except Exception as exc:
        logger.warning("DB session fallback to memory: %s", exc)

    # LLM session state (ConversationSession) — still in memory
    if session_id not in _session_llm_state and _ConversationSession is not None:
        # ... existing ConversationSession init logic
        pass

    return session_id, _session_llm_state.get(session_id)
```

### Обновить get_session_history

Читать историю из DB:
```python
@router.get("/sessions/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(session_id: str) -> HistoryResponse:
    try:
        from db.engine import async_session
        from db.models import Message
        from sqlalchemy import select

        async with async_session() as db:
            result = await db.execute(
                select(Message)
                .where(Message.session_id == uuid.UUID(session_id))
                .order_by(Message.created_at)
            )
            messages = [
                HistoryMessage(role=m.role, content=m.content)
                for m in result.scalars()
            ]
            if not messages:
                raise HTTPException(status_code=404, detail="Session not found")
            return HistoryResponse(session_id=session_id, messages=messages)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("DB history fallback: %s", exc)
        # Fallback to memory
        raise HTTPException(status_code=404, detail="Session not found")
```

### Сохранять сообщения в DB

После каждого `/api/ask` — сохранить user question + assistant answer:
```python
# В конце обработки /api/ask, после получения ответа:
try:
    from db.engine import async_session as db_session_factory
    from db.models import Message

    async with db_session_factory() as db:
        db.add(Message(session_id=uuid.UUID(sid), role="user", content=body.question))
        db.add(Message(session_id=uuid.UUID(sid), role="assistant", content=answer_text))
        await db.commit()
except Exception as exc:
    logger.warning("Failed to persist messages: %s", exc)
```

---

## CONSTRAINTS
- Изменить только `api/app.py`
- Graceful degradation: если DB недоступна — in-memory fallback, не crash
- LLM state (ConversationSession, retriever, llm) остаётся in-memory
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `_sessions` dict удалён или используется только как fallback
- [ ] Сессии сохраняются в PostgreSQL таблицу `sessions`
- [ ] Сообщения сохраняются в таблицу `messages`
- [ ] Restart app → `GET /api/sessions/{id}/history` возвращает историю
- [ ] Без PostgreSQL — app стартует и работает (fallback)
- [ ] `pytest tests/ -v` — проходит
