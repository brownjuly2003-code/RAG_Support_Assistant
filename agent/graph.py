"""
agent/graph.py

LangGraph-пайплайн для RAG-ассистента (Level 1-3).

Level 1: retrieve → generate → evaluate → route
Level 2: + transform_query, grade_docs (Corrective RAG), Self-RAG retry loop
Level 3: + conversation memory, multi-query retrieval, contextual retrieval
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, Optional, Protocol, cast

from langgraph.graph import END, StateGraph

from tracing.langfuse_trace import trace_llm_call

try:
    from tracing.otel import get_tracer as get_otel_tracer
except ImportError:
    class _NoopSpan:
        def __enter__(self) -> "_NoopSpan":
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            tb: Any,
        ) -> Literal[False]:
            return False

        def set_attribute(self, key: str, value: object) -> None:
            return None

    class _NoopTracer:
        def start_as_current_span(self, name: str) -> _NoopSpan:
            return _NoopSpan()

    def get_otel_tracer(name: str = "rag.graph") -> Any:
        _ = name
        return _NoopTracer()

logger = logging.getLogger(__name__)

# Online-evaluator failures are deduplicated per process: the first occurrence of
# a given error signature logs at WARNING, repeats drop to DEBUG. In a standalone
# graph run with no Postgres reachable, persistence fails identically on *every*
# request (e.g. `password authentication failed for user "rag"`); logging that once
# is signal, logging it per-request is noise that reads like a recurring outage.
# New, distinct failures still surface at WARNING. (Dogfood finding #2, 2026-06-18.)
_ONLINE_EVAL_WARN_LOCK = threading.Lock()
_ONLINE_EVAL_WARNED: set[str] = set()
_ONLINE_EVAL_WARNED_MAX = 64


def _online_eval_first_time(signature: str) -> bool:
    """Return True the first time ``signature`` is seen this process, else False."""
    with _ONLINE_EVAL_WARN_LOCK:
        if signature in _ONLINE_EVAL_WARNED:
            return False
        if len(_ONLINE_EVAL_WARNED) >= _ONLINE_EVAL_WARNED_MAX:
            _ONLINE_EVAL_WARNED.clear()
        _ONLINE_EVAL_WARNED.add(signature)
        return True

if TYPE_CHECKING:
    from utils.circuit_breaker import CircuitBreaker

from agent.judge_policy import (  # noqa: E402
    judge_fail_closed_fields,
    parse_judge_score,
    resolve_judge_llm,
)
from agent.prompts import (  # noqa: E402
    build_classify_complexity_prompt,
    build_conversational_qa_prompt,
    build_conversational_query_transform_prompt,
    build_doc_grade_batch_prompt,
    build_doc_grade_prompt,
    build_extract_claims_prompt,
    build_qa_prompt,
    build_query_rewrite_prompt,
    build_query_transform_prompt,
    build_self_eval_prompt,
    build_suggested_questions_prompt,
    build_verify_claim_prompt,
)
from agent.response_safety import apply_pre_response_safety  # noqa: E402
from agent.state import GraphState, create_initial_state  # noqa: E402
from tracing.sqlite_trace import finish_trace, log_step, start_trace  # noqa: E402

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


def _escalate_to_inbox(state: GraphState) -> dict[str, str | None]:
    """Durable escalation via services.escalation (plan §4.3).

    Returns ticket_id / delivery_state for the caller. Never claims operator
    handoff without a durable ticket (message comes from the service).
    """
    from services.escalation import create_escalation_sync

    trace_id = str(state.get("trace_id", "unknown") or "unknown")
    question = str(state.get("question", "") or "")
    tenant_id = str(state.get("tenant_id", "default") or "default")
    session_id = str(state.get("session_id") or trace_id)
    draft = (
        f"error_node={state.get('error_node', '')}\n"
        f"error_message={str(state.get('error_message', ''))[:500]}"
    )
    try:
        outcome = create_escalation_sync(
            tenant_id=tenant_id,
            session_id=session_id,
            question=question or "(ошибка пайплайна)",
            source="handle_error",
            ai_draft=draft,
            reason=str(state.get("error_node") or "pipeline_error"),
            trace_id=trace_id,
        )
        return {
            "ticket_id": outcome.ticket_id,
            "delivery_state": outcome.delivery_state,
            "user_message": outcome.user_message,
            "durable": "1" if outcome.durable else "0",
        }
    except Exception as exc:
        logger.error("Durable handle_error escalation failed: %s", exc, exc_info=True)
        return {
            "ticket_id": None,
            "delivery_state": "failed",
            "user_message": (
                "Не удалось зарегистрировать обращение. "
                "Повторите попытку или свяжитесь с поддержкой другим каналом."
            ),
            "durable": "0",
        }


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
    """Узел handle_error: durable escalation + честный user message (plan §4.3)."""

    def node(state: GraphState) -> GraphState:
        trace_id = state.get("trace_id", "unknown")
        logger.error(
            "Pipeline error escalation: node='%s' trace_id=%s",
            state.get("error_node", "unknown"),
            trace_id,
            extra={"trace_id": trace_id},
        )

        esc = _escalate_to_inbox(state)

        try:
            log_step(trace_id, "handle_error", state)
        except Exception as exc:
            logger.warning("Failed to log handle_error step: %s", exc, extra={"trace_id": trace_id})

        return {
            **state,  # type: ignore[misc]
            "answer": esc.get("user_message")
            or (
                "Не удалось зарегистрировать обращение. "
                "Повторите попытку или свяжитесь с поддержкой другим каналом."
            ),
            "route": "error_escalation",
            "ticket_id": esc.get("ticket_id"),
            "delivery_state": esc.get("delivery_state"),
        }

    return node


# ---------------------------------------------------------------------------
# Интерфейс для LLM (простой протокол)
# ---------------------------------------------------------------------------


class SupportsInvoke(Protocol):
    """Протокол для объектов, у которых есть метод invoke(prompt: str) -> str."""

    def invoke(self, prompt: str, **kwargs: Any) -> str:  # pragma: no cover
        ...


def _invoke_llm(
    llm: SupportsInvoke,
    prompt: str,
    *,
    role: str = "default",
) -> str:
    """Invoke LLM with plan §3.1d per-role temperature / max_tokens.

    Falls back to bare ``invoke(prompt)`` when the backend rejects kwargs
    (legacy fakes / LocalOllama without generation options).
    ``LLMBudgetExceeded`` / deadline errors propagate fail-closed.
    """
    from llm.request_budget import LLMBudgetExceeded
    from llm.role_params import generation_kwargs_for_role

    params = generation_kwargs_for_role(role)
    invoke = getattr(llm, "invoke", None)
    if not callable(invoke):
        raise TypeError("llm does not support invoke()")
    try:
        return str(invoke(prompt, **params))
    except TypeError:
        # Distinguish "kwargs not accepted" from other TypeErrors inside invoke.
        try:
            return str(invoke(prompt))
        except LLMBudgetExceeded:
            raise
    except LLMBudgetExceeded:
        raise


def _coerce_stream_chunk(chunk: Any) -> str:
    """Normalize provider/LangChain stream chunks to plain text."""
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    content = getattr(chunk, "content", None)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(str(item["text"]))
            else:
                text = getattr(item, "text", None)
                if text:
                    parts.append(str(text))
        return "".join(parts)
    text = getattr(chunk, "text", None)
    if isinstance(text, str):
        return text
    return str(chunk)


def _stream_llm_tokens(
    llm: SupportsInvoke,
    prompt: str,
    *,
    role: str = "default",
    on_token: Callable[[str], None],
) -> str | None:
    """Best-effort provider/LangChain token stream; None → caller falls back.

    Plan §4.8: used only when SSE parity enables provider token streaming.
    Failures return None so generate can fall back to ``_invoke_llm`` without
    claiming ``provider_generate`` tokens.
    """
    from llm.request_budget import LLMBudgetExceeded
    from llm.role_params import generation_kwargs_for_role

    params = generation_kwargs_for_role(role)

    gen_stream = getattr(llm, "generate_stream", None)
    if callable(gen_stream):
        parts: list[str] = []

        async def _agen() -> Any:
            messages = [{"role": "user", "content": prompt}]
            try:
                stream = gen_stream(messages, **params)
            except TypeError:
                stream = gen_stream(messages)
            async for chunk in stream:
                text = _coerce_stream_chunk(chunk)
                if text:
                    parts.append(text)
                    on_token(text)
                    yield text

        try:
            # Drain for side effects; reassemble from parts.
            async def _collect() -> str:
                async for _ in _agen():
                    pass
                return "".join(parts)

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                text = asyncio.run(_collect())
            else:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    text = pool.submit(lambda: asyncio.run(_collect())).result()
            if text:
                return text
        except LLMBudgetExceeded:
            raise
        except Exception as exc:
            logger.warning(
                "[generate] provider generate_stream failed; fallback invoke: %s",
                exc,
            )
            return None

    stream_fn = getattr(llm, "stream", None)
    if not callable(stream_fn):
        # LocalOllama wraps an inner langchain model that may stream.
        inner = getattr(llm, "_llm", None)
        stream_fn = getattr(inner, "stream", None) if inner is not None else None
    if callable(stream_fn):
        parts = []
        try:
            try:
                chunks = stream_fn(prompt, **params)
            except TypeError:
                chunks = stream_fn(prompt)
            for chunk in chunks:
                text = _coerce_stream_chunk(chunk)
                if text:
                    parts.append(text)
                    on_token(text)
            if parts:
                return "".join(parts)
        except LLMBudgetExceeded:
            raise
        except Exception as exc:
            logger.warning(
                "[generate] sync stream failed; fallback invoke: %s",
                exc,
            )
            return None
    return None


def _emit_provider_token(token: str) -> None:
    """Write a provider token into LangGraph custom stream (best-effort)."""
    if not token:
        return
    try:
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
    except Exception:
        return
    if not callable(writer):
        return
    try:
        writer(
            {
                "type": "token",
                "token": token,
                "token_source": "provider_generate",
                "source": "graph",
            }
        )
    except Exception:
        # Writer may be a no-op under invoke(); never break generate.
        return


def _generate_answer_text(
    llm: SupportsInvoke,
    prompt: str,
    *,
    role: str = "generate",
) -> str:
    """Generate answer text; stream provider tokens when SSE flag is on."""
    try:
        from agent.graph_stream import provider_token_stream_enabled
    except Exception:
        provider_token_stream_enabled = None  # type: ignore[assignment]

    stream_on = False
    if provider_token_stream_enabled is not None:
        try:
            stream_on = bool(provider_token_stream_enabled.get())
        except Exception:
            stream_on = False

    if stream_on:
        streamed = _stream_llm_tokens(
            llm,
            prompt,
            role=role,
            on_token=_emit_provider_token,
        )
        if streamed is not None:
            return streamed
    return _invoke_llm(llm, prompt, role=role)


def _budget_exhausted_state(
    question: str,
    trace_id: Optional[str],
    tenant_id: str,
    *,
    reason: str = "exhausted",
) -> GraphState:
    """Degraded terminal when per-request LLM budget is hit — never route=auto."""
    state = create_initial_state(question, trace_id=trace_id, tenant_id=tenant_id)
    state["answer"] = (
        "Извините, лимит обработки запроса исчерпан. "
        "Пожалуйста, упростите вопрос или обратитесь к специалисту поддержки."
    )
    state["route"] = "human"
    state["quality_score"] = 0
    state["error"] = True
    state["error_message"] = f"LLM request budget exceeded ({reason})"
    state["error_node"] = "llm_budget"
    return state


_USE_DEFAULT_BREAKER = object()


def _with_ollama_timeout_kwargs(model_name: str, timeout_sec: float) -> list[dict[str, Any]]:
    return [
        {"model": model_name, "timeout": timeout_sec},
        {"model": model_name, "request_timeout": timeout_sec},
        {"model": model_name, "client_kwargs": {"timeout": timeout_sec}},
        {"model": model_name},
    ]


def _instantiate_local_ollama(cls: Any, model_name: str, timeout_sec: float) -> Any:
    last_type_error: TypeError | None = None
    for kwargs in _with_ollama_timeout_kwargs(model_name, timeout_sec):
        try:
            return cls(**kwargs)
        except TypeError as exc:
            last_type_error = exc
    if last_type_error is not None:
        raise last_type_error
    return cls(model=model_name)


def _create_local_ollama_llm(model_name: str, timeout_sec: float) -> Any:
    try:
        from langchain_ollama import OllamaLLM as ollama_llm_cls  # type: ignore[import-not-found]

        return _instantiate_local_ollama(ollama_llm_cls, model_name, timeout_sec)
    except ImportError:
        from langchain_community.llms import Ollama as community_ollama_cls

        return _instantiate_local_ollama(community_ollama_cls, model_name, timeout_sec)


class LocalOllamaLLM:
    """Обёртка над локальной моделью Ollama."""

    def __init__(
        self,
        model_name: str = "mistral",
        breaker: CircuitBreaker | None | object = _USE_DEFAULT_BREAKER,
    ):
        from config.settings import get_settings
        from utils.retry import retry_with_backoff

        settings = get_settings()
        timeout_sec = getattr(settings, "ollama_request_timeout_sec", 60.0)
        self._llm = _create_local_ollama_llm(model_name, timeout_sec)
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

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        invoke_with_retry = getattr(self, "_invoke_with_retry", self._llm.invoke)

        def _call(text: str) -> str:
            try:
                return str(invoke_with_retry(text, **kwargs)) if kwargs else str(invoke_with_retry(text))
            except TypeError:
                return str(invoke_with_retry(text))

        if self._breaker is None:
            return _call(prompt)
        return cast("CircuitBreaker", self._breaker).call(_call, prompt)


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

    def _prom_hook(name: str, old_state: Any, new_state: Any) -> None:
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


def _docs_to_plain_dicts(docs: list[Any]) -> list[dict[str, Any]]:
    """Преобразует Document объекты в plain dicts для JSON/SQLite."""
    plain_docs: list[dict[str, Any]] = []
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


def _coerce_relevance_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"yes", "true", "relevant", "supported", "1"}:
            return True
        if normalized in {"no", "false", "irrelevant", "unsupported", "0"}:
            return False
    return None


def _coerce_doc_grade_batch(
    payload: Any,
    doc_count: int,
) -> list[tuple[bool, str]] | None:
    if doc_count <= 0:
        return []

    raw_grades = payload
    if isinstance(payload, dict):
        raw_grades = payload.get("grades") or payload.get("documents") or payload.get("results")
    if not isinstance(raw_grades, list):
        return None

    grades_by_index: dict[int, tuple[bool, str]] = {}
    ordered_bool_grades: list[tuple[bool, str]] = []
    for position, item in enumerate(raw_grades, start=1):
        if isinstance(item, bool | str):
            relevant = _coerce_relevance_bool(item)
            if relevant is None:
                return None
            ordered_bool_grades.append((relevant, ""))
            continue
        if not isinstance(item, dict):
            return None

        raw_index = item.get("index") or item.get("doc_index") or item.get("document_index") or position
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            return None
        if index < 1 or index > doc_count:
            return None

        relevant = _coerce_relevance_bool(item.get("relevant"))
        if relevant is None:
            relevant = _coerce_relevance_bool(item.get("verdict"))
        if relevant is None:
            return None
        grades_by_index[index] = (relevant, str(item.get("reason") or ""))

    if ordered_bool_grades:
        if len(ordered_bool_grades) != doc_count:
            return None
        return ordered_bool_grades

    if len(grades_by_index) != doc_count:
        return None
    return [grades_by_index[index] for index in range(1, doc_count + 1)]


def _parse_doc_grade_batch_text(raw: str, doc_count: int) -> list[tuple[bool, str]] | None:
    text = raw.strip()
    if not text:
        return None

    try:
        return _coerce_doc_grade_batch(json.loads(text), doc_count)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            parsed = None
        if parsed is not None:
            grades = _coerce_doc_grade_batch(parsed, doc_count)
            if grades is not None:
                return grades

    indexed: dict[int, tuple[bool, str]] = {}
    ordered: list[tuple[bool, str]] = []
    for position, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip().strip("-*")
        if not stripped:
            continue
        indexed_match = re.match(
            r"^(?:doc(?:ument)?\s*)?(\d+)\s*[\).:\-]?\s*(yes|no|true|false|relevant|irrelevant)\b",
            stripped,
            flags=re.IGNORECASE,
        )
        if indexed_match:
            index = int(indexed_match.group(1))
            relevant = _coerce_relevance_bool(indexed_match.group(2))
            if relevant is not None and 1 <= index <= doc_count:
                indexed[index] = (relevant, "")
            continue
        ordered_match = re.match(
            r"^(yes|no|true|false|relevant|irrelevant)\b",
            stripped,
            flags=re.IGNORECASE,
        )
        if ordered_match:
            relevant = _coerce_relevance_bool(ordered_match.group(1))
            if relevant is not None:
                ordered.append((relevant, ""))

    if len(indexed) == doc_count:
        return [indexed[index] for index in range(1, doc_count + 1)]
    if len(ordered) == doc_count:
        return ordered
    return None


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


def _new_llm_usage(node_name: str) -> dict[str, Any]:
    return {
        "provider_name": None,
        "model_name": None,
        "prompt_tokens": None,
        "completion_tokens": None,
        "cost_usd": None,
        "usage_metadata": {},
        "usage_node": node_name,
    }


def _capture_llm_usage(llm: SupportsInvoke, node_name: str) -> dict[str, Any]:
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


def _merge_llm_usage(total: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
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


def _apply_llm_usage(state: GraphState, usage: dict[str, Any]) -> GraphState:
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


def _agentic_unmeasured_gate(
    *,
    route: Literal["agentic", "human"] = "agentic",
) -> dict[str, Any]:
    """Fail-closed quality fields for agentic terminals without evaluate/grounding.

    Plan §6.1: never invent quality 80/85/90 or ``quality_source="fixed"``, and
    never claim ``route=auto`` until a real measured gate runs. Tool results and
    confirmation UX stay deliverable as ``route=agentic`` with honest provenance.
    """
    from agent.agentic_measure import unmeasured_agentic_fields

    return unmeasured_agentic_fields(route=route)


def _agentic_terminal_fields(
    *,
    answer: str,
    kb_docs: list[Any] | None = None,
    quality_score: int | None = None,
    relevance_score: float | None = None,
    quality_source: str | None = None,
) -> dict[str, Any]:
    """Plan §6.5: measured gate when KB docs exist; else §6.1 unmeasured."""
    from agent.agentic_measure import has_kb_context, measure_agentic_terminal
    from agent.calibration import resolve_routing_thresholds

    if not has_kb_context(kb_docs):
        return _agentic_unmeasured_gate()

    min_quality = 80
    min_factuality = 80
    min_relevance = 0.8
    try:
        if get_settings is not None:
            thr = resolve_routing_thresholds(get_settings())
            min_quality = int(thr.min_quality)
            min_factuality = int(thr.min_factuality)
            min_relevance = float(thr.min_relevance)
    except Exception:
        pass

    return measure_agentic_terminal(
        answer=answer,
        kb_docs=kb_docs,
        quality_score=quality_score,
        relevance_score=relevance_score,
        quality_source=quality_source,
        min_quality=min_quality,
        min_factuality=min_factuality,
        min_relevance=min_relevance,
    )


def _agentic_judge_candidates(
    generator_llm: Any | None = None,
    *,
    settings: Any | None = None,
) -> tuple[Any | None, Any | None, Any | None]:
    """Resolve (fast, strong, generator) for agentic quality evaluate (§6.6)."""
    fast: Any | None = None
    strong: Any | None = None
    generator = generator_llm
    try:
        if build_provider_runtime is not None:
            runtime_settings = settings
            if runtime_settings is None:
                try:
                    from config.settings import get_settings as _gs

                    runtime_settings = _gs()
                except Exception:
                    runtime_settings = None
            if runtime_settings is not None:
                runtime = build_provider_runtime(runtime_settings)
                fast = getattr(runtime, "fast", None)
                strong = getattr(runtime, "strong", None)
    except Exception:
        fast = None
        strong = None
    if generator is None:
        generator = strong or fast
    if fast is None:
        fast = generator
    if strong is None:
        strong = generator
    return fast, strong, generator


def _agentic_terminal_fields_with_eval(
    *,
    question: str,
    answer: str,
    kb_docs: list[Any] | None = None,
    generator_llm: Any | None = None,
    quality_score: int | None = None,
    relevance_score: float | None = None,
    quality_source: str | None = None,
) -> dict[str, Any]:
    """Plan §6.6: optional LLM evaluate on KB agentic terminals, then §6.5 gate.

    When ``agentic_quality_eval`` is enabled and KB docs exist, run the
    independent-judge self-eval. Measured ``quality_source=llm`` is passed
    into the §6.5 gate so ``route=auto`` can clear floors. Judge failure is
    fail-closed for quality (stays unmeasured) without inventing scores and
    without wiping citation-bound grounding.
    """
    from agent.agentic_evaluate import (
        agentic_quality_eval_enabled,
        evaluate_agentic_answer,
    )
    from agent.agentic_measure import has_kb_context

    # Local import so tests can monkeypatch config.settings.get_settings
    # (same pattern as ConversationSession.ask).
    try:
        from config.settings import get_settings as _get_settings
    except ImportError:
        _get_settings = None  # type: ignore[assignment]

    judge_fields: dict[str, Any] = {}
    q_score = quality_score
    r_score = relevance_score
    q_source = quality_source

    settings = None
    try:
        if _get_settings is not None:
            settings = _get_settings()
    except Exception:
        settings = None

    if (
        has_kb_context(kb_docs)
        and agentic_quality_eval_enabled(settings)
        and q_source not in {"llm", "heuristic"}
    ):
        require_independence = False
        if settings is not None:
            require_independence = bool(
                getattr(settings, "judge_independence_required", False)
            )
        fast, strong, generator = _agentic_judge_candidates(
            generator_llm, settings=settings
        )

        def _invoke(llm: Any, prompt: str) -> str:
            return _invoke_llm(llm, prompt, role="evaluate")

        eval_result = evaluate_agentic_answer(
            question=question,
            answer=answer,
            context_docs=kb_docs,
            candidate_fast=fast,
            candidate_strong=strong,
            generator_llm=generator,
            require_independence=require_independence,
            invoke=_invoke,
        )
        judge_fields = eval_result.as_state_fields()
        measure_kwargs = eval_result.as_measure_kwargs()
        if measure_kwargs:
            q_score = measure_kwargs.get("quality_score")
            r_score = measure_kwargs.get("relevance_score")
            q_source = measure_kwargs.get("quality_source")

    fields = _agentic_terminal_fields(
        answer=answer,
        kb_docs=kb_docs,
        quality_score=q_score,
        relevance_score=r_score,
        quality_source=q_source,
    )
    if judge_fields:
        fields = {**fields, **judge_fields}
    return fields


def _finalize_agentic_terminal(state: GraphState) -> GraphState:
    """Apply §6.2 pre-response safety on agentic terminals before delivery."""
    return cast(GraphState, apply_pre_response_safety(state))


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
                                "enum": ["simple", "complex", "global"],
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
                raw = _invoke_llm(classifier_llm, prompt, role="classify").strip().upper()
            usage = _capture_llm_usage(classifier_llm, "classify_complexity")
            trace_llm_call(
                trace_id=trace_id,
                node_name="classify_complexity",
                prompt=prompt,
                response=raw,
                model=model,
                duration_ms=0.0,
                tool_calls=state.get("tool_calls") or None,
            )
            complexity: Literal["simple", "complex", "global", "unknown"]
            if raw.startswith("SIMPLE"):
                complexity = "simple"
            elif raw.startswith("GLOBAL") or raw.startswith("MULTI_HOP") or raw.startswith("MULTIHOP"):
                complexity = "global"
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
                raw_search_query = _invoke_llm(llm, prompt, role="transform").strip()
                usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "transform_query"))
                usage_recorded = True
                trace_llm_call(
                    trace_id=trace_id,
                    node_name="transform_query",
                    prompt=prompt,
                    response=raw_search_query,
                    model=model,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    tool_calls=state.get("tool_calls") or None,
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
                    hyde_doc = _invoke_llm(llm, hyde_prompt, role="transform").strip()
                    usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "transform_query"))
                    usage_recorded = True
                    trace_llm_call(
                        trace_id=trace_id,
                        node_name="hyde",
                        prompt=hyde_prompt,
                        response=hyde_doc,
                        model=model,
                        duration_ms=(time.monotonic() - t0) * 1000,
                        tool_calls=state.get("tool_calls") or None,
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


_RETRIEVAL_STRATEGIES = {"vector", "hybrid", "graph", "factcard"}


def _normalize_retrieval_strategy(value: object) -> Literal["vector", "hybrid", "graph", "factcard"]:
    raw = str(value or "hybrid").strip().lower()
    if raw in _RETRIEVAL_STRATEGIES:
        return cast(Literal["vector", "hybrid", "graph", "factcard"], raw)
    return "hybrid"


def _select_retrieval_strategy(state: GraphState) -> Literal["vector", "hybrid", "graph", "factcard"]:
    if get_settings is not None:
        settings = get_settings()
        configured = _normalize_retrieval_strategy(
            getattr(settings, "retrieval_strategy", "hybrid")
        )
    else:
        configured = "hybrid"

    complexity = state.get("complexity", "unknown")
    if configured == "vector":
        return "vector"
    # Fact-card lane (Track F) is opt-in via config only: when explicitly
    # selected it serves every query (with an empty->hybrid fallback at dispatch).
    # Per-query routing to factcard is deferred to Phase 3; keep it off the
    # automatic path so default behaviour (hybrid/vector) is unchanged.
    if configured == "factcard":
        return "factcard"
    if complexity == "simple":
        return "vector"
    if configured == "graph" and complexity == "global":
        return "graph"
    return "hybrid"


def make_retrieve_node(retriever: Any) -> Callable[[GraphState], GraphState]:
    """Узел retrieve: ищет документы по search_query (или question как fallback)."""

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        from utils.request_deadline import RequestDeadlineExceeded, check_request_deadline

        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            # Cooperative deadline (plan §3.1g): refuse new retrieve work after wall.
            # Re-raise so ConversationSession.ask maps to route=timeout (not empty docs).
            check_request_deadline("retrieve")
            query = state.get("hyde_query") or state.get("search_query") or state.get("question", "")
            requested_strategy = _select_retrieval_strategy(state)
            effective_strategy = requested_strategy
            tracer = get_otel_tracer()
            with tracer.start_as_current_span("rag.retrieve") as span:
                span.set_attribute("rag.question_length", len(str(state.get("question", "") or "")))
                span.set_attribute("rag.query_length", len(str(query or "")))
                span.set_attribute("rag.tenant_id", str(state.get("tenant_id", "default")))
                span.set_attribute("rag.retrieval_strategy", requested_strategy)
                try:
                    if requested_strategy == "factcard":
                        from vectordb.manager import get_factcard_documents

                        tenant_id = str(state.get("tenant_id", "default"))
                        cards = get_factcard_documents(query, tenant_id=tenant_id)
                        if cards:
                            docs = cards
                        else:
                            # No card matched (or collection missing) — degrade to
                            # the hybrid lane so the request still gets an answer.
                            effective_strategy = "hybrid"
                            docs = retriever.get_relevant_documents(query)
                    elif requested_strategy == "vector" and hasattr(retriever, "get_vector_documents"):
                        docs = retriever.get_vector_documents(query)
                    elif requested_strategy == "graph" and hasattr(retriever, "get_graph_documents"):
                        docs = retriever.get_graph_documents(query)
                    else:
                        if requested_strategy == "graph":
                            effective_strategy = "hybrid"
                        docs = retriever.get_relevant_documents(query)
                except RequestDeadlineExceeded:
                    raise
                except Exception as exc:
                    logger.warning("[retrieve] Retriever error: %s", exc, extra={"trace_id": trace_id})
                    docs = []
                span.set_attribute("rag.num_docs", len(docs))
                span.set_attribute("rag.retrieval_strategy_effective", effective_strategy)
            plain_docs = _docs_to_plain_dicts(docs)
            new_state: GraphState = {
                **state,
                "context_docs": plain_docs,
                "retrieval_strategy": effective_strategy,
            }
            log_step(trace_id, "retrieve", new_state)
            return new_state
        except RequestDeadlineExceeded:
            raise
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

    Plan §5.3 fail-closed:
    - grader error → document rejected (not silently accepted);
    - no forced top-1 re-injection after rejection;
    - all_rejected / grader_error mark knowledge_gap + not_verified.
    """

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            from agent.doc_grade import finalize_grade_state

            question = state.get("question", "")
            context_docs = state.get("context_docs", []) or []
            model = _get_llm_model_name(llm) or ""

            if not context_docs:
                new_state = finalize_grade_state(
                    state,
                    graded=[],
                    context_docs=[],
                    filtered_count=0,
                    grader_errors=0,
                )
                log_step(trace_id, "grade_docs", new_state)
                return new_state  # type: ignore[return-value]

            graded: list[dict[str, Any]] = []
            filtered_count = 0
            grader_errors = 0
            usage = _new_llm_usage("grade_docs")
            usage_recorded = False
            tracer = get_otel_tracer()
            with tracer.start_as_current_span("rag.rerank") as span:
                span.set_attribute("rag.tenant_id", str(state.get("tenant_id", "default")))
                span.set_attribute("rag.input_docs", len(context_docs))
                batch_grades: list[tuple[bool, str]] | None = None
                if len(context_docs) > 1:
                    batch_prompt = build_doc_grade_batch_prompt(question=question, documents=context_docs)
                    try:
                        t0 = time.monotonic()
                        raw_verdict = ""
                        if _llm_supports_structured_output(llm):
                            try:
                                structured = _invoke_with_schema(
                                    llm,
                                    batch_prompt,
                                    {
                                        "type": "object",
                                        "properties": {
                                            "grades": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "index": {"type": "integer"},
                                                        "relevant": {"type": "boolean"},
                                                        "reason": {"type": "string"},
                                                    },
                                                    "required": ["index", "relevant"],
                                                    "additionalProperties": True,
                                                },
                                            }
                                        },
                                        "required": ["grades"],
                                        "additionalProperties": True,
                                    },
                                )
                            except Exception:
                                structured = None
                            if structured is not None:
                                raw_verdict = str(structured)
                                batch_grades = _coerce_doc_grade_batch(structured, len(context_docs))
                        if batch_grades is None:
                            raw_verdict = _invoke_llm(
                                llm, batch_prompt, role="grade"
                            ).strip()
                            batch_grades = _parse_doc_grade_batch_text(raw_verdict, len(context_docs))
                        usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "grade_docs"))
                        usage_recorded = True
                        trace_llm_call(
                            trace_id=trace_id,
                            node_name="grade_docs",
                            prompt=batch_prompt,
                            response=raw_verdict,
                            model=model,
                            duration_ms=(time.monotonic() - t0) * 1000,
                            tool_calls=state.get("tool_calls") or None,
                        )
                    except Exception as exc:
                        logger.warning("[grade_docs] Batch LLM error: %s", exc, extra={"trace_id": trace_id})
                        batch_grades = None

                if batch_grades is not None:
                    # strict=False: LLM batch-grade count can drift from doc count;
                    # tolerate by truncating to the shorter (existing behavior).
                    for doc, (is_relevant, _reason) in zip(context_docs, batch_grades, strict=False):
                        if is_relevant:
                            graded.append(doc)
                        else:
                            filtered_count += 1
                else:
                    for doc in context_docs:
                        prompt = build_doc_grade_prompt(question=question, document=doc)
                        try:
                            t0 = time.monotonic()
                            if _llm_supports_structured_output(llm):
                                try:
                                    structured = _invoke_with_schema(
                                        llm,
                                        prompt,
                                        {
                                            "type": "object",
                                            "properties": {
                                                "relevant": {"type": "boolean"},
                                                "reason": {"type": "string"},
                                            },
                                            "required": ["relevant"],
                                            "additionalProperties": True,
                                        },
                                    )
                                except Exception:
                                    structured = None
                                if isinstance(structured, dict) and isinstance(structured.get("relevant"), bool):
                                    is_relevant = bool(structured["relevant"])
                                    raw_verdict = str(structured.get("reason") or "")
                                else:
                                    raw_verdict = _invoke_llm(
                                        llm, prompt, role="grade"
                                    ).strip()
                                    is_relevant = raw_verdict.upper().startswith("YES")
                            else:
                                raw_verdict = _invoke_llm(
                                    llm, prompt, role="grade"
                                ).strip()
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
                                tool_calls=state.get("tool_calls") or None,
                            )
                        except Exception as exc:
                            logger.warning("[grade_docs] LLM error: %s", exc, extra={"trace_id": trace_id})
                            # Plan §5.3: fail-closed — do not accept on grader error.
                            is_relevant = False
                            grader_errors += 1
                        if is_relevant:
                            graded.append(doc)
                        else:
                            filtered_count += 1
                # Plan §5.3: do NOT force re-insert top-ranked doc after rejection.
                span.set_attribute("rag.filtered_docs", filtered_count)
                span.set_attribute("rag.output_docs", len(graded))
                span.set_attribute("rag.grader_errors", grader_errors)

            new_state = finalize_grade_state(
                state,
                graded=graded,
                context_docs=context_docs,
                filtered_count=filtered_count,
                grader_errors=grader_errors,
            )
            if usage_recorded:
                new_state = _apply_llm_usage(new_state, usage)  # type: ignore[arg-type]
            log_step(trace_id, "grade_docs", new_state)
            return new_state  # type: ignore[return-value]
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
            from agent.doc_grade import resolve_generation_context_docs

            question = state.get("question", "")
            # Plan §5.3: after grade_docs, empty graded_docs must not fall back
            # to raw context_docs (silent restore of rejected / failed grade).
            docs = resolve_generation_context_docs(state)
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
                    # Plan §4.8: when provider_token_stream_enabled, stream tokens
                    # via LangGraph custom writer (single generation, no second path).
                    answer = _generate_answer_text(llm, prompt, role="generate")
                    usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "generate"))
                    usage_recorded = True
                    trace_llm_call(
                        trace_id=trace_id,
                        node_name="generate",
                        prompt=prompt,
                        response=answer,
                        model=model,
                        duration_ms=(time.monotonic() - t0) * 1000,
                        tool_calls=state.get("tool_calls") or None,
                    )
                except Exception as exc:
                    logger.warning("[generate] LLM error: %s", exc, extra={"trace_id": trace_id})
                    answer = "Извините, при обработке запроса произошла внутренняя ошибка."
                span.set_attribute("rag.answer_length", len(str(answer or "")))

            citations: list[dict[str, Any]] = []
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
            if complexity == "simple":
                # Plan §5.1: simple path skips verify_facts — not a free 100.
                from agent.grounding import status_for_skip

                g_status, g_score, g_skipped = status_for_skip(reason="simple_complexity")
                new_state["claims"] = []
                new_state["fact_verification_skipped"] = g_skipped
                new_state["factuality_score"] = g_score
                new_state["grounding_status"] = g_status
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
            from agent.grounding import (
                apply_citation_bound_claims,
                status_for_claims,
                status_for_empty_claim_parse,
                status_for_no_claims_none,
                status_for_short_answer,
                status_for_skip,
                status_for_truncated_coverage,
            )
            from config.settings import get_settings

            settings = get_settings()
            if not getattr(settings, "fact_verification_enabled", True):
                g_status, g_score, g_skipped = status_for_skip(reason="disabled")
                new_state: GraphState = {
                    **state,
                    "claims": [],
                    "fact_verification_skipped": g_skipped,
                    "factuality_score": g_score,
                    "grounding_status": g_status,
                }
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            from agent.doc_grade import resolve_generation_context_docs

            answer = state.get("answer", "")
            # Same doc selection as generate (§5.3) — no silent restore after grade.
            docs = resolve_generation_context_docs(state)
            # Verification evidence must cover the same context the answer was
            # generated from: with parent-expansion ON chunks reach
            # parent_expansion_max_chars (3600), so a tighter cap here would
            # mark facts from chunk tails as unsupported.
            max_docs = int(getattr(settings, "fact_verify_context_max_docs", 5))
            chars_per_doc = int(getattr(settings, "fact_verify_context_chars_per_doc", 3600))
            context_text = "\n\n".join(
                str(
                    d.get("page_content") if isinstance(d, dict) else getattr(d, "page_content", "")
                )[:chars_per_doc]
                for d in docs[:max_docs]
            )

            if not answer or not context_text:
                g_status, g_score, g_skipped = status_for_skip(reason="no_answer_or_context")
                new_state = {
                    **state,
                    "claims": [],
                    "fact_verification_skipped": g_skipped,
                    "factuality_score": g_score,
                    "grounding_status": g_status,
                }
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            if len(re.findall(r"\w+", answer)) < 3:
                g_status, g_score, g_skipped = status_for_short_answer()
                new_state = {
                    **state,
                    "claims": [],
                    "fact_verification_skipped": g_skipped,
                    "factuality_score": g_score,
                    "grounding_status": g_status,
                }
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            usage = _new_llm_usage("verify_facts")
            usage_recorded = False
            model = _get_llm_model_name(llm) or ""
            extract_prompt = build_extract_claims_prompt(answer)
            t0 = time.monotonic()
            raw_claims = _invoke_llm(llm, extract_prompt, role="verify").strip()
            usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "verify_facts"))
            usage_recorded = True
            trace_llm_call(
                trace_id=trace_id,
                node_name="verify_facts.extract_claims",
                prompt=extract_prompt,
                response=raw_claims,
                model=model,
                duration_ms=(time.monotonic() - t0) * 1000,
                tool_calls=state.get("tool_calls") or None,
            )
            if raw_claims.upper().startswith("NONE"):
                g_status, g_score, g_skipped = status_for_no_claims_none()
                new_state = {
                    **state,
                    "claims": [],
                    "fact_verification_skipped": g_skipped,
                    "factuality_score": g_score,
                    "grounding_status": g_status,
                }
                new_state = _apply_llm_usage(new_state, usage)
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            all_claim_lines = [
                line.lstrip("- ").strip()
                for line in raw_claims.splitlines()
                if line.strip().startswith("-")
            ]
            max_claims = 10
            claim_lines = all_claim_lines[:max_claims]
            if not claim_lines:
                g_status, g_score, g_skipped = status_for_empty_claim_parse()
                new_state = {
                    **state,
                    "claims": [],
                    "fact_verification_skipped": g_skipped,
                    "factuality_score": g_score,
                    "grounding_status": g_status,
                }
                if usage_recorded:
                    new_state = _apply_llm_usage(new_state, usage)
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            consensus_enabled = bool(
                getattr(settings, "fact_verify_consensus_enabled", False)
            )
            reliability_level = str(
                getattr(settings, "fact_verify_reliability_level", "standard") or "standard"
            ).strip() or "standard"

            claims_result: list[dict] = []
            for claim in claim_lines:
                verify_prompt = build_verify_claim_prompt(claim, context_text)
                if consensus_enabled and _llm_supports_structured_output(llm):
                    t0 = time.monotonic()
                    structured = _invoke_with_schema(
                        llm,
                        verify_prompt,
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
                        trace_llm_call(
                            trace_id=trace_id,
                            node_name="verify_facts.verify_claim",
                            prompt=verify_prompt,
                            response=str(structured),
                            model=model,
                            duration_ms=(time.monotonic() - t0) * 1000,
                            tool_calls=state.get("tool_calls") or None,
                        )
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
                t0 = time.monotonic()
                verdict = _invoke_llm(llm, verify_prompt, role="verify").strip()
                usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "verify_facts"))
                trace_llm_call(
                    trace_id=trace_id,
                    node_name="verify_facts.verify_claim",
                    prompt=verify_prompt,
                    response=verdict,
                    model=model,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    tool_calls=state.get("tool_calls") or None,
                )
                supported = verdict.upper().startswith("SUPPORTED")
                evidence = ""
                if supported and ":" in verdict:
                    evidence = verdict.split(":", 1)[1].strip()[:200]
                claims_result.append(
                    {"text": claim, "supported": supported, "evidence": evidence}
                )

            # Plan §5.2: bind claims to answer [N] citations (cited docs only).
            claims_result, citation_override = apply_citation_bound_claims(
                answer=str(answer or ""),
                claims=claims_result,
                docs=docs,
            )
            g_status, factuality, g_skipped = status_for_claims(
                claims_result,
                require_citation_bound=True,
            )
            if citation_override is not None:
                # Missing/invalid citations: never treat as verified auto path.
                g_status = citation_override
                if citation_override == "not_verified" and factuality > 0:
                    # Keep partial observability score only when some binds existed;
                    # pure missing citations → zero effective factuality for auto.
                    if not any(bool(c.get("citation_bound")) for c in claims_result):
                        factuality = 0
            # Claim budget truncation: unverified remainder → whole answer not_verified.
            truncated = status_for_truncated_coverage(
                extracted_claim_count=len(all_claim_lines),
                verified_claim_count=len(claims_result),
                max_claims=max_claims,
            )
            if truncated is not None:
                g_status = truncated
                # Keep measured fraction for observability, but status blocks auto.
                if not claims_result:
                    factuality = 0

            new_state = {
                **state,
                "claims": claims_result,
                "fact_verification_skipped": g_skipped,
                "factuality_score": factuality,
                "grounding_status": g_status,
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
    """Узел evaluate: quality judge (1-100), plan §6.3 independence policy.

    Selects judge via ``resolve_judge_llm`` (must differ from generator when
    ``judge_independence_required``). Judge error / parse failure / missing
    independent judge → fail-closed unmeasured scores (never silent default 50
    with ``quality_source=llm``).
    """

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        complexity = state.get("complexity", "unknown")
        # Same selection rule as generate: simple→fast, else→strong.
        generator_llm = llm_fast if complexity == "simple" else llm_strong
        require_independence = False
        if get_settings is not None:
            try:
                require_independence = bool(
                    getattr(get_settings(), "judge_independence_required", False)
                )
            except Exception:
                require_independence = False
        resolution = resolve_judge_llm(
            candidate_fast=llm_fast,
            candidate_strong=llm_strong,
            generator_llm=generator_llm,
            require_independence=require_independence,
        )
        model = resolution.judge_model or ""
        provider = resolution.judge_provider or ""
        evaluate_started_at = time.monotonic()
        logger.info(
            "[evaluate] boundary=start monotonic=%.6f provider=%s model=%s "
            "independent=%s require=%s",
            evaluate_started_at,
            provider or "-",
            model or "-",
            resolution.independent,
            require_independence,
            extra={"trace_id": trace_id},
        )
        try:
            if not resolution.ok or resolution.judge_llm is None:
                new_state = cast(
                    GraphState,
                    {
                        **state,
                        **judge_fail_closed_fields(
                            reason=resolution.reason,
                            status="unavailable",
                        ),
                        "judge_independent": False,
                    },
                )
                new_state["knowledge_gap"] = _is_knowledge_gap(new_state)
                log_step(trace_id, "evaluate", new_state)
                return new_state

            llm = resolution.judge_llm
            model = _get_llm_model_name(llm) or model
            provider = _get_llm_provider_name(llm) or provider
            question = state.get("question", "")
            answer = state.get("answer") or ""
            docs = state.get("graded_docs") or state.get("context_docs", []) or []
            answer_for_eval = re.sub(r"\s*\[\d+\]", "", answer)
            answer_for_eval = re.sub(r"\s{2,}", " ", answer_for_eval).strip()
            prompt = build_self_eval_prompt(
                question=question, answer=answer_for_eval, context_docs=docs
            )
            usage = _new_llm_usage("evaluate")
            usage_recorded = False
            raw = ""
            judge_call_error: str | None = None
            tracer = get_otel_tracer()
            with tracer.start_as_current_span("rag.evaluate") as span:
                span.set_attribute("rag.tenant_id", str(state.get("tenant_id", "default")))
                span.set_attribute("rag.judge_independent", bool(resolution.independent))
                try:
                    t0 = time.monotonic()
                    raw = _invoke_llm(llm, prompt, role="evaluate")
                    usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "evaluate"))
                    usage_recorded = True
                    trace_llm_call(
                        trace_id=trace_id,
                        node_name="evaluate",
                        prompt=prompt,
                        response=raw,
                        model=model,
                        duration_ms=(time.monotonic() - t0) * 1000,
                        tool_calls=state.get("tool_calls") or None,
                    )
                except Exception as exc:
                    logger.warning(
                        "[evaluate] judge LLM error: %s", exc, extra={"trace_id": trace_id}
                    )
                    judge_call_error = str(exc) or type(exc).__name__
                    raw = ""

                if judge_call_error is not None:
                    new_state = cast(
                        GraphState,
                        {
                            **state,
                            **judge_fail_closed_fields(
                                reason=f"judge_error:{judge_call_error[:120]}",
                                status="error",
                            ),
                            "judge_independent": bool(resolution.independent),
                        },
                    )
                    if usage_recorded:
                        new_state = _apply_llm_usage(new_state, usage)
                    new_state["knowledge_gap"] = _is_knowledge_gap(new_state)
                    span.set_attribute("rag.quality_score", 0)
                    log_step(trace_id, "evaluate", new_state)
                    return new_state

                score = parse_judge_score(raw)
                if score is None:
                    new_state = cast(
                        GraphState,
                        {
                            **state,
                            **judge_fail_closed_fields(
                                reason="judge_parse_failure",
                                status="parse_failure",
                            ),
                            "judge_independent": bool(resolution.independent),
                        },
                    )
                    if usage_recorded:
                        new_state = _apply_llm_usage(new_state, usage)
                    new_state["knowledge_gap"] = _is_knowledge_gap(new_state)
                    span.set_attribute("rag.quality_score", 0)
                    log_step(trace_id, "evaluate", new_state)
                    return new_state

                span.set_attribute("rag.quality_score", score)
            # Plan §5.4: relevance is retrieval coverage — never quality/100.
            from agent.relevance import measure_retrieval_relevance

            rel_score, rel_source = measure_retrieval_relevance(
                context_docs=state.get("context_docs"),
                graded_docs=state.get("graded_docs"),
            )
            new_state = cast(
                GraphState,
                {
                    **state,
                    "quality_score": score,
                    "relevance_score": rel_score,
                    "relevance_source": rel_source,
                    "quality_source": "llm",
                    "judge_status": "ok",
                    "judge_reason": resolution.reason,
                    "judge_independent": bool(resolution.independent),
                },
            )
            if usage_recorded:
                new_state = _apply_llm_usage(new_state, usage)
            new_state["knowledge_gap"] = _is_knowledge_gap(new_state)
            log_step(trace_id, "evaluate", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "evaluate", exc)
        finally:
            evaluate_finished_at = time.monotonic()
            logger.info(
                "[evaluate] boundary=end monotonic=%.6f elapsed=%.6fs "
                "provider=%s model=%s",
                evaluate_finished_at,
                evaluate_finished_at - evaluate_started_at,
                provider or "-",
                model or "-",
                extra={"trace_id": trace_id},
            )

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
        if get_settings is not None:
            settings = get_settings()
            if not getattr(settings, "suggested_questions_enabled", True):
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
            raw = _invoke_llm(llm, prompt, role="suggest")
            usage = _capture_llm_usage(llm, "suggest_questions")
            trace_llm_call(
                trace_id=trace_id,
                node_name="suggest_questions",
                prompt=prompt,
                response=raw,
                model=model,
                duration_ms=(time.monotonic() - t0) * 1000,
                tool_calls=state.get("tool_calls") or None,
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
            fallback_state: GraphState = {**state, "suggested_questions": []}
            log_step(trace_id, "suggest_questions", fallback_state)
            return fallback_state

    return node


# ---------------------------------------------------------------------------
# Level 2: Route or Retry (Self-RAG loop)
# ---------------------------------------------------------------------------


def make_route_or_retry_node(
    min_quality: int = 80,
    min_relevance: float = 0.8,
    min_factuality: int | None = None,
) -> Callable[[GraphState], GraphState]:
    """Узел route_or_retry: финал / retry / human (plan §5.1 fail-closed).

    Логика:
    - auto только при quality+relevance **и** grounding_allows_auto
      (context, knowledge_gap=false, grounding_status=verified, factuality);
    - иначе retry при оставшихся итерациях, иначе human;
    - scores None → human (не auto).

    Floors prefer plan §6.4 calibration artifact via resolve_routing_thresholds
    when explicit min_factuality is omitted.
    """

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            from agent.calibration import resolve_routing_thresholds
            from agent.grounding import (
                DEFAULT_MIN_FACTUALITY_FOR_AUTO,
                grounding_allows_auto,
            )
            from config.settings import get_settings

            q = state.get("quality_score")
            r = state.get("relevance_score")
            iteration = state.get("iteration", 0)
            max_iter = state.get("max_iterations", 2)

            if min_factuality is not None:
                min_fact = int(min_factuality)
            else:
                try:
                    thresholds = resolve_routing_thresholds(get_settings())
                    min_fact = int(thresholds.min_factuality)
                except Exception:
                    min_fact = DEFAULT_MIN_FACTUALITY_FOR_AUTO

            scores_ok = (
                q is not None
                and r is not None
                and q >= min_quality
                and r >= min_relevance
            )
            grounded = grounding_allows_auto(state, min_factuality=min_fact)
            # Plan §6.3: judge infrastructure failure is not Self-RAG material —
            # do not retry hoping for measured auto without a working judge.
            judge_broken = state.get("judge_status") in {
                "unavailable",
                "error",
                "parse_failure",
            }

            route: Literal["auto", "human", "retry"]
            if judge_broken:
                route = "human"
            elif q is None or r is None:
                route = "human"
            elif scores_ok and grounded:
                route = "auto"
            elif iteration < max_iter:
                # Simple path skips verify forever — retry cannot make it verified.
                if (
                    state.get("complexity") == "simple"
                    and state.get("fact_verification_skipped")
                ):
                    route = "human"
                else:
                    # Retry for weak scores, all_rejected grade, incomplete grounding.
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
                raw_new_query = _invoke_llm(llm, prompt, role="rewrite").strip()
                usage = _merge_llm_usage(usage, _capture_llm_usage(llm, "rewrite_query"))
                usage_recorded = True
                trace_llm_call(
                    trace_id=trace_id,
                    node_name="rewrite_query",
                    prompt=prompt,
                    response=raw_new_query,
                    model=model,
                    duration_ms=(time.monotonic() - t0) * 1000,
                    tool_calls=state.get("tool_calls") or None,
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


def make_response_safety_node() -> Callable[[GraphState], GraphState]:
    """Pre-response PII + document prompt-injection gate (plan §6.2)."""

    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown-trace-id")
        try:
            new_state = cast(GraphState, apply_pre_response_safety(state))
            log_step(trace_id, "response_safety", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "response_safety", exc)

    return node


# ---------------------------------------------------------------------------
# Conditional routing function
# ---------------------------------------------------------------------------


def _should_retry(state: GraphState) -> str:
    """Conditional edge: определяет, куда идти после route_or_retry.

    Returns:
        "error"  → handle_error → END  (необработанное исключение)
        "retry"  → rewrite_query → retrieve → ...  (Self-RAG loop)
        "safety" → response_safety → suggest|log  (terminal; plan §6.2)
    """
    route = state.get("route", "human")
    if state.get("error") or route == "error":
        return "error"
    if route == "retry":
        return "retry"
    return "safety"


def _after_response_safety(state: GraphState) -> str:
    """After safety: only clean auto may get suggested questions."""
    if state.get("route") == "auto":
        return "suggest"
    return "end"


def _route_after_retrieve(state: GraphState) -> str:
    if state.get("error"):
        return "error"
    if state.get("complexity") == "simple":
        return "generate"
    return "grade"


def _route_after_generate(state: GraphState) -> str:
    if state.get("error"):
        return "error"
    if state.get("complexity") == "simple":
        return "evaluate"
    return "verify"


# ---------------------------------------------------------------------------
# Сборка графа (Level 2: Corrective & Self-RAG)
# ---------------------------------------------------------------------------


# Compiled-graph cache (F-4): run_qa_pipeline used to rebuild and recompile the
# StateGraph on every request. Cached only for the provider-runtime path, where
# the runtime cache pins fast/strong instances: the cache value holds strong
# references to retriever/llm objects, so the id()-based key cannot be reused
# by a new object while its entry is alive (CPython ids are addresses).
# Compiled LangGraph graphs carry no per-invoke state — state goes into
# invoke() — so sharing one graph across to_thread workers is safe.
_GRAPH_CACHE: OrderedDict[tuple[int, int, int, int, int], tuple[Any, tuple[Any, ...]]] = (
    OrderedDict()
)
_GRAPH_CACHE_LOCK = threading.Lock()
_GRAPH_CACHE_MAX = 16


def clear_support_graph_cache() -> None:
    with _GRAPH_CACHE_LOCK:
        _GRAPH_CACHE.clear()


def build_support_graph(
    retriever: Any,
    llm: SupportsInvoke | None = None,
    min_quality: int | None = None,
    max_iterations: int = 2,
) -> Any:
    """Собирает и компилирует граф LangGraph Level 2.

    Граф:
        classify_complexity → transform_query → retrieve → grade_docs? → generate
            → verify_facts → evaluate → route_or_retry
                ├─ (retry) → rewrite_query → retrieve → ...
                └─ (end)   → log → END
    """
    from agent.calibration import resolve_routing_thresholds
    from config.settings import get_settings

    settings = get_settings()
    # Plan §6.4: floors from versioned calibration artifact when present.
    try:
        routing_thresholds = resolve_routing_thresholds(settings)
    except Exception:
        routing_thresholds = None
    if min_quality is None:
        if routing_thresholds is not None:
            min_quality = int(routing_thresholds.min_quality)
        else:
            min_quality = getattr(settings, "quality_threshold", 80)

    llm_fast: SupportsInvoke
    llm_strong: SupportsInvoke
    graph_cache_key: tuple[int, int, int, int, int] | None = None
    if llm is None:
        if build_provider_runtime is not None:
            runtime = build_provider_runtime(settings)
            llm_fast = runtime.fast
            llm_strong = runtime.strong
            graph_cache_key = (
                id(retriever),
                id(llm_fast),
                id(llm_strong),
                int(min_quality),
                int(max_iterations),
            )
            with _GRAPH_CACHE_LOCK:
                cached = _GRAPH_CACHE.get(graph_cache_key)
                if cached is not None:
                    _GRAPH_CACHE.move_to_end(graph_cache_key)
                    return cached[0]
        else:
            # Per-call LocalOllamaLLM instances have no stable identity — do
            # not cache a graph keyed on their ids.
            llm_strong = LocalOllamaLLM(model_name=settings.ollama_model_name)
            if getattr(settings, "model_routing_enabled", False):
                llm_fast = LocalOllamaLLM(model_name=settings.ollama_fast_model_name)
            else:
                llm_fast = llm_strong
    else:
        llm_fast = llm
        llm_strong = llm

    workflow: Any = StateGraph(GraphState)

    # Регистрируем узлы
    workflow.add_node("classify_complexity", make_classify_complexity_node(llm_fast))
    workflow.add_node("transform_query", make_transform_query_node(llm_fast))
    workflow.add_node("retrieve", make_retrieve_node(retriever))
    workflow.add_node("grade_docs", make_grade_docs_node(llm_fast))
    workflow.add_node("generate", make_generate_node(llm_fast, llm_strong))
    workflow.add_node("verify_facts", make_verify_facts_node(llm_fast))
    # evaluate receives both LLMs: plan §6.3 resolves an independent judge
    # (prefer fast when generator is strong — keeps complex-path latency low;
    # when independence is required and generator is fast, uses strong).
    # suggest_questions is cosmetic follow-up text — fast is enough there too.
    workflow.add_node("evaluate", make_evaluate_node(llm_fast, llm_strong))
    route_min_relevance = (
        float(routing_thresholds.min_relevance)
        if routing_thresholds is not None
        else float(getattr(settings, "min_relevance_for_auto", 0.8) or 0.8)
    )
    route_min_factuality = (
        int(routing_thresholds.min_factuality)
        if routing_thresholds is not None
        else int(getattr(settings, "min_factuality_for_auto", 80) or 80)
    )
    workflow.add_node(
        "route_or_retry",
        make_route_or_retry_node(
            min_quality=min_quality,
            min_relevance=route_min_relevance,
            min_factuality=route_min_factuality,
        ),
    )
    workflow.add_node("response_safety", make_response_safety_node())
    workflow.add_node("suggest_questions", make_suggest_questions_node(llm_fast))
    workflow.add_node("rewrite_query", make_rewrite_query_node(llm_strong))
    workflow.add_node("log", make_log_node())
    workflow.add_node("handle_error", make_handle_error_node())

    # Основной путь
    workflow.set_entry_point("classify_complexity")
    workflow.add_edge("classify_complexity", "transform_query")
    workflow.add_edge("transform_query", "retrieve")
    workflow.add_conditional_edges(
        "retrieve",
        _route_after_retrieve,
        {
            "error": "handle_error",
            "grade": "grade_docs",
            "generate": "generate",
        },
    )
    workflow.add_edge("grade_docs", "generate")
    workflow.add_conditional_edges(
        "generate",
        _route_after_generate,
        {
            "error": "handle_error",
            "verify": "verify_facts",
            "evaluate": "evaluate",
        },
    )
    workflow.add_edge("verify_facts", "evaluate")
    workflow.add_edge("evaluate", "route_or_retry")

    # Conditional: retry or terminal safety (plan §6.2) then suggest/log
    workflow.add_conditional_edges(
        "route_or_retry",
        _should_retry,
        {
            "error": "handle_error",
            "retry": "rewrite_query",
            "safety": "response_safety",
        },
    )
    workflow.add_conditional_edges(
        "response_safety",
        _after_response_safety,
        {
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

    compiled = workflow.compile()
    if graph_cache_key is not None:
        with _GRAPH_CACHE_LOCK:
            # refs pin retriever/llm ids for the lifetime of the entry (see
            # cache comment above); LRU cap bounds stale entries after a
            # provider-runtime invalidation.
            _GRAPH_CACHE[graph_cache_key] = (compiled, (retriever, llm_fast, llm_strong))
            _GRAPH_CACHE.move_to_end(graph_cache_key)
            while len(_GRAPH_CACHE) > _GRAPH_CACHE_MAX:
                _GRAPH_CACHE.popitem(last=False)
    return compiled


# ---------------------------------------------------------------------------
# Высокоуровневая функция запуска (обратная совместимость)
# ---------------------------------------------------------------------------


def _start_trace_for_request(
    external_request_id: str | None,
    tenant_id: str = "default",
) -> str:
    """Create a fresh internal trace, storing the caller's request id as correlation.

    Higher-level APIs still name the inbound value ``trace_id`` (e.g. X-Request-Id
    from /api/ask). That value is an *external correlation*, not the SQLite PK.
    Canonical ``start_trace`` receives it via ``correlation_id`` when supported.

    Signature inspection preserves narrow monkeypatched / older callables that
    accept only ``trace_id``, positional input, or no arguments. Call shape is
    chosen from ``inspect.Parameter.kind`` before invocation so positional-only
    parameters are never passed as keywords, and real TypeErrors from inside
    the callable are not swallowed.
    """
    start_trace_params = inspect.signature(start_trace).parameters
    has_var_kwargs = any(
        param.kind == inspect.Parameter.VAR_KEYWORD
        for param in start_trace_params.values()
    )

    def _accepts_keyword(name: str) -> bool:
        param = start_trace_params.get(name)
        return param is not None and param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )

    def _is_positional_only(name: str) -> bool:
        param = start_trace_params.get(name)
        return param is not None and param.kind == inspect.Parameter.POSITIONAL_ONLY

    args: list[Any] = []
    kwargs: dict[str, Any] = {}

    if _accepts_keyword("tenant_id") or has_var_kwargs:
        kwargs["tenant_id"] = tenant_id

    if _accepts_keyword("correlation_id"):
        kwargs["correlation_id"] = external_request_id
    elif _is_positional_only("correlation_id"):
        args.append(external_request_id)
    elif has_var_kwargs and not _accepts_keyword("trace_id") and not _is_positional_only(
        "trace_id"
    ):
        kwargs["correlation_id"] = external_request_id
    elif _accepts_keyword("trace_id") or (
        has_var_kwargs and not _is_positional_only("trace_id")
    ):
        # Legacy alias: external value travels as trace_id= for older stubs.
        kwargs["trace_id"] = external_request_id
    elif _is_positional_only("trace_id"):
        args.append(external_request_id)
    elif args or kwargs:
        pass
    elif external_request_id is not None:
        return start_trace(external_request_id)
    else:
        return start_trace()

    return start_trace(*args, **kwargs)


def _prepare_qa_pipeline(
    question: str,
    retriever: Any,
    llm: SupportsInvoke | None = None,
    max_iterations: int = 2,
    chat_history: list[dict[str, str]] | None = None,
    trace_id: str | None = None,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    session_id: str | None = None,
) -> tuple[Any, GraphState, Any, str, Any]:
    """Shared setup for invoke and event-stream QA paths.

    Returns ``(graph, initial_state, settings, internal_trace_id, experiment_token)``.
    """
    # Inbound ``trace_id`` is external correlation; internal UUID comes back.
    internal_trace_id = _start_trace_for_request(trace_id, tenant_id=tenant_id)
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
        trace_id=internal_trace_id,
        tenant_id=tenant_id,
    )
    initial_state["max_iterations"] = max_iterations
    if chat_history:
        initial_state["chat_history"] = chat_history

    graph = build_support_graph(
        retriever=retriever,
        llm=llm,
        min_quality=getattr(settings, "quality_threshold", 80) if settings else 80,
        max_iterations=max_iterations,
    )
    return graph, initial_state, settings, internal_trace_id, experiment_token


def run_qa_pipeline(
    question: str,
    retriever: Any,
    llm: SupportsInvoke | None = None,
    max_iterations: int = 2,
    chat_history: list[dict[str, str]] | None = None,
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
        trace_id: external request correlation (e.g. X-Request-Id); not the
            internal SQLite primary key.
    """
    graph, initial_state, settings, trace_id, experiment_token = _prepare_qa_pipeline(
        question=question,
        retriever=retriever,
        llm=llm,
        max_iterations=max_iterations,
        chat_history=chat_history,
        trace_id=trace_id,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
    )
    try:
        final_state = graph.invoke(initial_state)
        finish_trace(trace_id, final_state)
        if (
            getattr(settings, "online_evaluators_enabled", False)
            and run_online_evaluators is not None
            and persist_online_evaluations is not None
        ):
            timeout_sec = float(getattr(settings, "online_evaluators_timeout_sec", 1.0))
            trace_state = dict(final_state)
            trace_state["trace_id"] = trace_id

            async def _persist_results(dispose_engine: bool) -> None:
                # Bug 4 fix: trace_id stub upsert is performed inside
                # persist_online_evaluations within the same engine.begin()
                # transaction as the trace_evaluations INSERTs, so the FK
                # constraint always holds. Doing a second engine.begin()
                # here would race with that one on the asyncpg pool
                # ("InterfaceError: another operation is in progress").
                try:
                    results = await asyncio.wait_for(
                        asyncio.to_thread(run_online_evaluators, trace_state),
                        timeout=timeout_sec,
                    )
                    persisted = persist_online_evaluations(trace_id, results)
                    if inspect.isawaitable(persisted):
                        await persisted
                finally:
                    # Bug 2 fix: the sync-script path wraps this in asyncio.run(),
                    # which creates a fresh event loop each call. The async
                    # engine pool caches asyncpg connections bound to the
                    # previous loop -> "InterfaceError: another operation in
                    # progress" on the next case. Dispose the pool here so the
                    # next asyncio.run() gets fresh connections. When we instead
                    # bridge onto the application's main loop (F-5), the pool
                    # lives there across requests and must NOT be disposed.
                    if dispose_engine:
                        try:
                            from db.engine import engine as _engine
                            await _engine.dispose()
                        except Exception:
                            logger.debug(
                                "engine.dispose() after online-eval persist failed",
                                exc_info=True,
                            )

            # F-5: when the API process registered its loop at startup, bridge
            # this synchronous pipeline back onto the loop that owns the asyncpg
            # pool via run_coroutine_threadsafe instead of an asyncio.run() +
            # full engine.dispose() per request. Sync CLI scripts register no
            # loop and keep the legacy path. F-18: the timeout is configurable
            # and dropped runs are counted by reason.
            from monitoring.prometheus import record_online_evaluators_dropped
            from utils.event_loop import get_main_loop

            try:
                running_loop = asyncio.get_running_loop()
            except RuntimeError:
                running_loop = None
            main_loop = get_main_loop()

            try:
                if main_loop is not None and main_loop is not running_loop:
                    fut = asyncio.run_coroutine_threadsafe(
                        _persist_results(False), main_loop
                    )
                    fut.result(timeout=timeout_sec + 10)
                else:
                    asyncio.run(_persist_results(True))
            except TimeoutError:
                record_online_evaluators_dropped("timeout")
                if _online_eval_first_time("timeout"):
                    logger.warning(
                        "Online evaluators timed out after %.1fs "
                        "(further timeouts this process will log at DEBUG)",
                        timeout_sec,
                        extra={"trace_id": trace_id},
                    )
                else:
                    logger.debug(
                        "Online evaluators timed out after %.1fs",
                        timeout_sec,
                        extra={"trace_id": trace_id},
                    )
            except Exception as exc:
                record_online_evaluators_dropped("error")
                signature = f"{type(exc).__name__}:{str(exc)[:200]}"
                if _online_eval_first_time(signature):
                    logger.warning(
                        "Online evaluators failed: %s "
                        "(repeats of this error this process will log at DEBUG; "
                        "if running standalone without Postgres this is expected)",
                        exc,
                        extra={"trace_id": trace_id},
                    )
                else:
                    logger.debug(
                        "Online evaluators failed: %s",
                        exc,
                        extra={"trace_id": trace_id},
                    )
        return final_state
    finally:
        if experiment_token is not None and reset_current_experiment is not None:
            reset_current_experiment(experiment_token)


def iter_qa_pipeline_events(
    question: str,
    retriever: Any,
    llm: SupportsInvoke | None = None,
    max_iterations: int = 2,
    chat_history: list[dict[str, str]] | None = None,
    trace_id: str | None = None,
    tenant_id: str = "default",
    user_id: str = "anonymous",
    session_id: str | None = None,
) -> Any:
    """Yield real LangGraph node/token events then a terminal pipeline_result.

    Plan §4.7: SSE can relay graph node names while the single pipeline runs.
    Plan §4.8: enables provider token streaming into LangGraph custom mode
    (``token_source=provider_generate``) when the LLM supports stream.
    Does not run a second generation. Sync callers should use ``run_qa_pipeline``.
    """
    from agent.graph_stream import (
        provider_token_stream_enabled,
        stream_graph_node_events,
    )

    graph, initial_state, settings, internal_trace, experiment_token = _prepare_qa_pipeline(
        question=question,
        retriever=retriever,
        llm=llm,
        max_iterations=max_iterations,
        chat_history=chat_history,
        trace_id=trace_id,
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
    )
    stream_flag = provider_token_stream_enabled.set(True)
    try:
        final_state: GraphState | None = None
        for event in stream_graph_node_events(graph, initial_state):
            if event.get("type") == "pipeline_result":
                state = event.get("state")
                final_state = cast(GraphState, state if isinstance(state, dict) else {})
                # Ensure trace_id is the internal one used for finish_trace.
                if final_state.get("trace_id") in (None, "", trace_id):
                    final_state = {**final_state, "trace_id": internal_trace}
                finish_trace(internal_trace, final_state)
                yield {
                    "type": "pipeline_result",
                    "state": final_state,
                    "source": "graph",
                    "nodes": list(event.get("nodes") or []),
                }
            else:
                yield event
        if final_state is None:
            final_state = graph.invoke(initial_state)
            finish_trace(internal_trace, final_state)
            yield {
                "type": "pipeline_result",
                "state": final_state,
                "source": "graph",
                "nodes": [],
            }
    finally:
        provider_token_stream_enabled.reset(stream_flag)
        if experiment_token is not None and reset_current_experiment is not None:
            reset_current_experiment(experiment_token)


# ---------------------------------------------------------------------------
# Level 3: Conversation Session (multi-turn)
# ---------------------------------------------------------------------------


class ConversationSession:
    """Управляет многоходовым диалогом с RAG-ассистентом.

    Хранит историю и автоматически передаёт её в каждый вызов графа.

    Concurrent same-session ``ask`` calls are serialized (plan §3.1c). A
    monotonic turn epoch discards late mutations from wall-budget orphan
    workers so ``_history`` / ``_pending_action`` stay coherent.

    Slice 3.1i: ``mutation_version`` / ``expected_version`` give process-local
    optimistic concurrency for clients; ``user_id`` / ``session_id`` are
    forwarded into the normal pipeline for sticky experiment assignment.
    Multi-replica durable version store is still out of scope.

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
        self._history: list[dict[str, str]] = []
        self._pending_action: dict[str, str] | None = None
        # Per-session serialize + epoch (plan §3.1c / REL-01 session races).
        self._lock = threading.RLock()
        self._turn_cv = threading.Condition(self._lock)
        self._busy = False
        self._mutation_epoch = 0
        self._active_turn: int | None = None

    @property
    def history(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._history)

    @property
    def mutation_version(self) -> int:
        """Process-local optimistic version (idle = last completed turn epoch)."""
        with self._lock:
            return int(self._mutation_epoch)

    def _history_snapshot(self) -> list[dict[str, str]]:
        """Copy history for pipeline input (safe under concurrent mutation)."""
        with self._lock:
            return list(self._history)

    def _stamp_session_version(self, result: GraphState) -> GraphState:
        """Attach current mutation version so clients can CAS the next turn."""
        stamped: GraphState = {**result, "session_version": self.mutation_version}
        return stamped

    def _version_conflict_state(
        self,
        question: str,
        expected_version: int,
        actual_version: int,
        trace_id: Optional[str],
        tenant_id: str,
    ) -> GraphState:
        """Fail-closed when client If-Match version does not match (never auto)."""
        state = create_initial_state(question, trace_id=trace_id, tenant_id=tenant_id)
        state["answer"] = (
            "Конфликт версии сессии: состояние диалога изменилось. "
            "Обновите session_version и повторите запрос."
        )
        state["route"] = "conflict"
        state["quality_score"] = 0
        state["error"] = True
        state["error_message"] = (
            f"session version conflict expected={expected_version} actual={actual_version}"
        )
        state["error_node"] = "session_version"
        state["session_version"] = actual_version
        return state

    def _acquire_turn(self, *, expected_version: int | None = None) -> int | None:
        """Block until free; optionally CAS on mutation_version before exclusive turn.

        Returns the new turn epoch, or ``None`` when ``expected_version`` mismatches
        the idle version (optimistic concurrency conflict, plan §3.1i).
        """
        with self._lock:
            while self._busy:
                self._turn_cv.wait()
            if expected_version is not None and int(expected_version) != self._mutation_epoch:
                return None
            self._busy = True
            self._mutation_epoch += 1
            turn = self._mutation_epoch
            self._active_turn = turn
            return turn

    def _release_turn(self, turn: int, *, invalidate: bool = False) -> None:
        """End exclusive turn; optionally invalidate orphan worker mutations."""
        with self._lock:
            if invalidate and self._mutation_epoch == turn:
                # Bump so late budget-orphan writes see a stale turn.
                self._mutation_epoch += 1
            if self._active_turn == turn:
                self._active_turn = None
            self._busy = False
            self._turn_cv.notify_all()

    def _turn_is_current(self, turn: int) -> bool:
        return turn == self._mutation_epoch

    def _append_history(
        self,
        question: str,
        answer: str,
        *,
        turn: int | None = None,
        force: bool = False,
    ) -> None:
        with self._lock:
            if (
                not force
                and turn is not None
                and not self._turn_is_current(turn)
            ):
                logger.warning(
                    "Discarding stale session history append turn=%s epoch=%s",
                    turn,
                    self._mutation_epoch,
                )
                return
            self._history.append({"role": "user", "content": question})
            self._history.append({"role": "assistant", "content": answer})
            if len(self._history) > self._max_history * 2:
                self._history = self._history[-(self._max_history * 2) :]

    def _set_pending_action(
        self,
        value: dict[str, str] | None,
        *,
        turn: int | None = None,
    ) -> bool:
        """Mutate pending action only for the current session turn."""
        with self._lock:
            # Prefer explicit turn; fall back to active turn ownership.
            if turn is None:
                if self._active_turn is None or not self._turn_is_current(self._active_turn):
                    return False
            elif not self._turn_is_current(turn):
                logger.warning(
                    "Discarding stale pending_action write turn=%s epoch=%s",
                    turn,
                    self._mutation_epoch,
                )
                return False
            self._pending_action = None if value is None else dict(value)
            return True

    def _get_pending_action_copy(self) -> dict[str, str] | None:
        with self._lock:
            if self._pending_action is None:
                return None
            return dict(self._pending_action)

    def _take_pending_action(self, *, turn: int | None = None) -> dict[str, str] | None:
        with self._lock:
            if turn is not None and not self._turn_is_current(turn):
                return None
            if turn is None and (
                self._active_turn is None or not self._turn_is_current(self._active_turn)
            ):
                return None
            pending = self._pending_action
            self._pending_action = None
            return dict(pending) if pending is not None else None

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
        kb_docs_acc: list[Any] = []

        for _ in range(max_loops):
            prompt = "\n\n".join(
                f"{item.get('role', 'user')}: {item.get('content', '')}" for item in messages
            )
            try:
                t0 = time.monotonic()
                from llm.role_params import generation_kwargs_for_role

                agentic_kwargs = generation_kwargs_for_role("agentic")
                response = tool_llm.generate_with_tools(
                    messages,
                    _agentic_tool_definitions(),
                    **agentic_kwargs,
                )
            except Exception as exc:
                logger.warning("[agentic] provider tool loop unavailable: %s", exc)
                return None
            usage = _merge_llm_usage(usage, _capture_llm_usage(tool_llm, "agentic"))
            raw_tool_calls = cast(list[dict[str, Any]], getattr(response, "tool_calls", None) or [])
            traced_tool_calls: list[str] | list[dict[str, Any]] | None
            if raw_tool_calls:
                traced_tool_calls = raw_tool_calls
            else:
                traced_tool_calls = list(tool_calls) or None
            trace_llm_call(
                trace_id=active_trace_id,
                node_name="agentic_tool_loop",
                prompt=prompt,
                response=str(response.text or ""),
                model=(
                    _normalize_optional_str(getattr(response, "model", None))
                    or _get_llm_model_name(tool_llm)
                    or ""
                ),
                duration_ms=(time.monotonic() - t0) * 1000,
                tool_calls=traced_tool_calls,
            )

            if not raw_tool_calls:
                answer = str(response.text or "").strip()
                if not answer:
                    return None
                final_state: GraphState = {
                    **state,
                    "answer": answer,
                    **_agentic_terminal_fields_with_eval(
                        question=question,
                        answer=answer,
                        kb_docs=kb_docs_acc,
                        generator_llm=tool_llm,
                    ),
                    "tool_calls": tool_calls,
                    "requires_confirmation": False,
                    "action_summary": "",
                }
                final_state = _apply_llm_usage(final_state, usage)
                final_state = _finalize_agentic_terminal(final_state)
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
                    result, found_docs = agent_tools.search_kb_docs(
                        str(arguments.get("query") or question),
                        tenant_id,
                        retriever=self._retriever,
                    )
                    if found_docs:
                        kb_docs_acc.extend(found_docs)
                elif tool_name == "check_order_status":
                    order_id = str(arguments.get("order_id") or _extract_order_id(question) or "")
                    result = agent_tools.check_order_status(order_id, tenant_id)
                elif tool_name == "create_ticket":
                    summary = str(arguments.get("summary") or question).strip()
                    priority = str(arguments.get("priority") or "medium").strip() or "medium"
                    action_summary = f"создать тикет по запросу: {summary[:120]}"
                    self._set_pending_action(
                        {
                            "summary": summary,
                            "priority": priority,
                            "action_summary": action_summary,
                        }
                    )
                    confirmation_state: GraphState = {
                        **state,
                        "answer": f"Подтвердите: {action_summary}",
                        **_agentic_unmeasured_gate(),
                        "tool_calls": tool_calls + [tool_name],
                        "requires_confirmation": True,
                        "action_summary": action_summary,
                    }
                    confirmation_state = _apply_llm_usage(confirmation_state, usage)
                    confirmation_state = _finalize_agentic_terminal(confirmation_state)
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
        fallback_answer = "\n\n".join(answer_parts)
        fallback_state: GraphState = {
            **state,
            "answer": fallback_answer,
            **_agentic_terminal_fields_with_eval(
                question=question,
                answer=fallback_answer,
                kb_docs=kb_docs_acc,
                generator_llm=tool_llm,
            ),
            "tool_calls": tool_calls,
            "requires_confirmation": False,
            "action_summary": "",
        }
        fallback_state = _apply_llm_usage(fallback_state, usage)
        fallback_state = _finalize_agentic_terminal(fallback_state)
        log_step(active_trace_id, "agentic_fallback", fallback_state)
        return fallback_state

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

        active_trace_id = _start_trace_for_request(trace_id, tenant_id=tenant_id)
        state = create_initial_state(
            question=question,
            trace_id=active_trace_id,
            tenant_id=tenant_id,
        )

        pending_snapshot = self._get_pending_action_copy()
        if pending_snapshot is not None:
            if confirm is True:
                pending = self._take_pending_action()
                if pending is None:
                    pending = pending_snapshot
                ticket_result = agent_tools.create_ticket(
                    summary=pending["summary"],
                    priority=pending["priority"],
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=session_id or "",
                )
                state.update(
                    {
                        "answer": ticket_result,
                        **_agentic_unmeasured_gate(),
                        "tool_calls": ["create_ticket"],
                        "requires_confirmation": False,
                        "action_summary": "",
                    }
                )
                state = _finalize_agentic_terminal(state)
                log_step(active_trace_id, "create_ticket", state)
                finish_trace(active_trace_id, state)
                return state
            if confirm is False:
                self._set_pending_action(None)
                state.update(
                    {
                        "answer": "Действие отменено.",
                        **_agentic_unmeasured_gate(),
                        "tool_calls": [],
                        "requires_confirmation": False,
                        "action_summary": "",
                    }
                )
                state = _finalize_agentic_terminal(state)
                log_step(active_trace_id, "confirmation_cancelled", state)
                finish_trace(active_trace_id, state)
                return state

            state.update(
                {
                    "answer": f"Подтвердите: {pending_snapshot['action_summary']}",
                    **_agentic_unmeasured_gate(),
                    "tool_calls": [],
                    "requires_confirmation": True,
                    "action_summary": pending_snapshot["action_summary"],
                }
            )
            state = _finalize_agentic_terminal(state)
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
            # Provider path already finalizes each terminal; re-apply is idempotent.
            provider_agentic_result = _finalize_agentic_terminal(provider_agentic_result)
            finish_trace(active_trace_id, provider_agentic_result)
            return provider_agentic_result

        if has_ticket_intent:
            summary = question.strip()
            action_summary = f"создать тикет по запросу: {summary[:120]}"
            self._set_pending_action(
                {
                    "summary": summary,
                    "priority": "medium",
                    "action_summary": action_summary,
                }
            )
            state.update(
                {
                    "answer": f"Подтвердите: {action_summary}",
                    **_agentic_unmeasured_gate(),
                    "tool_calls": ["create_ticket"],
                    "requires_confirmation": True,
                    "action_summary": action_summary,
                }
            )
            state = _finalize_agentic_terminal(state)
            log_step(active_trace_id, "confirmation_gate", state)
            finish_trace(active_trace_id, state)
            return state

        order_id = _extract_order_id(question)
        if order_id is None or not any(
            marker in normalized for marker in ("заказ", "достав", "статус")
        ):
            finish_trace(active_trace_id, state)
            return None

        tool_calls: list[str] = []
        answer_parts: list[str] = []
        kb_docs: list[Any] = []

        if any(marker in normalized for marker in ("достав", "стоит", "москв")):
            kb_result, found_docs = agent_tools.search_kb_docs(
                _build_agentic_search_query(question),
                tenant_id,
                retriever=self._retriever,
            )
            tool_calls.append("search_kb")
            answer_parts.append(kb_result)
            if found_docs:
                kb_docs.extend(found_docs)
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

        terminal_answer = "\n\n".join(part for part in answer_parts if part)
        state.update(
            {
                "answer": terminal_answer,
                **_agentic_terminal_fields_with_eval(
                    question=question,
                    answer=terminal_answer,
                    kb_docs=kb_docs,
                    generator_llm=self._llm,
                ),
                "tool_calls": tool_calls,
                "requires_confirmation": False,
                "action_summary": "",
            }
        )
        state = _finalize_agentic_terminal(state)
        finish_trace(active_trace_id, state)
        return state

    def _timed_out_state(
        self, question: str, budget_sec: float, trace_id: Optional[str], tenant_id: str
    ) -> GraphState:
        """Graceful degraded result when ``ask`` overruns its wall-budget."""
        state = create_initial_state(question, trace_id=trace_id, tenant_id=tenant_id)
        state["answer"] = (
            "Извините, обработка запроса заняла слишком много времени и была "
            "прервана. Пожалуйста, повторите попытку или обратитесь к специалисту "
            "поддержки."
        )
        state["route"] = "timeout"
        state["quality_score"] = 0
        state["error"] = True
        state["error_message"] = f"ask() exceeded wall-budget of {budget_sec:.1f}s"
        state["error_node"] = "wall_budget"
        return state

    def _run_within_budget(
        self,
        fn: Callable[[], GraphState],
        budget_sec: float,
        question: str,
        trace_id: Optional[str],
        tenant_id: str,
    ) -> GraphState:
        """Run ``fn`` under a wall-clock budget (dogfood finding #3).

        Uses the process-wide request executor (plan §3 / REL-01) — never a
        per-call ``ThreadPoolExecutor``. The graph is still not cooperatively
        cancellable: on timeout we return a degraded result while the worker
        may continue. Nested calls already on a request-executor thread run
        inline so HTTP ``wait_for`` remains the single outer deadline.
        ``RAG_ASK_BUDGET_SEC=0`` (default) keeps the original blocking call.
        """
        from utils.request_executor import run_on_request_executor

        try:
            return run_on_request_executor(fn, timeout_sec=budget_sec)
        except TimeoutError:
            logger.warning(
                "ConversationSession.ask exceeded wall-budget of %.1fs; returning a "
                "degraded result (the background run is not cancellable)",
                budget_sec,
                extra={"trace_id": trace_id},
            )
            return self._timed_out_state(question, budget_sec, trace_id, tenant_id)

    def iter_ask_events(
        self,
        question: str,
        trace_id: Optional[str] = None,
        tenant_id: str = "default",
        confirm: bool | None = None,
        user_id: str = "anonymous",
        session_id: str | None = None,
        expected_version: int | None = None,
    ) -> Any:
        """Yield graph node status events then a terminal pipeline_result (plan §4.7).

        Same exclusive-turn and history semantics as ``ask``, but the LangGraph
        path publishes real node names for SSE. Agentic short-circuit yields a
        single ``agentic`` status then the agentic terminal state.
        """
        from config.settings import get_settings

        settings = get_settings()
        if expected_version is not None:
            try:
                expected_version = int(expected_version)
            except (TypeError, ValueError):
                conflict = self._version_conflict_state(
                    question,
                    expected_version=-1,
                    actual_version=self.mutation_version,
                    trace_id=trace_id,
                    tenant_id=tenant_id,
                )
                yield {"type": "status", "node": "conflict", "source": "graph", "phase": "end"}
                yield {
                    "type": "pipeline_result",
                    "state": conflict,
                    "source": "graph",
                    "nodes": ["conflict"],
                }
                return

        turn = self._acquire_turn(expected_version=expected_version)
        if turn is None:
            conflict = self._version_conflict_state(
                question,
                expected_version=int(expected_version or -1),
                actual_version=self.mutation_version,
                trace_id=trace_id,
                tenant_id=tenant_id,
            )
            yield {"type": "status", "node": "conflict", "source": "graph", "phase": "end"}
            yield {
                "type": "pipeline_result",
                "state": conflict,
                "source": "graph",
                "nodes": ["conflict"],
            }
            return

        history_appended = False
        try:
            def _emit_terminal(state: GraphState, *, nodes: list[str] | None = None) -> Any:
                nonlocal history_appended
                answer = state.get("answer") or ""
                if not history_appended:
                    self._append_history(question, answer, turn=turn)
                    history_appended = True
                stamped = self._stamp_session_version(state)
                return {
                    "type": "pipeline_result",
                    "state": stamped,
                    "source": "graph",
                    "nodes": list(nodes or []),
                }

            if getattr(settings, "agentic_mode", False):
                yield {
                    "type": "status",
                    "node": "agentic",
                    "source": "graph",
                    "phase": "end",
                }
                agentic_result = self._run_agentic_flow(
                    question=question,
                    trace_id=trace_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    session_id=session_id,
                    confirm=confirm,
                )
                if agentic_result is not None:
                    yield _emit_terminal(agentic_result, nodes=["agentic"])
                    return

            for event in iter_qa_pipeline_events(
                question=question,
                retriever=self._retriever,
                llm=self._llm,
                max_iterations=self._max_iterations,
                chat_history=self._history_snapshot(),
                trace_id=trace_id,
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            ):
                if event.get("type") == "pipeline_result":
                    state = event.get("state")
                    final = cast(GraphState, state if isinstance(state, dict) else {})
                    nodes = event.get("nodes") if isinstance(event.get("nodes"), list) else []
                    yield _emit_terminal(final, nodes=[str(n) for n in nodes])
                else:
                    yield event
        finally:
            self._release_turn(turn, invalidate=False)

    def ask(
        self,
        question: str,
        trace_id: Optional[str] = None,
        tenant_id: str = "default",
        confirm: bool | None = None,
        user_id: str = "anonymous",
        session_id: str | None = None,
        deadline_sec: float | None = None,
        expected_version: int | None = None,
    ) -> GraphState:
        """Задаёт вопрос с учётом истории диалога.

        ``deadline_sec`` (optional) is the outer wall budget from the HTTP path
        (or other callers). Combined with ``RAG_ASK_BUDGET_SEC`` via the tighter
        positive timeout and bound as a cooperative request deadline so provider
        entry points refuse new work after the wall elapses (plan §3.1b).

        ``expected_version`` (optional, plan §3.1i): optimistic If-Match against
        ``mutation_version``. Mismatch returns ``route=conflict`` without running
        the pipeline (never ``auto``). Successful results include
        ``session_version`` for the next CAS.

        ``user_id`` / ``session_id`` are forwarded into the normal QA pipeline so
        sticky experiment assignment can hash the same identity as agentic paths.
        """
        from config.settings import get_settings
        from llm.request_budget import (
            LLMBudgetExceeded,
            bind_llm_request_budget_from_settings,
            clear_llm_request_budget,
        )
        from utils.request_deadline import (
            RequestDeadlineExceeded,
            bind_request_deadline,
            clear_request_deadline,
            tighter_timeout_sec,
        )

        settings = get_settings()
        budget_sec = float(getattr(settings, "ask_budget_sec", 0.0) or 0.0)
        wall_sec = tighter_timeout_sec(budget_sec, deadline_sec)

        # Exclusive session turn: concurrent same-session asks queue (3.1c).
        # Optional CAS on idle mutation_version before exclusive work (3.1i).
        if expected_version is not None:
            try:
                expected_version = int(expected_version)
            except (TypeError, ValueError):
                return self._version_conflict_state(
                    question,
                    expected_version=-1,
                    actual_version=self.mutation_version,
                    trace_id=trace_id,
                    tenant_id=tenant_id,
                )

        turn = self._acquire_turn(expected_version=expected_version)
        if turn is None:
            return self._version_conflict_state(
                question,
                expected_version=int(expected_version or -1),
                actual_version=self.mutation_version,
                trace_id=trace_id,
                tenant_id=tenant_id,
            )
        invalidate_orphan = False
        try:

            def _run() -> GraphState:
                # Bind on the worker thread when the caller did not pre-bind
                # a shared deadline/budget (stream path may share one object).
                from llm.request_budget import get_llm_request_budget
                from utils.request_deadline import get_request_deadline

                bound_deadline_here = False
                bound_budget_here = False
                if wall_sec > 0 and get_request_deadline() is None:
                    bind_request_deadline(wall_sec, source="ask")
                    bound_deadline_here = True
                if get_llm_request_budget() is None:
                    bind_llm_request_budget_from_settings(settings, source="ask")
                    bound_budget_here = True
                try:
                    try:
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
                                return agentic_result

                        return run_qa_pipeline(
                            question=question,
                            retriever=self._retriever,
                            llm=self._llm,
                            max_iterations=self._max_iterations,
                            chat_history=self._history_snapshot(),
                            trace_id=trace_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            session_id=session_id,
                        )
                    except RequestDeadlineExceeded:
                        logger.warning(
                            "ConversationSession.ask hit cooperative deadline "
                            "wall_sec=%.1fs",
                            wall_sec,
                            extra={"trace_id": trace_id},
                        )
                        return self._timed_out_state(
                            question, wall_sec, trace_id, tenant_id
                        )
                    except LLMBudgetExceeded as exc:
                        logger.warning(
                            "ConversationSession.ask hit LLM budget reason=%s",
                            getattr(exc, "reason", "exhausted"),
                            extra={"trace_id": trace_id},
                        )
                        return _budget_exhausted_state(
                            question,
                            trace_id,
                            tenant_id,
                            reason=str(getattr(exc, "reason", "exhausted") or "exhausted"),
                        )
                finally:
                    if bound_deadline_here:
                        clear_request_deadline()
                    if bound_budget_here:
                        clear_llm_request_budget()

            if budget_sec > 0:
                result = self._run_within_budget(
                    _run, budget_sec, question, trace_id, tenant_id
                )
            else:
                result = _run()

            answer = result.get("answer") or ""
            # Wall-budget path returns while the worker may still run: bump
            # epoch immediately so orphan cannot write history/pending, then
            # force-append the client-visible timeout answer.
            if result.get("error_node") == "wall_budget":
                with self._lock:
                    if self._mutation_epoch == turn:
                        self._mutation_epoch += 1
                    # Drop any pending set by the orphan mid-flight.
                    self._pending_action = None
                self._append_history(question, answer, force=True)
                invalidate_orphan = False  # already invalidated
            else:
                self._append_history(question, answer, turn=turn)
            return self._stamp_session_version(result)
        finally:
            self._release_turn(turn, invalidate=invalidate_orphan)

    def clear(self) -> None:
        """Сбрасывает историю (waits for any in-flight exclusive turn)."""
        with self._lock:
            while self._busy:
                self._turn_cv.wait()
            self._mutation_epoch += 1
            self._active_turn = None
            self._history.clear()
            self._pending_action = None
