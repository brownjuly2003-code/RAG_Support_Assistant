"""LLM fact-card extractor (adaptive-retrieval Track F / F1).

A *fact-card* is a flat, structured digest of one document: the full list of
required fields, required documents/evidence, and escalation conditions, plus a
source pointer. It targets the enumeration failure mode where a query like
"какие поля/данные нужны для X" loses field names because the chunk holding the
"Обязательные поля" table sits deep in the retrieval pool and the reranker does
not lift it into top-k (residual MISS ``customs-clearance-fields``). Storing one
compact card per topic lets the whole field list be returned intact.

This module only does extraction + validation; collection wiring (F2) and the
retriever lane (F3/F4) live elsewhere. Keep imports light — ``ingestion.*`` is in
the mypy strict scope.

Schema (per plan ``docs/plans/2026-06-13-adaptive-retrieval-factcard-plan.md``)::

    {"topic": "customs_clearance", "fields": [...], "required_docs": [...],
     "conditions": [...], "source": "customs.md#sec3"}
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator


class SupportsInvoke(Protocol):
    """Minimal LLM contract: ``invoke(prompt) -> str`` (same shape as the graph)."""

    def invoke(self, prompt: str) -> str: ...  # pragma: no cover - structural


class FactCard(BaseModel):
    """One flat structured record extracted from a document."""

    topic: str
    fields: list[str] = Field(default_factory=list)
    required_docs: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    source: str

    @field_validator("topic", "source")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("must be non-empty")
        return cleaned

    @field_validator("fields", "required_docs", "conditions")
    @classmethod
    def _dedupe_clean(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in values:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            out.append(text)
        return out


_PROMPT_TEMPLATE = """Ты извлекаешь СТРУКТУРНУЮ КАРТУ ФАКТОВ из внутреннего документа поддержки.
Карта нужна, чтобы на запрос вида «какие поля / документы / условия нужны для X»
вернуть ПОЛНЫЙ перечень, ничего не потеряв.

Верни СТРОГО JSON-массив объектов (без markdown, без пояснений). Один объект — одна
тема документа (обычно ровно одна). Каждый объект:
{{
  "topic": "<короткая тема в snake_case на латинице, напр. customs_clearance>",
  "fields": ["<все имена полей>"],
  "required_docs": ["<все обязательные документы / доказательства / источники>"],
  "conditions": ["<все условия, триггеры эскалации, основания HOLD/STOP>"],
  "source": "{source}"
}}

ПРАВИЛА (критично):
- В "fields" перенеси ВСЕ идентификаторы полей ДОСЛОВНО как в документе
  (snake_case коды из таблиц «Обязательные поля» и плейсхолдеры вида {{{{name}}}}
  без скобок). Не переводи, не сокращай, не выдумывай. Не теряй ни одного поля.
- В "required_docs" — обязательные документы/доказательства/источники для ответа.
- В "conditions" — условия применения, триггеры эскалации, основания HOLD/STOP.
- "source" всегда строго "{source}".

ДОКУМЕНТ:
---
{doc_text}
---
JSON:"""


# F1-validated safe input size: extraction of the full «Обязательные поля» table
# completes in ~13s well within the request timeout, while the full 17k-char doc
# drives a runaway response that times out. The required-field table sits in the
# first ~5k chars, so 6000 keeps "поля не теряются" intact. Full-document coverage
# (late required_docs/conditions sections) is F2 work (chunk-aware extraction).
_DEFAULT_MAX_CHARS = 6000


def build_factcard_prompt(doc_text: str, source: str, *, max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """Render the extraction prompt, truncating very long documents."""
    text = doc_text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[truncated]…"
    return _PROMPT_TEMPLATE.format(doc_text=text, source=source)


def _strip_code_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    return s


def _coerce_card_list(payload: Any) -> list[dict[str, Any]]:
    """Accept a JSON array, a single object, or {"fact_cards": [...]}-style wraps."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list) and all(isinstance(i, dict) for i in value):
                return value
        return [payload]
    return []


def parse_factcards(raw: str, source: str) -> list[FactCard]:
    """Parse + validate the LLM response into ``FactCard`` records.

    Raises ``ValueError`` if no JSON object/array can be located.
    """
    blob = _strip_code_fence(raw)
    start_candidates = [i for i in (blob.find("["), blob.find("{")) if i >= 0]
    if not start_candidates:
        raise ValueError("no JSON found in extractor response")
    start = min(start_candidates)
    end = max(blob.rfind("]"), blob.rfind("}"))
    snippet = blob[start : end + 1] if end >= start else blob[start:]

    payload = json.loads(snippet)
    cards: list[FactCard] = []
    for item in _coerce_card_list(payload):
        item.setdefault("source", source)
        item["source"] = source
        cards.append(FactCard.model_validate(item))
    return cards


def extract_fact_cards(
    doc_text: str,
    source: str,
    llm: SupportsInvoke,
    *,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> list[FactCard]:
    """Extract fact-cards from a document using the given LLM."""
    prompt = build_factcard_prompt(doc_text, source, max_chars=max_chars)
    raw = llm.invoke(prompt)
    return parse_factcards(raw, source)
