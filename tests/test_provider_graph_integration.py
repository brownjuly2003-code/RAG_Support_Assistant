from __future__ import annotations

from types import SimpleNamespace

from agent.state import create_initial_state
from llm.providers import LLMResponse


def test_build_support_graph_uses_provider_runtime_when_llm_missing(
    monkeypatch,
) -> None:
    import agent.graph as graph

    captured: dict[str, object] = {}

    class _FakeWorkflow:
        def __init__(self, *_args, **_kwargs) -> None:
            self.nodes: list[tuple[str, object]] = []

        def add_node(self, name: str, node) -> None:
            self.nodes.append((name, node))

        def set_entry_point(self, _name: str) -> None:
            return None

        def add_edge(self, *_args, **_kwargs) -> None:
            return None

        def add_conditional_edges(self, *_args, **_kwargs) -> None:
            return None

        def compile(self):
            return self

    runtime = SimpleNamespace(
        profile_name="local-first",
        fast=SimpleNamespace(invoke=lambda prompt: "SIMPLE", provider_id="ollama", model_name="qwen2.5:7b"),
        strong=SimpleNamespace(invoke=lambda prompt: "SIMPLE", provider_id="ollama", model_name="qwen2.5:7b"),
    )

    monkeypatch.setattr(graph, "StateGraph", _FakeWorkflow)
    monkeypatch.setattr(graph, "build_provider_runtime", lambda settings: captured.setdefault("runtime", runtime))
    monkeypatch.setattr("config.settings.get_settings", lambda: SimpleNamespace(quality_threshold=80))

    graph.build_support_graph(retriever=object(), llm=None)

    assert captured["runtime"] is runtime


def test_make_generate_node_copies_provider_response_metadata_into_state(
    monkeypatch,
) -> None:
    import agent.graph as graph
    from llm.providers import LLMProvider, LLMResponse, ProviderBackedLLM

    class _FakeProvider(LLMProvider):
        provider_id = "fake"
        model_name = "fake-model"

        def generate(self, messages, tools=None, **kwargs):
            _ = messages, tools, kwargs
            return LLMResponse(
                text="Provider answer [1]",
                provider="fake",
                model="fake-model",
                input_tokens=12,
                output_tokens=6,
                cost_usd=0.000123,
            )

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda trace_id, node_name, state: None)

    llm = ProviderBackedLLM(_FakeProvider())
    node = graph.make_generate_node(llm, llm)
    state = create_initial_state(question="How to reset router?", trace_id="trace-provider-1")
    state["graded_docs"] = [
        {
            "page_content": "Hold reset for ten seconds.",
            "metadata": {"source": "kb://router-reset", "doc_id": "router-reset"},
        }
    ]
    state["complexity"] = "simple"

    result = node(state)

    assert result["answer"] == "Provider answer [1]"
    assert result["provider_name"] == "fake"
    assert result["model_name"] == "fake-model"
    assert result["prompt_tokens"] == 12
    assert result["completion_tokens"] == 6
    assert result["cost_usd"] == 0.000123
    assert result["usage_metadata"]["input_tokens"] == 12
    assert result["usage_metadata"]["output_tokens"] == 6


def test_classify_complexity_node_uses_generate_with_schema_when_available(
    monkeypatch,
) -> None:
    import agent.graph as graph

    class _SchemaLLM:
        provider_id = "gracekelly"
        model_name = "mistral-small"
        supports_structured_output = True

        def __init__(self) -> None:
            self.last_response = None
            self.calls: list[tuple[list[dict[str, object]], dict[str, object]]] = []

        def generate_with_schema(self, messages, schema, **kwargs):
            self.calls.append((list(messages), dict(kwargs)))
            response = LLMResponse(
                text='{"complexity":"simple"}',
                provider=self.provider_id,
                model=self.model_name,
                structured_output={"complexity": "simple"},
                input_tokens=8,
                output_tokens=2,
            )
            self.last_response = response
            return response

    monkeypatch.setattr("config.settings.get_settings", lambda: SimpleNamespace(model_routing_enabled=True))
    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda trace_id, node_name, state: None)

    llm = _SchemaLLM()
    node = graph.make_classify_complexity_node(llm)
    state = create_initial_state(question="Need routing", trace_id="trace-schema-1")

    result = node(state)

    assert llm.calls
    assert result["complexity"] == "simple"
    assert result["usage_metadata"]["input_tokens"] == 8


def test_grade_docs_node_uses_generate_with_schema_when_available(
    monkeypatch,
) -> None:
    import agent.graph as graph

    class _SchemaLLM:
        provider_id = "gracekelly"
        model_name = "mistral-small"
        supports_structured_output = True

        def __init__(self) -> None:
            self.last_response = None

        def generate_with_schema(self, messages, schema, **kwargs):
            _ = messages, schema, kwargs
            response = LLMResponse(
                text='{"relevant": false, "reason": "off-topic"}',
                provider=self.provider_id,
                model=self.model_name,
                structured_output={"relevant": False, "reason": "off-topic"},
            )
            self.last_response = response
            return response

    monkeypatch.setattr(graph, "trace_llm_call", lambda **kwargs: None)
    monkeypatch.setattr(graph, "log_step", lambda trace_id, node_name, state: None)

    llm = _SchemaLLM()
    node = graph.make_grade_docs_node(llm)
    state = create_initial_state(question="Как сделать возврат?", trace_id="trace-schema-2")
    state["context_docs"] = [
        {
            "page_content": "Этот документ только про доставку.",
            "metadata": {"source": "shipping.md"},
        }
    ]

    result = node(state)

    assert result["graded_docs"] == []
    assert "filtered 1" in (result["doc_grade_reason"] or "")


def test_verify_facts_node_uses_consensus_schema_when_enabled(
    monkeypatch,
) -> None:
    import agent.graph as graph

    captured_metrics: list[tuple[str, str]] = []

    class _Metric:
        def labels(self, *, level: str, verdict: str):
            captured_metrics.append((level, verdict))
            return self

        def inc(self) -> None:
            return None

    class _ConsensusLLM:
        provider_id = "gracekelly"
        model_name = "claude-sonnet-4-6-api"
        supports_structured_output = True

        def __init__(self) -> None:
            self.last_response = None
            self.schema_calls: list[dict[str, object]] = []
            self._invoke_calls = 0

        def invoke(self, prompt: str) -> str:
            _ = prompt
            self._invoke_calls += 1
            if self._invoke_calls == 1:
                return "- Возврат доступен 14 дней."
            raise AssertionError("plain-text verification should be bypassed in consensus mode")

        def generate_with_schema(self, messages, schema, **kwargs):
            _ = messages, schema
            self.schema_calls.append(dict(kwargs))
            response = LLMResponse(
                text='{"supported": true, "evidence": "Возврат доступен 14 дней."}',
                provider=self.provider_id,
                model=self.model_name,
                structured_output={
                    "supported": True,
                    "evidence": "Возврат доступен 14 дней.",
                },
            )
            self.last_response = response
            return response

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            fact_verification_enabled=True,
            fact_verify_consensus_enabled=True,
            fact_verify_reliability_level="standard",
        ),
    )
    monkeypatch.setattr(graph, "log_step", lambda trace_id, node_name, state: None)
    monkeypatch.setattr("monitoring.prometheus.FACT_VERIFICATION_CONSENSUS_TOTAL", _Metric())

    llm = _ConsensusLLM()
    node = graph.make_verify_facts_node(llm)
    state = create_initial_state(question="Какие правила возврата?", trace_id="trace-consensus-1")
    state["answer"] = "Возврат доступен 14 дней."
    state["graded_docs"] = [
        {
            "page_content": "Возврат товара возможен в течение 14 дней.",
            "metadata": {"source": "returns.md"},
        }
    ]

    result = node(state)

    assert llm.schema_calls
    assert llm.schema_calls[0]["reliability_level"] == "standard"
    assert result["factuality_score"] == 100
    assert captured_metrics == [("standard", "supported")]
