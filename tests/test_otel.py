from __future__ import annotations

from types import SimpleNamespace


def test_init_otel_noops_when_disabled(monkeypatch) -> None:
    from tracing import otel as otel_module

    monkeypatch.setattr(otel_module, "_OTEL_INITIALIZED", False, raising=False)
    monkeypatch.setattr(
        otel_module,
        "_ensure_dependencies",
        lambda: (_ for _ in ()).throw(AssertionError("dependencies should not load")),
        raising=False,
    )

    tracer = otel_module.init_otel(
        service_name="rag-support-assistant",
        endpoint="http://collector:4317",
        enabled=False,
    )

    assert tracer is None
    assert otel_module._OTEL_INITIALIZED is False


def test_init_otel_instruments_fastapi_sqlalchemy_httpx_and_redis(monkeypatch) -> None:
    from tracing import otel as otel_module

    calls: dict[str, object] = {}

    class _FakeTraceAPI:
        def set_tracer_provider(self, provider) -> None:
            calls["provider"] = provider

        def get_tracer(self, name: str):
            calls["tracer_name"] = name
            return "fake-tracer"

    class _FakeResource:
        @staticmethod
        def create(attrs: dict[str, object]):
            calls["resource_attrs"] = attrs
            return {"attrs": attrs}

    class _FakeProvider:
        def __init__(self, resource=None) -> None:
            calls["provider_resource"] = resource

        def add_span_processor(self, processor) -> None:
            calls["span_processor"] = processor

    class _FakeProcessor:
        def __init__(self, exporter) -> None:
            calls["exporter"] = exporter

    class _FakeExporter:
        def __init__(self, endpoint: str, insecure: bool = True) -> None:
            calls["endpoint"] = endpoint
            calls["insecure"] = insecure

    class _FastAPIInstrumentor:
        def instrument_app(self, app, **kwargs) -> None:
            calls["fastapi_app"] = app
            calls["fastapi_kwargs"] = kwargs

    class _HTTPXInstrumentor:
        def instrument(self, **kwargs) -> None:
            calls["httpx"] = kwargs or True

    class _RedisInstrumentor:
        def instrument(self, **kwargs) -> None:
            calls["redis"] = kwargs or True

    class _SQLAlchemyInstrumentor:
        def instrument(self, **kwargs) -> None:
            calls["sqlalchemy"] = kwargs

    monkeypatch.setattr(otel_module, "_OTEL_INITIALIZED", False, raising=False)
    monkeypatch.setattr(otel_module, "trace", _FakeTraceAPI(), raising=False)
    monkeypatch.setattr(otel_module, "Resource", _FakeResource, raising=False)
    monkeypatch.setattr(otel_module, "TracerProvider", _FakeProvider, raising=False)
    monkeypatch.setattr(otel_module, "BatchSpanProcessor", _FakeProcessor, raising=False)
    monkeypatch.setattr(otel_module, "OTLPSpanExporter", _FakeExporter, raising=False)
    monkeypatch.setattr(otel_module, "FastAPIInstrumentor", _FastAPIInstrumentor, raising=False)
    monkeypatch.setattr(otel_module, "HTTPXClientInstrumentor", _HTTPXInstrumentor, raising=False)
    monkeypatch.setattr(otel_module, "RedisInstrumentor", _RedisInstrumentor, raising=False)
    monkeypatch.setattr(otel_module, "SQLAlchemyInstrumentor", _SQLAlchemyInstrumentor, raising=False)
    monkeypatch.setattr(otel_module, "_ensure_dependencies", lambda: None, raising=False)

    app = object()
    tracer = otel_module.init_otel(
        service_name="rag-support-assistant",
        endpoint="http://collector:4317",
        enabled=True,
        app=app,
        sqlalchemy_engine="sync-engine",
        request_id_getter=lambda: "req-123",
    )

    assert tracer == "fake-tracer"
    assert calls["endpoint"] == "http://collector:4317"
    assert calls["resource_attrs"] == {"service.name": "rag-support-assistant"}
    assert calls["sqlalchemy"] == {"engine": "sync-engine"}
    assert calls["fastapi_app"] is app
    assert calls["tracer_name"] == "rag-support-assistant"

    hook = calls["fastapi_kwargs"]["server_request_hook"]
    captured: dict[str, object] = {}
    span = SimpleNamespace(
        is_recording=lambda: True,
        set_attribute=lambda key, value: captured.__setitem__(key, value),
    )
    hook(span, {})

    assert captured["request_id"] == "req-123"


def test_graph_key_nodes_emit_manual_spans(monkeypatch) -> None:
    import agent.graph as graph

    class _Span:
        def __init__(self, name: str, collector: list["_Span"]) -> None:
            self.name = name
            self.attributes: dict[str, object] = {}
            self._collector = collector

        def __enter__(self):
            self._collector.append(self)
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

        def set_attribute(self, key: str, value: object) -> None:
            self.attributes[key] = value

    class _Tracer:
        def __init__(self) -> None:
            self.started: list[_Span] = []

        def start_as_current_span(self, name: str):
            return _Span(name, self.started)

    class _Retriever:
        def get_relevant_documents(self, query: str):
            return [
                {
                    "page_content": "Reset the router from the admin panel.",
                    "metadata": {"source": "kb/router-reset", "title": "Router reset"},
                }
            ]

    class _LLM:
        def __init__(self, responses: list[str]) -> None:
            self._responses = iter(responses)
            self._llm = SimpleNamespace(model="test-model")

        def invoke(self, prompt: str) -> str:
            return next(self._responses)

    tracer = _Tracer()
    monkeypatch.setattr(graph, "get_otel_tracer", lambda: tracer, raising=False)
    monkeypatch.setattr(graph, "trace_llm_call", lambda *args, **kwargs: None)

    state = {
        "question": "How do I reset the router?",
        "search_query": "reset router",
        "trace_id": "trace-1",
        "tenant_id": "tenant-acme",
        "complexity": "simple",
    }

    retrieve_node = graph.make_retrieve_node(_Retriever())
    grade_node = graph.make_grade_docs_node(_LLM(["YES"]))
    generate_node = graph.make_generate_node(_LLM(["Use the admin panel [1]"]), _LLM(["unused"]))
    evaluate_node = graph.make_evaluate_node(_LLM(["88"]), _LLM(["unused"]))

    state = retrieve_node(state)
    state = grade_node(state)
    state = generate_node(state)
    state = evaluate_node(state)

    assert [span.name for span in tracer.started] == [
        "rag.retrieve",
        "rag.rerank",
        "rag.generate",
        "rag.evaluate",
    ]
    assert tracer.started[0].attributes["rag.tenant_id"] == "tenant-acme"
    assert tracer.started[0].attributes["rag.num_docs"] == 1
    assert tracer.started[1].attributes["rag.filtered_docs"] == 0
    assert tracer.started[2].attributes["rag.answer_length"] == len("Use the admin panel [1]")
    assert tracer.started[3].attributes["rag.quality_score"] == 88
