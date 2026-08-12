"""Grounding / factuality fail-closed helpers (plan §5.1–5.2).

States:
- ``verified``: every extracted claim is supported by evidence (or vacuous
  non-factual answer with extractor NONE — no claims to support) **and**
  (when claims exist) bound to cited ``[N]`` documents (§5.2).
- ``unsupported``: at least one claim failed support check against cited docs.
- ``not_verified``: verification skipped, disabled, missing context, parse
  failure, short answer, incomplete claim coverage, or missing/invalid
  answer citations for substantial claims.

Never treat skip / error / missing evidence as factuality 100.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

GroundingStatus = Literal["verified", "unsupported", "not_verified"]

# Default calibrated floor for auto route (same band as quality gate).
DEFAULT_MIN_FACTUALITY_FOR_AUTO = 80

_CITATION_RE = re.compile(r"\[(\d+)\]")
# Minimum characters for evidence/claim text match into a cited doc.
_MIN_BIND_CHARS = 8


def status_for_skip(*, reason: str) -> tuple[GroundingStatus, int, bool]:
    """Return (status, factuality_score, skipped) for non-verifying paths."""
    _ = reason
    return "not_verified", 0, True


def status_for_short_answer() -> tuple[GroundingStatus, int, bool]:
    return "not_verified", 0, False


def status_for_no_claims_none() -> tuple[GroundingStatus, int, bool]:
    """Extractor returned NONE — no factual claims.

    Vacuously verified (nothing unsupported), but **not** score 100: score 0
    with status verified so dashboards do not look like perfect checking.
    """
    return "verified", 0, False


def status_for_empty_claim_parse() -> tuple[GroundingStatus, int, bool]:
    """Claims text present but no parseable claim lines."""
    return "not_verified", 0, False


def _claim_effectively_supported(
    claim: Mapping[str, Any],
    *,
    require_citation_bound: bool,
) -> bool:
    if not bool(claim.get("supported")):
        return False
    if require_citation_bound and not bool(claim.get("citation_bound")):
        return False
    return True


def status_for_claims(
    claims: Sequence[Mapping[str, Any]],
    *,
    require_citation_bound: bool = False,
) -> tuple[GroundingStatus, int, bool]:
    """Score supported fraction; any unsupported → status unsupported.

    When ``require_citation_bound`` is True (plan §5.2), only claims that are
    both LLM-supported and ``citation_bound`` count as supported.
    """
    if not claims:
        return status_for_empty_claim_parse()
    supported = sum(
        1
        for c in claims
        if _claim_effectively_supported(c, require_citation_bound=require_citation_bound)
    )
    total = len(claims)
    factuality = int(100 * supported / total)
    if supported == total:
        return "verified", factuality, False
    if supported == 0:
        return "unsupported", factuality, False
    return "unsupported", factuality, False


def parse_answer_citation_indices(answer: str) -> list[int]:
    """1-based citation markers ``[N]`` appearing in the answer text."""
    found = {int(m) for m in _CITATION_RE.findall(answer or "") if m.isdigit()}
    return sorted(i for i in found if i >= 1)


def _doc_page_content(doc: Any) -> str:
    if isinstance(doc, Mapping):
        return str(doc.get("page_content") or "")
    return str(getattr(doc, "page_content", "") or "")


def _normalize_match_text(text: str) -> str:
    return " ".join((text or "").lower().split())


def _text_supported_by_doc(needle: str, haystack: str) -> bool:
    """True if needle has a usable overlap with haystack (fail-closed if too short)."""
    n = _normalize_match_text(needle)
    h = _normalize_match_text(haystack)
    if not n or not h:
        return False
    if len(n) < _MIN_BIND_CHARS:
        # Short needles: require full containment only when both are short.
        return n in h
    if n in h:
        return True
    # Token overlap for paraphrased evidence quotes.
    tokens = [t for t in re.findall(r"\w+", n) if len(t) > 2]
    if not tokens:
        return False
    hits = sum(1 for t in tokens if t in h)
    return hits >= max(2, (len(tokens) + 1) // 2)


def apply_citation_bound_claims(
    *,
    answer: str,
    claims: Sequence[Mapping[str, Any]],
    docs: Sequence[Any],
) -> tuple[list[dict[str, Any]], GroundingStatus | None]:
    """Bind claims to answer citations ``[N]`` (plan §5.2).

    Returns ``(updated_claims, status_override)``.

    - No claims → unchanged, no override.
    - Claims without any valid ``[N]`` in the answer → ``not_verified``.
    - Claims with citations: each claim gets ``citation_bound`` if evidence or
      claim text is grounded in a **cited** document (not merely any retrieved
      doc). Missing binding demotes effective support via ``citation_bound``.
    - Status override ``not_verified`` only for missing/invalid citation path;
      otherwise caller re-scores with ``require_citation_bound=True``.
    """
    if not claims:
        return [dict(c) for c in claims], None

    indices = parse_answer_citation_indices(answer)
    doc_list = list(docs or [])

    if not indices:
        updated = [
            {
                **dict(c),
                "citation_bound": False,
                "citation_indices": [],
            }
            for c in claims
        ]
        return updated, "not_verified"

    cited_texts: dict[int, str] = {}
    for idx in indices:
        if 1 <= idx <= len(doc_list):
            text = _doc_page_content(doc_list[idx - 1])
            if text.strip():
                cited_texts[idx] = text

    if not cited_texts:
        updated = [
            {
                **dict(c),
                "citation_bound": False,
                "citation_indices": list(indices),
            }
            for c in claims
        ]
        return updated, "not_verified"

    updated: list[dict[str, Any]] = []
    for raw in claims:
        claim = dict(raw)
        bound_idxs: list[int] = []
        if bool(claim.get("supported")):
            evidence = str(claim.get("evidence") or "").strip()
            claim_text = str(claim.get("text") or "").strip()
            for idx, text in cited_texts.items():
                if evidence and _text_supported_by_doc(evidence, text):
                    bound_idxs.append(idx)
                elif claim_text and _text_supported_by_doc(claim_text, text):
                    bound_idxs.append(idx)
            # Explicit [N] on the claim line may narrow binding.
            claim_local_refs = parse_answer_citation_indices(claim_text)
            if claim_local_refs:
                bound_idxs = [i for i in bound_idxs if i in claim_local_refs] or [
                    i for i in claim_local_refs if i in cited_texts
                    and (
                        (evidence and _text_supported_by_doc(evidence, cited_texts[i]))
                        or (claim_text and _text_supported_by_doc(claim_text, cited_texts[i]))
                    )
                ]
        claim["citation_bound"] = bool(bound_idxs)
        claim["citation_indices"] = bound_idxs
        updated.append(claim)

    return updated, None


def status_for_truncated_coverage(
    *,
    extracted_claim_count: int,
    verified_claim_count: int,
    max_claims: int = 10,
) -> GroundingStatus | None:
    """If claim budget truncates unverified remainder, force not_verified.

    Returns None when coverage is complete (caller uses claim status).
    """
    if extracted_claim_count > max_claims and verified_claim_count < extracted_claim_count:
        return "not_verified"
    return None


def has_retrieval_context(state: Mapping[str, Any]) -> bool:
    docs = state.get("graded_docs") or state.get("context_docs") or []
    return bool(docs)


def grounding_allows_auto(
    state: Mapping[str, Any],
    *,
    min_factuality: int = DEFAULT_MIN_FACTUALITY_FOR_AUTO,
) -> bool:
    """Fail-closed auto gate (plan §5 / RAG-02).

    Requires: no node error, knowledge_gap false, retrieval context present,
    grounding_status == verified, and factuality either vacuous (0 with
    verified + empty claims) or >= min_factuality when claims exist.
    """
    if state.get("error"):
        return False
    if state.get("knowledge_gap"):
        return False
    if not has_retrieval_context(state):
        return False

    status = str(state.get("grounding_status") or "not_verified").strip().lower()
    if status != "verified":
        return False

    claims = state.get("claims") or []
    fact_raw = state.get("factuality_score")
    try:
        factuality = int(fact_raw) if fact_raw is not None else 0
    except (TypeError, ValueError):
        return False

    if claims:
        # §5.2: every claim must be citation-bound for auto (not merely LLM-supported).
        if any(not bool(c.get("citation_bound")) for c in claims if isinstance(c, Mapping)):
            return False
        return factuality >= int(min_factuality)

    # Vacuous verified (NONE / no claims): allow auto only with context and
    # no knowledge gap — factuality 0 is intentional, not a perfect score.
    return True
