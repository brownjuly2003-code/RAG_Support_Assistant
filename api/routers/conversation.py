"""Conversation ask/chat endpoints."""
from __future__ import annotations

import asyncio
import inspect
import json as _json
import logging
import re
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.correlation import get_current_tenant, get_request_id
from api.rate_limit import limiter
from auth.dependencies import get_current_user
from monitoring import prometheus as prometheus_metrics

router = APIRouter()
logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = Field(default=None, max_length=100)
    confirm: Optional[bool] = None
    tenant_id: str = Field(
        default="default",
        max_length=50,
        pattern=r"^[a-zA-Z0-9_\-]+$",
    )


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
    sources: List[SourceInfo] = Field(default_factory=list)
    citations: List[Citation] = Field(default_factory=list)
    session_id: str = ""
    trace_id: str = ""
    suggested_questions: List[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    action_summary: str = ""


def _app_module():
    from api import app as _app  # noqa: PLC0415

    return _app


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

    tenant = get_current_tenant() or _user.get("tenant", "default")
    session_params = inspect.signature(_app._get_or_create_session).parameters
    if "tenant_id" in session_params or any(
        param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        for param in session_params.values()
    ):
        session_result = _app._get_or_create_session(body.session_id, tenant)
    else:
        session_result = _app._get_or_create_session(body.session_id)
    if asyncio.iscoroutine(session_result):
        session_id, session = await session_result
    else:
        session_id, session = session_result

    settings = _app.get_settings()
    cache_enabled = bool(getattr(settings, "llm_cache_enabled", False))
    llm_cache_key = _app._cache_key(tenant, question)
    cache_hit = False

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
                )
                cache_hit = True
            else:
                try:
                    prometheus_metrics.LLM_CACHE_MISSES.labels(tenant=tenant).inc()
                except Exception:
                    pass

        if not cache_hit:
            timeout = float(getattr(settings, "request_timeout_sec", 30.0))
            acquire_timeout = float(
                getattr(settings, "pipeline_acquire_timeout_sec", 0.5)
            )
            request_id = get_request_id()
            ask_params = inspect.signature(session.ask).parameters
            has_var_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in ask_params.values()
            )
            ask_kwargs: dict[str, Any] = {}
            if "trace_id" in ask_params or has_var_kwargs:
                ask_kwargs["trace_id"] = request_id
            if "tenant_id" in ask_params or has_var_kwargs:
                ask_kwargs["tenant_id"] = tenant
            if "confirm" in ask_params or has_var_kwargs:
                ask_kwargs["confirm"] = body.confirm
            if "user_id" in ask_params or has_var_kwargs:
                ask_kwargs["user_id"] = _user.get("sub", "anonymous")
            if "session_id" in ask_params or has_var_kwargs:
                ask_kwargs["session_id"] = session_id
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
                )
            try:
                prometheus_metrics.INFLIGHT_PIPELINES.inc()
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(session.ask, question, **ask_kwargs),
                        timeout=timeout,
                    )

                    answer = result.get("answer") or ""
                    quality = result.get("quality_score") or 50
                    route = result.get("route") or "auto"

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
                except asyncio.TimeoutError:
                    try:
                        prometheus_metrics.record_request_timeout("/api/ask")
                    except Exception:
                        pass
                    logger.warning(
                        "req_id=%s /api/ask exceeded timeout=%.1fs",
                        request_id or "-",
                        timeout,
                    )
                    raise HTTPException(
                        status_code=504,
                        detail=f"Request exceeded {timeout:.0f}s wall-time limit",
                    )
                except Exception as exc:
                    logger.error("Pipeline error in /ask: %s", exc, exc_info=True)
                    answer = "Не удалось обработать запрос автоматически. Ваш вопрос передан оператору."
                    # Codex audit 2026-04-27 H2: до этого фикса при exception
                    # пользователю обещали handoff, но реального escalated
                    # ticket в БД не создавалось — оператор мог не увидеть.
                    try:
                        from db.engine import async_session
                        from db.models import EscalatedTicket

                        draft = (
                            f"Запрос пользователя: {question}\n\n"
                            "Черновик ответа: Произошла техническая ошибка "
                            "при обработке запроса. Пожалуйста, ответьте "
                            "пользователю вручную."
                        )
                        async with async_session() as _esc_db:
                            _esc_db.add(
                                EscalatedTicket(
                                    tenant_id=tenant or "default",
                                    session_id=session_id,
                                    user_question=question,
                                    ai_draft=draft,
                                    status="open",
                                )
                            )
                            await _esc_db.commit()
                    except Exception as ticket_exc:
                        logger.warning(
                            "Failed to persist pipeline-failure ticket: %s",
                            ticket_exc,
                        )
                    if hasattr(session, "_history"):
                        session._history.append({"role": "user", "content": question})
                        session._history.append({"role": "assistant", "content": answer})
                    elif isinstance(session, dict):
                        session["history"].append({"role": "user", "content": question})
                        session["history"].append({"role": "assistant", "content": answer})
                    response = AskResponse(
                        answer=answer,
                        quality_score=0,
                        route="human",
                        sources=[],
                        citations=[],
                        session_id=session_id,
                        trace_id="",
                        suggested_questions=[],
                    )
            finally:
                try:
                    prometheus_metrics.INFLIGHT_PIPELINES.dec()
                except Exception:
                    pass
                semaphore.release()
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

    if time.monotonic() >= _app._db_retry_after:
        try:
            from db.engine import async_session as db_session_factory
            from db.models import Message

            async with db_session_factory() as db:
                session_uuid = uuid.UUID(session_id)
                db.add(Message(session_id=session_uuid, role="user", content=question))
                db.add(Message(session_id=session_uuid, role="assistant", content=response.answer))
                await asyncio.wait_for(db.commit(), timeout=0.5)
                _app._db_retry_after = 0.0
        except Exception as exc:
            _app._db_retry_after = time.monotonic() + 60.0
            logger.warning("Failed to persist messages: %s", exc)

    await _app.log_audit(
        actor=_user.get("sub", "anonymous"),
        action="ask",
        resource=f"session:{session_id}",
        detail={
            "question_length": len(body.question),
            "tenant": _user.get("tenant", "default"),
        },
        ip_address=request.client.host if request.client else None,
    )
    duration = time.monotonic() - t0
    prometheus_metrics.REQUEST_DURATION.observe(duration)
    prometheus_metrics.REQUEST_COUNT.labels(route=response.route).inc()
    if response.quality_score:
        prometheus_metrics.QUALITY_SCORE.observe(response.quality_score)
    if response.route == "human":
        prometheus_metrics.ESCALATION_TOTAL.inc()
    prometheus_metrics.ACTIVE_SESSIONS.set(len(_app._sessions))
    if response.citations:
        asyncio.create_task(_app._record_citation_stats(tenant, list(response.citations)))
    if cache_hit:
        return JSONResponse(content={**response.model_dump(), "cached": True})
    return response


@router.post("/chat")
@limiter.limit("60/minute")
async def chat(
    request: Request,
    body: AskRequest,
    _user: dict = Depends(get_current_user),
):
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
        session_params = inspect.signature(_app._get_or_create_session).parameters
        if "tenant_id" in session_params or any(
            param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            for param in session_params.values()
        ):
            session_result = _app._get_or_create_session(body.session_id, tenant)
        else:
            session_result = _app._get_or_create_session(body.session_id)
        if asyncio.iscoroutine(session_result):
            session_id, session = await session_result
        else:
            session_id, session = session_result
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
            detail={
                "question_length": len(body.question),
                "tenant": _user.get("tenant", "default"),
            },
            ip_address=request.client.host if request.client else None,
        )

        try:
            prompt = ""
            docs: List[Any] = []
            chat_history: List[Dict[str, str]] = []
            ask_params = inspect.signature(session.ask).parameters if hasattr(session, "ask") else {}
            ask_args = (
                (question, get_request_id(), tenant)
                if len(ask_params) >= 3
                or any(
                    param.kind == inspect.Parameter.VAR_POSITIONAL
                    for param in ask_params.values()
                )
                else (question, get_request_id())
            )

            # H1 parity: while we stream tokens for UX, run the full Self-RAG
            # graph in parallel so the final SSE event ships graph-level
            # route/quality/citations/trace_id rather than the stream-side
            # heuristic. The streamed answer text stays as the user saw it
            # — only the metadata is corrected. Opt-in via
            # STREAMING_RAG_PARITY=true; off by default so operators don't
            # silently pay for a second graph pass.
            settings_pre = _app.get_settings()
            graph_parity_enabled = bool(
                getattr(settings_pre, "streaming_rag_parity", False)
            )
            graph_parity_timeout = float(
                getattr(settings_pre, "request_timeout_sec", 60.0)
            )
            # When parity runs, session.ask appends turns to session._history
            # itself; the streaming branch must not re-append or we get
            # duplicate entries in the conversation log.
            history_pre_len = (
                len(getattr(session, "_history", []))
                if hasattr(session, "_history")
                else None
            )
            graph_task: asyncio.Future | None = None
            if graph_parity_enabled and hasattr(session, "ask"):
                loop = asyncio.get_running_loop()
                graph_task = loop.run_in_executor(
                    None, lambda: session.ask(*ask_args)
                )

            if hasattr(session, "_retriever") and session._retriever is not None:
                docs = await asyncio.get_running_loop().run_in_executor(
                    None,
                    session._retriever.get_relevant_documents,
                    question,
                )

                if hasattr(session, "history"):
                    chat_history = session.history
                elif isinstance(session, dict):
                    chat_history = session.get("history", [])

                from agent.prompts import build_qa_prompt, build_conversational_qa_prompt  # noqa: PLC0415

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
            except Exception as exc:
                logger.warning("Streaming error in /ask/stream: %s", exc)
                if not full_answer:
                    raise

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

            quality = 70 if len(full_answer.strip()) > 20 or sources else 40
            route = "auto" if quality >= 70 else "human"
            suggested_questions: List[str] = []
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
            graph_result: Dict[str, Any] | None = None
            if graph_task is not None:
                try:
                    graph_result = await asyncio.wait_for(
                        graph_task, timeout=graph_parity_timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Streaming RAG parity task exceeded %.1fs timeout",
                        graph_parity_timeout,
                    )
                    graph_task.cancel()
                    graph_result = None
                except Exception as graph_exc:
                    logger.warning("Streaming RAG parity task failed: %s", graph_exc)
                    graph_result = None
                # session.ask appends turns to session._history itself (see
                # ConversationSession._append_history). If parity ran, skip
                # the streaming-side append below to avoid duplicates.
                if (
                    history_pre_len is not None
                    and hasattr(session, "_history")
                    and len(session._history) > history_pre_len
                ):
                    graph_appended_history = True

            if not graph_appended_history:
                if hasattr(session, "_history"):
                    session._history.append({"role": "user", "content": question})
                    session._history.append({"role": "assistant", "content": full_answer})
                    max_history = getattr(session, "_max_history", 20)
                    if len(session._history) > max_history * 2:
                        session._history = session._history[-(max_history * 2):]
                elif isinstance(session, dict):
                    session["history"].append({"role": "user", "content": question})
                    session["history"].append({"role": "assistant", "content": full_answer})

            if isinstance(graph_result, dict) and graph_result:
                if graph_result.get("quality_score") is not None:
                    quality = int(graph_result["quality_score"])
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

            if time.monotonic() >= _app._db_retry_after:
                try:
                    from db.engine import async_session as db_session_factory
                    from db.models import Message

                    async with db_session_factory() as db:
                        session_uuid = uuid.UUID(session_id)
                        db.add(Message(session_id=session_uuid, role="user", content=question))
                        db.add(Message(session_id=session_uuid, role="assistant", content=full_answer))
                        await asyncio.wait_for(db.commit(), timeout=0.5)
                        _app._db_retry_after = 0.0
                except Exception as db_exc:
                    _app._db_retry_after = time.monotonic() + 60.0
                    logger.warning("Failed to persist streaming messages: %s", db_exc)
            yield "data: " + _json.dumps({
                "type": "result",
                "answer": full_answer,
                "quality_score": quality,
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
                result: Dict[str, Any] | None = None
                if graph_task is not None:
                    try:
                        result = await graph_task
                    except Exception as parity_exc:
                        logger.warning("Streaming parity task failed in fallback: %s", parity_exc)
                        result = None
                if result is None and hasattr(session, "ask"):
                    result = await asyncio.get_running_loop().run_in_executor(
                        None, session.ask, *ask_args
                    )
                if result is not None:
                    answer = result.get("answer") or "Не удалось получить ответ."
                    quality = result.get("quality_score") or 50
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

                if time.monotonic() >= _app._db_retry_after:
                    try:
                        from db.engine import async_session as db_session_factory
                        from db.models import Message

                        async with db_session_factory() as db:
                            session_uuid = uuid.UUID(session_id)
                            db.add(Message(session_id=session_uuid, role="user", content=question))
                            db.add(Message(session_id=session_uuid, role="assistant", content=answer))
                            await asyncio.wait_for(db.commit(), timeout=0.5)
                            _app._db_retry_after = 0.0
                    except Exception as db_exc:
                        _app._db_retry_after = time.monotonic() + 60.0
                        logger.warning("Failed to persist streamed fallback messages: %s", db_exc)

                yield "data: " + _json.dumps({
                    "type": "result",
                    "answer": answer,
                    "quality_score": quality,
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
