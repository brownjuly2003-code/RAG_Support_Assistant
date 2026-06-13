"""Langfuse LLM tracing integration."""
from __future__ import annotations

import copy
import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

_langfuse = None


def get_langfuse() -> Any:
    """Lazy init Langfuse client. Returns None if not configured."""
    global _langfuse
    if _langfuse is not None:
        return _langfuse
    try:
        from config.settings import get_settings

        settings = get_settings()
        if not settings.langfuse_public_key or not settings.langfuse_secret_key:
            return None
        try:
            from langfuse import Langfuse
        except ImportError:
            from langfuse.otel import Langfuse  # type: ignore[no-redef]
        _langfuse = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        logger.info("Langfuse connected: %s", settings.langfuse_host)
        return _langfuse
    except ImportError:
        logger.debug("langfuse package not installed")
        return None
    except Exception as exc:
        logger.warning("Langfuse init failed: %s", exc)
        return None


def trace_llm_call(
    trace_id: str,
    node_name: str,
    prompt: str,
    response: str,
    model: str = "",
    duration_ms: float = 0,
    tool_calls: list[str] | list[dict[str, Any]] | None = None,
) -> None:
    """Log an LLM call to Langfuse."""
    lf = get_langfuse()
    if lf is None:
        return
    try:
        langfuse_trace_id = hashlib.md5(
            (trace_id or f"{node_name}:{prompt[:256]}").encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
        metadata = {
            "duration_ms": duration_ms,
            "pipeline": "rag-pipeline",
            "sqlite_trace_id": trace_id,
        }
        if tool_calls is not None:
            metadata["tool_calls"] = copy.deepcopy(tool_calls)
        if hasattr(lf, "start_observation"):
            generation = lf.start_observation(
                trace_context={"trace_id": langfuse_trace_id},
                name=node_name,
                as_type="generation",
                model=model or None,
                input=prompt[:5000],
                output=response[:5000],
                metadata=metadata,
            )
            generation.end()
            return
        trace = lf.trace(id=langfuse_trace_id, name="rag-pipeline")
        trace.generation(
            name=node_name,
            model=model,
            input=prompt[:5000],
            output=response[:5000],
            metadata=metadata,
        )
    except Exception as exc:
        logger.warning("Langfuse trace failed: %s", exc)


def flush() -> None:
    """Flush Langfuse queue."""
    lf = get_langfuse()
    if lf is not None:
        try:
            if hasattr(lf, "shutdown"):
                lf.shutdown()
            else:
                lf.flush()
        except Exception:
            pass
