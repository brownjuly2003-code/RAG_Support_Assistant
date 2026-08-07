"""Independent judge policy for answer quality evaluation (plan §6.3).

Production policy: the quality judge must not be the same model/provider
identity as the answer generator (no same-model self-approval). When a
compliant judge is unavailable, or the judge call/parse fails, the path is
fail-closed: unmeasured scores and ``not_verified`` so route cannot become
heuristic ``auto``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

JudgeStatus = Literal["ok", "unavailable", "error", "parse_failure"]


@dataclass(frozen=True)
class LlmIdentity:
    provider: str
    model: str
    object_id: int

    @property
    def labeled(self) -> bool:
        return bool(self.provider or self.model)

    def key(self) -> tuple[str, str] | int:
        if self.labeled:
            return (self.provider, self.model)
        return self.object_id


def llm_identity(llm: Any) -> LlmIdentity:
    """Extract a stable identity for independence checks."""
    provider = getattr(llm, "provider_id", None)
    if provider is None:
        provider = getattr(llm, "provider_name", None)
    model = getattr(llm, "model_name", None)
    if model is None:
        inner = getattr(llm, "_llm", None)
        model = getattr(inner, "model", None) if inner is not None else None

    def _norm(value: Any) -> str:
        if value is None or not isinstance(value, (str, int, float)):
            return ""
        return str(value).strip().lower()

    return LlmIdentity(
        provider=_norm(provider),
        model=_norm(model),
        object_id=id(llm),
    )


def same_llm_identity(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    if left is right:
        return True
    a = llm_identity(left)
    b = llm_identity(right)
    if a.labeled and b.labeled:
        return a.key() == b.key()
    # Unlabeled mocks/fakes: only object identity counts as "same".
    return False


@dataclass(frozen=True)
class JudgeResolution:
    ok: bool
    judge_llm: Any | None
    status: JudgeStatus
    reason: str
    independent: bool
    judge_provider: str = ""
    judge_model: str = ""


def resolve_judge_llm(
    *,
    candidate_fast: Any | None,
    candidate_strong: Any | None,
    generator_llm: Any | None,
    require_independence: bool,
) -> JudgeResolution:
    """Pick a judge LLM under independence policy.

    When ``require_independence`` is True, the judge must differ from the
    generator identity. Prefer fast among independent candidates (latency).
    When independence is not required, prefer fast (historical evaluate path).
    """
    ordered: list[Any] = []
    for cand in (candidate_fast, candidate_strong):
        if cand is None:
            continue
        if cand not in ordered and not any(c is cand for c in ordered):
            ordered.append(cand)

    if not ordered:
        return JudgeResolution(
            ok=False,
            judge_llm=None,
            status="unavailable",
            reason="no_judge_candidate",
            independent=False,
        )

    independent = [
        cand for cand in ordered if not same_llm_identity(cand, generator_llm)
    ]

    if require_independence:
        if not independent:
            return JudgeResolution(
                ok=False,
                judge_llm=None,
                status="unavailable",
                reason="no_independent_judge",
                independent=False,
            )
        chosen = independent[0]
        ident = llm_identity(chosen)
        return JudgeResolution(
            ok=True,
            judge_llm=chosen,
            status="ok",
            reason="independent",
            independent=True,
            judge_provider=ident.provider,
            judge_model=ident.model,
        )

    # Non-strict: prefer fast (first in ordered) even if same as generator.
    chosen = ordered[0]
    ident = llm_identity(chosen)
    is_indep = not same_llm_identity(chosen, generator_llm)
    return JudgeResolution(
        ok=True,
        judge_llm=chosen,
        status="ok",
        reason="independence_not_required" if not is_indep else "independent",
        independent=is_indep,
        judge_provider=ident.provider,
        judge_model=ident.model,
    )


def judge_fail_closed_fields(
    *,
    reason: str,
    status: JudgeStatus = "unavailable",
) -> dict[str, Any]:
    """State fields when judge cannot produce a measured score.

    Leaves ``route`` unset so ``route_or_retry`` demotes to human on score 0.
    Never claims ``quality_source=llm``.
    """
    return {
        "quality_score": 0,
        "relevance_score": 0.0,
        "quality_source": "unmeasured",
        "grounding_status": "not_verified",
        "factuality_score": 0,
        "judge_status": status,
        "judge_reason": reason,
    }


def parse_judge_score(raw: str) -> int | None:
    """Parse 1–100 score; None if missing/unparseable (no silent default)."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    import re

    numbers = re.findall(r"\d+", text)
    if not numbers:
        return None
    value = int(numbers[0])
    if value < 1 or value > 100:
        # Clamp only when a number was present in range after clamp rules:
        # 0 or >100 still treated as parseable but clamped for safety.
        value = max(1, min(100, value))
    return value
