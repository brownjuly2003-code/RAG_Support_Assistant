"""Graph node + provider token event stream helpers (plan §4.7 / §4.8).

LangGraph is the source of node progress for SSE when streaming parity is on.
``stream_mode=updates`` yields real node names as each graph step completes;
the final full state is taken from ``stream_mode=values``.

Plan §4.8: ``stream_mode=custom`` relays live tokens written from the generate
node via ``get_stream_writer`` (``token_source=provider_generate``). When the
LLM has no stream capability, the SSE layer still falls back to UX chunks of
the finished graph answer (``token_source=graph_answer_chunks``).

This module never runs a second generation path.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextvars import ContextVar
from typing import Any

# When True, generate node prefers provider streaming into the LangGraph
# custom writer (SSE parity path). Sync ask() leaves this False.
provider_token_stream_enabled: ContextVar[bool] = ContextVar(
    "provider_token_stream_enabled",
    default=False,
)

# Public node names clients may see on SSE status events (stable contract).
KNOWN_GRAPH_NODES = frozenset(
    {
        "classify_complexity",
        "transform_query",
        "retrieve",
        "grade_docs",
        "generate",
        "verify_facts",
        "evaluate",
        "route_or_retry",
        "response_safety",
        "suggest_questions",
        "rewrite_query",
        "log",
        "handle_error",
        "agentic",
    }
)

TOKEN_SOURCE_PROVIDER = "provider_generate"
TOKEN_SOURCE_CHUNKS = "graph_answer_chunks"


def normalize_node_name(node: Any) -> str:
    text = str(node or "").strip()
    return text or "unknown"


def _normalize_token_event(payload: Any) -> dict[str, Any] | None:
    """Map LangGraph custom payloads to a stable token event dict."""
    if not isinstance(payload, Mapping):
        return None
    event_type = str(payload.get("type") or "").strip()
    if event_type != "token":
        # Allow bare custom string tokens.
        token = payload.get("token")
        if token is None:
            return None
        event_type = "token"
    token = payload.get("token")
    if token is None:
        return None
    text = str(token)
    if not text:
        return None
    source = str(payload.get("source") or "graph")
    token_source = str(payload.get("token_source") or TOKEN_SOURCE_PROVIDER)
    return {
        "type": "token",
        "token": text,
        "token_source": token_source,
        "source": source,
    }


def stream_graph_node_events(
    graph: Any,
    initial_state: Mapping[str, Any],
) -> Iterator[dict[str, Any]]:
    """Yield graph progress / token events then a terminal pipeline_result.

    Events:
      ``{"type": "status", "node": <name>, "source": "graph", "phase": "end"}``
      ``{"type": "token", "token": <str>, "token_source": "provider_generate",
         "source": "graph"}``
      ``{"type": "pipeline_result", "state": <final GraphState>, "source": "graph"}``

    Falls back to a single ``invoke`` when ``stream`` is unavailable (tests/fakes).
    """
    state_in = dict(initial_state)
    stream_fn = getattr(graph, "stream", None)
    if not callable(stream_fn):
        invoke = getattr(graph, "invoke", None)
        if not callable(invoke):
            raise TypeError("graph has neither stream nor invoke")
        final = invoke(state_in)
        yield {
            "type": "status",
            "node": "pipeline",
            "source": "graph",
            "phase": "end",
        }
        yield {
            "type": "pipeline_result",
            "state": final,
            "source": "graph",
        }
        return

    final_state: dict[str, Any] | None = None
    seen_nodes: list[str] = []
    try:
        stream_iter = stream_fn(
            state_in,
            stream_mode=["updates", "values", "custom"],
        )
    except TypeError:
        # Older/fakes that only accept stream_mode="updates" (or no custom).
        try:
            stream_iter = stream_fn(
                state_in,
                stream_mode=["updates", "values"],
            )
        except TypeError:
            stream_iter = stream_fn(state_in, stream_mode="updates")
            for chunk in stream_iter:
                if not isinstance(chunk, dict):
                    continue
                for node_name, _update in chunk.items():
                    name = normalize_node_name(node_name)
                    seen_nodes.append(name)
                    yield {
                        "type": "status",
                        "node": name,
                        "source": "graph",
                        "phase": "end",
                    }
            invoke = getattr(graph, "invoke", None)
            if callable(invoke):
                final_state = invoke(state_in)
            else:
                final_state = dict(state_in)
            yield {
                "type": "pipeline_result",
                "state": final_state,
                "source": "graph",
                "nodes": list(seen_nodes),
            }
            return

    for item in stream_iter:
        mode: str | None = None
        chunk: Any = item
        if isinstance(item, tuple) and len(item) == 2:
            mode, chunk = item[0], item[1]

        if mode == "custom":
            token_event = _normalize_token_event(chunk)
            if token_event is not None:
                yield token_event
            continue

        if mode == "updates" or (mode is None and isinstance(chunk, dict)):
            if not isinstance(chunk, dict):
                continue
            # Multi-mode updates: {node: update}; single-mode same shape.
            if mode is None and all(
                k in ("type", "node", "source", "phase", "state", "token", "token_source")
                for k in chunk
            ):
                # Might be a custom-like dict without mode tag.
                token_event = _normalize_token_event(chunk)
                if token_event is not None:
                    yield token_event
                continue
            for node_name in chunk:
                # Skip accidental full-state dicts mistaken as updates.
                if mode is None and node_name in state_in and len(chunk) > 8:
                    # Heuristic: values-like dict without mode — treat as values.
                    final_state = dict(chunk)
                    break
                name = normalize_node_name(node_name)
                if name in {"type", "state", "source", "token", "token_source"}:
                    continue
                seen_nodes.append(name)
                yield {
                    "type": "status",
                    "node": name,
                    "source": "graph",
                    "phase": "end",
                }
        if mode == "values" and isinstance(chunk, Mapping):
            final_state = dict(chunk)

    if final_state is None:
        invoke = getattr(graph, "invoke", None)
        if callable(invoke):
            final_state = invoke(state_in)
        else:
            final_state = dict(state_in)

    yield {
        "type": "pipeline_result",
        "state": final_state,
        "source": "graph",
        "nodes": list(seen_nodes),
    }
