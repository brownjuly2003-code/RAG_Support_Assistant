# Task 08 — Request/response logging middleware

## Problem
Structured logs exist, but there's no per-request log entry showing:
method, path, status code, duration, and trace_id.
At 1000+ req/day this is essential for debugging slow requests.

## Change needed in 1 file: api/app.py

Add a middleware **after** the `app = FastAPI(...)` line and before `app.include_router(router)`:

```python
import time as _time_mod  # add to imports at top if not already there

@app.middleware("http")
async def _log_requests(request: Request, call_next: Any) -> Any:
    t0 = _time_mod.monotonic()
    response = await call_next(request)
    duration_ms = round((_time_mod.monotonic() - t0) * 1000, 1)
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response
```

Note: `time` is already imported in api/app.py as `time`. Use that — don't add a duplicate import.
Use `time.monotonic()`, not `_time_mod`.

## CONSTRAINTS
- Touch ONLY api/app.py — add ~10 lines, nothing else
- Do NOT add a test for this (middleware integration test is out of scope)
- Do NOT modify any existing function
- ruff check api/app.py → 0 errors

## DONE WHEN
- [ ] `pytest tests/ -v` still passes (same count, 0 failed)
- [ ] App starts, a request to /api/health produces a log line like:
      `{"level":"INFO","msg":"GET /api/health → 200 (3.2ms)"}`
