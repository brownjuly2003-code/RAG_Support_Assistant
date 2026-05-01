from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _reset_langfuse_state():
    from tracing import langfuse_trace

    langfuse_trace._langfuse = None
    yield
    langfuse_trace._langfuse = None


def test_get_langfuse_returns_none_without_configured_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tracing import langfuse_trace

    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            langfuse_public_key="",
            langfuse_secret_key="",
            langfuse_host="http://langfuse.test",
        ),
    )

    assert langfuse_trace.get_langfuse() is None


def test_trace_llm_call_uses_start_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tracing import langfuse_trace

    calls: dict[str, Any] = {}

    class _Generation:
        def end(self) -> None:
            calls["ended"] = True

    class _Langfuse:
        def __init__(self, *, public_key: str, secret_key: str, host: str) -> None:
            calls["init"] = (public_key, secret_key, host)

        def start_observation(self, **kwargs: Any) -> _Generation:
            calls["observation"] = kwargs
            return _Generation()

    monkeypatch.setitem(sys.modules, "langfuse", SimpleNamespace(Langfuse=_Langfuse))
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(
            langfuse_public_key="public",
            langfuse_secret_key="secret",
            langfuse_host="http://langfuse.test",
        ),
    )

    langfuse_trace.trace_llm_call(
        "trace-1",
        "grade",
        "p" * 6000,
        "r" * 6000,
        duration_ms=12.5,
    )

    assert calls["init"] == ("public", "secret", "http://langfuse.test")
    assert calls["ended"] is True
    observation = calls["observation"]
    assert observation["name"] == "grade"
    assert observation["as_type"] == "generation"
    assert observation["model"] is None
    assert len(observation["input"]) == 5000
    assert len(observation["output"]) == 5000
    assert observation["metadata"] == {
        "duration_ms": 12.5,
        "pipeline": "rag-pipeline",
        "sqlite_trace_id": "trace-1",
    }


def test_trace_llm_call_start_observation_metadata_includes_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tracing import langfuse_trace

    calls: dict[str, Any] = {}

    class _Generation:
        def end(self) -> None:
            return None

    class _Langfuse:
        def start_observation(self, **kwargs: Any) -> _Generation:
            calls["observation"] = kwargs
            return _Generation()

    tool_calls = [{"name": "search_kb", "arguments": {"query": "returns"}}]
    monkeypatch.setattr(langfuse_trace, "get_langfuse", lambda: _Langfuse())

    langfuse_trace.trace_llm_call(
        "trace-2",
        "agentic",
        "prompt",
        "response",
        tool_calls=tool_calls,
    )

    assert calls["observation"]["metadata"]["tool_calls"] == tool_calls


def test_trace_llm_call_tool_calls_metadata_isolated_from_later_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tracing import langfuse_trace

    calls: dict[str, Any] = {}

    class _Generation:
        def end(self) -> None:
            return None

    class _Langfuse:
        def start_observation(self, **kwargs: Any) -> _Generation:
            calls["metadata"] = kwargs["metadata"]
            return _Generation()

    tool_calls = [{"name": "search_kb", "arguments": {"query": "returns"}}]
    monkeypatch.setattr(langfuse_trace, "get_langfuse", lambda: _Langfuse())

    langfuse_trace.trace_llm_call(
        "trace-2",
        "agentic",
        "prompt",
        "response",
        tool_calls=tool_calls,
    )
    tool_calls[0]["arguments"]["query"] = "mutated"

    assert calls["metadata"]["tool_calls"] == [
        {"name": "search_kb", "arguments": {"query": "returns"}}
    ]


def test_trace_llm_call_uses_legacy_trace_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tracing import langfuse_trace

    calls: dict[str, Any] = {}

    class _Trace:
        def generation(self, **kwargs: Any) -> None:
            calls["generation"] = kwargs

    class _Langfuse:
        def trace(self, *, id: str, name: str) -> _Trace:
            calls["trace"] = {"id": id, "name": name}
            return _Trace()

    monkeypatch.setattr(langfuse_trace, "get_langfuse", lambda: _Langfuse())

    langfuse_trace.trace_llm_call("", "node", "prompt", "response", model="mistral")

    assert calls["trace"]["name"] == "rag-pipeline"
    assert len(calls["trace"]["id"]) == 32
    assert calls["generation"]["name"] == "node"
    assert calls["generation"]["model"] == "mistral"
    assert calls["generation"]["input"] == "prompt"
    assert calls["generation"]["output"] == "response"
    assert calls["generation"]["metadata"]["sqlite_trace_id"] == ""


def test_trace_llm_call_legacy_metadata_includes_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tracing import langfuse_trace

    calls: dict[str, Any] = {}

    class _Trace:
        def generation(self, **kwargs: Any) -> None:
            calls["generation"] = kwargs

    class _Langfuse:
        def trace(self, *, id: str, name: str) -> _Trace:
            calls["trace"] = {"id": id, "name": name}
            return _Trace()

    tool_calls = ["search_kb", "check_order_status"]
    monkeypatch.setattr(langfuse_trace, "get_langfuse", lambda: _Langfuse())

    langfuse_trace.trace_llm_call(
        "trace-3",
        "agentic",
        "prompt",
        "response",
        tool_calls=tool_calls,
    )

    assert calls["generation"]["metadata"]["tool_calls"] == tool_calls


def test_trace_llm_call_logs_warning_on_backend_error(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from tracing import langfuse_trace

    class _Langfuse:
        def trace(self, *, id: str, name: str) -> object:
            _ = id, name
            raise RuntimeError("trace failed")

    monkeypatch.setattr(langfuse_trace, "get_langfuse", lambda: _Langfuse())

    langfuse_trace.trace_llm_call("trace-1", "node", "prompt", "response")

    assert "Langfuse trace failed: trace failed" in caplog.text


def test_flush_prefers_shutdown_and_falls_back_to_flush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tracing import langfuse_trace

    calls: list[str] = []

    class _WithShutdown:
        def shutdown(self) -> None:
            calls.append("shutdown")

    class _WithFlush:
        def flush(self) -> None:
            calls.append("flush")

    monkeypatch.setattr(langfuse_trace, "get_langfuse", lambda: _WithShutdown())
    langfuse_trace.flush()
    monkeypatch.setattr(langfuse_trace, "get_langfuse", lambda: _WithFlush())
    langfuse_trace.flush()

    assert calls == ["shutdown", "flush"]
