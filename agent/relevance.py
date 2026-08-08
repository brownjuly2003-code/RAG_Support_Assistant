"""Independent retrieval relevance (plan §5.4).

``relevance_score`` gates ``route=auto`` alongside quality and grounding.
It must measure retrieval/context coverage — **never** ``quality_score / 100``.

Sources (stable tags for traces / SSE):
- ``empty_context`` — no docs → 0.0 fail-closed
- ``graded_fraction`` — len(graded_docs) / len(context_docs)
- ``retrieval_scores`` — mean of per-doc retrieval metadata scores
- ``unmeasured`` — docs present but no grades/scores → None (not invent)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

RELEVANCE_SOURCE_EMPTY = "empty_context"
RELEVANCE_SOURCE_GRADED_FRACTION = "graded_fraction"
RELEVANCE_SOURCE_RETRIEVAL_SCORES = "retrieval_scores"
RELEVANCE_SOURCE_CONTEXT_KEPT = "context_kept"
RELEVANCE_SOURCE_UNMEASURED = "unmeasured"

_SCORE_KEYS = (
    "relevance_score",
    "score",
    "similarity",
    "similarity_score",
    "rerank_score",
)


def _as_mapping(doc: Any) -> Mapping[str, Any]:
    if isinstance(doc, Mapping):
        return doc
    meta = getattr(doc, "metadata", None)
    page = getattr(doc, "page_content", None)
    if meta is not None or page is not None:
        return {
            "page_content": page if page is not None else "",
            "metadata": meta if isinstance(meta, Mapping) else {},
        }
    return {}


def _doc_metadata(doc: Any) -> Mapping[str, Any]:
    m = _as_mapping(doc)
    meta = m.get("metadata")
    return meta if isinstance(meta, Mapping) else {}


def _normalize_score(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    # Heuristic: scores in (1, 100] are percent-like.
    if value > 1.0:
        value = value / 100.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _doc_retrieval_score(doc: Any) -> float | None:
    meta = _doc_metadata(doc)
    for key in _SCORE_KEYS:
        if key in meta:
            normalized = _normalize_score(meta.get(key))
            if normalized is not None:
                return normalized
    # Chroma distance: lower is better; map roughly into [0, 1].
    if "distance" in meta:
        try:
            distance = float(meta["distance"])
        except (TypeError, ValueError):
            return None
        if distance != distance:
            return None
        return max(0.0, min(1.0, 1.0 - distance))
    # Top-level score fields (some adapters flatten metadata).
    mapping = _as_mapping(doc)
    for key in _SCORE_KEYS:
        if key in mapping and key != "metadata":
            normalized = _normalize_score(mapping.get(key))
            if normalized is not None:
                return normalized
    return None


def _mean_retrieval_scores(docs: Sequence[Any]) -> float | None:
    scores: list[float] = []
    for doc in docs:
        s = _doc_retrieval_score(doc)
        if s is not None:
            scores.append(s)
    if not scores:
        return None
    return round(sum(scores) / len(scores), 3)


def measure_retrieval_relevance(
    *,
    context_docs: Sequence[Any] | None = None,
    graded_docs: Sequence[Any] | None = None,
) -> tuple[float | None, str]:
    """Compute retrieval relevance in ``[0, 1]`` or ``None`` if unmeasured.

    Never accepts or reads answer ``quality_score``. Callers that previously
    did ``relevance = quality / 100`` must use this instead.
    """
    context = list(context_docs) if context_docs is not None else None
    graded = list(graded_docs) if graded_docs is not None else None

    context_n = len(context) if context is not None else 0
    graded_n = len(graded) if graded is not None else 0

    if context_n == 0 and graded_n == 0:
        return 0.0, RELEVANCE_SOURCE_EMPTY

    # Prefer explicit retrieval/rerank scores when present (independent signal).
    pool: list[Any] = []
    if graded is not None and graded_n > 0:
        pool = list(graded)
    elif context is not None and context_n > 0:
        pool = list(context)
    mean_score = _mean_retrieval_scores(pool) if pool else None
    if mean_score is not None:
        return mean_score, RELEVANCE_SOURCE_RETRIEVAL_SCORES

    # Graded-vs-retrieved fraction when both sides known (graph grade_docs path).
    # graded=[] with context>0 means grader rejected everything → 0.0.
    if context is not None and graded is not None and context_n > 0:
        fraction = graded_n / float(context_n)
        return round(max(0.0, min(1.0, fraction)), 3), RELEVANCE_SOURCE_GRADED_FRACTION

    # Only one doc list provided (typical agentic search hits / pre-grade).
    # These docs *are* the kept generation context — full keep, not quality-derived.
    if context_n > 0 and graded is None:
        return 1.0, RELEVANCE_SOURCE_CONTEXT_KEPT
    if graded_n > 0 and context is None:
        return 1.0, RELEVANCE_SOURCE_CONTEXT_KEPT

    # Docs present but no rejection ratio and no retrieval scores → unmeasured.
    # Do not invent a high relevance or copy quality.
    return None, RELEVANCE_SOURCE_UNMEASURED


def relevance_from_state(state: Mapping[str, Any]) -> tuple[float | None, str]:
    """Convenience: measure from a graph/agentic state mapping."""
    return measure_retrieval_relevance(
        context_docs=state.get("context_docs"),
        graded_docs=state.get("graded_docs"),
    )
