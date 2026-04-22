from __future__ import annotations

from typing import Any

import pytest

from utils.retry import is_retryable_error


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code < 400:
            return None
        raise RuntimeError(f"http {self.status_code}")


def _build_provider():
    from llm.providers.mistral import MistralProvider

    return MistralProvider(
        model_name="mistral-small-latest",
        api_key_env="MISTRAL_API_KEY",
        timeout_sec=15.0,
        input_price_per_1m_tokens=0.20,
        output_price_per_1m_tokens=0.60,
    )


def test_mistral_provider_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        _build_provider()


def test_mistral_provider_returns_llm_response_with_usage_and_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(
            payload={
                "choices": [
                    {
                        "message": {"content": "Mistral says hello"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 30,
                },
            },
            headers={
                "x-ratelimit-remaining-requests": "59",
                "x-ratelimit-remaining-tokens": "499000",
            },
        )

    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test-key")
    monkeypatch.setattr("httpx.post", _fake_post)

    provider = _build_provider()
    response = provider.generate(
        [
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Say hello."},
        ],
        tools=[{"type": "function", "function": {"name": "lookup_order"}}],
        temperature=0.2,
        max_tokens=64,
    )

    assert captured["url"] == "https://api.mistral.ai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer mistral-test-key"
    assert captured["json"]["model"] == "mistral-small-latest"
    assert captured["json"]["messages"][0]["role"] == "system"
    assert captured["json"]["messages"][1]["role"] == "user"
    assert captured["json"]["tools"][0]["function"]["name"] == "lookup_order"
    assert captured["json"]["temperature"] == 0.2
    assert captured["json"]["max_tokens"] == 64
    assert response.text == "Mistral says hello"
    assert response.provider == "mistral"
    assert response.model == "mistral-small-latest"
    assert response.input_tokens == 120
    assert response.output_tokens == 30
    assert response.cost_usd == pytest.approx(0.000042)
    assert response.metadata["rate_limit_remaining_requests"] == "59"
    assert response.metadata["rate_limit_remaining_tokens"] == "499000"


def test_mistral_provider_falls_back_to_estimated_output_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test-key")
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: _FakeResponse(
            payload={
                "choices": [
                    {
                        "message": {"content": "fallback text"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10},
            }
        ),
    )

    provider = _build_provider()
    response = provider.generate([{"role": "user", "content": "hello"}])

    assert response.input_tokens == 10
    assert response.output_tokens > 0
    assert response.text == "fallback text"


def test_mistral_provider_maps_rate_limit_to_retryable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test-key")
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: _FakeResponse(
            status_code=429,
            payload={"detail": "rate limited"},
            headers={"retry-after": "1"},
        ),
    )

    provider = _build_provider()

    with pytest.raises(Exception) as exc_info:
        provider.generate([{"role": "user", "content": "hello"}])

    assert is_retryable_error(exc_info.value)


def test_mistral_provider_generate_with_tools_returns_tool_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(
            payload={
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup_order",
                                        "arguments": "{\"order_id\":\"42\"}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 42,
                    "completion_tokens": 7,
                },
            }
        )

    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test-key")
    monkeypatch.setattr("httpx.post", _fake_post)

    provider = _build_provider()
    response = provider.generate_with_tools(
        [{"role": "user", "content": "Проверь заказ #42"}],
        [{"type": "function", "function": {"name": "lookup_order"}}],
    )

    assert captured["json"]["tools"][0]["function"]["name"] == "lookup_order"
    assert response.tool_calls is not None
    assert response.tool_calls[0]["function"]["name"] == "lookup_order"
    assert response.finish_reason == "tool_calls"


def test_mistral_provider_generate_with_schema_returns_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(
            payload={
                "choices": [
                    {
                        "message": {"content": "{\"complexity\":\"simple\"}"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 24,
                    "completion_tokens": 8,
                },
            }
        )

    monkeypatch.setenv("MISTRAL_API_KEY", "mistral-test-key")
    monkeypatch.setattr("httpx.post", _fake_post)

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

    assert captured["json"]["response_format"]["type"] == "json_schema"
    assert response.structured_output == {"complexity": "simple"}
