# Task 92 — RAG QUALITY: Fact-verification узел после generate

## Goal
Из `rec.md` §2.2: «Fact verification — нет проверки фактов в сгенерированном
ответе» (LOW priority, но даёт ощутимый quality win).

Сейчас после `generate` у нас `evaluate` (самооценка 0-100 от LLM). Но это
**мета-оценка**: модель сама себе ставит оценку, склонна завышать. Реальных
фактических ошибок она не ловит — классический hallucination'у, когда ответ
выглядит правдоподобно и получает `quality_score=85`, но утверждение
отсутствует в retrieved context.

**Решение:** новый узел `verify_facts` между `generate` и `evaluate`:

1. Извлекает из ответа **атомарные claims** (LLM-prompt'ом).
2. Для каждого claim: проверяет, поддерживается ли он retrieved context'ом
   (LLM sees claim + context → supported/unsupported).
3. Считает долю supported/total → `factuality_score` (0-100).
4. Если < `min_factuality`: route=retry (Self-RAG) или human эскалация.

## Почему это ценно
- Ловит типичные galluцинации, которые `evaluate` пропускает (ответ
  правильный по форме, неправильный по фактам).
- Честно отделяет «качество ответа» (evaluate) от «основанность на
  context'е» (verify_facts).
- Новая метрика `rag_factuality_score` для Grafana → можно смотреть
  тренд доли hallucinated ответов.

## Files to change
- `state.py` — 3 новых поля
- `prompts.py` — 2 новых prompt template'а
- `graph.py` — новый узел + добавление в workflow
- `config/settings.py` — 2 env-флага
- `monitoring/prometheus.py` — Summary для factuality_score
- `.env.example`, `README.md`

## Files to create
- `tests/test_fact_verification.py` — 5 тестов

---

## 1. `state.py`

```python
class GraphState(TypedDict, total=False):
    # ... existing fields ...
    claims: list[dict]           # [{"text": str, "supported": bool, "evidence": str}]
    factuality_score: int        # 0-100, share of supported claims
    fact_verification_skipped: bool  # True если factcheck отключён
```

В `create_initial_state`:
```python
    claims=[],
    factuality_score=0,
    fact_verification_skipped=False,
```

---

## 2. `prompts.py` — 2 новых template

```python
def build_extract_claims_prompt(answer: str) -> str:
    return (
        "You are an assistant that breaks a text into atomic factual claims.\n"
        "A claim is a single, verifiable statement of fact.\n"
        "Ignore greetings, meta-commentary, and hedges.\n"
        "Output each claim on its own line, prefixed with '- '.\n"
        "If there are no factual claims, output 'NONE'.\n\n"
        f"Text:\n{answer}\n\nClaims:"
    )


def build_verify_claim_prompt(claim: str, context: str) -> str:
    return (
        "You are a fact-checker. Decide whether the CLAIM is DIRECTLY supported by the CONTEXT.\n"
        "Answer strictly:\n"
        "  SUPPORTED: <one-line quote or paraphrase from context>\n"
        "  UNSUPPORTED\n"
        "Do not use outside knowledge. If context is silent or ambiguous — UNSUPPORTED.\n\n"
        f"CONTEXT:\n{context}\n\nCLAIM: {claim}\n\nAnswer:"
    )
```

---

## 3. `graph.py` — новый узел

Добавить рядом с другими make_*_node:

```python
def make_verify_facts_node(llm: SupportsInvoke) -> Callable[[GraphState], GraphState]:
    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown")
        try:
            from config.settings import get_settings
            settings = get_settings()
            if not getattr(settings, "fact_verification_enabled", True):
                new_state = dict(state)
                new_state["fact_verification_skipped"] = True
                new_state["factuality_score"] = 100  # не валим route
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            answer = state.get("answer", "")
            docs = state.get("graded_docs") or state.get("context_docs") or []
            context_text = "\n\n".join(
                (d.get("page_content") if isinstance(d, dict) else getattr(d, "page_content", ""))[:500]
                for d in docs[:5]
            )

            if not answer or not context_text:
                new_state = dict(state)
                new_state["fact_verification_skipped"] = True
                new_state["factuality_score"] = 100
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            # Step 1: extract atomic claims
            raw_claims = llm.invoke(build_extract_claims_prompt(answer)).strip()
            if raw_claims.upper().startswith("NONE"):
                new_state = dict(state)
                new_state["claims"] = []
                new_state["factuality_score"] = 100
                log_step(trace_id, "verify_facts", new_state)
                return new_state

            claim_lines = [
                ln.lstrip("- ").strip()
                for ln in raw_claims.splitlines()
                if ln.strip().startswith("-")
            ]
            claim_lines = claim_lines[:10]  # guard

            # Step 2: verify each claim
            claims_result: list[dict] = []
            for claim in claim_lines:
                verdict = llm.invoke(
                    build_verify_claim_prompt(claim, context_text)
                ).strip()
                supported = verdict.upper().startswith("SUPPORTED")
                evidence = ""
                if supported and ":" in verdict:
                    evidence = verdict.split(":", 1)[1].strip()[:200]
                claims_result.append(
                    {"text": claim, "supported": supported, "evidence": evidence}
                )

            # Step 3: score
            if not claims_result:
                factuality = 100
            else:
                factuality = int(
                    100 * sum(1 for c in claims_result if c["supported"]) / len(claims_result)
                )

            new_state = dict(state)
            new_state["claims"] = claims_result
            new_state["factuality_score"] = factuality

            # Prometheus
            try:
                from monitoring.prometheus import FACTUALITY_SCORE
                FACTUALITY_SCORE.observe(factuality)
            except Exception:
                pass

            log_step(trace_id, "verify_facts", new_state)
            return new_state

        except Exception as exc:
            return _make_error_state(state, "verify_facts", exc)

    return node
```

**Вставка в workflow:**

```python
    workflow.add_node("verify_facts", make_verify_facts_node(llm))
    # ... существующие edges ...
    # было: workflow.add_edge("generate", "evaluate")
    # стало:
    workflow.add_edge("generate", "verify_facts")
    workflow.add_edge("verify_facts", "evaluate")
```

**Важно:** `evaluate` теперь видит `factuality_score` в state. Можно
использовать его в `route_or_retry`: если `factuality_score <
min_factuality`, возвращать `route="retry"` (Self-RAG reformulates query).
Но минимальный фикс — пока просто добавить узел, `evaluate` сам решит.
Усиление route — отдельная задача.

---

## 4. `config/settings.py`

```python
    fact_verification_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "FACT_VERIFICATION_ENABLED", "true"
        ).strip().lower() in ("1", "true", "yes")
    )
    fact_verification_min_score: int = field(
        default_factory=lambda: int(os.getenv("FACT_VERIFICATION_MIN_SCORE", "70"))
    )
```

---

## 5. `monitoring/prometheus.py`

```python
# В __all__:
    "FACTUALITY_SCORE",

# В except ImportError:
    FACTUALITY_SCORE = _NoopMetric()

# В else:
    FACTUALITY_SCORE = Summary(
        "rag_factuality_score",
        "Share of answer claims supported by retrieved context (0-100)",
        registry=REGISTRY,
    )
```

---

## 6. `.env.example` + `README.md`

```
FACT_VERIFICATION_ENABLED=true
FACT_VERIFICATION_MIN_SCORE=70
```

README таблица:
```
| `FACT_VERIFICATION_ENABLED` | `true` | включить узел verify_facts после generate |
| `FACT_VERIFICATION_MIN_SCORE` | `70` | минимальный factuality_score для route=auto |
```

---

## 7. `tests/test_fact_verification.py`

```python
"""Тесты verify_facts узла."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_all_supported_claims_give_score_100():
    from graph import make_verify_facts_node
    from state import create_initial_state

    llm = MagicMock()
    llm.invoke.side_effect = [
        "- Python was released in 1991.\n- It is open source.",  # extract
        "SUPPORTED: Python released 1991",  # verify 1
        "SUPPORTED: Python is open source",  # verify 2
    ]
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Python was released in 1991 and is open source."
    state["graded_docs"] = [{"page_content": "Python 1.0 released 1991. Open source."}]

    out = node(state)
    assert out["factuality_score"] == 100
    assert all(c["supported"] for c in out["claims"])


def test_mixed_claims_give_partial_score():
    from graph import make_verify_facts_node
    from state import create_initial_state

    llm = MagicMock()
    llm.invoke.side_effect = [
        "- Python was created by Guido.\n- Python was created in 1987.",
        "SUPPORTED: Python created by Guido",
        "UNSUPPORTED",
    ]
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Python was created by Guido in 1987."
    state["graded_docs"] = [{"page_content": "Python was created by Guido van Rossum."}]

    out = node(state)
    assert out["factuality_score"] == 50


def test_no_claims_answer_scores_100():
    from graph import make_verify_facts_node
    from state import create_initial_state

    llm = MagicMock()
    llm.invoke.return_value = "NONE"
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "Привет! Как дела?"
    state["graded_docs"] = [{"page_content": "anything"}]

    out = node(state)
    assert out["factuality_score"] == 100
    assert out["claims"] == []


def test_disabled_via_settings_skips_verification(monkeypatch):
    from graph import make_verify_facts_node
    from state import create_initial_state
    import config.settings as _s
    monkeypatch.setenv("FACT_VERIFICATION_ENABLED", "false")
    _s._settings = None

    llm = MagicMock()
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "x"
    state["graded_docs"] = [{"page_content": "y"}]

    out = node(state)
    assert out["fact_verification_skipped"] is True
    assert out["factuality_score"] == 100
    llm.invoke.assert_not_called()


def test_llm_error_produces_error_state():
    from graph import make_verify_facts_node
    from state import create_initial_state

    llm = MagicMock()
    llm.invoke.side_effect = RuntimeError("ollama down")
    node = make_verify_facts_node(llm)
    state = create_initial_state(question="?", trace_id="t")
    state["answer"] = "anything"
    state["graded_docs"] = [{"page_content": "y"}]

    out = node(state)
    assert out.get("error") is not None  # _make_error_state set
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **166+ passed** (161 + 5 новых).
- `ruff check .` — 0 errors.
- `FACT_VERIFICATION_ENABLED=false` отключает узел без регрессии.
- Узел ловит свои exception'ы через `_make_error_state` — не падает
  пайплайн полностью.
- Counter atomic-claims capped 10 — защита от pathological ответов.

## DONE WHEN
- [ ] `verify_facts` узел реализован и вставлен между `generate` и `evaluate`
- [ ] `claims`, `factuality_score`, `fact_verification_skipped` в GraphState
- [ ] 2 новых prompt в prompts.py
- [ ] 2 env-флага в Settings
- [ ] `rag_factuality_score` Summary в prometheus
- [ ] 5 тестов в `tests/test_fact_verification.py`
- [ ] `pytest tests/ -v` — 166+ passed
- [ ] `ruff check .` — 0 errors
