"""Grounding / factuality fail-closed helpers (plan §5.1).

States:
- ``verified``: every extracted claim is supported by evidence (or vacuous
  non-factual answer with extractor NONE — no claims to support).
- ``unsupported``: at least one claim failed support check.
- ``not_verified``: verification skipped, disabled, missing context, parse
  failure, short answer, or incomplete claim coverage.

Never treat skip / error / missing evidence as factuality 100.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

GroundingStatus = Literal["verified", "unsupported", "not_verified"]

# Default calibrated floor for auto route (same band as quality gate).
DEFAULT_MIN_FACTUALITY_FOR_AUTO = 80


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


def status_for_claims(claims: list[Mapping[str, Any]]) -> tuple[GroundingStatus, int, bool]:
    """Score supported fraction; any unsupported → status unsupported."""
    if not claims:
        return status_for_empty_claim_parse()
    supported = sum(1 for c in claims if bool(c.get("supported")))
    total = len(claims)
    factuality = int(100 * supported / total)
    if supported == total:
        return "verified", factuality, False
    if supported == 0:
        return "unsupported", factuality, False
    return "unsupported", factuality, False


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
        return factuality >= int(min_factuality)

    # Vacuous verified (NONE / no claims): allow auto only with context and
    # no knowledge gap — factuality 0 is intentional, not a perfect score.
    return True
