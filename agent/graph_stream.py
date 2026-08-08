"""Graph node event stream helpers (plan §4.7).

LangGraph is the source of node progress for SSE when streaming parity is on.
``stream_mode=updates`` yields real node names as each graph step completes;
the final full state is taken from ``stream_mode=values``.

Token SSE still reuses the finished graph answer (UX chunks) — true provider
token streaming through generate remains a later residual. This module never
runs a second generation path.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

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


def normalize_node_name(node: Any) -> str:
    text = str(node or "").strip()
    return text or "unknown"


def stream_graph_node_events(
    graph: Any,
    initial_state: Mapping[str, Any],
) -> Iterator[dict[str, Any]]:
    """Yield graph progress events then a terminal pipeline_result.

    Events:
      ``{"type": "status", "node": <name>, "source": "graph", "phase": "end"}``
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
            stream_mode=["updates", "values"],
        )
    except TypeError:
        # Older/fakes that only accept stream_mode="updates"
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
        # Reconstruct final via invoke if updates-only left no values.
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
        if mode == "updates" or (mode is None and isinstance(chunk, dict)):
            if not isinstance(chunk, dict):
                continue
            # Multi-mode updates: {node: update}; single-mode same shape.
            if mode is None and all(
                k in ("type", "node", "source", "phase", "state") for k in chunk
            ):
                continue
            for node_name in chunk:
                # Skip accidental full-state dicts mistaken as updates.
                if mode is None and node_name in state_in and len(chunk) > 8:
                    # Heuristic: values-like dict without mode — treat as values.
                    final_state = dict(chunk)
                    break
                name = normalize_node_name(node_name)
                if name in {"type", "state", "source"}:
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
