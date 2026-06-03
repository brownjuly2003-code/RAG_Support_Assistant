from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

try:
    from langdetect import DetectorFactory
    from langdetect import detect as _langdetect_detect
except ImportError:
    DetectorFactory = None
    _langdetect_detect = None
else:
    DetectorFactory.seed = 0


_CITATION_RE = re.compile(r"\[\d+\]")
_PATTERNS_CACHE: dict[str, Any] | None = None


def _load_patterns() -> dict[str, Any]:
    global _PATTERNS_CACHE
    if _PATTERNS_CACHE is not None:
        return _PATTERNS_CACHE

    config_path = Path(__file__).resolve().parent.parent / "config" / "evaluator_patterns.yml"
    payload: dict[str, Any] = {}
    if config_path.exists():
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            payload = loaded

    refusal = payload.get("refusal") if isinstance(payload.get("refusal"), list) else []
    pii = payload.get("pii") if isinstance(payload.get("pii"), dict) else {}
    _PATTERNS_CACHE = {
        "refusal": [str(item).lower() for item in refusal if str(item).strip()],
        "pii": {
            str(name): str(pattern)
            for name, pattern in pii.items()
            if str(name).strip() and str(pattern).strip()
        },
    }
    return _PATTERNS_CACHE


def _result(score: float, verdict: str, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "score": float(score),
        "verdict": str(verdict),
        "metadata": metadata,
    }


def evaluate_citation_coverage(trace_state: dict[str, Any]) -> dict[str, Any]:
    answer = str(trace_state.get("answer") or "")
    sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", answer) if item.strip()]
    if not sentences:
        return _result(0.0, "missing", {"sentence_count": 0, "cited_sentences": 0})

    cited_sentences = sum(1 for sentence in sentences if _CITATION_RE.search(sentence))
    score = cited_sentences / len(sentences)
    if cited_sentences == 0:
        verdict = "missing"
    elif cited_sentences == len(sentences):
        verdict = "ok"
    else:
        verdict = "partial"
    return _result(
        score,
        verdict,
        {
            "sentence_count": len(sentences),
            "cited_sentences": cited_sentences,
        },
    )


def evaluate_answer_length_anomaly(
    trace_state: dict[str, Any],
    mean: float,
    std: float,
) -> dict[str, Any]:
    answer = str(trace_state.get("answer") or "")
    answer_words = len(answer.split())
    if std <= 0:
        return _result(
            0.0,
            "unknown",
            {
                "answer_words": answer_words,
                "z_score": 0.0,
            },
        )

    z_score = (answer_words - float(mean)) / float(std)
    is_anomaly = abs(z_score) > 2
    return _result(
        1.0 if is_anomaly else 0.0,
        "anomaly" if is_anomaly else "ok",
        {
            "answer_words": answer_words,
            "z_score": z_score,
        },
    )


def evaluate_retrieval_hit_rate(trace_state: dict[str, Any]) -> dict[str, Any]:
    retrieved_docs = trace_state.get("retrieved_docs") or []
    scores: list[float] = []
    for doc in retrieved_docs:
        if not isinstance(doc, dict):
            continue
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        score = metadata.get("relevance_score")
        if score is None:
            continue
        try:
            scores.append(float(score))
        except (TypeError, ValueError):
            continue

    if not scores:
        return _result(
            0.0,
            "unknown",
            {
                "retrieved_docs": len(retrieved_docs),
                "scored_docs": 0,
            },
        )

    hits = sum(1 for score in scores if score > 0.5)
    score = hits / len(scores)
    return _result(
        score,
        "ok" if score >= 0.8 else "partial" if hits else "low",
        {
            "retrieved_docs": len(retrieved_docs),
            "scored_docs": len(scores),
            "relevant_docs": hits,
            "min_score": min(scores),
            "max_score": max(scores),
            "mean_score": sum(scores) / len(scores),
        },
    )


def evaluate_tool_use_efficiency(trace_state: dict[str, Any]) -> dict[str, Any]:
    answer_final_tokens = trace_state.get("answer_final_tokens")
    if answer_final_tokens is None:
        tokens = trace_state.get("tokens") if isinstance(trace_state.get("tokens"), dict) else {}
        answer_final_tokens = tokens.get("answer_final_tokens") or tokens.get("completion_tokens") or 0
    try:
        answer_final_tokens_value = float(answer_final_tokens or 0.0)
    except (TypeError, ValueError):
        answer_final_tokens_value = 0.0

    tool_token_total = 0.0
    tool_calls = trace_state.get("tool_calls") or []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        token_value = tool_call.get("total_tokens")
        if token_value is None and isinstance(tool_call.get("tokens"), dict):
            token_value = (
                tool_call["tokens"].get("total_tokens")
                or tool_call["tokens"].get("completion_tokens")
                or tool_call["tokens"].get("prompt_tokens")
            )
        try:
            tool_token_total += float(token_value or 0.0)
        except (TypeError, ValueError):
            continue

    total_tokens = answer_final_tokens_value + tool_token_total
    score = (answer_final_tokens_value / total_tokens) if total_tokens else 0.0
    return _result(
        score,
        "efficient" if score >= 0.5 else "inefficient",
        {
            "answer_final_tokens": answer_final_tokens_value,
            "tool_tokens": tool_token_total,
            "tool_call_count": len(tool_calls),
        },
    )


def evaluate_refusal_detected(trace_state: dict[str, Any]) -> dict[str, Any]:
    answer = str(trace_state.get("answer") or "")
    answer_lower = answer.lower()
    matches = [pattern for pattern in _load_patterns()["refusal"] if pattern in answer_lower]
    return _result(
        1.0 if matches else 0.0,
        "refusal" if matches else "ok",
        {"matches": matches},
    )


def evaluate_pii_leak_suspicion(trace_state: dict[str, Any]) -> dict[str, Any]:
    answer = str(trace_state.get("answer") or "")
    matches = [
        pattern_name
        for pattern_name, pattern in _load_patterns()["pii"].items()
        if re.search(pattern, answer, flags=re.IGNORECASE)
    ]
    return _result(
        1.0 if matches else 0.0,
        "suspicious" if matches else "ok",
        {"matches": sorted(set(matches))},
    )


def evaluate_language_mismatch(trace_state: dict[str, Any]) -> dict[str, Any]:
    query = str(trace_state.get("question") or trace_state.get("query") or "")
    answer = str(trace_state.get("answer") or "")
    query_words = len(query.split())
    answer_words = len(answer.split())
    if query_words < 4 and answer_words < 4:
        return _result(
            0.0,
            "low_confidence",
            {
                "query_words": query_words,
                "answer_words": answer_words,
            },
        )

    try:
        query_language = _detect_language(query)
        answer_language = _detect_language(answer)
    except Exception as exc:
        return _result(
            0.0,
            "unknown",
            {
                "error": str(exc),
                "query_words": query_words,
                "answer_words": answer_words,
            },
        )

    mismatch = query_language != answer_language
    return _result(
        1.0 if mismatch else 0.0,
        "mismatch" if mismatch else "ok",
        {
            "query_language": query_language,
            "answer_language": answer_language,
            "query_words": query_words,
            "answer_words": answer_words,
        },
    )


def _detect_language(text: str) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        raise ValueError("text is empty")
    if _langdetect_detect is not None:
        return str(_langdetect_detect(normalized))

    cyrillic = len(re.findall(r"[А-Яа-яЁё]", normalized))
    latin = len(re.findall(r"[A-Za-z]", normalized))
    if cyrillic > latin and cyrillic > 0:
        return "ru"
    if latin > 0:
        return "en"
    return "unknown"
