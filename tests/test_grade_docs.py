from __future__ import annotations

import logging

from agent.state import create_initial_state
from llm.providers import LLMResponse


def test_grade_docs_accepts_mistral_tool_payload_with_extra_type(
    monkeypatch,
    caplog,
) -> None:
    import agent.graph as graph

    class _MistralSchemaLLM:
        provider_id = "mistral"
        model_name = "mistral-small-latest"
        supports_structured_output = True

        def generate_with_schema(self, messages, schema, **kwargs):
            _ = messages, kwargs
            payload = {"type": "object", "relevant": False}
            properties = schema.get("properties") if isinstance(schema.get("properties"), dict) else {}
            if schema.get("additionalProperties") is False and "type" not in properties:
                raise ValueError("$.type is not allowed")
            for field_name in schema.get("required") or []:
                if field_name not in payload:
                    raise ValueError(f"$.{field_name} is required")
            return LLMResponse(
                text='{"type": "object", "relevant": false}',
                provider=self.provider_id,
                model=self.model_name,
                structured_output=payload,
            )

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda trace_id, node_name, state: None)

    node = graph.make_grade_docs_node(_MistralSchemaLLM())
    state = create_initial_state(question="Как оформить возврат?", trace_id="trace-mistral-grade")
    state["context_docs"] = [
        {
            "page_content": "Этот фрагмент только про установку приложения.",
            "metadata": {"source": "install.md"},
        }
    ]

    with caplog.at_level(logging.WARNING, logger="agent.graph"):
        result = node(state)

    assert result["graded_docs"] == []
    assert "filtered 1" in (result["doc_grade_reason"] or "")
    assert "[grade_docs] LLM error" not in caplog.text


def test_grade_docs_does_not_force_top_hit_after_rejection(
    monkeypatch,
) -> None:
    """Plan §5.3: no silent top-1 restore when grader rejects rank-1."""
    import agent.graph as graph

    class _SequencedSchemaLLM:
        provider_id = "mistral"
        model_name = "ministral-3b-latest"
        supports_structured_output = True

        def __init__(self) -> None:
            self.relevance = iter([False, True])

        def generate_with_schema(self, messages, schema, **kwargs):
            _ = messages, schema, kwargs
            if "grades" in (schema.get("properties") or {}):
                return LLMResponse(
                    text='{"grades":[{"index":1,"relevant":false},{"index":2,"relevant":true}]}',
                    provider=self.provider_id,
                    model=self.model_name,
                    structured_output={
                        "grades": [
                            {"index": 1, "relevant": False},
                            {"index": 2, "relevant": True},
                        ]
                    },
                )
            relevant = next(self.relevance)
            return LLMResponse(
                text=f'{{"relevant": {str(relevant).lower()}}}',
                provider=self.provider_id,
                model=self.model_name,
                structured_output={"relevant": relevant},
            )

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda trace_id, node_name, state: None)

    node = graph.make_grade_docs_node(_SequencedSchemaLLM())
    state = create_initial_state(
        question="В течение скольких дней можно вернуть товар надлежащего качества?",
        trace_id="trace-grade-top-hit",
    )
    top_doc = {
        "page_content": "Покупатель имеет право вернуть товар надлежащего качества в течение 14 дней.",
        "metadata": {"source": "returns_policy.md"},
    }
    second_doc = {
        "page_content": "Документ про ошибки E10 и E30.",
        "metadata": {"source": "errors_e10_e30.md"},
    }
    state["context_docs"] = [top_doc, second_doc]

    result = node(state)

    assert top_doc not in result["graded_docs"]
    assert result["graded_docs"] == [second_doc]
    assert "preserved top-ranked doc" not in (result["doc_grade_reason"] or "")
    assert result.get("doc_grade_outcome") == "ok"


def test_grade_docs_uses_same_source_content_when_only_context_header_is_relevant(
    monkeypatch,
) -> None:
    """A relevant contextual header represents its content-bearing source chunk."""
    import agent.graph as graph

    class _HeaderOnlyRelevantLLM:
        provider_id = "mistral"
        model_name = "ministral-3b-latest"
        supports_structured_output = True

        def generate_with_schema(self, messages, schema, **kwargs):
            _ = messages, schema, kwargs
            return LLMResponse(
                text='{"grades":[{"index":1,"relevant":true},{"index":2,"relevant":false}]}',
                provider=self.provider_id,
                model=self.model_name,
                structured_output={
                    "grades": [
                        {"index": 1, "relevant": True},
                        {"index": 2, "relevant": False},
                    ]
                },
            )

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda trace_id, node_name, state: None)

    node = graph.make_grade_docs_node(_HeaderOnlyRelevantLLM())
    state = create_initial_state(
        question="Какие узлы проверить при E20: фильтр, шланг или насос?",
        trace_id="trace-grade-e20-header-body",
    )
    shared_metadata = {
        "source": "errors_e10_e30.md",
        "content_hash": "same-logical-document",
        "contextual_header": "Из документа errors_e10_e30.md",
        "has_context_header": True,
    }
    header_doc = {
        "page_content": "[Контекст: Из документа errors_e10_e30.md]\n",
        "metadata": dict(shared_metadata),
    }
    content_doc = {
        "page_content": (
            "[Контекст: Из документа errors_e10_e30.md]\n"
            "E20 — проблема со сливом: проверьте фильтр, шланг и насос."
        ),
        "metadata": dict(shared_metadata),
    }
    state["context_docs"] = [header_doc, content_doc]

    result = node(state)

    assert result["graded_docs"] == [content_doc]
    assert header_doc not in result["graded_docs"]
    assert result["doc_grade_reason"] == "Kept 1/2, filtered 1"


def test_grade_docs_e30_saved_five_document_verdict_keeps_disconnect_instruction(
    monkeypatch,
) -> None:
    """QG-04: replay the retained header-only verdict among five documents."""
    import agent.graph as graph

    class _SavedE30VerdictLLM:
        provider_id = "mistral"
        model_name = "ministral-3b-latest"
        supports_structured_output = True

        def generate_with_schema(self, messages, schema, **kwargs):
            _ = messages, schema, kwargs
            payload = {
                "grades": [
                    {"index": 1, "relevant": False},
                    {"index": 2, "relevant": True},
                    {"index": 3, "relevant": False},
                    {"index": 4, "relevant": False},
                    {"index": 5, "relevant": False},
                ]
            }
            return LLMResponse(
                text=str(payload),
                provider=self.provider_id,
                model=self.model_name,
                structured_output=payload,
            )

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda trace_id, node_name, state: None)

    errors_metadata = {
        "source": "errors_e10_e30.md",
        "content_hash": "errors-document",
        "contextual_header": "Из документа errors_e10_e30.md",
        "has_context_header": True,
    }
    errors_header = {
        "page_content": "[Контекст: Из документа errors_e10_e30.md]\n",
        "metadata": dict(errors_metadata),
    }
    errors_body = {
        "page_content": (
            "[Контекст: Из документа errors_e10_e30.md]\n"
            "E30 — критическая системная ошибка. "
            "Отключите устройство от сети и обратитесь в сервисный центр."
        ),
        "metadata": dict(errors_metadata),
    }
    state = create_initial_state(
        question=(
            "При ошибке E30 можно продолжать пользоваться устройством "
            "или нужно отключить его от сети?"
        ),
        trace_id="trace-grade-e30-five-doc-replay",
    )
    state["context_docs"] = [
        {
            "page_content": "[Контекст: Из документа returns_policy.md]\n",
            "metadata": {"source": "returns_policy.md", "content_hash": "returns"},
        },
        errors_header,
        errors_body,
        {
            "page_content": "Правила возврата товара.",
            "metadata": {"source": "returns_policy.md", "content_hash": "returns"},
        },
        {
            "page_content": "Порядок гарантийного обращения.",
            "metadata": {"source": "warranty.md", "content_hash": "warranty"},
        },
    ]

    result = graph.make_grade_docs_node(_SavedE30VerdictLLM())(state)

    assert result["graded_docs"] == [errors_body]
    assert "Отключите устройство от сети" in result["graded_docs"][0]["page_content"]
    assert result["doc_grade_reason"] == "Kept 1/5, filtered 4"


def test_grade_docs_batches_multiple_documents_with_schema(
    monkeypatch,
) -> None:
    import agent.graph as graph

    class _BatchSchemaLLM:
        provider_id = "mistral"
        model_name = "mistral-small-latest"
        supports_structured_output = True

        def __init__(self) -> None:
            self.schema_calls = 0

        def generate_with_schema(self, messages, schema, **kwargs):
            _ = messages, schema, kwargs
            self.schema_calls += 1
            return LLMResponse(
                text='{"grades":[{"index":1,"relevant":true},{"index":2,"relevant":false}]}',
                provider=self.provider_id,
                model=self.model_name,
                structured_output={
                    "grades": [
                        {"index": 1, "relevant": True, "reason": "answers the question"},
                        {"index": 2, "relevant": False, "reason": "off topic"},
                    ]
                },
            )

        def invoke(self, prompt: str) -> str:
            raise AssertionError(f"unexpected per-document grade call: {prompt}")

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda trace_id, node_name, state: None)

    llm = _BatchSchemaLLM()
    node = graph.make_grade_docs_node(llm)
    state = create_initial_state(question="Как оформить возврат?", trace_id="trace-batch-grade")
    relevant_doc = {
        "page_content": "Возврат оформляется через форму возврата в личном кабинете.",
        "metadata": {"source": "returns_policy.md"},
    }
    irrelevant_doc = {
        "page_content": "Ошибка E30 означает проблему с обновлением прошивки.",
        "metadata": {"source": "errors_e10_e30.md"},
    }
    state["context_docs"] = [relevant_doc, irrelevant_doc]

    result = node(state)

    assert result["graded_docs"] == [relevant_doc]
    assert "filtered 1" in (result["doc_grade_reason"] or "")
    assert llm.schema_calls == 1
