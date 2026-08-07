"""Pre-response PII and document prompt-injection checks (plan §6.2).

Runs **before** terminal answer delivery. Policy actions:

- ``allow`` — no issue
- ``redact`` — PII in answer; replace with masked text (route may stay auto)
- ``refuse`` — injection detected; replace answer with safe refusal
- ``human`` — force ``route=human`` (used with refuse for injection)

Injection and unredacted PII must never leave a clean measured ``auto`` path
that still contains the unsafe payload. Post-response online evaluators remain
monitoring only — this module is runtime protection.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from utils.pii import contains_pii, redact_pii

SafetyAction = Literal["allow", "redact", "refuse", "human"]

REFUSAL_ANSWER = (
    "Не могу предоставить этот ответ: обнаружены признаки "
    "небезопасного содержимого (prompt injection). "
    "Вопрос передан на проверку специалисту."
)

# (reason_code, compiled pattern) — English + Russian adversarial markers.
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "ignore_previous",
        re.compile(
            r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
            re.IGNORECASE,
        ),
    ),
    (
        "disregard_previous",
        re.compile(
            r"disregard\s+(all\s+)?(previous|prior|above)",
            re.IGNORECASE,
        ),
    ),
    (
        "forget_instructions",
        re.compile(
            r"forget\s+(all\s+)?(your\s+)?(previous\s+)?instructions?",
            re.IGNORECASE,
        ),
    ),
    (
        "override_system",
        re.compile(
            r"override\s+(the\s+)?(system\s+)?prompt",
            re.IGNORECASE,
        ),
    ),
    (
        "you_are_now",
        re.compile(r"\byou\s+are\s+now\b", re.IGNORECASE),
    ),
    (
        "system_tag",
        re.compile(r"<\s*/?\s*system\s*>", re.IGNORECASE),
    ),
    (
        "system_role_line",
        re.compile(r"(?m)^\s*system\s*:\s*\S+", re.IGNORECASE),
    ),
    (
        "developer_mode",
        re.compile(r"\bdeveloper\s+mode\b", re.IGNORECASE),
    ),
    (
        "ru_ignore_instructions",
        re.compile(
            r"игнорируй(те)?\s+(все\s+)?предыдущие\s+инструкции",
            re.IGNORECASE,
        ),
    ),
    (
        "ru_forget_instructions",
        re.compile(
            r"забудь(те)?\s+(все\s+)?(свои\s+)?инструкции",
            re.IGNORECASE,
        ),
    ),
    (
        "ru_new_system",
        re.compile(
            r"(новый|смени)\s+системн(ый|ого)\s+промпт",
            re.IGNORECASE,
        ),
    ),
    (
        "ru_you_are_now",
        re.compile(r"\bты\s+теперь\b", re.IGNORECASE),
    ),
]


@dataclass(frozen=True)
class SafetyDecision:
    action: SafetyAction
    reasons: list[str] = field(default_factory=list)
    pii_found: bool = False
    injection_found: bool = False
    answer: str = ""


def detect_prompt_injection(text: str) -> list[str]:
    """Return reason codes for prompt-injection markers in ``text``."""
    if not text or not str(text).strip():
        return []
    hits: list[str] = []
    body = str(text)
    for code, pattern in _INJECTION_PATTERNS:
        if pattern.search(body):
            hits.append(code)
    return hits


def _doc_texts(context_docs: Sequence[Any] | None) -> list[str]:
    if not context_docs:
        return []
    texts: list[str] = []
    for doc in context_docs:
        if isinstance(doc, Mapping):
            texts.append(str(doc.get("page_content") or ""))
        else:
            texts.append(str(getattr(doc, "page_content", "") or ""))
    return texts


def evaluate_pre_response_safety(
    *,
    answer: str,
    context_docs: Sequence[Any] | None = None,
    requires_confirmation: bool = False,
) -> SafetyDecision:
    """Decide redact / refuse / human / allow for a candidate terminal answer."""
    answer_text = str(answer or "")
    reasons: list[str] = []
    pii_found = contains_pii(answer_text)
    if pii_found:
        reasons.append("pii_in_answer")

    injection_codes: list[str] = []
    if not requires_confirmation:
        for code in detect_prompt_injection(answer_text):
            injection_codes.append(f"answer:{code}")
        for idx, doc_text in enumerate(_doc_texts(context_docs), start=1):
            for code in detect_prompt_injection(doc_text):
                injection_codes.append(f"doc{idx}:{code}")

    injection_found = bool(injection_codes)
    if injection_found:
        # Deduplicate while keeping order.
        seen: set[str] = set()
        for code in injection_codes:
            if code not in seen:
                seen.add(code)
                reasons.append(f"injection:{code}")
        # Refuse content + force human route (runtime protection, not monitoring).
        return SafetyDecision(
            action="refuse",
            reasons=reasons,
            pii_found=pii_found,
            injection_found=True,
            answer=REFUSAL_ANSWER,
        )

    if pii_found:
        return SafetyDecision(
            action="redact",
            reasons=reasons,
            pii_found=True,
            injection_found=False,
            answer=redact_pii(answer_text),
        )

    return SafetyDecision(
        action="allow",
        reasons=[],
        pii_found=False,
        injection_found=False,
        answer=answer_text,
    )


def apply_pre_response_safety(state: Mapping[str, Any]) -> dict[str, Any]:
    """Return a new state dict with pre-response safety applied.

    - empty/missing answer → allow (no-op fields)
    - confirmation UX: PII redact only (no injection refuse on tool prompts)
    - injection → refuse answer, ``route=human``, scores zeroed, not_verified
    - PII only → redact answer; route unchanged
    - never leaves ``route=auto`` with unredacted PII or injection payload
    """
    answer = state.get("answer")
    if answer is None or not str(answer).strip():
        out = dict(state)
        out.setdefault("safety_action", "allow")
        out.setdefault("safety_reasons", [])
        return out

    requires_confirmation = bool(state.get("requires_confirmation"))
    docs = state.get("graded_docs") or state.get("context_docs") or []
    decision = evaluate_pre_response_safety(
        answer=str(answer),
        context_docs=docs if isinstance(docs, Sequence) else [],
        requires_confirmation=requires_confirmation,
    )

    out = dict(state)
    out["safety_action"] = decision.action
    out["safety_reasons"] = list(decision.reasons)
    out["answer"] = decision.answer

    if decision.action == "refuse":
        out["route"] = "human"
        out["quality_score"] = 0
        out["relevance_score"] = 0.0
        out["grounding_status"] = "not_verified"
        out["factuality_score"] = 0
        out["suggested_questions"] = []
        # Keep requires_confirmation false after refuse — not a confirm UX.
        out["requires_confirmation"] = False
        return out

    if decision.action == "redact":
        # Redacted payload may keep prior route (including auto/agentic).
        return out

    return out
