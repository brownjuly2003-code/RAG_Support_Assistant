from __future__ import annotations

from types import SimpleNamespace

from agent.state import create_initial_state


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
        profile_name="latency-first",
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
