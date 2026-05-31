from __future__ import annotations

from types import SimpleNamespace

import pytest


def test_parse_doc_grade_batch_text_accepts_embedded_json_and_orders_by_index() -> None:
    import agent.graph as graph

    raw = """
    The relevant documents are:
    {"grades":[
      {"index":2,"relevant":false,"reason":"off topic"},
      {"index":1,"relevant":true,"reason":"answers the question"}
    ]}
    """

    assert graph._parse_doc_grade_batch_text(raw, 2) == [
        (True, "answers the question"),
        (False, "off topic"),
    ]


def test_parse_doc_grade_batch_text_accepts_indexed_plain_text() -> None:
    import agent.graph as graph

    raw = """
    document 2: no
    document 1: yes
    """

    assert graph._parse_doc_grade_batch_text(raw, 2) == [
        (True, ""),
        (False, ""),
    ]


def test_parse_doc_grade_batch_text_rejects_incomplete_grades() -> None:
    import agent.graph as graph

    assert graph._parse_doc_grade_batch_text("document 1: yes", 2) is None


def test_is_knowledge_gap_requires_enough_docs_and_supported_answer() -> None:
    import agent.graph as graph

    assert graph._is_knowledge_gap({"graded_docs": [{"page_content": "one"}]}) is True
    assert graph._is_knowledge_gap(
        {
            "graded_docs": [{"page_content": "one"}, {"page_content": "two"}],
            "factuality_score": 49,
            "answer": "Ответ найден.",
        }
    ) is True
    assert graph._is_knowledge_gap(
        {
            "graded_docs": [{"page_content": "one"}, {"page_content": "two"}],
            "factuality_score": 90,
            "answer": "Недостаточно информации в базе знаний.",
        }
    ) is True
    assert graph._is_knowledge_gap(
        {
            "graded_docs": [{"page_content": "one"}, {"page_content": "two"}],
            "factuality_score": 90,
            "answer": "Возврат доступен в течение 14 дней.",
        }
    ) is False


def test_capture_and_merge_llm_usage_accumulates_tokens_and_cost() -> None:
    import agent.graph as graph

    llm = SimpleNamespace(
        provider_id="fallback-provider",
        model_name="fallback-model",
        last_response=SimpleNamespace(
            provider="mistral",
            model="mistral-small-latest",
            input_tokens="12",
            output_tokens="5",
            cost_usd="0.00042",
        ),
    )

    captured = graph._capture_llm_usage(llm, "generate")

    assert captured["provider_name"] == "mistral"
    assert captured["model_name"] == "mistral-small-latest"
    assert captured["prompt_tokens"] == 12
    assert captured["completion_tokens"] == 5
    assert captured["cost_usd"] == 0.00042
    assert captured["usage_metadata"] == {
        "input_tokens": 12,
        "output_tokens": 5,
        "total_tokens": 17,
    }

    total = graph._new_llm_usage("total")
    graph._merge_llm_usage(total, captured)
    graph._merge_llm_usage(
        total,
        {
            "provider_name": "mistral",
            "model_name": "ministral-3b-latest",
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "cost_usd": 0.0001,
        },
    )

    assert total["model_name"] == "ministral-3b-latest"
    assert total["prompt_tokens"] == 15
    assert total["completion_tokens"] == 7
    assert total["cost_usd"] == pytest.approx(0.00052)
    assert total["usage_metadata"] == {
        "input_tokens": 15,
        "output_tokens": 7,
        "total_tokens": 22,
    }


def test_normalize_tool_call_accepts_direct_and_openai_function_shapes() -> None:
    import agent.graph as graph

    assert graph._normalize_tool_call(
        {"name": " search_kb ", "arguments": {"query": "returns"}}
    ) == ("search_kb", {"query": "returns"})
    assert graph._normalize_tool_call(
        {
            "function": {
                "name": "check_order_status",
                "arguments": '{"order_id": "42"}',
            }
        }
    ) == ("check_order_status", {"order_id": "42"})


def test_normalize_tool_call_rejects_missing_name_and_non_object_arguments() -> None:
    import agent.graph as graph

    assert graph._normalize_tool_call({"arguments": '["not", "an", "object"]'}) == (
        None,
        {},
    )
    assert graph._normalize_tool_call(
        {"function": {"name": "   ", "arguments": "{bad json"}}
    ) == (None, {})


def test_agentic_tool_definitions_keep_expected_contracts() -> None:
    import agent.graph as graph

    tools = graph._agentic_tool_definitions()
    by_name = {item["function"]["name"]: item["function"] for item in tools}

    assert set(by_name) == {"search_kb", "check_order_status", "create_ticket"}
    assert by_name["search_kb"]["parameters"]["required"] == ["query"]
    assert by_name["check_order_status"]["parameters"]["required"] == ["order_id"]
    assert by_name["create_ticket"]["parameters"]["required"] == [
        "summary",
        "priority",
    ]
    assert all(
        item["parameters"]["additionalProperties"] is False
        for item in by_name.values()
    )


def test_llm_capability_detection_uses_flags_and_static_methods() -> None:
    import agent.graph as graph

    class ToolMethodLLM:
        def generate_with_tools(self, messages, tools, **kwargs):
            raise AssertionError("capability detection must not call the method")

    class SchemaMethodLLM:
        def generate_with_schema(self, messages, schema, **kwargs):
            raise AssertionError("capability detection must not call the method")

    class DynamicOnlyLLM:
        def __getattr__(self, name):
            if name == "generate_with_tools":
                return lambda *args, **kwargs: None
            raise AttributeError(name)

    assert graph._llm_supports_tool_use(SimpleNamespace(supports_tool_use=True)) is True
    assert graph._llm_supports_tool_use(ToolMethodLLM()) is True
    assert graph._llm_supports_tool_use(DynamicOnlyLLM()) is False
    assert (
        graph._llm_supports_structured_output(
            SimpleNamespace(supports_structured_output=True)
        )
        is True
    )
    assert graph._llm_supports_structured_output(SchemaMethodLLM()) is True
