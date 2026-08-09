"""Document grading fail-closed helpers (plan §5.3).

Rules:
- Grader LLM/tool errors must not silently accept the document.
- Forced top-1 re-injection after rejection is forbidden.
- Empty ``graded_docs`` after a real grade pass must not fall back to raw
  ``context_docs`` in generate (that would restore rejected context).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

DocGradeOutcome = Literal[
    "ok",
    "empty_retrieval",
    "all_rejected",
    "grader_error",
    "partial_grader_error",
]


def _doc_metadata(doc: Any) -> Mapping[str, Any]:
    if isinstance(doc, Mapping):
        metadata = doc.get("metadata")
    else:
        metadata = getattr(doc, "metadata", None)
    return metadata if isinstance(metadata, Mapping) else {}


def _doc_text(doc: Any) -> str:
    if isinstance(doc, Mapping):
        return str(doc.get("page_content") or "")
    return str(getattr(doc, "page_content", "") or "")


def _logical_source_key(doc: Any) -> tuple[str, str] | None:
    metadata = _doc_metadata(doc)
    source = str(metadata.get("source") or metadata.get("doc_id") or "").strip()
    if not source:
        return None
    return source, str(metadata.get("content_hash") or "").strip()


def _is_context_header_only(doc: Any) -> bool:
    metadata = _doc_metadata(doc)
    if metadata.get("has_context_header") is not True:
        return False
    text = _doc_text(doc).strip()
    first_line, separator, remainder = text.partition("\n")
    return first_line.startswith("[Контекст:") and (not separator or not remainder.strip())


def replace_relevant_context_headers(
    *,
    context_docs: Sequence[Any],
    graded: Sequence[Any],
) -> list[Any]:
    """Replace relevant header-only shells with content from the same source."""
    header_keys = {
        key
        for doc in graded
        if _is_context_header_only(doc)
        if (key := _logical_source_key(doc)) is not None
    }
    replacement_keys = {
        key
        for key in header_keys
        if any(
            _logical_source_key(doc) == key and not _is_context_header_only(doc)
            for doc in context_docs
        )
    }
    if not replacement_keys:
        return list(graded)

    resolved: list[Any] = []
    for doc in context_docs:
        key = _logical_source_key(doc)
        if key in replacement_keys:
            if not _is_context_header_only(doc):
                resolved.append(doc)
        elif doc in graded:
            resolved.append(doc)
    return resolved


def resolve_generation_context_docs(state: Mapping[str, Any]) -> list[Any]:
    """Select docs for answer generation without silent post-grade restore.

    If ``doc_grade_reason`` is set, grade_docs has run: use ``graded_docs``
    only (may be empty). Otherwise prefer non-empty graded, else context.
    """
    if state.get("doc_grade_reason") is not None:
        return list(state.get("graded_docs") or [])
    graded = state.get("graded_docs")
    if graded:
        return list(graded)
    return list(state.get("context_docs") or [])


def classify_grade_outcome(
    *,
    context_count: int,
    graded_count: int,
    grader_errors: int,
) -> DocGradeOutcome:
    if context_count <= 0:
        return "empty_retrieval"
    if graded_count > 0 and grader_errors > 0:
        return "partial_grader_error"
    if graded_count > 0:
        return "ok"
    if grader_errors > 0:
        return "grader_error"
    return "all_rejected"


def finalize_grade_state(
    state: Mapping[str, Any],
    *,
    graded: Sequence[Any],
    context_docs: Sequence[Any],
    filtered_count: int,
    grader_errors: int,
) -> dict[str, Any]:
    """Build grade_docs result fields (no top-1 force, fail-closed markers)."""
    graded_list = list(graded)
    context_count = len(context_docs)
    outcome = classify_grade_outcome(
        context_count=context_count,
        graded_count=len(graded_list),
        grader_errors=int(grader_errors or 0),
    )

    reason = f"Kept {len(graded_list)}/{context_count}, filtered {filtered_count}"
    if outcome == "all_rejected":
        reason += ", all_docs_rejected"
    elif outcome == "grader_error":
        reason += f", grader_error (errors={grader_errors})"
    elif outcome == "partial_grader_error":
        reason += f", partial_grader_error (errors={grader_errors})"
    elif outcome == "empty_retrieval":
        reason = "No documents retrieved"

    new_state: dict[str, Any] = {
        **dict(state),
        "graded_docs": graded_list,
        "doc_grade_reason": reason,
        "doc_grade_outcome": outcome,
    }

    # Fail-closed signals for routing / grounding when context is unsafe.
    # Do not set fact_verification_skipped here — that flag means verify_facts
    # was intentionally skipped (e.g. simple path); grade failures still allow
    # Self-RAG rewrite/retrieve retry.
    if outcome in {"all_rejected", "grader_error", "empty_retrieval"}:
        new_state["knowledge_gap"] = True
        new_state["grounding_status"] = "not_verified"
        new_state["factuality_score"] = 0

    return new_state


def mark_doc_grader_error(is_relevant_on_error: bool = False) -> bool:
    """Relevance decision when a per-doc grade call fails (default: reject)."""
    return bool(is_relevant_on_error)
