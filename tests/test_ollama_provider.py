from __future__ import annotations

import asyncio
import sys
import types
from types import SimpleNamespace
from typing import Any


def _build_provider():
    from llm.providers.ollama import OllamaProvider

    return OllamaProvider(
        model_name="qwen2.5:7b",
        base_url="http://ollama.test",
        timeout_sec=15.0,
        input_price_per_1m_tokens=0.0,
        output_price_per_1m_tokens=0.0,
    )


def test_ollama_provider_generate_with_tools_returns_tool_calls(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeBoundChat:
        def invoke(self, prompt: str):
            captured["prompt"] = prompt
            return SimpleNamespace(
                content="",
                tool_calls=[
                    {
                        "name": "lookup_order",
                        "args": {"order_id": "42"},
                    }
                ],
                response_metadata={"done_reason": "tool_calls"},
            )

    class _FakeChatOllama:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        def bind_tools(self, tools):
            captured["tools"] = tools
            return _FakeBoundChat()

    fake_module = types.ModuleType("langchain_ollama")
    fake_module.ChatOllama = _FakeChatOllama
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_module)

    provider = _build_provider()
    response = provider.generate_with_tools(
        [{"role": "user", "content": "Проверь заказ #42"}],
        [{"type": "function", "function": {"name": "lookup_order"}}],
    )

    assert captured["init"]["model"] == "qwen2.5:7b"
    assert captured["tools"][0]["function"]["name"] == "lookup_order"
    assert "Проверь заказ #42" in captured["prompt"]
    assert response.tool_calls is not None
    assert response.tool_calls[0]["name"] == "lookup_order"
    assert response.finish_reason == "tool_calls"


def test_ollama_provider_generate_with_schema_returns_structured_output(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeOllamaLLM:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        def invoke(self, prompt: str) -> str:
            captured["prompt"] = prompt
            return '{"complexity":"simple"}'

    fake_module = types.ModuleType("langchain_ollama")
    fake_module.OllamaLLM = _FakeOllamaLLM
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_module)

    provider = _build_provider()
    response = provider.generate_with_schema(
        [{"role": "user", "content": "Определи сложность"}],
        {
            "type": "object",
            "properties": {
                "complexity": {
                    "type": "string",
                    "enum": ["simple", "complex"],
                }
            },
            "required": ["complexity"],
            "additionalProperties": False,
        },
    )

    assert captured["init"]["model"] == "qwen2.5:7b"
    assert "JSON" in captured["prompt"]
    assert "complexity" in captured["prompt"]
    assert response.structured_output == {"complexity": "simple"}


def test_ollama_provider_generate_stream_yields_multiple_chunks(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    class _FakeOllamaLLM:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        async def astream(self, prompt: str):
            captured["prompt"] = prompt
            yield "Сброс "
            yield SimpleNamespace(content="пароля")

    fake_module = types.ModuleType("langchain_ollama")
    fake_module.OllamaLLM = _FakeOllamaLLM
    monkeypatch.setitem(sys.modules, "langchain_ollama", fake_module)

    provider = _build_provider()

    async def _collect() -> list[str]:
        return [chunk async for chunk in provider.generate_stream([{"role": "user", "content": "Как восстановить доступ?"}])]

    chunks = asyncio.run(_collect())

    assert captured["init"]["base_url"] == "http://ollama.test"
    assert "Как восстановить доступ?" in captured["prompt"]
    assert chunks == ["Сброс ", "пароля"]
