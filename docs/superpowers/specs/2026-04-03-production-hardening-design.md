# Production Hardening — RAG Support Assistant

**Date:** 2026-04-03  
**Status:** Approved  
**Goal:** Bring RAG Support Assistant to production-ready state for 1000+ req/day  
**Priority:** Reliability — no silent crashes, graceful error handling with auto-escalation

---

## Context

LangGraph-based RAG pipeline, Ollama/Mistral, hybrid search (BM25 + embeddings), FastAPI.  
Current state: functional PoC, ~10% test coverage, no structured error handling, no health checks, no rate limiting.

**File layout note:** Core modules live in project root — `graph.py`, `state.py`, `manager.py`,
`prompts.py`, `sqlite_trace.py`, `cache.py`. Package directories (`agent/`, `vectordb/`, `tracing/`)
contain only `__init__.py` stubs.

**Deployment target:** Production service, 1000+ req/day, environment TBD  
**Primary concern:** Unhandled exceptions in pipeline → crashes instead of graceful responses

---

## Scope

Approach B: Reliability + Production Hardening

1. Error handling in LangGraph pipeline
2. Health checks for all dependencies
3. Rate limiting
4. Structured logging
5. Config validation on startup

---

## 1. Error Handling in LangGraph Pipeline

### Problem
Any exception in `retrieve`, `generate`, `evaluate`, `route_or_retry`, or `log` nodes causes
an unhandled crash. No escalation, no user feedback.

### Solution

Each node body wrapped in try/except. On exception the node sets error fields in state and
returns immediately. After `route_or_retry`, `_should_retry()` checks for error state and routes
to a new `handle_error` node instead of retry/finish.

**Changes to `state.py`:**
- Add `error: bool = False`
- Add `error_message: str = ""`
- Add `error_node: str = ""`
- Extend `route` type: `Optional[Literal["auto", "human", "retry", "error"]]`

**Changes to `graph.py`:**
1. Each node's body: wrap main logic in try/except, on exception set
   `state["error"] = True`, `state["error_message"] = repr(e)`, `state["error_node"] = "<name>"`,
   `state["route"] = "error"`, return early.
2. New `handle_error` node:
   - Calls `escalate()` (mock_inbox or bitrix depending on `SUPPORT_SINK_BACKEND`)
   - Sets `state["answer"]` to user-friendly Russian message
   - Logs full traceback via `log_step()`
3. Update `_should_retry()`:
   ```python
   if route == "error":
       return "error"
   if route == "retry":
       return "retry"
   return "finish"
   ```
4. Add `"error": "handle_error"` to `add_conditional_edges()` mapping.
5. Add `workflow.add_node("handle_error", handle_error_node)`.
6. `handle_error` → END.

### Error message to user
> "Не удалось обработать запрос автоматически. Ваш вопрос передан оператору — мы ответим в ближайшее время."

### Graph topology (updated)
```
retrieve → generate → evaluate → route_or_retry ──┬── (retry) → rewrite_query → ...
                                                   ├── (finish) → log → END
                                                   └── (error) → handle_error → END
Any node on exception → sets route="error", route_or_retry sees it → handle_error
```

### Files
- `state.py` — add error fields + extend Literal
- `graph.py` — wrap nodes, add handle_error node, update _should_retry + conditional edges

---

## 2. Health Checks

### Problem
`GET /api/health` returns `{"status": "ok"}` unconditionally.

### Solution

Active probes in health endpoint:
- **Ollama** — `httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=3)`
- **ChromaDB** — `chromadb.PersistentClient(path=chroma_dir).list_collections()` (native client,
  not langchain wrapper), timeout 3s
- **SQLite** — `SELECT 1` on traces.db, timeout 1s

Response schema:
```json
{
  "status": "ok | degraded | unhealthy",
  "components": {
    "ollama":   {"status": "ok | error", "latency_ms": 42},
    "chromadb": {"status": "ok | error", "latency_ms": 12},
    "sqlite":   {"status": "ok | error", "latency_ms": 1}
  }
}
```

HTTP status:
- All OK → 200
- Any component degraded → 200 with `"status": "degraded"`
- Ollama or ChromaDB down → 503

### Files
- `api/app.py` — replace stub health endpoint

---

## 3. Rate Limiting

### Problem
No rate limiting — single client can flood Ollama with concurrent requests.

### Solution

`slowapi` (standard FastAPI rate limiting, wraps `limits`).

Limits:
- `POST /api/ask` — 60 req/min per IP
- `POST /api/upload` — 10 req/min per IP

On exceeded: 429 + `Retry-After: 60` header + Russian message:
> "Слишком много запросов. Попробуйте через минуту."

### Files
- `requirements.txt` — add `slowapi>=0.1.9`
- `api/app.py` — SlowAPI setup + decorators

---

## 4. Structured Logging

### Problem
Scattered `print()` calls, no log levels, no trace_id correlation.

### Solution

New `config/logging_config.py` — configures root logger with JSON formatter.

Log format (stdout, one JSON per line):
```json
{"ts": "2026-04-03T12:00:00Z", "level": "INFO", "module": "graph", "trace_id": "abc-123", "msg": "..."}
```

Per-module: `logger = logging.getLogger(__name__)`

Log levels:
- DEBUG — chunk counts, retrieval details
- INFO — pipeline start/end, routing decisions, escalations
- WARNING — low quality scores, retry attempts
- ERROR — exceptions with full traceback

`setup_logging()` called once in `api/app.py` lifespan startup.

### Files
- `config/logging_config.py` — new file
- `api/app.py` — call setup_logging() in lifespan
- `graph.py`, `manager.py`, `ingestion/pipeline.py` — replace print() with logger calls

---

## 5. Config Validation on Startup

### Problem
App starts silently even when Ollama is down — crashes on first real request.

### Solution

FastAPI `lifespan` startup event runs validation. Behavior controlled by env var:
- `REQUIRE_OLLAMA=true` (prod default) → fail fast if Ollama unreachable
- `REQUIRE_OLLAMA=false` (dev default) → warn only, allow degraded start

Checks:
1. Ollama reachable (same probe as health check)
2. ChromaDB data directory exists or is creatable

On fail with `REQUIRE_OLLAMA=true`:
```
ERROR: Cannot connect to Ollama at http://localhost:11434
       Start Ollama with: ollama serve
       Then run: ollama pull mistral
```
Exit with code 1.

On fail with `REQUIRE_OLLAMA=false`: log WARNING, continue.

### Files
- `config/settings.py` — add `REQUIRE_OLLAMA` field + `validate()` method
- `api/app.py` — call `settings.validate()` in lifespan

---

## Implementation Order

1. `requirements.txt` — add `slowapi>=0.1.9` (before api/app.py changes)
2. `state.py` — add error fields + extend route Literal
3. `graph.py` — wrap nodes + handle_error node + update _should_retry + conditional edges
4. `config/logging_config.py` — new file, JSON logging setup
5. `config/settings.py` — add REQUIRE_OLLAMA + validate()
6. `api/app.py` — health checks + rate limiting + startup validation + logging init
7. Replace print() in `graph.py`, `manager.py`, `ingestion/pipeline.py`

---

## Out of Scope

- Semantic chunking
- Tests
- Prometheus metrics
- Auth / JWT
- Deployment config

---

## Success Criteria

- Any unhandled exception in pipeline → user gets friendly Russian message + ticket created
- `/api/health` returns real dependency status with per-component detail
- 429 returned when rate limit exceeded
- All logs are JSON with trace_id included
- App refuses to start (REQUIRE_OLLAMA=true) if Ollama unreachable
- Existing self-RAG retry loop (route="retry") unaffected by error handling changes
