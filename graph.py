"""
agent/graph.py

LangGraph-пайплайн для RAG-ассистента (Level 1-3).

Level 1: retrieve → generate → evaluate → route
Level 2: + transform_query, grade_docs (Corrective RAG), Self-RAG retry loop
Level 3: + conversation memory, multi-query retrieval, contextual retrieval
"""

from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol

from langgraph.graph import END, StateGraph
from tracing.langfuse_trace import trace_llm_call

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from utils.circuit_breaker import CircuitBreaker

# Support both package-style and root-level imports
try:
    from agent.state import GraphState, create_initial_state
    from agent.prompts import (
        build_qa_prompt,
        build_self_eval_prompt,
        build_suggested_questions_prompt,
        build_query_transform_prompt,
        build_doc_grade_prompt,
        build_query_rewrite_prompt,
        build_conversational_qa_prompt,
        build_conversational_query_transform_prompt,
    )
    from tracing.sqlite_trace import start_trace, log_step, finish_trace
except ImportError:
    from state import GraphState, create_initial_state
    from prompts import (
        build_qa_prompt,
        build_self_eval_prompt,
        build_suggested_questions_prompt,
        build_query_transform_prompt,
        build_doc_grade_prompt,
        build_query_rewrite_prompt,
        build_conversational_qa_prompt,
        build_conversational_query_transform_prompt,
    )
    from sqlite_trace import start_trace, log_step, finish_trace


# ---------------------------------------------------------------------------
# Error escalation helpers
# ---------------------------------------------------------------------------


def _escalate_to_inbox(state: GraphState) -> None:
    """Записывает ошибку в support inbox (mock или Bitrix)."""
    import json as _json
    import traceback as _tb  # noqa: F401 (used in format_exc)
    from datetime import datetime, timezone
    from pathlib import Path

    trace_id = state.get("trace_id", "unknown")
    record = {
        "entity_id": trace_id,
        "question": state.get("question", ""),
        "answer": state.get("answer"),
        "route": "error_escalation",
        "error_message": state.get("error_message", ""),
        "error_node": state.get("error_node", ""),
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    try:
        from mock_inbox import get_support_sink  # type: ignore[import-not-found]
        get_support_sink().send(trace_id, _json.dumps(record, ensure_ascii=False))
        return
    except ImportError:
        logger.debug("mock_inbox not available, falling back to JSONL")
    except Exception as exc:
        logger.warning("Failed to send to support sink: %s", exc)

    # Fallback: прямая запись в JSONL
    try:
        inbox_path = Path(__file__).parent / "data" / "inbox" / "support_inbox.jsonl"
        inbox_path.parent.mkdir(parents=True, exist_ok=True)
        with inbox_path.open("a", encoding="utf-8") as f:
            f.write(_json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error("Не удалось записать в inbox: %s", exc)


def _make_error_state(state: GraphState, node_name: str, exc: Exception) -> GraphState:
    """Возвращает состояние с заполненными полями ошибки."""
    import traceback as _tb

    logger.error(
        "Необработанное исключение в узле '%s': %s",
        node_name,
        exc,
        extra={"trace_id": state.get("trace_id", "")},
        exc_info=True,
    )
    return {
        **state,  # type: ignore[misc]
        "error": True,
        "error_message": f"{type(exc).__name__}: {exc}\n{_tb.format_exc()}",
        "error_node": node_name,
        "route": "error",
    }


def make_handle_error_node() -> Callable[[GraphState], GraphState]:
    """Узел handle_error: эскалирует ошибку и возвращает понятный ответ пользователю."""

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown")
        logger.error(
            "Pipeline error escalation: node='%s' trace_id=%s",
            state.get("error_node", "unknown"),
            trace_id,
            extra={"trace_id": trace_id},
        )

        _escalate_to_inbox(state)

        try:
            log_step(trace_id, "handle_error", state)
        except Exception as exc:
            logger.warning("Failed to log handle_error step: %s", exc, extra={"trace_id": trace_id})

        return {
            **state,  # type: ignore[misc]
            "answer": (
                "Не удалось обработать запрос автоматически. "
                "Ваш вопрос передан оператору — мы ответим в ближайшее время."
            ),
            "route": "error_escalation",
        }

    return node


# ---------------------------------------------------------------------------
# Интерфейс для LLM (простой протокол)
# ---------------------------------------------------------------------------


class SupportsInvoke(Protocol):
    """Протокол для объектов, у которых есть метод invoke(prompt: str) -> str."""

    def invoke(self, prompt: str) -> str:  # pragma: no cover
        ...


_USE_DEFAULT_BREAKER = object()


class LocalOllamaLLM:
    """Обёртка над локальной моделью Ollama."""

    def __init__(
        self,
        model_name: str = "mistral",
        breaker: CircuitBreaker | None | object = _USE_DEFAULT_BREAKER,
    ):
        from langchain_community.llms import Ollama
        from config.settings import get_settings
        from utils.retry import retry_with_backoff

        settings = get_settings()
        timeout_sec = getattr(settings, "ollama_request_timeout_sec", 60.0)
        try:
            self._llm = Ollama(model=model_name, timeout=timeout_sec)
        except TypeError:
            self._llm = Ollama(model=model_name, request_timeout=timeout_sec)
        self._breaker = get_default_breaker() if breaker is _USE_DEFAULT_BREAKER else breaker

        def _retry_prom_hook(event: str) -> None:
            try:
                from monitoring.prometheus import record_ollama_retry_event

                record_ollama_retry_event(event)
            except Exception:
                pass

        self._invoke_with_retry = retry_with_backoff(
            self._llm.invoke,
            max_attempts=getattr(settings, "ollama_retry_max_attempts", 3),
            base_delay_sec=getattr(settings, "ollama_retry_base_delay_sec", 0.5),
            max_delay_sec=getattr(settings, "ollama_retry_max_delay_sec", 5.0),
            jitter=getattr(settings, "ollama_retry_jitter", True),
            on_event=_retry_prom_hook,
        )

    def invoke(self, prompt: str) -> str:
        invoke_with_retry = getattr(self, "_invoke_with_retry", self._llm.invoke)
        if self._breaker is None:
            return invoke_with_retry(prompt)
        return self._breaker.call(invoke_with_retry, prompt)


_default_breaker: CircuitBreaker | None = None


def get_default_breaker() -> CircuitBreaker | None:
    """Return the shared Ollama breaker, or None when disabled in settings."""
    global _default_breaker
    if _default_breaker is not None:
        return _default_breaker

    from config.settings import get_settings
    from utils.circuit_breaker import CircuitBreaker

    settings = get_settings()
    if not getattr(settings, "circuit_breaker_enabled", True):
        return None

    def _prom_hook(name: str, old_state, new_state) -> None:
        try:
            from monitoring.prometheus import record_circuit_breaker_change

            record_circuit_breaker_change(name, old_state.value, new_state.value)
        except Exception:
            pass

    _default_breaker = CircuitBreaker(
        failure_threshold=getattr(settings, "circuit_breaker_failure_threshold", 5),
        reset_timeout_sec=getattr(settings, "circuit_breaker_reset_timeout_sec", 30.0),
        name="ollama",
        on_state_change=_prom_hook,
    )
    try:
        from monitoring.prometheus import record_circuit_breaker_change

        record_circuit_breaker_change("ollama", "closed", "closed")
    except Exception:
        pass
    return _default_breaker


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------


def _docs_to_plain_dicts(docs: List[Any]) -> List[Dict[str, Any]]:
    """Преобразует Document объекты в plain dicts для JSON/SQLite."""
    plain_docs: List[Dict[str, Any]] = []
    for doc in docs:
        if hasattr(doc, "page_content"):
            text = getattr(doc, "page_content", "")
            metadata = getattr(doc, "metadata", {}) or {}
        elif isinstance(doc, dict):
            text = doc.get("page_content", "")
            metadata = doc.get("metadata", {}) or {}
        else:
            text = str(doc)
            metadata = {}
        plain_docs.append({"page_content": text, "metadata": metadata})
    return plain_docs


def _parse_int_score(text: str, default: int = 50) -> int:
    """Извлекает целое число 1-100 из текста."""
    numbers = re.findall(r"\d+", text)
    if not numbers:
        return default
    value = int(numbers[0])
    return max(1, min(100, value))


def _build_hyde_prompt(question: str) -> str:
    return (
        "You are a helpful assistant. Write a short hypothetical answer (2-3 sentences) "
        "to the following support question. Write only the answer, no intro or meta-text.\n\n"
        f"Question: {question}\n\nHypothetical answer:"
    )


# ---------------------------------------------------------------------------
# Level 2: Query Transform node
# ---------------------------------------------------------------------------


def make_transform_query_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел transform_query: переформулирует вопрос в поисковый запрос.

    Level 3: учитывает chat_history для уточняющих вопросов.
    """

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            question = state.get("question", "")
            chat_history = state.get("chat_history", [])

            if state.get("search_query"):
                log_step(trace_id, "transform_query", state)
                return state

            if chat_history:
                prompt = build_conversational_query_transform_prompt(question, chat_history)
            else:
                prompt = build_query_transform_prompt(question)
            model = str(getattr(getattr(llm, "_llm", None), "model", "") or "")

            try:
                t0 = time.monotonic()
                raw_search_query = llm.invoke(prompt).strip()
                trace_llm_call(
                    trace_id=trace_id,
                    node_name="transform_query",
                    prompt=prompt,
                    response=raw_search_query,
                    model=model,
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
                search_query = raw_search_query
                if not search_query or len(search_query) < 3:
                    search_query = question
            except Exception as exc:
                logger.warning("[transform_query] LLM error: %s", exc, extra={"trace_id": trace_id})
                search_query = question

            from config.settings import get_settings  # noqa: PLC0415

            settings = get_settings()
            hyde_query: Optional[str] = None
            if settings.hyde:
                try:
                    hyde_prompt = _build_hyde_prompt(question)
                    t0 = time.monotonic()
                    hyde_doc = llm.invoke(hyde_prompt).strip()
                    trace_llm_call(
                        trace_id=trace_id,
                        node_name="hyde",
                        prompt=hyde_prompt,
                        response=hyde_doc,
                        model=model,
                        duration_ms=(time.monotonic() - t0) * 1000,
                    )
                    if hyde_doc and len(hyde_doc) > 10:
                        hyde_query = hyde_doc
                        logger.debug("[transform_query] HyDE generated (%d chars)", len(hyde_doc))
                except Exception as exc:
                    logger.warning("[transform_query] HyDE failed, fallback to search_query: %s", exc)

            new_state: GraphState = {
                **state,
                "search_query": search_query,
                "hyde_query": hyde_query,
            }
            log_step(trace_id, "transform_query", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "transform_query", exc)

    return node


# ---------------------------------------------------------------------------
# Level 1: Retrieve node (updated to use search_query)
# ---------------------------------------------------------------------------


def make_retrieve_node(retriever: Any) -> Callable[[GraphState], GraphState]:
    """Узел retrieve: ищет документы по search_query (или question как fallback)."""

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            query = state.get("hyde_query") or state.get("search_query") or state.get("question", "")
            try:
                docs = retriever.get_relevant_documents(query)
            except Exception as exc:
                logger.warning("[retrieve] Retriever error: %s", exc, extra={"trace_id": trace_id})
                docs = []
            plain_docs = _docs_to_plain_dicts(docs)
            new_state: GraphState = {**state, "context_docs": plain_docs}
            log_step(trace_id, "retrieve", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "retrieve", exc)

    return node


# ---------------------------------------------------------------------------
# Level 2: Grade Documents node (Corrective RAG)
# ---------------------------------------------------------------------------


def make_grade_docs_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел grade_docs: оценивает каждый документ на релевантность.

    Corrective RAG: LLM проверяет каждый документ (YES/NO).
    Нерелевантные отфильтровываются → в graded_docs попадают только полезные.
    """

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            question = state.get("question", "")
            context_docs = state.get("context_docs", []) or []
            model = str(getattr(getattr(llm, "_llm", None), "model", "") or "")

            if not context_docs:
                new_state: GraphState = {**state, "graded_docs": [], "doc_grade_reason": "No documents retrieved"}
                log_step(trace_id, "grade_docs", new_state)
                return new_state

            graded: List[Dict[str, Any]] = []
            filtered_count = 0
            for doc in context_docs:
                prompt = build_doc_grade_prompt(question=question, document=doc)
                try:
                    t0 = time.monotonic()
                    raw_verdict = llm.invoke(prompt).strip()
                    trace_llm_call(
                        trace_id=trace_id,
                        node_name="grade_docs",
                        prompt=prompt,
                        response=raw_verdict,
                        model=model,
                        duration_ms=(time.monotonic() - t0) * 1000,
                    )
                    is_relevant = raw_verdict.upper().startswith("YES")
                except Exception as exc:
                    logger.warning("[grade_docs] LLM error: %s", exc, extra={"trace_id": trace_id})
                    is_relevant = True
                if is_relevant:
                    graded.append(doc)
                else:
                    filtered_count += 1

            reason = f"Kept {len(graded)}/{len(context_docs)}, filtered {filtered_count}"
            new_state = {**state, "graded_docs": graded, "doc_grade_reason": reason}
            log_step(trace_id, "grade_docs", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "grade_docs", exc)

    return node


# ---------------------------------------------------------------------------
# Level 1: Generate node (updated to use graded_docs)
# ---------------------------------------------------------------------------


def make_generate_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел generate: формирует ответ. Level 3: учитывает chat_history."""

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            question = state.get("question", "")
            docs = state.get("graded_docs") or state.get("context_docs", []) or []
            chat_history = state.get("chat_history", [])
            model = str(getattr(getattr(llm, "_llm", None), "model", "") or "")

            if chat_history:
                prompt = build_conversational_qa_prompt(question=question, context_docs=docs, chat_history=chat_history)
            else:
                prompt = build_qa_prompt(question=question, context_docs=docs)

            try:
                t0 = time.monotonic()
                answer = llm.invoke(prompt)
                trace_llm_call(
                    trace_id=trace_id,
                    node_name="generate",
                    prompt=prompt,
                    response=answer,
                    model=model,
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
            except Exception as exc:
                logger.warning("[generate] LLM error: %s", exc, extra={"trace_id": trace_id})
                answer = "Извините, при обработке запроса произошла внутренняя ошибка."

            new_state: GraphState = {**state, "answer": answer}
            log_step(trace_id, "generate", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "generate", exc)

    return node


# ---------------------------------------------------------------------------
# Level 1: Evaluate node
# ---------------------------------------------------------------------------


def make_evaluate_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел evaluate: самооценка качества ответа (1-100)."""

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            question = state.get("question", "")
            answer = state.get("answer") or ""
            docs = state.get("graded_docs") or state.get("context_docs", []) or []
            prompt = build_self_eval_prompt(question=question, answer=answer, context_docs=docs)
            model = str(getattr(getattr(llm, "_llm", None), "model", "") or "")
            try:
                t0 = time.monotonic()
                raw = llm.invoke(prompt)
                trace_llm_call(
                    trace_id=trace_id,
                    node_name="evaluate",
                    prompt=prompt,
                    response=raw,
                    model=model,
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
            except Exception as exc:
                logger.warning("[evaluate] LLM error: %s", exc, extra={"trace_id": trace_id})
                raw = ""
            score = _parse_int_score(raw, default=50)
            new_state: GraphState = {**state, "quality_score": score, "relevance_score": round(score / 100.0, 3)}
            log_step(trace_id, "evaluate", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "evaluate", exc)

    return node


# ---------------------------------------------------------------------------
# Suggested questions node
# ---------------------------------------------------------------------------


def make_suggest_questions_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Generate 2-3 follow-up questions after an answer."""

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        if state.get("route") != "auto":
            return {**state, "suggested_questions": []}

        trace_id = state.get("trace_id", "unknown-trace-id")
        docs = state.get("graded_docs") or state.get("context_docs", []) or []
        context_snippet = "\n\n".join(
            str(doc.get("page_content", ""))
            for doc in docs[:2]
            if isinstance(doc, dict)
        )[:500]
        model = str(getattr(getattr(llm, "_llm", None), "model", "") or "")

        try:
            prompt = build_suggested_questions_prompt(
                state.get("question", ""),
                state.get("answer") or "",
                context_snippet=context_snippet,
            )
            t0 = time.monotonic()
            raw = llm.invoke(prompt)
            trace_llm_call(
                trace_id=trace_id,
                node_name="suggest_questions",
                prompt=prompt,
                response=raw,
                model=model,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
            questions = [
                re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
                for line in raw.strip().splitlines()
                if line.strip()
            ][:3]
            new_state: GraphState = {**state, "suggested_questions": questions}
            log_step(trace_id, "suggest_questions", new_state)
            return new_state
        except Exception as exc:
            logger.warning(
                "Failed to generate suggested questions: %s",
                exc,
                extra={"trace_id": trace_id},
            )
            new_state: GraphState = {**state, "suggested_questions": []}
            log_step(trace_id, "suggest_questions", new_state)
            return new_state

    return node


# ---------------------------------------------------------------------------
# Level 2: Route or Retry (Self-RAG loop)
# ---------------------------------------------------------------------------


def make_route_or_retry_node(
    min_quality: int = 80,
    min_relevance: float = 0.8,
) -> Callable[[GraphState], GraphState]:
    """Узел route_or_retry: решает — финал или повторная попытка.

    Логика:
    - quality >= min_quality → route="auto" → END
    - quality < min_quality и iteration < max_iterations → route="retry"
    - quality < min_quality и итерации кончились → route="human" → END
    """

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            q = state.get("quality_score")
            r = state.get("relevance_score")
            iteration = state.get("iteration", 0)
            max_iter = state.get("max_iterations", 2)

            if q is None or r is None:
                route = "human"
            elif q >= min_quality and r >= min_relevance:
                route = "auto"
            elif iteration < max_iter:
                route = "retry"
            else:
                route = "human"

            new_state: GraphState = {**state, "route": route}
            log_step(trace_id, "route_or_retry", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "route_or_retry", exc)

    return node


# ---------------------------------------------------------------------------
# Level 2: Rewrite Query (для Self-RAG retry)
# ---------------------------------------------------------------------------


def make_rewrite_query_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    """Узел rewrite_query: переформулирует запрос после неудачного ответа.

    Используется только при route="retry" (Self-RAG цикл).
    Инкрементирует iteration, сбрасывает search_query для нового поиска.
    """

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            question = state.get("question", "")
            previous_answer = state.get("answer") or ""
            quality_score = state.get("quality_score") or 50
            iteration = state.get("iteration", 0)
            prompt = build_query_rewrite_prompt(question=question, previous_answer=previous_answer, quality_score=quality_score)
            model = str(getattr(getattr(llm, "_llm", None), "model", "") or "")
            try:
                t0 = time.monotonic()
                raw_new_query = llm.invoke(prompt).strip()
                trace_llm_call(
                    trace_id=trace_id,
                    node_name="rewrite_query",
                    prompt=prompt,
                    response=raw_new_query,
                    model=model,
                    duration_ms=(time.monotonic() - t0) * 1000,
                )
                new_query = raw_new_query
                if not new_query or len(new_query) < 3:
                    new_query = question
            except Exception as exc:
                logger.warning("[rewrite_query] LLM error: %s", exc, extra={"trace_id": trace_id})
                new_query = question
            new_state: GraphState = {
                **state,
                "search_query": new_query,
                "hyde_query": None,
                "iteration": iteration + 1,
                "context_docs": [],
                "graded_docs": [],
                "answer": None,
                "quality_score": None,
                "relevance_score": None,
            }
            log_step(trace_id, "rewrite_query", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "rewrite_query", exc)

    return node


# ---------------------------------------------------------------------------
# Log node
# ---------------------------------------------------------------------------


def make_log_node() -> Callable[[GraphState], GraphState]:
    """Финальный узел: логирует итоговое состояние."""

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown-trace-id")
        log_step(trace_id, "log", state)
        return state

    return node


# ---------------------------------------------------------------------------
# Conditional routing function
# ---------------------------------------------------------------------------


def _should_retry(state: GraphState) -> str:
    """Conditional edge: определяет, куда идти после route_or_retry.

    Returns:
        "error" → handle_error → END  (необработанное исключение)
        "retry" → rewrite_query → retrieve → ...  (Self-RAG loop)
        "end"   → log → END  (auto / human, финал)
    """
    route = state.get("route", "human")
    if state.get("error") or route == "error":
        return "error"
    if route == "retry":
        return "retry"
    if route == "auto":
        return "suggest"
    return "end"


# ---------------------------------------------------------------------------
# Сборка графа (Level 2: Corrective & Self-RAG)
# ---------------------------------------------------------------------------


def build_support_graph(
    retriever: Any,
    llm: SupportsInvoke | None = None,
    min_quality: int = 80,
    max_iterations: int = 2,
):
    """Собирает и компилирует граф LangGraph Level 2.

    Граф:
        transform_query → retrieve → grade_docs → generate → evaluate
            → route_or_retry ─┬─ (retry) → rewrite_query → retrieve → ...
                               └─ (end)   → log → END
    """
    if llm is None:
        llm = LocalOllamaLLM(model_name="mistral", breaker=get_default_breaker())

    workflow = StateGraph(GraphState)

    # Регистрируем узлы
    workflow.add_node("transform_query", make_transform_query_node(llm))
    workflow.add_node("retrieve", make_retrieve_node(retriever))
    workflow.add_node("grade_docs", make_grade_docs_node(llm))
    workflow.add_node("generate", make_generate_node(llm))
    workflow.add_node("evaluate", make_evaluate_node(llm))
    workflow.add_node("route_or_retry", make_route_or_retry_node(min_quality=min_quality))
    workflow.add_node("suggest_questions", make_suggest_questions_node(llm))
    workflow.add_node("rewrite_query", make_rewrite_query_node(llm))
    workflow.add_node("log", make_log_node())
    workflow.add_node("handle_error", make_handle_error_node())

    # Основной путь
    workflow.set_entry_point("transform_query")
    workflow.add_edge("transform_query", "retrieve")
    workflow.add_edge("retrieve", "grade_docs")
    workflow.add_edge("grade_docs", "generate")
    workflow.add_edge("generate", "evaluate")
    workflow.add_edge("evaluate", "route_or_retry")

    # Conditional: retry или finish
    workflow.add_conditional_edges(
        "route_or_retry",
        _should_retry,
        {
            "error": "handle_error",
            "retry": "rewrite_query",
            "suggest": "suggest_questions",
            "end": "log",
        },
    )
    workflow.add_edge("handle_error", END)

    # Retry path: rewrite → retrieve → grade → generate → evaluate → route_or_retry
    workflow.add_edge("rewrite_query", "retrieve")

    # Финал
    workflow.add_edge("suggest_questions", "log")
    workflow.add_edge("log", END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# Высокоуровневая функция запуска (обратная совместимость)
# ---------------------------------------------------------------------------


def run_qa_pipeline(
    question: str,
    retriever: Any,
    llm: SupportsInvoke | None = None,
    max_iterations: int = 2,
    chat_history: List[Dict[str, str]] | None = None,
) -> GraphState:
    """Обрабатывает один вопрос через граф.

    Args:
        question: вопрос пользователя.
        retriever: retriever для поиска документов.
        llm: LLM для генерации.
        max_iterations: макс. итераций Self-RAG.
        chat_history: история диалога (Level 3).
    """
    trace_id = start_trace()
    initial_state = create_initial_state(question=question, trace_id=trace_id)
    initial_state["max_iterations"] = max_iterations
    if chat_history:
        initial_state["chat_history"] = chat_history

    graph = build_support_graph(
        retriever=retriever,
        llm=llm,
        max_iterations=max_iterations,
    )

    final_state = graph.invoke(initial_state)
    finish_trace(trace_id, final_state)
    return final_state


# ---------------------------------------------------------------------------
# Level 3: Conversation Session (multi-turn)
# ---------------------------------------------------------------------------


class ConversationSession:
    """Управляет многоходовым диалогом с RAG-ассистентом.

    Хранит историю и автоматически передаёт её в каждый вызов графа.

    Пример:
        session = ConversationSession(retriever=ret, llm=llm)

        r1 = session.ask("Что означает ошибка E20?")
        print(r1["answer"])  # "E20 — перегрев двигателя..."

        r2 = session.ask("А покрывает ли это гарантия?")
        print(r2["answer"])  # "Гарантия действует 3 года..." (знает контекст!)
    """

    def __init__(
        self,
        retriever: Any,
        llm: SupportsInvoke | None = None,
        max_iterations: int = 2,
        max_history: int = 10,
    ):
        self._retriever = retriever
        self._llm = llm
        self._max_iterations = max_iterations
        self._max_history = max_history
        self._history: List[Dict[str, str]] = []

    @property
    def history(self) -> List[Dict[str, str]]:
        return list(self._history)

    def ask(self, question: str) -> GraphState:
        """Задаёт вопрос с учётом истории диалога."""
        result = run_qa_pipeline(
            question=question,
            retriever=self._retriever,
            llm=self._llm,
            max_iterations=self._max_iterations,
            chat_history=self._history,
        )

        # Сохраняем в историю
        self._history.append({"role": "user", "content": question})
        answer = result.get("answer") or ""
        self._history.append({"role": "assistant", "content": answer})

        # Обрезаем историю
        if len(self._history) > self._max_history * 2:
            self._history = self._history[-(self._max_history * 2):]

        return result

    def clear(self) -> None:
        """Сбрасывает историю."""
        self._history.clear()
