# Task 02 — Session TTL cleanup (memory leak prevention)

## Problem
`api/app.py` has `_sessions: Dict[str, Any]` that grows forever.
At 1000+ req/day, stale sessions will eat memory.

## Changes needed in 3 files

### 1. config/settings.py
Add one field to the `Settings` dataclass (after `require_ollama`):
```python
session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "7200"))
```

### 2. .env.example
Add one line (with comment) after `REQUIRE_OLLAMA`:
```
# Session idle timeout in seconds (default 2 hours)
SESSION_TTL_SECONDS=7200
```

### 3. api/app.py — three small changes

**Change A** — Add timestamp tracking to `_sessions`.
Replace the existing dict value with a wrapper. After the line:
```python
_sessions: Dict[str, Any] = {}
```
Add:
```python
_session_last_access: Dict[str, float] = {}
```

**Change B** — In `_get_or_create_session()`, record access time.
At the very end of the function, before `return session_id, _sessions[session_id]`, add:
```python
    import time as _time
    _session_last_access[session_id] = _time.monotonic()
```

**Change C** — Add background cleanup task in `_lifespan()`.
After `initialize_vector_store()` and before `yield`, add:
```python
    async def _cleanup_sessions() -> None:
        import asyncio
        import time as _time
        settings = get_settings()
        while True:
            await asyncio.sleep(600)  # every 10 minutes
            cutoff = _time.monotonic() - settings.session_ttl_seconds
            stale = [sid for sid, t in _session_last_access.items() if t < cutoff]
            for sid in stale:
                _sessions.pop(sid, None)
                _session_last_access.pop(sid, None)
            if stale:
                logger.info("Cleaned up %d stale sessions", len(stale))

    cleanup_task = asyncio.create_task(_cleanup_sessions())
    yield
    cleanup_task.cancel()
```
(Replace the existing bare `yield` with this block.)

## CONSTRAINTS
- Touch only: config/settings.py, .env.example, api/app.py
- Do NOT add a test (asyncio background task testing is out of scope here)
- ruff check on each modified file → 0 errors
- Do NOT rewrite any existing functions — surgical inserts only

## DONE WHEN
- [ ] `python -c "from api.app import app"` runs without error
- [ ] ruff check config/settings.py api/app.py → 0 errors
