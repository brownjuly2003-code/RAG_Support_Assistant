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
