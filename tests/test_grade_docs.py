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


def test_grade_docs_preserves_top_retrieval_hit_when_grader_drops_it(
    monkeypatch,
) -> None:
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

    assert result["graded_docs"][0] is top_doc
    assert result["graded_docs"][1] is second_doc
    assert "preserved top-ranked doc" in (result["doc_grade_reason"] or "")


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
