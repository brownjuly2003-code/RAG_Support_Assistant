from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"

TRACES_DB_PATH = DATA_DIR / "tracing" / "traces.db"
INBOX_FILE_PATH = DATA_DIR / "inbox" / "support_inbox.jsonl"

try:
    from agent.graph import run_support_pipeline
except ImportError:
    def run_support_pipeline(
        question: str,
        entity_id: Optional[str],
        trace_id: str,
    ) -> Dict[str, Any]:
        return {
            "answer": f"[DEMO] Я не нашёл LangGraph, но услышал вопрос: {question!r}",
            "route": "auto",
            "quality_score": 50,
            "relevance_score": 0.5,
            "trace_id": trace_id,
        }


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    entity_id: Optional[str] = Field(default=None, max_length=100)


class AskResponse(BaseModel):
    answer: str
    route: str
    quality: Optional[int]
    relevance: Optional[float]
    trace_id: str


class TraceSummary(BaseModel):
    trace_id: str
    started_at: str
    finished_at: Optional[str]
    final_route: Optional[str]
    final_quality: Optional[int]
    final_relevance: Optional[float]


class TraceStep(BaseModel):
    step_order: int
    node_name: str
    ts: str
    state_json: str


class TraceDetail(BaseModel):
    trace_id: str
    started_at: str
    finished_at: Optional[str]
    final_route: Optional[str]
    final_quality: Optional[int]
    final_relevance: Optional[float]
    steps: List[TraceStep]


app = FastAPI(title="RAG Support Assistant PoC", version="0.1.0")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ---------------------------------------------------------------------------
# Mount new REST API router (api/app.py) and static files
# ---------------------------------------------------------------------------
try:
    from api.app import router as api_router, initialize_vector_store
    app.include_router(api_router)
except ImportError:
    api_router = None  # noqa: F841
    initialize_vector_store = None

try:
    from fastapi.staticfiles import StaticFiles
    _static_dir = BASE_DIR / "static"
    if _static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")
except ImportError:
    pass


def _ensure_dirs() -> None:
    (DATA_DIR / "tracing").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "inbox").mkdir(parents=True, exist_ok=True)


def _open_traces_db() -> sqlite3.Connection:
    if not TRACES_DB_PATH.exists():
        raise HTTPException(status_code=500, detail="База трассинга ещё не создана")
    conn = sqlite3.connect(TRACES_DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _read_inbox_jsonl() -> List[Dict[str, Any]]:
    if not INBOX_FILE_PATH.exists():
        return []
    items: List[Dict[str, Any]] = []
    with INBOX_FILE_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    items.append(obj)
            except json.JSONDecodeError:
                continue
    return items


@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest) -> AskResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question is empty")

    trace_id = uuid.uuid4().hex

    final_state = run_support_pipeline(
        question=request.question.strip(),
        entity_id=request.entity_id,
        trace_id=trace_id,
    )

    answer = final_state.get("answer") or ""
    route = final_state.get("route") or "auto"
    quality = final_state.get("quality_score")
    relevance = final_state.get("relevance_score")
    returned_trace_id = final_state.get("trace_id") or trace_id

    return AskResponse(
        answer=answer,
        route=route,
        quality=quality,
        relevance=relevance,
        trace_id=returned_trace_id,
    )


@app.get("/escalations")
async def get_escalations() -> Dict[str, Any]:
    items = _read_inbox_jsonl()
    items_sorted = sorted(items, key=lambda x: x.get("ts", ""), reverse=True)
    return {
        "total": len(items_sorted),
        "items": items_sorted,
    }


@app.get("/traces", response_model=List[TraceSummary])
async def get_traces(limit: int = 50) -> List[TraceSummary]:
    conn = _open_traces_db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT trace_id, started_at, finished_at,
                   final_route, final_quality, final_relevance
            FROM traces
            ORDER BY started_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    return [
        TraceSummary(
            trace_id=row["trace_id"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            final_route=row["final_route"],
            final_quality=row["final_quality"],
            final_relevance=row["final_relevance"],
        )
        for row in rows
    ]


@app.get("/traces/{trace_id}", response_model=TraceDetail)
async def get_trace_detail(trace_id: str) -> TraceDetail:
    conn = _open_traces_db()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT trace_id, started_at, finished_at,
                   final_route, final_quality, final_relevance
            FROM traces
            WHERE trace_id = ?
            """,
            (trace_id,),
        )
        head = cur.fetchone()
        if head is None:
            raise HTTPException(status_code=404, detail="trace not found")

        cur.execute(
            """
            SELECT step_order, node_name, state_json, ts
            FROM trace_steps
            WHERE trace_id = ?
            ORDER BY step_order ASC
            """,
            (trace_id,),
        )
        step_rows = cur.fetchall()
    finally:
        conn.close()

    steps: List[TraceStep] = []
    for row in step_rows:
        steps.append(
            TraceStep(
                step_order=row["step_order"],
                node_name=row["node_name"],
                ts=row["ts"],
                state_json=row["state_json"],
            )
        )

    return TraceDetail(
        trace_id=head["trace_id"],
        started_at=head["started_at"],
        finished_at=head["finished_at"],
        final_route=head["final_route"],
        final_quality=head["final_quality"],
        final_relevance=head["final_relevance"],
        steps=steps,
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    _ensure_dirs()

    try:
        traces = await get_traces(limit=10)
    except HTTPException:
        traces = []

    inbox_items = _read_inbox_jsonl()
    stats = {
        "total": len(inbox_items),
    }

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "traces": traces,
            "inbox_stats": stats,
        },
    )


@app.post("/ask-ui", response_class=HTMLResponse)
async def ask_ui(
    request: Request,
    question: str = Form(...),
    entity_id: str = Form(""),
):
    ask_req = AskRequest(
        question=question,
        entity_id=entity_id or None,
    )
    response = await ask(ask_req)
    return templates.TemplateResponse(
        "ask_result.html",
        {
            "request": request,
            "question": question,
            "response": response,
        },
    )


@app.get("/escalations-ui", response_class=HTMLResponse)
async def escalations_ui(request: Request):
    data = await get_escalations()
    return templates.TemplateResponse(
        "escalations.html",
        {
            "request": request,
            "items": data["items"],
            "total": data["total"],
        },
    )


@app.get("/traces-ui", response_class=HTMLResponse)
async def traces_ui(request: Request, limit: int = 50):
    traces = await get_traces(limit=limit)
    return templates.TemplateResponse(
        "traces.html",
        {
            "request": request,
            "traces": traces,
        },
    )


@app.get("/traces-ui/{trace_id}", response_class=HTMLResponse)
async def trace_detail_ui(request: Request, trace_id: str):
    detail = await get_trace_detail(trace_id)

    pretty_steps: List[Dict[str, Any]] = []
    for step in detail.steps:
        pretty = step.state_json
        try:
            obj = json.loads(step.state_json)
            pretty = json.dumps(obj, ensure_ascii=False, indent=2)
        except Exception:
            pass
        pretty_steps.append(
            {
                "step_order": step.step_order,
                "node_name": step.node_name,
                "ts": step.ts,
                "state_pretty": pretty,
            }
        )

    return templates.TemplateResponse(
        "trace_detail.html",
        {
            "request": request,
            "trace": detail,
            "steps": pretty_steps,
        },
    )


@app.get("/chat", response_class=HTMLResponse)
async def chat_ui(request: Request):
    """Serve the web chat interface."""
    chat_html = BASE_DIR / "static" / "chat.html"
    if chat_html.exists():
        return HTMLResponse(chat_html.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Chat UI not found</h1>", status_code=404)


def _run_alembic_upgrade() -> None:
    """Apply pending alembic migrations. Idempotent and safe to call repeatedly.

    Gated on AUTO_MIGRATE env (default "true"). On failure, logs a warning but
    does not abort startup — the operator can run `alembic upgrade head` manually.
    """
    import logging
    import os

    if os.getenv("AUTO_MIGRATE", "true").strip().lower() not in ("1", "true", "yes"):
        return

    logger = logging.getLogger("rag.startup")
    try:
        from alembic import command
        from alembic.config import Config

        cfg_path = BASE_DIR / "alembic.ini"
        if not cfg_path.exists():
            logger.warning("alembic.ini not found at %s; skipping auto-migrate", cfg_path)
            return
        cfg = Config(str(cfg_path))
        cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
        command.upgrade(cfg, "head")
        logger.info("alembic upgrade head: OK")
    except Exception as exc:  # noqa: BLE001
        logger.warning("alembic auto-migrate skipped: %s", exc)


@app.on_event("startup")
async def startup():
    import asyncio

    _ensure_dirs()
    await asyncio.get_running_loop().run_in_executor(None, _run_alembic_upgrade)
    if initialize_vector_store is not None:
        initialize_vector_store()


if __name__ == "__main__":
    import os

    import uvicorn

    _ensure_dirs()
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
