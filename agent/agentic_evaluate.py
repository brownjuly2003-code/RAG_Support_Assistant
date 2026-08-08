"""Agentic LLM quality evaluate wire (plan §6.6).

§6.5 measures citation-bound grounding when agentic terminals have KB docs,
but quality stays unmeasured until a real evaluate score is supplied. This
module runs the same independent-judge self-eval used by the main graph
``evaluate`` node and returns measured ``quality_source=llm`` scores — or
fail-closed unmeasured provenance when the judge is unavailable / errors /
fails to parse.

Never invents fixed 80/85/90. Does not overwrite grounding fields; callers
pass the score into ``measure_agentic_terminal``. Confirmation / order-only /
no-KB paths should not call this helper.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from agent.agentic_measure import has_kb_context, normalize_context_docs
from agent.judge_policy import parse_judge_score, resolve_judge_llm
from agent.prompts import build_self_eval_prompt

logger = logging.getLogger(__name__)

InvokeFn = Callable[[Any, str], str]


@dataclass(frozen=True)
class AgenticEvaluateResult:
    """Outcome of an agentic terminal quality evaluate attempt."""

    quality_score: int | None
    relevance_score: float | None
    quality_source: str | None
    judge_status: str
    judge_reason: str
    judge_independent: bool
    measured: bool

    def as_measure_kwargs(self) -> dict[str, Any]:
        """Kwargs accepted by ``measure_agentic_terminal`` when measured.

        Plan §5.4: never invent ``relevance = quality/100``. When relevance is
        unmeasured (None), omit it so the measure path computes retrieval
        relevance independently.
        """
        if not self.measured or self.quality_score is None:
            return {}
        out: dict[str, Any] = {
            "quality_score": int(self.quality_score),
            "quality_source": self.quality_source or "llm",
        }
        if self.relevance_score is not None:
            out["relevance_score"] = float(self.relevance_score)
        return out

    def as_state_fields(self) -> dict[str, Any]:
        """Observability fields; safe to merge without clobbering grounding."""
        return {
            "judge_status": self.judge_status,
            "judge_reason": self.judge_reason,
            "judge_independent": bool(self.judge_independent),
        }


def _default_invoke(llm: Any, prompt: str) -> str:
    """Minimal invoke for pure unit tests / fallback when graph helper absent."""
    if llm is None:
        raise TypeError("judge llm is None")
    if hasattr(llm, "invoke"):
        raw = llm.invoke(prompt)
        if hasattr(raw, "content"):
            return str(raw.content or "")
        return str(raw or "")
    raise TypeError(f"judge llm has no invoke: {type(llm)!r}")


def _strip_citation_markers(answer: str) -> str:
    cleaned = re.sub(r"\s*\[\d+\]", "", answer or "")
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _unmeasured(
    *,
    status: str,
    reason: str,
    independent: bool = False,
) -> AgenticEvaluateResult:
    return AgenticEvaluateResult(
        quality_score=None,
        relevance_score=None,
        quality_source=None,
        judge_status=status,
        judge_reason=reason,
        judge_independent=independent,
        measured=False,
    )


def evaluate_agentic_answer(
    *,
    question: str,
    answer: str,
    context_docs: Sequence[Any] | None,
    candidate_fast: Any | None = None,
    candidate_strong: Any | None = None,
    generator_llm: Any | None = None,
    require_independence: bool = False,
    invoke: InvokeFn | None = None,
) -> AgenticEvaluateResult:
    """Run judge self-eval for an agentic terminal with KB context.

    Returns measured ``quality_source=llm`` only when the judge produces a
    parseable 1–100 score. Failures are fail-closed (unmeasured), never
    silent default 50 with llm provenance.
    """
    if not has_kb_context(context_docs):
        return _unmeasured(status="unavailable", reason="no_kb_context")

    answer_text = str(answer or "").strip()
    if not answer_text:
        return _unmeasured(status="unavailable", reason="empty_answer")

    resolution = resolve_judge_llm(
        candidate_fast=candidate_fast,
        candidate_strong=candidate_strong,
        generator_llm=generator_llm,
        require_independence=bool(require_independence),
    )
    if not resolution.ok or resolution.judge_llm is None:
        return _unmeasured(
            status=str(resolution.status or "unavailable"),
            reason=resolution.reason or "no_judge_candidate",
            independent=bool(resolution.independent),
        )

    docs = normalize_context_docs(context_docs or [])
    # build_self_eval_prompt expects list[dict]; normalize already returns that.
    prompt_docs: list[dict[str, Any]] = [
        {"page_content": d.get("page_content", ""), "metadata": d.get("metadata") or {}}
        for d in docs
    ]
    answer_for_eval = _strip_citation_markers(answer_text)
    prompt = build_self_eval_prompt(
        question=str(question or ""),
        answer=answer_for_eval,
        context_docs=prompt_docs,
    )

    invoker = invoke or _default_invoke
    try:
        raw = invoker(resolution.judge_llm, prompt)
    except Exception as exc:  # noqa: BLE001 — judge path must fail closed
        logger.warning(
            "[agentic_evaluate] judge error: %s",
            exc,
        )
        return _unmeasured(
            status="error",
            reason=f"judge_error:{str(exc)[:120] or type(exc).__name__}",
            independent=bool(resolution.independent),
        )

    score = parse_judge_score(str(raw or ""))
    if score is None:
        return _unmeasured(
            status="parse_failure",
            reason="judge_parse_failure",
            independent=bool(resolution.independent),
        )

    # Plan §5.4: relevance from retrieval docs — never quality/100.
    from agent.relevance import measure_retrieval_relevance

    rel_score, _rel_source = measure_retrieval_relevance(
        context_docs=docs,
        graded_docs=None,
    )

    return AgenticEvaluateResult(
        quality_score=int(score),
        relevance_score=rel_score,
        quality_source="llm",
        judge_status="ok",
        judge_reason=resolution.reason or "ok",
        judge_independent=bool(resolution.independent),
        measured=True,
    )


def agentic_quality_eval_enabled(settings: Any | None) -> bool:
    """Feature flag: default ON (parity with streaming_quality_eval)."""
    if settings is None:
        return True
    return bool(getattr(settings, "agentic_quality_eval", True))
