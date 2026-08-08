"""Conversation ask/chat endpoints."""
from __future__ import annotations

import asyncio
import json as _json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from api._shared import app_module as _app_module
from api.correlation import get_current_tenant, get_request_id
from api.rate_limit import limiter
from auth.dependencies import get_current_user
from monitoring import prometheus as prometheus_metrics
from utils.background_tasks import spawn_tracked

router = APIRouter()
logger = logging.getLogger(__name__)

# Plan §4.4: terminal routes that must carry a durable ticket (or explicit failure).
_TERMINAL_ESCALATE_ROUTES = frozenset({"human", "error", "error_escalation"})


def _release_pipeline_capacity(semaphore: Any) -> None:
    """Drop inflight gauge + release the pipeline semaphore (best-effort)."""
    try:
        prometheus_metrics.INFLIGHT_PIPELINES.dec()
    except Exception:
        pass
    try:
        semaphore.release()
    except Exception:
        pass


def _hold_capacity_until_future_done(
    *,
    loop: asyncio.AbstractEventLoop,
    fut: Any,
    semaphore: Any,
) -> None:
    """Keep pipeline capacity until a thread-pool future finishes (3.1a / 3.1f)."""

    def _on_done(_fut: Any) -> None:
        _release_pipeline_capacity(semaphore)

    fut.add_done_callback(
        lambda done: loop.call_soon_threadsafe(_on_done, done)
    )


def _resolve_stream_terminal(
    *,
    stream_answer: str,
    graph_result: dict[str, Any] | None,
    graph_appended_history: bool,
) -> tuple[str, bool, str]:
    """Pick the single terminal answer and history policy for /api/ask/stream (plan §4.1).

    When graph parity returns a non-empty answer, that answer is authoritative for
    the SSE result, DB persist, and history — not a second stream-side mutation.
    Tokens already sent for UX may differ; the final ``result`` event is graph-owned.

    Returns:
        (terminal_answer, skip_stream_history_append, answer_source)
        answer_source is ``"graph"`` or ``"stream"``.
    """
    if isinstance(graph_result, dict) and graph_result:
        graph_answer = str(graph_result.get("answer") or "").strip()
        if graph_answer:
            # Graph owns terminal semantics; never double-append stream text.
            return graph_answer, True, "graph"
        # Graph ran but empty answer (timeout/conflict shell): keep stream text,
        # still skip stream history if graph already mutated the session.
        return stream_answer, bool(graph_appended_history), "stream"
    return stream_answer, bool(graph_appended_history), "stream"


def _chunk_text_for_sse(text: str, *, chunk_size: int = 48) -> list[str]:
    """Split a finished answer into SSE token chunks (UX only; not a second LLM)."""
    body = str(text or "")
    if not body:
        return []
    size = max(1, int(chunk_size))
    return [body[i : i + size] for i in range(0, len(body), size)]


def _graph_result_sources_and_citations(
    graph_result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build sources/citations lists from a graph ask result."""
    sources: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    graph_citations_raw = graph_result.get("citations") or []
    if graph_citations_raw:
        citations = [
            {
                "index": int(item.get("index") or 0),
                "doc_id": str(item.get("doc_id") or ""),
                "title": str(item.get("title") or ""),
                "excerpt": str(item.get("excerpt") or ""),
            }
            for item in graph_citations_raw
            if isinstance(item, dict)
        ]
    graph_graded = (
        graph_result.get("graded_docs")
        or graph_result.get("context_docs")
        or []
    )
    if graph_graded:
        for idx, item in enumerate(graph_graded, start=1):
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata", {}) or {}
            content = item.get("page_content", "") or ""
            sources.append({
                "source": metadata.get("source") or metadata.get("file_name") or "",
                "page_content": content,
            })
            if not graph_citations_raw:
                citations.append({
                    "index": idx,
                    "doc_id": str(
                        metadata.get("doc_id")
                        or metadata.get("id")
                        or metadata.get("source")
                        or metadata.get("file_name")
                        or f"doc_{idx}"
                    ),
                    "title": str(
                        metadata.get("title")
                        or metadata.get("source")
                        or metadata.get("file_name")
                        or metadata.get("doc_id")
                        or f"doc_{idx}"
                    ),
                    "excerpt": str(content)[:300],
                })
    return sources, citations


def _append_stream_history(
    session: Any,
    *,
    question: str,
    answer: str,
) -> None:
    """Exactly one user+assistant pair on the in-memory session history."""
    if hasattr(session, "_history"):
        session._history.append({"role": "user", "content": question})
        session._history.append({"role": "assistant", "content": answer})
        max_history = getattr(session, "_max_history", 20)
        if len(session._history) > max_history * 2:
            session._history = session._history[-(max_history * 2) :]
    elif isinstance(session, dict):
        session.setdefault("history", [])
        session["history"].append({"role": "user", "content": question})
        session["history"].append({"role": "assistant", "content": answer})


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=100)
    confirm: Optional[bool] = None
    tenant_id: str = Field(
        default="default",
        max_length=50,
        pattern=r"^[a-zA-Z0-9_\-]+$",
    )

    @field_validator("session_id")
    @classmethod
    def _validate_session_id(cls, value: Optional[str]) -> Optional[str]:
        """Reject malformed session UUIDs at the API boundary (422)."""
        if value is None:
            return None
        raw = value.strip()
        if not raw:
            return None
        try:
            return uuid.UUID(raw).hex
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("session_id must be a valid UUID") from exc


class SourceInfo(BaseModel):
    source: str = ""
    page_content: str = ""


class Citation(BaseModel):
    index: int
    doc_id: str = ""
    title: str = ""
    excerpt: str = ""


class AskResponse(BaseModel):
    answer: str
    quality_score: int = 50
    route: str = "auto"
    sources: list[SourceInfo] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    session_id: str = ""
    trace_id: str = ""
    suggested_questions: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    action_summary: str = ""
    cached: bool = False
    # Plan §4.3: durable escalation identity (only set on human/error handoff paths).
    ticket_id: str | None = None
    delivery_state: str | None = None


async def _persist_ask_messages(
    session_id: str,
    tenant_id: str,
    question: str,
    answer: str,
    path: str,
) -> None:
    """Persist ask messages only when Session is owned by ``tenant_id``.

    Shared by sync / SSE / fallback paths so foreign or missing owners never
    receive a write. Ownership rejection is silent (no write); real DB failures
    retain the existing cooldown fallback.
    """
    _app = _app_module()
    if time.monotonic() < _app._db_retry_after:
        return
    try:
        session_uuid = uuid.UUID(str(session_id))
    except (TypeError, ValueError, AttributeError):
        return

    try:
        from sqlalchemy import select

        from db.engine import async_session as db_session_factory
        from db.models import Message
        from db.models import Session as DBSession

        settings = _app.get_settings()
        timeout = float(getattr(settings, "db_persist_timeout_sec", 2.0))
        async with db_session_factory() as db:
            owned = await asyncio.wait_for(
                db.execute(
                    select(DBSession.id)
                    .where(DBSession.id == session_uuid)
                    .where(DBSession.tenant_id == tenant_id)
                ),
                timeout=timeout,
            )
            if owned.scalar_one_or_none() is None:
                return
            db.add(
                Message(
                    session_id=session_uuid,
                    tenant_id=tenant_id,
                    role="user",
                    content=question,
                )
            )
            db.add(
                Message(
                    session_id=session_uuid,
                    tenant_id=tenant_id,
                    role="assistant",
                    content=answer,
                )
            )
            await asyncio.wait_for(db.commit(), timeout=timeout)
            _app._db_retry_after = 0.0
    except Exception as exc:
        _app._db_retry_after = time.monotonic() + 60.0
        try:
            prometheus_metrics.record_message_persist_failure(path)
        except Exception:
            pass
        logger.warning("Failed to persist messages (%s): %s", path, exc)


@router.post("/ask", response_model=AskResponse)
@limiter.limit("60/minute")
async def ask(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
) -> AskResponse:
    """Ask a question to the RAG assistant."""
    _app = _app_module()
    t0 = time.monotonic()
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is empty")

    settings = _app.get_settings()
    timeout = float(getattr(settings, "request_timeout_sec", 30.0))
    request_id = get_request_id()
    logger.info(
        "req_id=%s /api/ask effective_timeouts request=%.3fs "
        "ask_budget=%.3fs ollama_mistral=%.3fs gracekelly=%.3fs "
        "profile=%s",
        request_id or "-",
        timeout,
        float(getattr(settings, "ask_budget_sec", 0.0) or 0.0),
        float(getattr(settings, "ollama_request_timeout_sec", 60.0)),
        float(getattr(settings, "gracekelly_request_timeout_sec", 30.0)),
        str(getattr(settings, "llm_provider_profile", "local-first")),
        extra={"trace_id": request_id},
    )

    tenant = get_current_tenant() or _user.get("tenant", "default")
    session_started_at = time.monotonic()
    logger.info(
        "req_id=%s /api/ask session_setup boundary=start monotonic=%.6f",
        request_id or "-",
        session_started_at,
        extra={"trace_id": request_id},
    )
    try:
        session_id, session = await _app._get_or_create_session(body.session_id, tenant)
    finally:
        session_finished_at = time.monotonic()
        logger.info(
            "req_id=%s /api/ask session_setup boundary=end "
            "monotonic=%.6f elapsed=%.6fs",
            request_id or "-",
            session_finished_at,
            session_finished_at - session_started_at,
            extra={"trace_id": request_id},
        )

    cache_enabled = bool(getattr(settings, "llm_cache_enabled", False))
    if cache_enabled:
        # The cache key is tenant+question only. A follow-up inside a dialog
        # ("а сколько это стоит?") depends on the conversation context, so
        # caching it — or serving it from cache — would leak answers across
        # unrelated dialogs. Cache applies to history-less first turns only.
        session_history = (
            getattr(session, "_history", None)
            if hasattr(session, "_history")
            else session.get("history") if isinstance(session, dict) else None
        )
        if session_history:
            cache_enabled = False
    llm_cache_key = _app._cache_key(tenant, question)
    cache_hit = False
    # Provenance for the QUALITY_SCORE metric; cached replays keep their
    # original "llm" provenance, agentic unmeasured paths report "unmeasured".
    quality_source = "llm"

    if hasattr(session, "ask"):
        if cache_enabled:
            cached_payload = _app.cache_json_get(llm_cache_key)
            if isinstance(cached_payload, dict) and cached_payload.get("answer"):
                try:
                    prometheus_metrics.LLM_CACHE_HITS.labels(tenant=tenant).inc()
                except Exception:
                    pass

                answer = str(cached_payload.get("answer") or "")
                cached_sources = []
                for item in cached_payload.get("sources", [])[:5]:
                    if not isinstance(item, dict):
                        continue
                    cached_sources.append(
                        SourceInfo(
                            source=item.get("source", ""),
                            page_content=item.get("page_content", ""),
                        )
                    )
                cached_citations = []
                for item in cached_payload.get("citations", []):
                    if not isinstance(item, dict):
                        continue
                    cached_citations.append(
                        Citation(
                            index=int(item.get("index") or 0),
                            doc_id=str(item.get("doc_id") or ""),
                            title=str(item.get("title") or ""),
                            excerpt=str(item.get("excerpt") or ""),
                        )
                    )
                if not cached_citations:
                    for idx, source in enumerate(cached_sources, start=1):
                        cached_citations.append(
                            Citation(
                                index=idx,
                                doc_id=source.source or f"doc_{idx}",
                                title=source.source or f"doc_{idx}",
                                excerpt=(source.page_content or "")[:300],
                            )
                        )

                if hasattr(session, "_history"):
                    session._history.append({"role": "user", "content": question})
                    session._history.append({"role": "assistant", "content": answer})
                    max_history = getattr(session, "_max_history", 20)
                    if len(session._history) > max_history * 2:
                        session._history = session._history[-(max_history * 2):]
                elif isinstance(session, dict):
                    session["history"].append({"role": "user", "content": question})
                    session["history"].append({"role": "assistant", "content": answer})

                response = AskResponse(
                    answer=answer,
                    quality_score=int(cached_payload.get("quality_score") or 50),
                    route=str(cached_payload.get("route") or "auto"),
                    sources=cached_sources,
                    citations=cached_citations,
                    session_id=session_id,
                    trace_id="",
                    suggested_questions=cached_payload.get("suggested_questions") or [],
                    cached=True,
                )
                cache_hit = True
            else:
                try:
                    prometheus_metrics.LLM_CACHE_MISSES.labels(tenant=tenant).inc()
                except Exception:
                    pass

        if not cache_hit:
            acquire_timeout = float(
                getattr(settings, "pipeline_acquire_timeout_sec", 0.5)
            )
            ask_kwargs: dict[str, Any] = {
                "trace_id": request_id,
                "tenant_id": tenant,
                "confirm": body.confirm,
                "user_id": _user.get("sub", "anonymous"),
                "session_id": session_id,
                # Cooperative provider deadline matches outer wait_for wall (§3.1b).
                "deadline_sec": float(timeout),
            }
            semaphore = _app._get_pipeline_semaphore()
            try:
                await asyncio.wait_for(semaphore.acquire(), timeout=acquire_timeout)
            except asyncio.TimeoutError:
                try:
                    prometheus_metrics.record_pipeline_rejection("busy")
                except Exception:
                    pass
                logger.warning(
                    "req_id=%s /api/ask rejected: pipeline pool saturated",
                    request_id or "-",
                )
                raise HTTPException(
                    status_code=503,
                    detail="Server is busy processing other requests - retry in a moment",
                ) from None
            # Hold pipeline capacity until the underlying worker finishes.
            # asyncio.wait_for only cancels the wait — not the thread (REL-01 / §3.1a).
            capacity_held_for_orphan = False
            try:
                prometheus_metrics.INFLIGHT_PIPELINES.inc()
                try:
                    from utils.request_executor import get_request_executor

                    loop = asyncio.get_running_loop()
                    ask_future = loop.run_in_executor(
                        get_request_executor(),
                        lambda: session.ask(question, **ask_kwargs),
                    )
                    try:
                        result = await asyncio.wait_for(
                            asyncio.shield(ask_future),
                            timeout=timeout,
                        )
                    except asyncio.TimeoutError:
                        # Keep semaphore + inflight until the orphaned worker ends.
                        capacity_held_for_orphan = True
                        _hold_capacity_until_future_done(
                            loop=loop,
                            fut=ask_future,
                            semaphore=semaphore,
                        )
                        try:
                            prometheus_metrics.record_request_timeout("/api/ask")
                        except Exception:
                            pass
                        outer_timeout_at = time.monotonic()
                        logger.warning(
                            "req_id=%s /api/ask exceeded timeout=%.1fs "
                            "outer_timeout_monotonic=%.6f capacity_held_until_done=1",
                            request_id or "-",
                            timeout,
                            outer_timeout_at,
                            extra={"trace_id": request_id},
                        )
                        raise HTTPException(
                            status_code=504,
                            detail=f"Request exceeded {timeout:.0f}s wall-time limit",
                        ) from None

                    answer = result.get("answer") or ""
                    quality = result.get("quality_score") or 50
                    route = result.get("route") or "auto"
                    quality_source = str(result.get("quality_source") or "llm")

                    sources_list = []
                    citations_list = []
                    docs = result.get("graded_docs") or result.get("context_docs") or []
                    for idx, doc in enumerate(docs, start=1):
                        if isinstance(doc, dict):
                            metadata = doc.get("metadata", {}) or {}
                            src = metadata.get("source") or metadata.get("file_name") or ""
                            content = doc.get("page_content", "")
                        else:
                            metadata = getattr(doc, "metadata", {}) or {}
                            src = metadata.get("source") or metadata.get("file_name") or ""
                            content = getattr(doc, "page_content", "")
                        sources_list.append(SourceInfo(source=src, page_content=content))
                        citations_list.append(
                            Citation(
                                index=idx,
                                doc_id=str(
                                    metadata.get("doc_id")
                                    or metadata.get("id")
                                    or src
                                    or f"doc_{idx}"
                                ),
                                title=str(
                                    metadata.get("title")
                                    or src
                                    or metadata.get("file_name")
                                    or f"doc_{idx}"
                                ),
                                excerpt=str(content or "")[:300],
                            )
                        )
                    if result.get("citations"):
                        citations_list = [
                            Citation(
                                index=int(item.get("index") or 0),
                                doc_id=str(item.get("doc_id") or ""),
                                title=str(item.get("title") or ""),
                                excerpt=str(item.get("excerpt") or ""),
                            )
                            for item in result.get("citations", [])
                            if isinstance(item, dict)
                        ]

                    # Pass through graph-owned escalation identity when present
                    # (handle_error / agentic create_ticket); otherwise §4.4
                    # auto-escalates terminal human/error on the normal path.
                    ticket_id = result.get("ticket_id")
                    delivery_state = result.get("delivery_state")
                    if ticket_id is not None:
                        ticket_id = str(ticket_id) or None
                    if delivery_state is not None:
                        delivery_state = str(delivery_state) or None

                    route_norm = str(route or "auto").strip().lower() or "auto"
                    if (
                        route_norm in _TERMINAL_ESCALATE_ROUTES
                        and not ticket_id
                    ):
                        from services.escalation import create_escalation

                        try:
                            esc = await create_escalation(
                                tenant_id=tenant or "default",
                                session_id=session_id,
                                question=question,
                                source="human_route",
                                ai_draft=answer or None,
                                reason=f"route={route_norm}",
                                trace_id=str(
                                    result.get("trace_id") or request_id or ""
                                ),
                                project_root=Path(
                                    getattr(_app, "PROJECT_ROOT", Path("."))
                                ),
                            )
                            ticket_id = esc.ticket_id
                            delivery_state = esc.delivery_state
                            # Keep the pipeline answer (AI draft). Never inject a
                            # false "передан оператору" claim when durable failed.
                            # Operator-facing copy lives on the ticket / ai_draft.
                        except Exception as esc_exc:
                            logger.error(
                                "Auto-escalation on route=%s failed: %s",
                                route_norm,
                                esc_exc,
                                exc_info=True,
                            )
                            ticket_id = None
                            delivery_state = "failed"

                    response = AskResponse(
                        answer=answer,
                        quality_score=quality,
                        route=route,
                        sources=sources_list,
                        citations=citations_list,
                        session_id=session_id,
                        trace_id=result.get("trace_id") or "",
                        suggested_questions=result.get("suggested_questions") or [],
                        requires_confirmation=bool(result.get("requires_confirmation")),
                        action_summary=str(result.get("action_summary") or ""),
                        ticket_id=ticket_id,
                        delivery_state=delivery_state,
                    )
                    if (
                        cache_enabled
                        and response.answer
                        and response.route == "auto"
                        and not response.requires_confirmation
                        and not result.get("tool_calls")
                    ):
                        _app.cache_json_set(
                            llm_cache_key,
                            {
                                "answer": response.answer,
                                "quality_score": response.quality_score,
                                "route": response.route,
                                "sources": [source.model_dump() for source in response.sources],
                                "suggested_questions": response.suggested_questions,
                            },
                            ttl_seconds=int(getattr(settings, "llm_cache_ttl_seconds", 3600)),
                        )
                except HTTPException:
                    raise
                except Exception as exc:
                    logger.error("Pipeline error in /ask: %s", exc, exc_info=True)
                    # Plan §4.3: single idempotent escalation service — claim
                    # operator handoff only after durable ticket insert.
                    from services.escalation import create_escalation

                    draft = (
                        f"Запрос пользователя: {question}\n\n"
                        "Черновик ответа: Произошла техническая ошибка "
                        "при обработке запроса. Пожалуйста, ответьте "
                        "пользователю вручную."
                    )
                    esc = await create_escalation(
                        tenant_id=tenant or "default",
                        session_id=session_id,
                        question=question,
                        source="pipeline_error",
                        ai_draft=draft,
                        reason="pipeline_exception",
                        trace_id=request_id or "",
                        project_root=Path(getattr(_app, "PROJECT_ROOT", Path("."))),
                    )
                    answer = esc.user_message
                    if hasattr(session, "_history"):
                        session._history.append({"role": "user", "content": question})
                        session._history.append({"role": "assistant", "content": answer})
                    elif isinstance(session, dict):
                        session["history"].append({"role": "user", "content": question})
                        session["history"].append({"role": "assistant", "content": answer})
                    response = AskResponse(
                        answer=answer,
                        quality_score=0,
                        route="human" if esc.durable else "error",
                        sources=[],
                        citations=[],
                        session_id=session_id,
                        trace_id=request_id or "",
                        suggested_questions=[],
                        ticket_id=esc.ticket_id,
                        delivery_state=esc.delivery_state,
                    )
            finally:
                # On outer timeout the done-callback owns release (capacity hold).
                if not capacity_held_for_orphan:
                    _release_pipeline_capacity(semaphore)
    else:
        session["history"].append({"role": "user", "content": question})
        fallback_answer = f"[DEMO] Pipeline not available. Question received: {question}"
        session["history"].append({"role": "assistant", "content": fallback_answer})
        response = AskResponse(
            answer=fallback_answer,
            quality_score=0,
            route="human",
            sources=[],
            citations=[],
            session_id=session_id,
            trace_id="",
            suggested_questions=[],
        )

    await _persist_ask_messages(
        session_id=session_id,
        tenant_id=tenant,
        question=question,
        answer=response.answer,
        path="ask",
    )

    await _app.log_audit(
        actor=_user.get("sub", "anonymous"),
        action="ask",
        resource=f"session:{session_id}",
        tenant_id=tenant,
        detail={
            "question_length": len(body.question),
            "tenant": tenant,
        },
        ip_address=request.client.host if request.client else None,
    )
    duration = time.monotonic() - t0
    prometheus_metrics.REQUEST_DURATION.observe(duration)
    prometheus_metrics.REQUEST_COUNT.labels(route=response.route).inc()
    if response.quality_score:
        prometheus_metrics.QUALITY_SCORE.observe(response.quality_score)
        try:
            prometheus_metrics.record_quality_score_source(quality_source)
        except Exception:
            pass
    if response.route == "human":
        prometheus_metrics.ESCALATION_TOTAL.inc()
    prometheus_metrics.ACTIVE_SESSIONS.set(len(_app._sessions))
    if response.citations:
        spawn_tracked(_app._record_citation_stats(tenant, list(response.citations)))
    return JSONResponse(
        content=response.model_dump(),
        media_type="application/json; charset=utf-8",
    )


@router.post("/chat")
@limiter.limit("60/minute")
async def chat(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
) -> AskResponse:
    return await ask(request, body, _user)


@router.post("/ask/stream")
@limiter.limit("60/minute")
async def ask_stream(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
) -> StreamingResponse:
    """SSE endpoint с реальным стримингом токенов из Ollama."""
    _app = _app_module()

    async def event_generator() -> AsyncGenerator[str, None]:
        yield "data: " + _json.dumps({"type": "status", "node": "processing"}) + "\n\n"

        tenant = get_current_tenant() or _user.get("tenant", "default")
        session_id, session = await _app._get_or_create_session(body.session_id, tenant)
        question = (body.question or "").strip()

        if not question:
            yield "data: " + _json.dumps({
                "type": "error",
                "detail": "question is required",
            }) + "\n\n"
            return

        await _app.log_audit(
            actor=_user.get("sub", "anonymous"),
            action="ask",
            resource=f"session:{session_id}",
            tenant_id=tenant,
            detail={
                "question_length": len(body.question),
                "tenant": tenant,
            },
            ip_address=request.client.host if request.client else None,
        )

        # The except-branch below reuses graph_task/_session_ask; they must exist
        # even when the failure happens before their full initialization,
        # otherwise the fallback itself dies with NameError and the SSE stream
        # ends without a result event.
        graph_task: asyncio.Future | None = None
        request_id = get_request_id()
        settings_pre = _app.get_settings()
        request_timeout = float(getattr(settings_pre, "request_timeout_sec", 60.0))
        capacity_held_for_orphan = False
        loop = asyncio.get_running_loop()

        def _session_ask() -> Any:
            """Parity/fallback full-graph ask with cooperative deadline kwargs."""
            return session.ask(
                question,
                trace_id=request_id,
                tenant_id=tenant,
                confirm=body.confirm,
                user_id=_user.get("sub", "anonymous"),
                session_id=session_id,
                deadline_sec=request_timeout,
            )

        # Streaming consumes the same retriever/LLM resources as /api/ask —
        # it must respect the same bounded-concurrency pool instead of
        # bypassing it (fable_com.md F-3).
        semaphore = _app._get_pipeline_semaphore()
        acquire_timeout = float(
            getattr(settings_pre, "pipeline_acquire_timeout_sec", 0.5)
        )
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=acquire_timeout)
        except asyncio.TimeoutError:
            try:
                prometheus_metrics.record_pipeline_rejection("busy")
            except Exception:
                pass
            yield "data: " + _json.dumps({
                "type": "error",
                "detail": "Server is busy processing other requests - retry in a moment",
            }) + "\n\n"
            return
        try:
            prometheus_metrics.INFLIGHT_PIPELINES.inc()
        except Exception:
            pass

        # Bind deadline + LLM budget for stream-side provider work (3.1f).
        # Parity worker reuses the same budget object via ContextVar install.
        from llm.request_budget import (
            bind_llm_request_budget_from_settings,
            clear_llm_request_budget,
            get_llm_request_budget,
            set_llm_request_budget,
        )
        from utils.request_deadline import (
            RequestDeadlineExceeded,
            bind_request_deadline,
            check_request_deadline,
            clear_request_deadline,
            set_request_deadline,
        )
        from utils.request_executor import get_request_executor

        stream_deadline_obj = bind_request_deadline(
            request_timeout, source="ask_stream"
        )
        stream_budget_obj = bind_llm_request_budget_from_settings(
            settings_pre, source="ask_stream"
        )

        def _session_ask_with_shared_limits() -> Any:
            if stream_deadline_obj is not None:
                set_request_deadline(stream_deadline_obj)
            if stream_budget_obj is not None:
                set_llm_request_budget(stream_budget_obj)
            return _session_ask()

        try:
            prompt = ""
            docs: list[Any] = []
            plain_docs: list[dict[str, Any]] = []
            chat_history: list[dict[str, str]] = []
            # Plan §4.1–4.2: STREAMING_RAG_PARITY=true → single graph generation
            # (session.ask only). SSE tokens are UX chunks of the graph answer —
            # not a second LLM stream. Off by default keeps legacy direct stream.
            graph_parity_enabled = bool(
                getattr(settings_pre, "streaming_rag_parity", False)
            )
            graph_parity_timeout = float(
                getattr(settings_pre, "request_timeout_sec", 60.0)
            )
            history_pre_len = (
                len(getattr(session, "_history", []))
                if hasattr(session, "_history")
                else None
            )
            settings = _app.get_settings()

            if graph_parity_enabled and (
                hasattr(session, "iter_ask_events") or hasattr(session, "ask")
            ):
                # --- 4.2/4.7 single graph path (no parallel stream LLM) ---
                # Prefer iter_ask_events (§4.7): real LangGraph node status SSE.
                # Fall back to session.ask for test doubles without event stream.
                graph_result: dict[str, Any] | None = None
                graph_nodes: list[str] = []
                use_events = callable(getattr(session, "iter_ask_events", None))

                # Plan §4.8: live provider tokens from generate (when available).
                provider_tokens_seen = False
                token_start_emitted = False

                if use_events:
                    event_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

                    def _session_events_worker() -> None:
                        try:
                            if stream_deadline_obj is not None:
                                from utils.request_deadline import (  # noqa: PLC0415
                                    set_request_deadline,
                                )

                                set_request_deadline(stream_deadline_obj)
                            if stream_budget_obj is not None:
                                from llm.request_budget import (  # noqa: PLC0415
                                    set_llm_request_budget,
                                )

                                set_llm_request_budget(stream_budget_obj)
                            for ev in session.iter_ask_events(
                                question,
                                tenant_id=tenant,
                                user_id=str(_user.get("sub") or "anonymous"),
                                session_id=session_id,
                                trace_id=request_id,
                                confirm=body.confirm,
                            ):
                                loop.call_soon_threadsafe(
                                    event_queue.put_nowait, ("event", ev)
                                )
                            loop.call_soon_threadsafe(
                                event_queue.put_nowait, ("done", None)
                            )
                        except Exception as worker_exc:  # noqa: BLE001
                            loop.call_soon_threadsafe(
                                event_queue.put_nowait, ("error", worker_exc)
                            )

                    graph_task = loop.run_in_executor(
                        get_request_executor(),
                        _session_events_worker,
                    )
                    try:
                        while True:
                            try:
                                kind, payload = await asyncio.wait_for(
                                    event_queue.get(),
                                    timeout=graph_parity_timeout,
                                )
                            except asyncio.TimeoutError:
                                logger.warning(
                                    "Streaming graph events exceeded %.1fs timeout; "
                                    "holding pipeline capacity until orphan completes",
                                    graph_parity_timeout,
                                )
                                if not capacity_held_for_orphan:
                                    capacity_held_for_orphan = True
                                    _hold_capacity_until_future_done(
                                        loop=loop,
                                        fut=graph_task,
                                        semaphore=semaphore,
                                    )
                                try:
                                    prometheus_metrics.record_request_timeout(
                                        "/api/ask/stream"
                                    )
                                except Exception:
                                    pass
                                yield "data: " + _json.dumps({
                                    "type": "error",
                                    "detail": "Request deadline exceeded waiting for graph",
                                    "route": "timeout",
                                    "generation_source": "graph_only",
                                }) + "\n\n"
                                return

                            if kind == "error":
                                logger.warning(
                                    "Streaming graph event path failed: %s", payload
                                )
                                yield "data: " + _json.dumps({
                                    "type": "error",
                                    "detail": "Graph pipeline failed",
                                    "route": "error",
                                    "generation_source": "graph_only",
                                }) + "\n\n"
                                return
                            if kind == "done":
                                break
                            if not isinstance(payload, dict):
                                continue
                            if payload.get("type") == "status":
                                node_name = str(payload.get("node") or "unknown")
                                graph_nodes.append(node_name)
                                yield "data: " + _json.dumps({
                                    "type": "status",
                                    "node": node_name,
                                    "source": "graph",
                                    "phase": str(payload.get("phase") or "end"),
                                }) + "\n\n"
                            elif payload.get("type") == "token":
                                # Live provider tokens from generate (§4.8).
                                token_text = str(payload.get("token") or "")
                                if not token_text:
                                    continue
                                token_source = str(
                                    payload.get("token_source") or "provider_generate"
                                )
                                if not token_start_emitted:
                                    token_start_emitted = True
                                    yield "data: " + _json.dumps({
                                        "type": "token_start",
                                        "source": "graph",
                                        "token_source": token_source,
                                    }) + "\n\n"
                                if token_source == "provider_generate":
                                    provider_tokens_seen = True
                                yield "data: " + _json.dumps({
                                    "type": "token",
                                    "token": token_text,
                                    "source": "graph",
                                    "token_source": token_source,
                                }) + "\n\n"
                            elif payload.get("type") == "pipeline_result":
                                state = payload.get("state")
                                if isinstance(state, dict):
                                    graph_result = state
                                nodes = payload.get("nodes")
                                if isinstance(nodes, list):
                                    for n in nodes:
                                        name = str(n)
                                        if name and name not in graph_nodes:
                                            graph_nodes.append(name)
                    except Exception as graph_exc:
                        logger.warning(
                            "Streaming graph event path failed: %s", graph_exc
                        )
                        yield "data: " + _json.dumps({
                            "type": "error",
                            "detail": "Graph pipeline failed",
                            "route": "error",
                            "generation_source": "graph_only",
                        }) + "\n\n"
                        return
                else:
                    # Legacy §4.2 ask-only path (test doubles without events).
                    graph_task = loop.run_in_executor(
                        get_request_executor(),
                        _session_ask_with_shared_limits,
                    )
                    try:
                        graph_result = await asyncio.wait_for(
                            asyncio.shield(graph_task),
                            timeout=graph_parity_timeout,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(
                            "Streaming graph path exceeded %.1fs timeout; "
                            "holding pipeline capacity until orphan completes",
                            graph_parity_timeout,
                        )
                        if not capacity_held_for_orphan:
                            capacity_held_for_orphan = True
                            _hold_capacity_until_future_done(
                                loop=loop,
                                fut=graph_task,
                                semaphore=semaphore,
                            )
                        try:
                            prometheus_metrics.record_request_timeout("/api/ask/stream")
                        except Exception:
                            pass
                        yield "data: " + _json.dumps({
                            "type": "error",
                            "detail": "Request deadline exceeded waiting for graph",
                            "route": "timeout",
                            "generation_source": "graph_only",
                        }) + "\n\n"
                        return
                    except Exception as graph_exc:
                        logger.warning("Streaming graph path failed: %s", graph_exc)
                        yield "data: " + _json.dumps({
                            "type": "error",
                            "detail": "Graph pipeline failed",
                            "route": "error",
                            "generation_source": "graph_only",
                        }) + "\n\n"
                        return

                if not isinstance(graph_result, dict):
                    yield "data: " + _json.dumps({
                        "type": "error",
                        "detail": "Graph pipeline returned no result",
                        "route": "error",
                        "generation_source": "graph_only",
                    }) + "\n\n"
                    return

                graph_appended_history = False
                if (
                    history_pre_len is not None
                    and hasattr(session, "_history")
                    and len(session._history) > history_pre_len
                ):
                    graph_appended_history = True

                terminal_answer = str(graph_result.get("answer") or "")
                # Plan §4.8: if live provider tokens already streamed, do not
                # re-chunk the finished answer. Else §4.7 UX chunk fallback.
                if provider_tokens_seen:
                    token_source_final = "provider_generate"
                else:
                    token_source_final = "graph_answer_chunks"
                    if not token_start_emitted:
                        yield "data: " + _json.dumps({
                            "type": "token_start",
                            "source": "graph",
                            "token_source": token_source_final,
                        }) + "\n\n"
                    for chunk in _chunk_text_for_sse(terminal_answer):
                        yield "data: " + _json.dumps({
                            "type": "token",
                            "token": chunk,
                            "source": "graph",
                            "token_source": token_source_final,
                        }) + "\n\n"

                if not graph_appended_history:
                    _append_stream_history(
                        session,
                        question=question,
                        answer=terminal_answer,
                    )

                quality = int(graph_result.get("quality_score") or 0)
                quality_source = str(graph_result.get("quality_source") or "llm")
                route = str(graph_result.get("route") or "human")
                trace_id_value = str(graph_result.get("trace_id") or "")
                suggested_questions = list(graph_result.get("suggested_questions") or [])
                sources, citations = _graph_result_sources_and_citations(graph_result)

                await _persist_ask_messages(
                    session_id=session_id,
                    tenant_id=tenant,
                    question=question,
                    answer=terminal_answer,
                    path="stream",
                )
                try:
                    prometheus_metrics.record_quality_score_source(quality_source)
                except Exception:
                    pass
                yield "data: " + _json.dumps({
                    "type": "result",
                    "answer": terminal_answer,
                    "answer_source": "graph",
                    "generation_source": "graph_only",
                    "events_source": "graph" if use_events else "ask",
                    "token_source": token_source_final,
                    "graph_nodes": graph_nodes,
                    "quality_score": quality,
                    "quality_source": quality_source,
                    "route": route,
                    "session_id": session_id,
                    "sources": sources,
                    "citations": citations,
                    "trace_id": trace_id_value,
                    "suggested_questions": suggested_questions,
                }) + "\n\n"
                return

            # --- Legacy direct stream (parity off): single stream LLM path ---
            if hasattr(session, "_retriever") and session._retriever is not None:
                # Cooperative deadline (plan §3.1g): refuse stream retrieve after wall.
                try:
                    check_request_deadline("stream.retrieve")
                except RequestDeadlineExceeded as deadline_exc:
                    logger.warning(
                        "Streaming retrieve refused after deadline: %s",
                        deadline_exc,
                    )
                    try:
                        prometheus_metrics.record_request_timeout("/api/ask/stream")
                    except Exception:
                        pass
                    yield "data: " + _json.dumps({
                        "type": "error",
                        "detail": "Request deadline exceeded before retrieval",
                        "route": "timeout",
                    }) + "\n\n"
                    return
                docs = await asyncio.get_running_loop().run_in_executor(
                    None,
                    session._retriever.get_relevant_documents,
                    question,
                )

                if hasattr(session, "history"):
                    chat_history = session.history
                elif isinstance(session, dict):
                    chat_history = session.get("history", [])

                from agent.prompts import (  # noqa: PLC0415
                    build_conversational_qa_prompt,
                    build_qa_prompt,
                )

                plain_docs = []
                for doc in docs[:5]:
                    if hasattr(doc, "page_content"):
                        plain_docs.append({
                            "page_content": getattr(doc, "page_content", ""),
                            "metadata": getattr(doc, "metadata", {}) or {},
                        })
                    elif isinstance(doc, dict):
                        plain_docs.append(doc)

                if chat_history:
                    prompt = build_conversational_qa_prompt(
                        question=question,
                        context_docs=plain_docs,
                        chat_history=chat_history,
                    )
                else:
                    prompt = build_qa_prompt(question=question, context_docs=plain_docs)

            if not prompt:
                raise RuntimeError("streaming prompt unavailable")

            settings = _app.get_settings()
            full_answer = ""
            streaming_llm = getattr(session, "_llm", None)
            if not (
                streaming_llm is not None
                and callable(getattr(streaming_llm, "generate_stream", None))
            ) and _app._build_provider_runtime is not None:
                try:
                    runtime = _app._build_provider_runtime(settings)
                except Exception as runtime_exc:
                    logger.warning("Streaming runtime unavailable: %s", runtime_exc)
                else:
                    for candidate in (runtime.strong, runtime.fast):
                        if callable(getattr(candidate, "generate_stream", None)):
                            streaming_llm = candidate
                            break

            # Wall-clock budget for the token loop: without it a wedged model
            # holds the SSE connection (and now a pipeline slot) forever.
            stream_deadline = time.monotonic() + float(
                getattr(settings, "streaming_timeout_sec", 120.0)
            )
            stream_truncated = False
            yield "data: " + _json.dumps({"type": "token_start"}) + "\n\n"
            try:
                if streaming_llm is not None and callable(getattr(streaming_llm, "generate_stream", None)):
                    async for token in streaming_llm.generate_stream(
                        [{"role": "user", "content": prompt}],
                    ):
                        full_answer += token
                        yield "data: " + _json.dumps({
                            "type": "token",
                            "token": token,
                        }) + "\n\n"
                        if time.monotonic() > stream_deadline:
                            stream_truncated = True
                            break
                else:
                    async for token in _app._stream_ollama(
                        prompt,
                        settings.ollama_model_name,
                        settings.ollama_base_url,
                    ):
                        full_answer += token
                        yield "data: " + _json.dumps({
                            "type": "token",
                            "token": token,
                        }) + "\n\n"
                        if time.monotonic() > stream_deadline:
                            stream_truncated = True
                            break
            except Exception as exc:
                logger.warning("Streaming error in /ask/stream: %s", exc)
                if not full_answer:
                    raise
            if stream_truncated:
                try:
                    prometheus_metrics.record_request_timeout("/api/ask/stream")
                except Exception:
                    pass
                logger.warning(
                    "Streaming exceeded %.0fs budget; answer truncated",
                    float(getattr(settings, "streaming_timeout_sec", 120.0)),
                )

            if not full_answer:
                raise RuntimeError("empty streaming answer")

            sources = []
            citations = []
            for idx, doc in enumerate(docs, start=1):
                if hasattr(doc, "page_content"):
                    metadata = getattr(doc, "metadata", {}) or {}
                    sources.append({
                        "source": metadata.get("source") or metadata.get("file_name") or "",
                        "page_content": getattr(doc, "page_content", ""),
                    })
                elif isinstance(doc, dict):
                    metadata = doc.get("metadata", {}) or {}
                    sources.append({
                        "source": metadata.get("source") or metadata.get("file_name") or "",
                        "page_content": doc.get("page_content", ""),
                    })
                else:
                    metadata = {}
                citations.append({
                    "index": idx,
                    "doc_id": str(
                        metadata.get("doc_id")
                        or metadata.get("id")
                        or metadata.get("source")
                        or metadata.get("file_name")
                        or f"doc_{idx}"
                    ),
                    "title": str(
                        metadata.get("title")
                        or metadata.get("source")
                        or metadata.get("file_name")
                        or metadata.get("doc_id")
                        or f"doc_{idx}"
                    ),
                    "excerpt": str(sources[-1]["page_content"] if sources else "")[:300],
                })

            # Cheap RAG parity (fable_com.md F-3): one self-eval call over the
            # docs the stream actually used replaces the length heuristic, so
            # streamed answers stop reporting a synthetic quality of 70/40.
            heuristic_quality = 70 if len(full_answer.strip()) > 20 or sources else 40
            quality = heuristic_quality
            quality_source = "heuristic"
            if bool(getattr(settings, "streaming_quality_eval", True)):
                try:
                    from agent.graph import LocalOllamaLLM, _parse_int_score  # noqa: PLC0415
                    from agent.prompts import build_self_eval_prompt  # noqa: PLC0415

                    eval_llm = getattr(session, "_llm", None)
                    if eval_llm is None and callable(getattr(streaming_llm, "invoke", None)):
                        eval_llm = streaming_llm
                    if eval_llm is None:
                        eval_llm = LocalOllamaLLM(model_name=settings.ollama_model_name)

                    answer_for_eval = re.sub(r"\s*\[\d+\]", "", full_answer)
                    answer_for_eval = re.sub(r"\s{2,}", " ", answer_for_eval).strip()
                    eval_prompt = build_self_eval_prompt(
                        question=question,
                        answer=answer_for_eval,
                        context_docs=plain_docs,
                    )
                    raw_eval = await asyncio.get_running_loop().run_in_executor(
                        None, eval_llm.invoke, eval_prompt
                    )
                    # "llm" provenance only when the model actually returned a
                    # numeric score; an unparseable reply keeps the heuristic
                    # quality AND its routing threshold (quality_threshold only
                    # applies to genuine LLM scores).
                    parsed_eval = _parse_int_score(raw_eval, default=-1)
                    if parsed_eval != -1:
                        quality = parsed_eval
                        quality_source = "llm"
                    else:
                        logger.warning(
                            "Streaming self-eval returned no numeric score; keeping heuristic quality"
                        )
                except Exception as eval_exc:
                    logger.warning(
                        "Streaming self-eval failed, falling back to heuristic quality: %s",
                        eval_exc,
                    )
            if quality_source == "llm":
                route = "auto" if quality >= int(getattr(settings, "quality_threshold", 80)) else "human"
            else:
                route = "auto" if quality >= 70 else "human"
            suggested_questions: list[str] = []
            if route == "auto":
                try:
                    from agent.prompts import build_suggested_questions_prompt  # noqa: PLC0415

                    question_llm = getattr(session, "_llm", None)
                    if question_llm is None:
                        from agent.graph import LocalOllamaLLM  # noqa: PLC0415
                        question_llm = LocalOllamaLLM(model_name=settings.ollama_model_name)

                    context_snippet = "\n\n".join(
                        source.get("page_content", "")
                        for source in sources[:2]
                        if source.get("page_content")
                    )[:500]
                    prompt = build_suggested_questions_prompt(
                        question=question,
                        answer=full_answer,
                        context_snippet=context_snippet,
                    )
                    raw_questions = await asyncio.get_running_loop().run_in_executor(
                        None,
                        question_llm.invoke,
                        prompt,
                    )
                    suggested_questions = [
                        re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
                        for line in raw_questions.strip().splitlines()
                        if line.strip()
                    ][:3]
                except Exception as suggest_exc:
                    logger.warning(
                        "Failed to generate streaming suggested questions: %s",
                        suggest_exc,
                    )
            trace_id_value = ""
            graph_appended_history = False
            graph_result: dict[str, Any] | None = None
            if graph_task is not None:
                try:
                    graph_result = await asyncio.wait_for(
                        asyncio.shield(graph_task),
                        timeout=graph_parity_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Streaming RAG parity task exceeded %.1fs timeout; "
                        "holding pipeline capacity until orphan completes",
                        graph_parity_timeout,
                    )
                    # Thread work is not cancellable; hold capacity until done (3.1f).
                    if not capacity_held_for_orphan:
                        capacity_held_for_orphan = True
                        _hold_capacity_until_future_done(
                            loop=loop,
                            fut=graph_task,
                            semaphore=semaphore,
                        )
                    graph_result = None
                except Exception as graph_exc:
                    logger.warning("Streaming RAG parity task failed: %s", graph_exc)
                    graph_result = None
                # session.ask appends turns to session._history itself (see
                # ConversationSession._append_history). Detect growth so we do
                # not double-append after a successful graph mutation (plan §4.1).
                if (
                    history_pre_len is not None
                    and hasattr(session, "_history")
                    and len(session._history) > history_pre_len
                ):
                    graph_appended_history = True

            terminal_answer, skip_stream_history, answer_source = _resolve_stream_terminal(
                stream_answer=full_answer,
                graph_result=graph_result if isinstance(graph_result, dict) else None,
                graph_appended_history=graph_appended_history,
            )

            if not skip_stream_history:
                _append_stream_history(
                    session,
                    question=question,
                    answer=terminal_answer,
                )

            if isinstance(graph_result, dict) and graph_result:
                if graph_result.get("quality_score") is not None:
                    quality = int(graph_result["quality_score"])
                    quality_source = str(graph_result.get("quality_source") or "llm")
                if graph_result.get("route"):
                    route = str(graph_result["route"])
                if graph_result.get("trace_id"):
                    trace_id_value = str(graph_result["trace_id"])
                if graph_result.get("suggested_questions"):
                    suggested_questions = list(graph_result["suggested_questions"])
                graph_citations_raw = graph_result.get("citations") or []
                if graph_citations_raw:
                    citations = [
                        {
                            "index": int(item.get("index") or 0),
                            "doc_id": str(item.get("doc_id") or ""),
                            "title": str(item.get("title") or ""),
                            "excerpt": str(item.get("excerpt") or ""),
                        }
                        for item in graph_citations_raw
                        if isinstance(item, dict)
                    ]
                graph_graded = (
                    graph_result.get("graded_docs")
                    or graph_result.get("context_docs")
                    or []
                )
                if graph_graded:
                    sources = []
                    for item in graph_graded:
                        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
                        content = item.get("page_content", "") if isinstance(item, dict) else ""
                        sources.append({
                            "source": metadata.get("source") or metadata.get("file_name") or "",
                            "page_content": content,
                        })

            await _persist_ask_messages(
                session_id=session_id,
                tenant_id=tenant,
                question=question,
                answer=terminal_answer,
                path="stream",
            )
            try:
                prometheus_metrics.record_quality_score_source(quality_source)
            except Exception:
                pass
            yield "data: " + _json.dumps({
                "type": "result",
                "answer": terminal_answer,
                "answer_source": answer_source,
                "generation_source": "stream",
                "quality_score": quality,
                "quality_source": quality_source,
                "route": route,
                "session_id": session_id,
                "sources": sources,
                "citations": citations,
                "trace_id": trace_id_value,
                "suggested_questions": suggested_questions,
            }) + "\n\n"
        except Exception as exc:
            logger.warning("SSE streaming path failed, fallback to sync pipeline: %s", exc, exc_info=True)
            try:
                # If we already kicked off the parity graph in parallel, reuse
                # its result instead of running session.ask twice.
                result: dict[str, Any] | None = None
                if graph_task is not None:
                    try:
                        result = await graph_task
                    except Exception as parity_exc:
                        logger.warning("Streaming parity task failed in fallback: %s", parity_exc)
                        result = None
                if result is None and hasattr(session, "ask"):
                    result = await loop.run_in_executor(
                        get_request_executor(),
                        _session_ask_with_shared_limits,
                    )
                if result is not None:
                    answer = result.get("answer") or "Не удалось получить ответ."
                    quality = result.get("quality_score") or 50
                    quality_source = str(result.get("quality_source") or "llm")
                    route = result.get("route") or "auto"
                    raw_sources = result.get("graded_docs") or result.get("context_docs") or []
                    sources = []
                    citations = []
                    for idx, item in enumerate(raw_sources, start=1):
                        metadata = item.get("metadata", {}) if isinstance(item, dict) else {}
                        content = item.get("page_content", "") if isinstance(item, dict) else ""
                        sources.append({
                            "source": metadata.get("source") or metadata.get("file_name") or "",
                            "page_content": content,
                        })
                        citations.append({
                            "index": idx,
                            "doc_id": str(
                                metadata.get("doc_id")
                                or metadata.get("id")
                                or metadata.get("source")
                                or metadata.get("file_name")
                                or f"doc_{idx}"
                            ),
                            "title": str(
                                metadata.get("title")
                                or metadata.get("source")
                                or metadata.get("file_name")
                                or metadata.get("doc_id")
                                or f"doc_{idx}"
                            ),
                            "excerpt": str(content or "")[:300],
                        })
                    if result.get("citations"):
                        citations = [
                            {
                                "index": int(item.get("index") or 0),
                                "doc_id": str(item.get("doc_id") or ""),
                                "title": str(item.get("title") or ""),
                                "excerpt": str(item.get("excerpt") or ""),
                            }
                            for item in result.get("citations", [])
                            if isinstance(item, dict)
                        ]
                    trace_id = result.get("trace_id") or ""
                    suggested_questions = result.get("suggested_questions") or []
                else:
                    answer = "Сессия не инициализирована."
                    session["history"].append({"role": "user", "content": question})
                    session["history"].append({"role": "assistant", "content": answer})
                    quality, route, sources, citations, trace_id, suggested_questions = 0, "human", [], [], "", []
                    quality_source = "heuristic"

                await _persist_ask_messages(
                    session_id=session_id,
                    tenant_id=tenant,
                    question=question,
                    answer=answer,
                    path="stream_fallback",
                )

                try:
                    if quality:
                        prometheus_metrics.record_quality_score_source(quality_source)
                except Exception:
                    pass
                yield "data: " + _json.dumps({
                    "type": "result",
                    "answer": answer,
                    "quality_score": quality,
                    "quality_source": quality_source,
                    "route": route,
                    "session_id": session_id,
                    "sources": sources,
                    "citations": citations,
                    "trace_id": trace_id,
                    "suggested_questions": suggested_questions,
                }) + "\n\n"
            except Exception as sync_exc:
                logger.error("SSE fallback error: %s", sync_exc, exc_info=True)
                yield "data: " + _json.dumps({
                    "type": "result",
                    "answer": "Ошибка обработки запроса.",
                    "quality_score": 0,
                    "route": "human",
                    "session_id": session_id,
                    "sources": [],
                    "citations": [],
                    "trace_id": "",
                    "suggested_questions": [],
                }) + "\n\n"
        finally:
            # Clear stream-side ContextVars. Do not clear a shared budget object
            # mid-orphan: worker may still charge against it until done.
            try:
                clear_request_deadline()
            except Exception:
                pass
            try:
                # Only clear if we still own the stream context binding.
                if get_llm_request_budget() is stream_budget_obj:
                    clear_llm_request_budget()
            except Exception:
                pass
            # Runs on normal completion, errors, and client disconnect
            # (GeneratorExit) — the pipeline slot must never leak.
            if capacity_held_for_orphan:
                pass  # done-callback owns release
            elif graph_task is not None and not graph_task.done():
                # Disconnect / early exit while parity still running.
                capacity_held_for_orphan = True
                _hold_capacity_until_future_done(
                    loop=loop,
                    fut=graph_task,
                    semaphore=semaphore,
                )
            else:
                _release_pipeline_capacity(semaphore)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/stream")
@limiter.limit("60/minute")
async def chat_stream(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
) -> StreamingResponse:
    return await ask_stream(request, body, _user)
