"""Measured agentic terminal gate when KB context exists (plan §6.5).

Plan §6.1 left tool/confirmation paths as ``quality_source=unmeasured`` so they
never invent fixed scores or unlock ``route=auto``. §6.5 closes the residual for
terminals that actually retrieved knowledge-base documents: attach context,
run citation-bound grounding, optionally apply quality floors when a real
evaluate score is supplied, and allow ``auto`` only when the same gates as the
main graph would allow it.

Without KB docs → fall back to unmeasured agentic (6.1).
Confirmation / order-only / empty-KB paths stay unmeasured.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

from agent.grounding import (
    grounding_allows_auto,
    parse_answer_citation_indices,
    status_for_claims,
)

KB_EMPTY_MARKER = "По базе знаний ничего не найдено."


def normalize_context_docs(docs: Sequence[Any]) -> list[dict[str, Any]]:
    """Normalize retriever docs to ``{page_content, metadata}`` dicts."""
    out: list[dict[str, Any]] = []
    for doc in docs:
        if isinstance(doc, Mapping):
            content = str(doc.get("page_content") or "")
            meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        else:
            content = str(getattr(doc, "page_content", "") or "")
            raw_meta = getattr(doc, "metadata", None)
            meta = dict(raw_meta) if isinstance(raw_meta, dict) else {}
        if not content.strip():
            continue
        out.append({"page_content": content, "metadata": meta})
    return out


def has_kb_context(docs: Sequence[Any] | None) -> bool:
    return bool(docs) and bool(normalize_context_docs(docs))


def unmeasured_agentic_fields(
    *,
    route: Literal["agentic", "human"] = "agentic",
) -> dict[str, Any]:
    """§6.1 fail-closed fields (shared with graph helper)."""
    return {
        "route": route,
        "quality_score": 0,
        "relevance_score": 0.0,
        "quality_source": "unmeasured",
        "grounding_status": "not_verified",
        "fact_verification_skipped": True,
        "factuality_score": 0,
    }


def _claims_from_cited_docs(
    answer: str,
    context_docs: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Build citation-bound claim stubs from answer ``[N]`` markers + docs."""
    indices = parse_answer_citation_indices(answer)
    claims: list[dict[str, Any]] = []
    n_docs = len(context_docs)
    for idx in indices:
        if idx < 1 or idx > n_docs:
            claims.append(
                {
                    "text": f"citation [{idx}]",
                    "supported": False,
                    "citation_bound": False,
                }
            )
            continue
        content = str(context_docs[idx - 1].get("page_content") or "")
        snippet = content[:120].strip() or f"doc-{idx}"
        claims.append(
            {
                "text": snippet,
                "supported": True,
                "citation_bound": True,
            }
        )
    return claims


def measure_agentic_terminal(
    *,
    answer: str,
    kb_docs: Sequence[Any] | None,
    quality_score: int | None = None,
    relevance_score: float | None = None,
    quality_source: str | None = None,
    min_quality: int = 80,
    min_factuality: int = 80,
    min_relevance: float = 0.8,
) -> dict[str, Any]:
    """Return state fields for an agentic terminal after optional KB measure.

    - No KB docs → unmeasured agentic (route stays agentic).
    - KB docs present → attach context, measure citation-bound grounding.
    - ``quality_score`` only accepted when ``quality_source`` is a measured
      provenance (``llm`` / ``heuristic``); never invent fixed 80/85/90.
    - ``route=auto`` only when grounding + measured scores clear floors.
    """
    context = normalize_context_docs(kb_docs or [])
    if not context:
        return unmeasured_agentic_fields(route="agentic")

    claims = _claims_from_cited_docs(answer or "", context)
    if not claims:
        # Retrieved context exists but answer has no bound citations → cannot
        # claim verified grounding; keep deliverable as agentic unmeasured scores.
        return {
            **unmeasured_agentic_fields(route="agentic"),
            "context_docs": list(context),
            "graded_docs": list(context),
            "claims": [],
            "grounding_status": "not_verified",
            "fact_verification_skipped": False,
            "agentic_measure": "kb_context_no_citations",
        }

    status, factuality, skipped = status_for_claims(
        claims, require_citation_bound=True
    )

    measured_quality = False
    q_score = 0
    r_score: float | None = None
    r_source = "unmeasured"
    q_source = "unmeasured"
    if quality_source in {"llm", "heuristic"} and quality_score is not None:
        try:
            q_score = int(quality_score)
            q_source = str(quality_source)
            measured_quality = True
        except (TypeError, ValueError):
            measured_quality = False
            q_score = 0
            q_source = "unmeasured"

    # Plan §5.4: never derive relevance from quality/100.
    from agent.relevance import measure_retrieval_relevance

    if relevance_score is not None:
        try:
            r_score = float(relevance_score)
            r_source = "caller"
        except (TypeError, ValueError):
            r_score = None
            r_source = "unmeasured"
    if r_score is None:
        # Prefer retrieval scores on KB docs; fraction of self is last resort
        # only when graded==context would apply after measure packs fields.
        measured_r, measured_src = measure_retrieval_relevance(
            context_docs=context,
            graded_docs=None,
        )
        r_score = measured_r
        r_source = measured_src

    fields: dict[str, Any] = {
        "context_docs": list(context),
        "graded_docs": list(context),
        "claims": claims,
        "grounding_status": status,
        "fact_verification_skipped": bool(skipped),
        "factuality_score": int(factuality),
        "quality_score": q_score if measured_quality else 0,
        "relevance_score": r_score if r_score is not None else 0.0,
        "relevance_source": r_source,
        "quality_source": q_source,
        "agentic_measure": "kb_grounding" + ("+quality" if measured_quality else ""),
        "knowledge_gap": False,
    }

    probe = {
        **fields,
        "error": False,
        "knowledge_gap": False,
    }
    grounded = grounding_allows_auto(probe, min_factuality=min_factuality)
    scores_ok = (
        measured_quality
        and r_score is not None
        and q_score >= int(min_quality)
        and float(r_score) >= float(min_relevance)
    )
    if grounded and scores_ok:
        fields["route"] = "auto"
    else:
        # Deliverable agentic answer with honest measured grounding provenance;
        # not auto without full floors.
        fields["route"] = "agentic"
    return fields
