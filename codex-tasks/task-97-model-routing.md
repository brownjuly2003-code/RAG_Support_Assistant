# Task 97 — RAG QUALITY: Model A/B routing — простые вопросы → fast model

## Goal
Сейчас у нас **одна модель для всех**: `OLLAMA_MODEL_NAME=qwen2.5:7b`
используется на всех узлах (`transform_query`, `grade_docs`, `generate`,
`evaluate`, `verify_facts`). Для простого «как восстановить пароль?»
мы гоняем qwen2.5:7b (большая, 4-8с на CPU). Для сложного «проанализируй
договор X и скажи, как он соотносится с требованием Y» — ту же qwen2.5:7b.

Первое **слишком медленно**. Второе **может не хватать качества** — для
сложных вопросов иногда нужна более крупная модель (llama3:70b через
external API, или Claude Haiku 4.5).

## Решение: классификатор → 2 модели
Дешёвый one-shot prompt перед `transform_query` классифицирует вопрос на
**simple** / **complex**. Узлы `generate` и `evaluate` используют две
разных модели:
- **simple** → `OLLAMA_FAST_MODEL` (default: `llama3.2:3b` — быстрая
  3B-модель, 1-2с на CPU)
- **complex** → `OLLAMA_MODEL_NAME` (текущая qwen2.5:7b)

Остальные узлы (`transform_query`, `grade_docs`, `verify_facts`) всегда
на fast модели — они не требуют большого reasoning.

**Почему это не ломает retrieval:** классификация идёт **до** retrieval,
сам retrieval (BM25 + vector + rerank) на модели не зависит. Меняется
только LLM, которая генерирует ответ.

**Observability**: counter `rag_model_routing_total{complexity}` +
histogram latency по tier'у.

## Files to change
- `config/settings.py` — 2 env-флага
- `graph.py` — новый узел `classify_complexity`, routing в generate/evaluate
- `prompts.py` — 1 prompt для классификатора
- `state.py` — поле `complexity`
- `monitoring/prometheus.py` — 1 counter
- `.env.example`, `README.md`

## Files to create
- `tests/test_model_routing.py` — 5 тестов

---

## 1. `config/settings.py`

```python
    ollama_fast_model_name: str = field(
        default_factory=lambda: os.getenv(
            "OLLAMA_FAST_MODEL_NAME", "llama3.2:3b"
        )
    )
    model_routing_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "MODEL_ROUTING_ENABLED", "false"
        ).strip().lower() in ("1", "true", "yes")
    )
```

**Дефолт false** — feature-flag, безопасный деплой. Включается
`MODEL_ROUTING_ENABLED=true`.

---

## 2. `state.py`

```python
class GraphState(TypedDict, total=False):
    # ... existing ...
    complexity: str  # "simple" | "complex" | "unknown"
```

`create_initial_state` → `complexity="unknown"`.

---

## 3. `prompts.py`

```python
def build_classify_complexity_prompt(question: str) -> str:
    return (
        "Classify the user question as SIMPLE or COMPLEX.\n\n"
        "SIMPLE: factual lookup, single concept, short answer (<5 sentences).\n"
        "  Examples: 'How to reset password?', 'What is X?', 'Where is the Y button?'\n\n"
        "COMPLEX: multi-step reasoning, comparison, analysis, inference,\n"
        "or synthesis across documents.\n"
        "  Examples: 'Compare A and B', 'Explain why X causes Y',\n"
        "            'Analyze this contract against policy Z'\n\n"
        "Output strictly one word: SIMPLE or COMPLEX.\n\n"
        f"Question: {question}\n\nClassification:"
    )
```

---

## 4. `graph.py`

### Новый узел `classify_complexity`

```python
def make_classify_complexity_node(
    classifier_llm: SupportsInvoke,
) -> Callable[[GraphState], GraphState]:
    def node(state: GraphState) -> GraphState:
        if state.get("error"):
            return state
        trace_id = state.get("trace_id", "unknown")
        try:
            from config.settings import get_settings

            settings = get_settings()
            if not getattr(settings, "model_routing_enabled", False):
                new_state = dict(state)
                new_state["complexity"] = "unknown"
                log_step(trace_id, "classify_complexity", new_state)
                return new_state

            question = state.get("question", "")
            prompt = build_classify_complexity_prompt(question)
            raw = classifier_llm.invoke(prompt).strip().upper()
            if raw.startswith("SIMPLE"):
                complexity = "simple"
            elif raw.startswith("COMPLEX"):
                complexity = "complex"
            else:
                complexity = "complex"  # safe default — не ронять качество

            new_state = dict(state)
            new_state["complexity"] = complexity

            try:
                from monitoring.prometheus import record_model_routing
                record_model_routing(complexity)
            except Exception:
                pass

            log_step(trace_id, "classify_complexity", new_state)
            return new_state
        except Exception as exc:
            return _make_error_state(state, "classify_complexity", exc)

    return node
```

### Routing в `generate` и `evaluate`

Обновить `make_generate_node` и `make_evaluate_node`, чтобы они принимали
**двух** LLM-клиентов:

```python
def make_generate_node(
    llm_fast: SupportsInvoke,
    llm_strong: SupportsInvoke,
) -> Callable[[GraphState], GraphState]:
    def node(state: GraphState) -> GraphState:
        # ... существующая логика ...
        complexity = state.get("complexity", "unknown")
        llm = llm_fast if complexity == "simple" else llm_strong
        answer = llm.invoke(prompt)
        # ... rest ...
    return node
```

Аналогично для `evaluate`. `transform_query`, `grade_docs`, `verify_facts`
**всегда** на fast (их prompt'ы короткие, reasoning не нужен).

### Сборка графа

```python
def build_graph(retriever, min_quality: int = 70, max_iterations: int = 2) -> Any:
    from config.settings import get_settings

    settings = get_settings()

    llm_strong = LocalOllamaLLM(model_name=settings.ollama_model_name)
    if settings.model_routing_enabled:
        llm_fast = LocalOllamaLLM(model_name=settings.ollama_fast_model_name)
    else:
        # feature off — обе ссылки указывают на strong
        llm_fast = llm_strong

    workflow = StateGraph(...)
    workflow.add_node("classify_complexity", make_classify_complexity_node(llm_fast))
    workflow.add_node("transform_query", make_transform_query_node(llm_fast))
    workflow.add_node("retrieve", ...)
    workflow.add_node("grade_docs", make_grade_docs_node(llm_fast))
    workflow.add_node("generate", make_generate_node(llm_fast, llm_strong))
    workflow.add_node("verify_facts", make_verify_facts_node(llm_fast))
    workflow.add_node("evaluate", make_evaluate_node(llm_fast, llm_strong))
    # ... rest unchanged ...

    # New edge: classify_complexity → transform_query
    workflow.set_entry_point("classify_complexity")
    workflow.add_edge("classify_complexity", "transform_query")
    # ... rest of edges unchanged ...
```

---

## 5. `monitoring/prometheus.py`

```python
# __all__:
    "MODEL_ROUTING",
    "record_model_routing",

# except ImportError:
    MODEL_ROUTING = _NoopMetric()

# else:
    MODEL_ROUTING = Counter(
        "rag_model_routing_total",
        "Classifier decisions: simple → fast model, complex → strong model",
        ["complexity"],
        registry=REGISTRY,
    )

def record_model_routing(complexity: str) -> None:
    MODEL_ROUTING.labels(complexity=complexity).inc()
```

---

## 6. `.env.example`

```
# Model A/B routing: classifier → fast для простых, strong для сложных
MODEL_ROUTING_ENABLED=false
OLLAMA_FAST_MODEL_NAME=llama3.2:3b
```

## 7. `README.md`

```
| `MODEL_ROUTING_ENABLED` | `false` | включить классификатор и routing simple/complex на разные модели |
| `OLLAMA_FAST_MODEL_NAME` | `llama3.2:3b` | быстрая модель для простых вопросов и utility-узлов |
```

---

## 8. `tests/test_model_routing.py`

```python
"""Тесты classify_complexity + routing."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_classifier_returns_simple_on_simple_question():
    from graph import make_classify_complexity_node
    from state import create_initial_state
    import os
    os.environ["MODEL_ROUTING_ENABLED"] = "true"
    import config.settings as _s
    _s._settings = None

    llm = MagicMock()
    llm.invoke.return_value = "SIMPLE"
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="How to reset password?", trace_id="t")

    out = node(state)
    assert out["complexity"] == "simple"


def test_classifier_returns_complex_on_complex_question():
    from graph import make_classify_complexity_node
    from state import create_initial_state
    import os
    os.environ["MODEL_ROUTING_ENABLED"] = "true"
    import config.settings as _s
    _s._settings = None

    llm = MagicMock()
    llm.invoke.return_value = "COMPLEX"
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="Compare X and Y in detail", trace_id="t")

    out = node(state)
    assert out["complexity"] == "complex"


def test_ambiguous_response_defaults_to_complex():
    """Если классификатор вернул мусор — safer fall back на strong model."""
    from graph import make_classify_complexity_node
    from state import create_initial_state
    import os
    os.environ["MODEL_ROUTING_ENABLED"] = "true"
    import config.settings as _s
    _s._settings = None

    llm = MagicMock()
    llm.invoke.return_value = "something off-script"
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="?", trace_id="t")

    out = node(state)
    assert out["complexity"] == "complex"


def test_routing_disabled_skips_classification(monkeypatch):
    from graph import make_classify_complexity_node
    from state import create_initial_state
    monkeypatch.setenv("MODEL_ROUTING_ENABLED", "false")
    import config.settings as _s
    _s._settings = None

    llm = MagicMock()
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="?", trace_id="t")

    out = node(state)
    assert out["complexity"] == "unknown"
    llm.invoke.assert_not_called()


def test_counter_increments_per_classification():
    from monitoring.prometheus import MODEL_ROUTING, PROMETHEUS_AVAILABLE
    if not PROMETHEUS_AVAILABLE:
        pytest.skip("prometheus_client not installed")

    from graph import make_classify_complexity_node
    from state import create_initial_state
    import os
    os.environ["MODEL_ROUTING_ENABLED"] = "true"
    import config.settings as _s
    _s._settings = None

    def _sum(complexity: str) -> float:
        for m in MODEL_ROUTING.collect():
            for s in m.samples:
                if s.labels.get("complexity") == complexity and s.name.endswith("_total"):
                    return s.value
        return 0.0

    before = _sum("simple")
    llm = MagicMock()
    llm.invoke.return_value = "SIMPLE"
    node = make_classify_complexity_node(llm)
    state = create_initial_state(question="trivial", trace_id="t")
    node(state)
    after = _sum("simple")
    assert after > before
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **189+ passed** (184 + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- `MODEL_ROUTING_ENABLED=false` — `llm_fast = llm_strong`, полное
  отсутствие регрессии.
- Неопределённый вывод классификатора → `complexity="complex"` (safer
  default — лучше потратить 8с и дать качественный ответ, чем 2с на
  galluцинированный).
- Остальные узлы (transform_query, grade_docs, verify_facts) всегда
  на fast — для них big model избыточна.

## DONE WHEN
- [ ] `classify_complexity` узел в начале pipeline
- [ ] `generate` и `evaluate` принимают `llm_fast` и `llm_strong`,
      выбирают по `state["complexity"]`
- [ ] `transform_query`, `grade_docs`, `verify_facts` всегда на fast
- [ ] 2 env-флага в Settings
- [ ] `rag_model_routing_total{complexity}` counter
- [ ] 5 тестов в `tests/test_model_routing.py`
- [ ] `pytest tests/ -v` — 189+ passed
- [ ] `ruff check .` — 0 errors
