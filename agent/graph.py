"""
agent/graph.py

LangGraph-пайплайн для RAG-ассистента (Level 1-3).

Level 1: retrieve → generate → evaluate → route
Level 2: + transform_query, grade_docs (Corrective RAG), Self-RAG retry loop
Level 3: + conversation memory, multi-query retrieval, contextual retrieval
"""

from __future__ import annotations

import asyncio
import logging
import inspect
import re
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Protocol

from langgraph.graph import END, StateGraph
from tracing.langfuse_trace import trace_llm_call
try:
    from tracing.otel import get_tracer as get_otel_tracer
except ImportError:
    class _NoopSpan:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def set_attribute(self, key: str, value: object) -> None:
            return None

    class _NoopTracer:
        def start_as_current_span(self, name: str):
            return _NoopSpan()

    def get_otel_tracer(name: str = "rag.graph"):
        _ = name
        return _NoopTracer()

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from utils.circuit_breaker import CircuitBreaker

# Support both package-style and root-level imports
try:
    from agent.state import GraphState, create_initial_state
    from agent.prompts import (
        build_classify_complexity_prompt,
        build_extract_claims_prompt,
        build_qa_prompt,
        build_self_eval_prompt,
        build_suggested_questions_prompt,
        build_query_transform_prompt,
        build_doc_grade_prompt,
        build_query_rewrite_prompt,
        build_verify_claim_prompt,
        build_conversational_qa_prompt,
        build_conversational_query_transform_prompt,
    )
    from tracing.sqlite_trace import start_trace, log_step, finish_trace
except ImportError:
    from state import GraphState, create_initial_state
    from prompts import (
        build_classify_complexity_prompt,
        build_extract_claims_prompt,
        build_qa_prompt,
        build_self_eval_prompt,
        build_suggested_questions_prompt,
        build_query_transform_prompt,
        build_doc_grade_prompt,
        build_query_rewrite_prompt,
        build_verify_claim_prompt,
        build_conversational_qa_prompt,
        build_conversational_query_transform_prompt,
    )
    from sqlite_trace import start_trace, log_step, finish_trace

try:
    from evaluation.evaluator_runner import persist_online_evaluations, run_online_evaluators
except ImportError:
    persist_online_evaluations = None  # type: ignore[assignment]
    run_online_evaluators = None  # type: ignore[assignment]

try:
    from agent.prompt_registry import (
        load_current_experiment,
        reset_current_experiment,
        set_current_experiment,
    )
except ImportError:
    load_current_experiment = None  # type: ignore[assignment]
    reset_current_experiment = None  # type: ignore[assignment]
    set_current_experiment = None  # type: ignore[assignment]

try:
    from config.settings import get_settings
except ImportError:
    get_settings = None  # type: ignore[assignment]

try:
    from llm.providers import build_provider_runtime
except ImportError:
    build_provider_runtime = None  # type: ignore[assignment]


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
        inbox_path = Path(__file__).resolve().parent.parent / "data" / "inbox" / "support_inbox.jsonl"
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


def _is_knowledge_gap(state: GraphState) -> bool:
    docs = state.get("graded_docs") or state.get("context_docs") or []
    if len(docs) < 2:
        return True

    factuality = state.get("factuality_score")
    if factuality is not None and factuality < 50:
        return True

    answer = str(state.get("answer") or "").lower()
    gap_patterns = (
        "я не знаю",
        "не нашел",
        "не нашёл",
        "недостаточно информации",
        "не могу ответить",
        "нет данных",
    )
    return any(pattern in answer for pattern in gap_patterns)


def _build_hyde_prompt(question: str) -> str:
    return (
        "You are a helpful assistant. Write a short hypothetical answer (2-3 sentences) "
        "to the following support question. Write only the answer, no intro or meta-text.\n\n"
        f"Question: {question}\n\nHypothetical answer:"
    )


def _extract_order_id(question: str) -> str | None:
    match = re.search(r"#?(\d{1,10})", question)
    if match is None:
        return None
    return match.group(1)


def _get_llm_provider_name(llm: SupportsInvoke) -> str | None:
    return _normalize_optional_str(getattr(llm, "provider_id", None))


def _get_llm_model_name(llm: SupportsInvoke) -> str | None:
    model_name = _normalize_optional_str(getattr(llm, "model_name", None))
    if model_name:
        return model_name
    return _normalize_optional_str(getattr(getattr(llm, "_llm", None), "model", None))


def _normalize_optional_str(value: Any) -> str | None:
    if value is None or not isinstance(value, (str, int, float)):
        return None
    normalized = str(value).strip()
    return normalized or None


def _normalize_optional_int(value: Any) -> int | None:
    if value is None or not isinstance(value, (str, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_optional_float(value: Any) -> float | None:
    if value is None or not isinstance(value, (str, int, float)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _new_llm_usage(node_name: str) -> Dict[str, Any]:
    return {
        "provider_name": None,
        "model_name": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "cost_usd": None,
        "usage_metadata": {},
        "usage_node": node_name,
    }


def _capture_llm_usage(llm: SupportsInvoke, node_name: str) -> Dict[str, Any]:
    usage = _new_llm_usage(node_name)
    usage["provider_name"] = _get_llm_provider_name(llm)
    usage["model_name"] = _get_llm_model_name(llm)
    response = getattr(llm, "last_response", None)
    if response is None:
        return usage

    prompt_tokens = _normalize_optional_int(getattr(response, "input_tokens", None))
    completion_tokens = _normalize_optional_int(getattr(response, "output_tokens", None))
    usage["provider_name"] = (
        _normalize_optional_str(getattr(response, "provider", None)) or usage["provider_name"]
    )
    usage["model_name"] = (
        _normalize_optional_str(getattr(response, "model", None)) or usage["model_name"]
    )
    usage["prompt_tokens"] = prompt_tokens
    usage["completion_tokens"] = completion_tokens
    usage["cost_usd"] = _normalize_optional_float(getattr(response, "cost_usd", None))
    if prompt_tokens is not None and completion_tokens is not None:
        usage["usage_metadata"] = {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
    return usage


def _merge_llm_usage(total: Dict[str, Any], snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if snapshot.get("provider_name"):
        total["provider_name"] = snapshot["provider_name"]
    if snapshot.get("model_name"):
        total["model_name"] = snapshot["model_name"]

    snapshot_prompt_tokens = snapshot.get("prompt_tokens")
    if snapshot_prompt_tokens is not None:
        total_prompt_tokens = total.get("prompt_tokens")
        if total_prompt_tokens is None:
            total["prompt_tokens"] = int(snapshot_prompt_tokens)
        else:
            total["prompt_tokens"] = int(total_prompt_tokens) + int(snapshot_prompt_tokens)

    snapshot_completion_tokens = snapshot.get("completion_tokens")
    if snapshot_completion_tokens is not None:
        total_completion_tokens = total.get("completion_tokens")
        if total_completion_tokens is None:
            total["completion_tokens"] = int(snapshot_completion_tokens)
        else:
            total["completion_tokens"] = int(total_completion_tokens) + int(
                snapshot_completion_tokens
            )

    snapshot_cost = snapshot.get("cost_usd")
    if snapshot_cost is not None:
        total_cost = total.get("cost_usd")
        if total_cost is None:
            total["cost_usd"] = float(snapshot_cost)
        else:
            total["cost_usd"] = float(total_cost) + float(snapshot_cost)

    prompt_tokens = total.get("prompt_tokens")
    completion_tokens = total.get("completion_tokens")
    if prompt_tokens is not None and completion_tokens is not None:
        total["usage_metadata"] = {
            "input_tokens": prompt_tokens,
            "output_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
    else:
        total["usage_metadata"] = {}

    return total


def _apply_llm_usage(state: GraphState, usage: Dict[str, Any]) -> GraphState:
    return {
        **state,
        "provider_name": usage.get("provider_name"),
        "model_name": usage.get("model_name"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "cost_usd": usage.get("cost_usd"),
        "usage_metadata": usage.get("usage_metadata", {}),
        "usage_node": usage.get("usage_node"),
    }


def _llm_supports_structured_output(llm: Any) -> bool:
    return bool(
        getattr(llm, "supports_structured_output", False) is True
        or callable(inspect.getattr_static(llm, "generate_with_schema", None))
    )


def _llm_supports_tool_use(llm: Any) -> bool:
    return bool(
        getattr(llm, "supports_tool_use", False) is True
        or callable(inspect.getattr_static(llm, "generate_with_tools", None))
    )


def _invoke_with_schema(
    llm: Any,
    prompt: str,
    schema: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any] | list[Any] | None:
    method = getattr(llm, "generate_with_schema", None)
    if not callable(method):
        return None
    response = method([{"role": "user", "content": prompt}], schema, **kwargs)
    structured_output = getattr(response, "structured_output", None)
    if isinstance(structured_output, (dict, list)):
        return structured_output
    return None


def _normalize_tool_call(tool_call: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    name = tool_call.get("name")
    if not isinstance(name, str):
        function = tool_call.get("function")
        if isinstance(function, dict):
            name = function.get("name")

    raw_arguments = tool_call.get("arguments")
    if raw_arguments is None:
        function = tool_call.get("function")
        if isinstance(function, dict):
            raw_arguments = function.get("arguments")

    if isinstance(raw_arguments, dict):
        arguments = dict(raw_arguments)
    elif isinstance(raw_arguments, str):
        try:
            import json as _json

            parsed = _json.loads(raw_arguments)
        except Exception:
            parsed = {}
        arguments = parsed if isinstance(parsed, dict) else {}
    else:
        arguments = {}

    return (str(name).strip() if isinstance(name, str) and name.strip() else None), arguments


def _agentic_tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "search_kb",
                "description": "Search the knowledge base and return relevant excerpts.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_order_status",
                "description": "Check the status of a customer order by ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                    },
                    "required": ["order_id"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_ticket",
                "description": "Create an escalation ticket. Requires confirmation before execution.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "priority": {"type": "string"},
                    },
                    "required": ["summary", "priority"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def _build_agentic_search_query(question: str) -> str:
    normalized = question.lower()
    if "достав" in normalized and "москв" in normalized:
        return "доставка в Москву"
    if "достав" in normalized:
        return "условия доставки"
    return question.strip()


# ---------------------------------------------------------------------------
# Model routing node
# ---------------------------------------------------------------------------


def make_classify_complexity_node(
    classifier_llm: SupportsInvoke,
) -> Callable[[GraphState], GraphState]:
    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown")
        try:
            from config.settings import get_settings

            settings = get_settings()
            if not getattr(settings, "model_routing_enabled", False):
                new_state: GraphState = {**state, "complexity": "unknown"}
                log_step(trace_id, "classify_complexity", new_state)
                return new_state

            question = state.get("question", "")
            prompt = build_classify_complexity_prompt(question)
            model = _get_llm_model_name(classifier_llm) or ""
            if _llm_supports_structured_output(classifier_llm):
                structured = _invoke_with_schema(
                    classifier_llm,
                    prompt,
                    {
                        "type": "object",
                        "properties": {
                            "complexity": {
                                "type": "string",
                                "enum": ["simple", "complex"],
                            }
                        },
                        "required": ["complexity"],
                        "additionalProperties": False,
                    },
                )
                raw = (
                    str(structured.get("complexity") or "")
                    if isinstance(structured, dict)
                    else ""
                ).strip().upper()
            else:
                raw = classifier_llm.invoke(prompt).strip().upper()
            usage = _capture_llm_usage(classifier_llm, "classify_complexity")
            trace_llm_call(
                trace_id=trace_id,
                node_name="classify_complexity",
                prompt=prompt,
                response=raw,
                model=model,
                duration_ms=0.0,
            )
            if raw.startswith("SIMPLE"):
                complexity = "simple"
            elif raw.startswith("COMPLEX"):
                complexity = "complex"
            else:
                complexity = "complex"

            new_state = _apply_llm_usage({**state, "complexity": complexity}, usage)

            try:
                from monitoring.prometheus import record_model_routing

                record_model_routing(complexity)
            except Exception:
                pass

            log_step(trace_id, "classify_complexity", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "classify_complexity", exc)

    return node


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
            model = _get_llm_model_name(llm) or ""
            usage = _new_llm_usage("transform_query")
            usage_recorded = False

            try:
                t0 = time.monotonic()
                raw_search_query = llm.invoke(prompt).strip()
                usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "transform_query"))
                usage_recorded = True
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
                    usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "transform_query"))
                    usage_recorded = True
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
            if usage_recorded:
                new_state = _apply_llm_usage(new_state, usage)
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
            tracer = get_otel_tracer()
            with tracer.start_as_current_span("rag.retrieve") as span:
                span.set_attribute("rag.question_length", len(str(state.get("question", "") or "")))
                span.set_attribute("rag.query_length", len(str(query or "")))
                span.set_attribute("rag.tenant_id", str(state.get("tenant_id", "default")))
                try:
                    docs = retriever.get_relevant_documents(query)
                except Exception as exc:
                    logger.warning("[retrieve] Retriever error: %s", exc, extra={"trace_id": trace_id})
                    docs = []
                span.set_attribute("rag.num_docs", len(docs))
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
            model = _get_llm_model_name(llm) or ""

            if not context_docs:
                new_state: GraphState = {**state, "graded_docs": [], "doc_grade_reason": "No documents retrieved"}
                log_step(trace_id, "grade_docs", new_state)
                return new_state

            graded: List[Dict[str, Any]] = []
            filtered_count = 0
            usage = _new_llm_usage("grade_docs")
            usage_recorded = False
            tracer = get_otel_tracer()
            with tracer.start_as_current_span("rag.rerank") as span:
                span.set_attribute("rag.tenant_id", str(state.get("tenant_id", "default")))
                span.set_attribute("rag.input_docs", len(context_docs))
                for doc in context_docs:
                    prompt = build_doc_grade_prompt(question=question, document=doc)
                    try:
                        t0 = time.monotonic()
                        if _llm_supports_structured_output(llm):
                            structured = _invoke_with_schema(
                                llm,
                                prompt,
                                {
                                    "type": "object",
                                    "properties": {
                                        "relevant": {"type": "boolean"},
                                        "reason": {"type": "string"},
                                    },
                                    "required": ["relevant", "reason"],
                                    "additionalProperties": False,
                                },
                            )
                            is_relevant = bool(
                                isinstance(structured, dict) and structured.get("relevant")
                            )
                            raw_verdict = (
                                str(structured.get("reason") or "")
                                if isinstance(structured, dict)
                                else ""
                            )
                        else:
                            raw_verdict = llm.invoke(prompt).strip()
                            is_relevant = raw_verdict.upper().startswith("YES")
                        usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "grade_docs"))
                        usage_recorded = True
                        trace_llm_call(
                            trace_id=trace_id,
                            node_name="grade_docs",
                            prompt=prompt,
                            response=raw_verdict,
                            model=model,
                            duration_ms=(time.monotonic() - t0) * 1000,
                        )
                    except Exception as exc:
                        logger.warning("[grade_docs] LLM error: %s", exc, extra={"trace_id": trace_id})
                        is_relevant = True
                    if is_relevant:
                        graded.append(doc)
                    else:
                        filtered_count += 1
                span.set_attribute("rag.filtered_docs", filtered_count)
                span.set_attribute("rag.output_docs", len(graded))

            reason = f"Kept {len(graded)}/{len(context_docs)}, filtered {filtered_count}"
            new_state = {**state, "graded_docs": graded, "doc_grade_reason": reason}
            if usage_recorded:
                new_state = _apply_llm_usage(new_state, usage)
            log_step(trace_id, "grade_docs", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "grade_docs", exc)

    return node


# ---------------------------------------------------------------------------
# Level 1: Generate node (updated to use graded_docs)
# ---------------------------------------------------------------------------


def make_generate_node(
    llm_fast: SupportsInvoke,
    llm_strong: SupportsInvoke,
) -> Callable[[GraphState], GraphState]:
    """Узел generate: формирует ответ. Level 3: учитывает chat_history."""

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            question = state.get("question", "")
            docs = state.get("graded_docs") or state.get("context_docs", []) or []
            chat_history = state.get("chat_history", [])
            complexity = state.get("complexity", "unknown")
            llm = llm_fast if complexity == "simple" else llm_strong
            model = _get_llm_model_name(llm) or ""
            usage = _new_llm_usage("generate")
            usage_recorded = False

            if chat_history:
                prompt = build_conversational_qa_prompt(question=question, context_docs=docs, chat_history=chat_history)
            else:
                prompt = build_qa_prompt(question=question, context_docs=docs)

            tracer = get_otel_tracer()
            with tracer.start_as_current_span("rag.generate") as span:
                span.set_attribute("rag.tenant_id", str(state.get("tenant_id", "default")))
                span.set_attribute("rag.input_docs", len(docs))
                try:
                    t0 = time.monotonic()
                    answer = llm.invoke(prompt)
                    usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "generate"))
                    usage_recorded = True
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
                span.set_attribute("rag.answer_length", len(str(answer or "")))

            citations: List[Dict[str, Any]] = []
            for idx, doc in enumerate(docs, start=1):
                if isinstance(doc, dict):
                    metadata = doc.get("metadata", {}) or {}
                    page_content = str(doc.get("page_content", "") or "")
                else:
                    metadata = getattr(doc, "metadata", {}) or {}
                    page_content = str(getattr(doc, "page_content", "") or "")
                doc_id = str(
                    metadata.get("doc_id")
                    or metadata.get("id")
                    or metadata.get("source")
                    or metadata.get("file_name")
                    or f"doc_{idx}"
                )
                title = str(
                    metadata.get("title")
                    or metadata.get("source")
                    or metadata.get("file_name")
                    or doc_id
                )
                citations.append(
                    {
                        "index": idx,
                        "doc_id": doc_id,
                        "title": title,
                        "excerpt": page_content[:300],
                    }
                )

            new_state: GraphState = {**state, "answer": answer, "citations": citations}
            if usage_recorded:
                new_state = _apply_llm_usage(new_state, usage)
            log_step(trace_id, "generate", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "generate", exc)

    return node


# ---------------------------------------------------------------------------
# Fact verification node
# ---------------------------------------------------------------------------


def make_verify_facts_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown")
        try:
            from config.settings import get_settings

            settings = get_settings()
            if not getattr(settings, "fact_verification_enabled", True):
                new_state: GraphState = {
                    **state,
                    "claims": [],
                    "fact_verification_skipped": True,
                    "factuality_score": 100,
                }
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            answer = state.get("answer", "")
            docs = state.get("graded_docs") or state.get("context_docs") or []
            context_text = "\n\n".join(
                str(
                    d.get("page_content") if isinstance(d, dict) else getattr(d, "page_content", "")
                )[:500]
                for d in docs[:5]
            )

            if not answer or not context_text:
                new_state = {
                    **state,
                    "claims": [],
                    "fact_verification_skipped": True,
                    "factuality_score": 100,
                }
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            if len(re.findall(r"\w+", answer)) < 3:
                new_state = {
                    **state,
                    "claims": [],
                    "fact_verification_skipped": False,
                    "factuality_score": 100,
                }
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            usage = _new_llm_usage("verify_facts")
            usage_recorded = False
            raw_claims = llm.invoke(build_extract_claims_prompt(answer)).strip()
            usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "verify_facts"))
            usage_recorded = True
            if raw_claims.upper().startswith("NONE"):
                new_state = {
                    **state,
                    "claims": [],
                    "fact_verification_skipped": False,
                    "factuality_score": 100,
                }
                new_state = _apply_llm_usage(new_state, usage)
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            claim_lines = [
                line.lstrip("- ").strip()
                for line in raw_claims.splitlines()
                if line.strip().startswith("-")
            ]
            claim_lines = claim_lines[:10]
            consensus_enabled = bool(
                getattr(settings, "fact_verify_consensus_enabled", False)
            )
            reliability_level = str(
                getattr(settings, "fact_verify_reliability_level", "standard") or "standard"
            ).strip() or "standard"

            claims_result: list[dict] = []
            for claim in claim_lines:
                if consensus_enabled and _llm_supports_structured_output(llm):
                    structured = _invoke_with_schema(
                        llm,
                        build_verify_claim_prompt(claim, context_text),
                        {
                            "type": "object",
                            "properties": {
                                "supported": {"type": "boolean"},
                                "evidence": {"type": "string"},
                            },
                            "required": ["supported", "evidence"],
                            "additionalProperties": False,
                        },
                        reliability_level=reliability_level,
                    )
                    usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "verify_facts"))
                    if isinstance(structured, dict):
                        supported = bool(structured.get("supported"))
                        evidence = str(structured.get("evidence") or "").strip()[:200]
                        claims_result.append(
                            {"text": claim, "supported": supported, "evidence": evidence}
                        )
                        try:
                            from monitoring.prometheus import FACT_VERIFICATION_CONSENSUS_TOTAL

                            FACT_VERIFICATION_CONSENSUS_TOTAL.labels(
                                level=reliability_level,
                                verdict="supported" if supported else "unsupported",
                            ).inc()
                        except Exception:
                            pass
                        continue
                verdict = llm.invoke(build_verify_claim_prompt(claim, context_text)).strip()
                usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "verify_facts"))
                supported = verdict.upper().startswith("SUPPORTED")
                evidence = ""
                if supported and ":" in verdict:
                    evidence = verdict.split(":", 1)[1].strip()[:200]
                claims_result.append(
                    {"text": claim, "supported": supported, "evidence": evidence}
                )

            if claims_result:
                factuality = int(
                    100 * sum(1 for claim in claims_result if claim["supported"]) / len(claims_result)
                )
            else:
                factuality = 100

            new_state = {
                **state,
                "claims": claims_result,
                "fact_verification_skipped": False,
                "factuality_score": factuality,
            }
            if usage_recorded:
                new_state = _apply_llm_usage(new_state, usage)

            try:
                from monitoring.prometheus import FACTUALITY_SCORE

                FACTUALITY_SCORE.observe(factuality)
            except Exception:
                pass

            log_step(trace_id, "verify_facts", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "verify_facts", exc)

    return node


# ---------------------------------------------------------------------------
# Level 1: Evaluate node
# ---------------------------------------------------------------------------


def make_evaluate_node(
    llm_fast: SupportsInvoke,
    llm_strong: SupportsInvoke,
) -> Callable[[GraphState], GraphState]:
    """Узел evaluate: самооценка качества ответа (1-100)."""

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            question = state.get("question", "")
            answer = state.get("answer") or ""
            docs = state.get("graded_docs") or state.get("context_docs", []) or []
            answer_for_eval = re.sub(r"\s*\[\d+\]", "", answer)
            answer_for_eval = re.sub(r"\s{2,}", " ", answer_for_eval).strip()
            prompt = build_self_eval_prompt(question=question, answer=answer_for_eval, context_docs=docs)
            complexity = state.get("complexity", "unknown")
            llm = llm_fast if complexity == "simple" else llm_strong
            model = _get_llm_model_name(llm) or ""
            usage = _new_llm_usage("evaluate")
            usage_recorded = False
            tracer = get_otel_tracer()
            with tracer.start_as_current_span("rag.evaluate") as span:
                span.set_attribute("rag.tenant_id", str(state.get("tenant_id", "default")))
                try:
                    t0 = time.monotonic()
                    raw = llm.invoke(prompt)
                    usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "evaluate"))
                    usage_recorded = True
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
                span.set_attribute("rag.quality_score", score)
            new_state = {
                **state,
                "quality_score": score,
                "relevance_score": round(score / 100.0, 3),
            }
            if usage_recorded:
                new_state = _apply_llm_usage(new_state, usage)
            new_state["knowledge_gap"] = _is_knowledge_gap(new_state)
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
        model = _get_llm_model_name(llm) or ""

        try:
            prompt = build_suggested_questions_prompt(
                state.get("question", ""),
                state.get("answer") or "",
                context_snippet=context_snippet,
            )
            t0 = time.monotonic()
            raw = llm.invoke(prompt)
            usage = _capture_llm_usage(llm, "suggest_questions")
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
            new_state: GraphState = _apply_llm_usage(
                {**state, "suggested_questions": questions},
                usage,
            )
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
            model = _get_llm_model_name(llm) or ""
            usage = _new_llm_usage("rewrite_query")
            usage_recorded = False
            try:
                t0 = time.monotonic()
                raw_new_query = llm.invoke(prompt).strip()
                usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "rewrite_query"))
                usage_recorded = True
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
                "claims": [],
                "factuality_score": 0,
                "fact_verification_skipped": False,
                "quality_score": None,
                "relevance_score": None,
            }
            if usage_recorded:
                new_state = _apply_llm_usage(new_state, usage)
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
    min_quality: int | None = None,
    max_iterations: int = 2,
):
    """Собирает и компилирует граф LangGraph Level 2.

    Граф:
        classify_complexity → transform_query → retrieve → grade_docs → generate
            → verify_facts → evaluate → route_or_retry
                ├─ (retry) → rewrite_query → retrieve → ...
                └─ (end)   → log → END
    """
    from config.settings import get_settings

    settings = get_settings()
    if min_quality is None:
        min_quality = getattr(settings, "quality_threshold", 80)

    if llm is None:
        if build_provider_runtime is not None:
            runtime = build_provider_runtime(settings)
            llm_fast = runtime.fast
            llm_strong = runtime.strong
        else:
            llm_strong = LocalOllamaLLM(model_name=settings.ollama_model_name)
            if getattr(settings, "model_routing_enabled", False):
                llm_fast = LocalOllamaLLM(model_name=settings.ollama_fast_model_name)
            else:
                llm_fast = llm_strong
    else:
        llm_fast = llm
        llm_strong = llm

    workflow = StateGraph(GraphState)

    # Регистрируем узлы
    workflow.add_node("classify_complexity", make_classify_complexity_node(llm_fast))
    workflow.add_node("transform_query", make_transform_query_node(llm_fast))
    workflow.add_node("retrieve", make_retrieve_node(retriever))
    workflow.add_node("grade_docs", make_grade_docs_node(llm_fast))
    workflow.add_node("generate", make_generate_node(llm_fast, llm_strong))
    workflow.add_node("verify_facts", make_verify_facts_node(llm_fast))
    workflow.add_node("evaluate", make_evaluate_node(llm_fast, llm_strong))
    workflow.add_node("route_or_retry", make_route_or_retry_node(min_quality=min_quality))
    workflow.add_node("suggest_questions", make_suggest_questions_node(llm_strong))
    workflow.add_node("rewrite_query", make_rewrite_query_node(llm_strong))
    workflow.add_node("log", make_log_node())
    workflow.add_node("handle_error", make_handle_error_node())

    # Основной путь
    workflow.set_entry_point("classify_complexity")
    workflow.add_edge("classify_complexity", "transform_query")
    workflow.add_edge("transform_query", "retrieve")
    workflow.add_edge("retrieve", "grade_docs")
    workflow.add_edge("grade_docs", "generate")
    workflow.add_edge("generate", "verify_facts")
    workflow.add_edge("verify_facts", "evaluate")
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
    trace_id: str | None = None,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    session_id: str | None = None,
) -> GraphState:
    """Обрабатывает один вопрос через граф.

    Args:
        question: вопрос пользователя.
        retriever: retriever для поиска документов.
        llm: LLM для генерации.
        max_iterations: макс. итераций Self-RAG.
        chat_history: история диалога (Level 3).
    """
    trace_id = start_trace(trace_id=trace_id, tenant_id=tenant_id)
    assigned_experiment = None
    try:
        from agent.prompt_registry import resolve_active_experiment as _resolve_active
        assigned_experiment = _resolve_active(
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:
        assigned_experiment = None
    experiment_token = (
        set_current_experiment(
            assigned_experiment
            if assigned_experiment is not None
            else (load_current_experiment() if load_current_experiment is not None else None)
        )
        if set_current_experiment is not None
        else None
    )
    try:
        if get_settings is not None and getattr(get_settings, "__module__", "") != "config.settings":
            settings = get_settings()
        else:
            try:
                from config.settings import get_settings as config_get_settings
            except ImportError:
                settings = get_settings() if get_settings is not None else None
            else:
                settings = config_get_settings()
        initial_state = create_initial_state(
            question=question,
            trace_id=trace_id,
            tenant_id=tenant_id,
        )
        initial_state["max_iterations"] = max_iterations
        if chat_history:
            initial_state["chat_history"] = chat_history

        graph = build_support_graph(
            retriever=retriever,
            llm=llm,
            min_quality=getattr(settings, "quality_threshold", 80),
            max_iterations=max_iterations,
        )

        final_state = graph.invoke(initial_state)
        finish_trace(trace_id, final_state)
        if (
            getattr(settings, "online_evaluators_enabled", False)
            and run_online_evaluators is not None
            and persist_online_evaluations is not None
        ):
            try:
                trace_state = dict(final_state)
                trace_state["trace_id"] = trace_id

                async def _persist_results() -> None:
                    results = await asyncio.wait_for(
                        asyncio.to_thread(run_online_evaluators, trace_state),
                        timeout=1.0,
                    )
                    persisted = persist_online_evaluations(trace_id, results)
                    if inspect.isawaitable(persisted):
                        await persisted

                asyncio.run(_persist_results())
            except Exception as exc:
                logger.warning(
                    "Online evaluators failed: %s",
                    exc,
                    extra={"trace_id": trace_id},
                )
        return final_state
    finally:
        if experiment_token is not None and reset_current_experiment is not None:
            reset_current_experiment(experiment_token)


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
        self._pending_action: Dict[str, str] | None = None

    @property
    def history(self) -> List[Dict[str, str]]:
        return list(self._history)

    def _append_history(self, question: str, answer: str) -> None:
        self._history.append({"role": "user", "content": question})
        self._history.append({"role": "assistant", "content": answer})
        if len(self._history) > self._max_history * 2:
            self._history = self._history[-(self._max_history * 2):]

    def _select_agentic_llm(self) -> Any | None:
        if self._llm is not None and _llm_supports_tool_use(self._llm):
            return self._llm
        if build_provider_runtime is None:
            return None
        try:
            settings = get_settings()
            runtime = build_provider_runtime(settings)
        except Exception:
            return None
        for candidate in (runtime.strong, runtime.fast):
            if _llm_supports_tool_use(candidate):
                return candidate
        return None

    def _run_provider_tool_loop(
        self,
        question: str,
        state: GraphState,
        *,
        active_trace_id: str,
        tenant_id: str,
        user_id: str,
        session_id: str | None,
    ) -> GraphState | None:
        from agent import tools as agent_tools

        tool_llm = self._select_agentic_llm()
        if tool_llm is None:
            return None

        try:
            settings = get_settings()
        except Exception:
            settings = None
        max_loops = int(getattr(settings, "agent_max_tool_loops", 5) or 5)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a support agent. Use tools when they help answer the user. "
                    "If tools are not needed, answer directly."
                ),
            },
            {"role": "user", "content": question},
        ]
        tool_calls: list[str] = []
        usage = _new_llm_usage("agentic")

        for _ in range(max_loops):
            try:
                response = tool_llm.generate_with_tools(messages, _agentic_tool_definitions())
            except Exception as exc:
                logger.warning("[agentic] provider tool loop unavailable: %s", exc)
                return None
            usage = _merge_llm_usage(usage, _capture_llm_usage(tool_llm, "agentic"))
            raw_tool_calls = getattr(response, "tool_calls", None) or []
            if not raw_tool_calls:
                answer = str(response.text or "").strip()
                if not answer:
                    return None
                final_state: GraphState = {
                    **state,
                    "answer": answer,
                    "route": "agentic",
                    "quality_score": 85,
                    "relevance_score": 0.85,
                    "tool_calls": tool_calls,
                    "requires_confirmation": False,
                    "action_summary": "",
                }
                final_state = _apply_llm_usage(final_state, usage)
                log_step(active_trace_id, "agentic_answer", final_state)
                return final_state

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": str(response.text or ""),
                "tool_calls": raw_tool_calls,
            }
            messages.append(assistant_message)

            for raw_tool_call in raw_tool_calls:
                if not isinstance(raw_tool_call, dict):
                    continue
                tool_name, arguments = _normalize_tool_call(raw_tool_call)
                if not tool_name:
                    continue
                if tool_name == "search_kb":
                    result = agent_tools.search_kb(
                        str(arguments.get("query") or question),
                        tenant_id,
                        retriever=self._retriever,
                    )
                elif tool_name == "check_order_status":
                    order_id = str(arguments.get("order_id") or _extract_order_id(question) or "")
                    result = agent_tools.check_order_status(order_id, tenant_id)
                elif tool_name == "create_ticket":
                    summary = str(arguments.get("summary") or question).strip()
                    priority = str(arguments.get("priority") or "medium").strip() or "medium"
                    action_summary = f"создать тикет по запросу: {summary[:120]}"
                    self._pending_action = {
                        "summary": summary,
                        "priority": priority,
                        "action_summary": action_summary,
                    }
                    confirmation_state: GraphState = {
                        **state,
                        "answer": f"Подтвердите: {action_summary}",
                        "route": "agentic",
                        "quality_score": 80,
                        "relevance_score": 0.8,
                        "tool_calls": tool_calls + [tool_name],
                        "requires_confirmation": True,
                        "action_summary": action_summary,
                    }
                    confirmation_state = _apply_llm_usage(confirmation_state, usage)
                    log_step(active_trace_id, "confirmation_gate", confirmation_state)
                    return confirmation_state
                else:
                    continue

                tool_calls.append(tool_name)
                tool_state = {**state, "tool_calls": list(tool_calls), "tool_output": result}
                log_step(active_trace_id, tool_name, tool_state)
                messages.append({"role": "tool", "name": tool_name, "content": result})

        answer_parts = [
            str(item.get("content") or "")
            for item in messages
            if item.get("role") == "tool" and str(item.get("content") or "").strip()
        ]
        if not answer_parts:
            return None
        final_state = {
            **state,
            "answer": "\n\n".join(answer_parts),
            "route": "agentic",
            "quality_score": 80,
            "relevance_score": 0.8,
            "tool_calls": tool_calls,
            "requires_confirmation": False,
            "action_summary": "",
        }
        final_state = _apply_llm_usage(final_state, usage)
        log_step(active_trace_id, "agentic_fallback", final_state)
        return final_state

    def _run_agentic_flow(
        self,
        question: str,
        trace_id: Optional[str],
        tenant_id: str,
        user_id: str,
        session_id: str | None,
        confirm: bool | None,
    ) -> GraphState | None:
        from agent import tools as agent_tools

        normalized = question.strip().lower()
        has_ticket_intent = any(
            marker in normalized
            for marker in ("создай тикет", "создать тикет", "тикет", "оператор", "эскал")
        )

        start_trace_params = inspect.signature(start_trace).parameters
        has_var_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in start_trace_params.values()
        )
        if "trace_id" in start_trace_params or "tenant_id" in start_trace_params or has_var_kwargs:
            active_trace_id = start_trace(trace_id=trace_id, tenant_id=tenant_id)
        elif trace_id is not None:
            active_trace_id = start_trace(trace_id)
        else:
            active_trace_id = start_trace()
        state = create_initial_state(
            question=question,
            trace_id=active_trace_id,
            tenant_id=tenant_id,
        )

        if self._pending_action is not None:
            if confirm is True:
                pending = self._pending_action
                self._pending_action = None
                ticket_result = agent_tools.create_ticket(
                    summary=pending["summary"],
                    priority=pending["priority"],
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=session_id or "",
                )
                state.update(
                    answer=ticket_result,
                    route="auto",
                    quality_score=90,
                    relevance_score=0.9,
                    tool_calls=["create_ticket"],
                    requires_confirmation=False,
                    action_summary="",
                )
                log_step(active_trace_id, "create_ticket", state)
                finish_trace(active_trace_id, state)
                return state
            if confirm is False:
                self._pending_action = None
                state.update(
                    answer="Действие отменено.",
                    route="auto",
                    quality_score=80,
                    relevance_score=0.8,
                    tool_calls=[],
                    requires_confirmation=False,
                    action_summary="",
                )
                log_step(active_trace_id, "confirmation_cancelled", state)
                finish_trace(active_trace_id, state)
                return state

            state.update(
                answer=f"Подтвердите: {self._pending_action['action_summary']}",
                route="agentic",
                quality_score=80,
                relevance_score=0.8,
                tool_calls=[],
                requires_confirmation=True,
                action_summary=self._pending_action["action_summary"],
            )
            log_step(active_trace_id, "await_confirmation", state)
            finish_trace(active_trace_id, state)
            return state

        provider_agentic_result = self._run_provider_tool_loop(
            question,
            state,
            active_trace_id=active_trace_id,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
        )
        if provider_agentic_result is not None:
            finish_trace(active_trace_id, provider_agentic_result)
            return provider_agentic_result

        if has_ticket_intent:
            summary = question.strip()
            action_summary = f"создать тикет по запросу: {summary[:120]}"
            self._pending_action = {
                "summary": summary,
                "priority": "medium",
                "action_summary": action_summary,
            }
            state.update(
                answer=f"Подтвердите: {action_summary}",
                route="agentic",
                quality_score=80,
                relevance_score=0.8,
                tool_calls=["create_ticket"],
                requires_confirmation=True,
                action_summary=action_summary,
            )
            log_step(active_trace_id, "confirmation_gate", state)
            finish_trace(active_trace_id, state)
            return state

        order_id = _extract_order_id(question)
        needs_order_tool = order_id is not None and any(
            marker in normalized for marker in ("заказ", "достав", "статус")
        )
        if not needs_order_tool:
            finish_trace(active_trace_id, state)
            return None

        tool_calls: list[str] = []
        answer_parts: list[str] = []

        if any(marker in normalized for marker in ("достав", "стоит", "москв")):
            kb_result = agent_tools.search_kb(
                _build_agentic_search_query(question),
                tenant_id,
                retriever=self._retriever,
            )
            tool_calls.append("search_kb")
            answer_parts.append(kb_result)
            log_step(
                active_trace_id,
                "search_kb",
                {**state, "tool_calls": list(tool_calls), "tool_output": kb_result},
            )

        order_result = agent_tools.check_order_status(order_id, tenant_id)
        tool_calls.append("check_order_status")
        answer_parts.insert(0, order_result)
        log_step(
            active_trace_id,
            "check_order_status",
            {**state, "tool_calls": list(tool_calls), "tool_output": order_result},
        )

        state.update(
            answer="\n\n".join(part for part in answer_parts if part),
            route="auto",
            quality_score=85,
            relevance_score=0.85,
            tool_calls=tool_calls,
            requires_confirmation=False,
            action_summary="",
        )
        finish_trace(active_trace_id, state)
        return state

    def ask(
        self,
        question: str,
        trace_id: Optional[str] = None,
        tenant_id: str = "default",
        confirm: bool | None = None,
        user_id: str = "anonymous",
        session_id: str | None = None,
    ) -> GraphState:
        """Задаёт вопрос с учётом истории диалога."""
        from config.settings import get_settings

        settings = get_settings()
        if getattr(settings, "agentic_mode", False):
            agentic_result = self._run_agentic_flow(
                question=question,
                trace_id=trace_id,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                confirm=confirm,
            )
            if agentic_result is not None:
                self._append_history(question, agentic_result.get("answer") or "")
                return agentic_result

        result = run_qa_pipeline(
            question=question,
            retriever=self._retriever,
            llm=self._llm,
            max_iterations=self._max_iterations,
            chat_history=self._history,
            trace_id=trace_id,
            tenant_id=tenant_id,
        )

        answer = result.get("answer") or ""
        self._append_history(question, answer)
        return result

    def clear(self) -> None:
        """Сбрасывает историю."""
        self._history.clear()
