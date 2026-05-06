from __future__ import annotations

import asyncio
from typing import Any

import pytest


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
    from llm.providers.gracekelly import GraceKellyProvider

    return GraceKellyProvider(
        model_name="mistral-small",
        base_url="http://127.0.0.1:8011",
        api_key_env="GRACEKELLY_API_KEY",
        timeout_sec=30.0,
        health_check_timeout_sec=2.0,
        input_price_per_1m_tokens=0.0,
        output_price_per_1m_tokens=0.0,
    )


def test_gracekelly_provider_generates_answer_after_ready_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {"health": 0}

    def _fake_get(url: str, *, timeout: float):
        captured["health"] += 1
        captured["health_url"] = url
        captured["health_timeout"] = timeout
        return _FakeResponse(status_code=200)

    def _fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float):
        captured["post_url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(
            payload={
                "answer": "GraceKelly answer",
                "task_type": "support",
                "complexity_level": "simple",
                "pattern_used": "single_call",
                "reliability_level": "quick",
                "was_decomposed": False,
                "used_consensus": False,
                "used_roles": False,
                "total_llm_calls": 1,
                "model_id": "mistral-small",
            }
        )

    monkeypatch.delenv("GRACEKELLY_API_KEY", raising=False)
    monkeypatch.setattr("httpx.get", _fake_get)
    monkeypatch.setattr("httpx.post", _fake_post)

    provider = _build_provider()
    response = provider.generate([{"role": "user", "content": "hello"}])

    assert captured["health"] == 1
    assert captured["health_url"] == "http://127.0.0.1:8011/healthz/ready"
    assert captured["post_url"] == "http://127.0.0.1:8011/api/v1/orchestrate"
    assert captured["json"]["model"] == "mistral-small"
    assert captured["json"]["requested_models"] == ["mistral-small"]
    assert captured["json"]["reliability_level"] == "quick"
    assert "USER:\nhello" in captured["json"]["prompt"]
    assert response.text == "GraceKelly answer"
    assert response.provider == "gracekelly"
    assert response.model == "mistral-small"
    assert response.cost_usd == 0.0
    assert response.metadata["total_llm_calls"] == 1
    assert response.metadata["task_type"] == "support"


def test_gracekelly_provider_adds_authorization_header_when_api_key_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setenv("GRACEKELLY_API_KEY", "secret-key")
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _FakeResponse(status_code=200))
    monkeypatch.setattr(
        "httpx.post",
        lambda url, *, headers, json, timeout: captured.setdefault(
            "response",
            _FakeResponse(
                payload={
                    "answer": "ok",
                    "task_type": "support",
                    "complexity_level": "simple",
                    "pattern_used": "single_call",
                    "reliability_level": "quick",
                    "was_decomposed": False,
                    "used_consensus": False,
                    "used_roles": False,
                    "total_llm_calls": 1,
                    "model_id": "mistral-small",
                },
                headers={"captured-authorization": headers.get("Authorization", "")},
            ),
        ),
    )

    provider = _build_provider()
    provider.generate([{"role": "user", "content": "hello"}])

    assert captured["response"].headers["captured-authorization"] == "Bearer secret-key"


def test_gracekelly_provider_skips_authorization_header_when_api_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float):
        _ = url, json, timeout
        captured["headers"] = headers
        return _FakeResponse(
            payload={
                "answer": "ok",
                "task_type": "support",
                "complexity_level": "simple",
                "pattern_used": "single_call",
                "reliability_level": "quick",
                "was_decomposed": False,
                "used_consensus": False,
                "used_roles": False,
                "total_llm_calls": 1,
                "model_id": "mistral-small",
            }
        )

    monkeypatch.delenv("GRACEKELLY_API_KEY", raising=False)
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _FakeResponse(status_code=200))
    monkeypatch.setattr("httpx.post", _fake_post)

    provider = _build_provider()
    provider.generate([{"role": "user", "content": "hello"}])

    assert "Authorization" not in captured["headers"]


def test_gracekelly_provider_raises_provider_unavailable_when_ready_check_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llm.providers.base import ProviderUnavailable

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _FakeResponse(status_code=503))

    provider = _build_provider()

    with pytest.raises(ProviderUnavailable):
        provider.generate([{"role": "user", "content": "hello"}])


def test_gracekelly_provider_raises_provider_unavailable_when_orchestrate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llm.providers.base import ProviderUnavailable

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _FakeResponse(status_code=200))
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: _FakeResponse(
            payload={
                "status": "failed",
                "failure_code": "provider_unavailable",
                "failure_message": "Adapter circuit breaker is open.",
            }
        ),
    )

    provider = _build_provider()

    with pytest.raises(ProviderUnavailable) as exc_info:
        provider.generate([{"role": "user", "content": "hello"}])

    assert exc_info.value.reason == "provider_unavailable"
    assert "Adapter circuit breaker is open." in str(exc_info.value)


def test_gracekelly_provider_stream_raises_provider_unavailable_when_orchestrate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from llm.providers.base import ProviderUnavailable

    class _FakeStreamResponse:
        def raise_for_status(self) -> None:
            return None

        async def __aenter__(self) -> "_FakeStreamResponse":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            _ = exc_type, exc, tb

        async def aiter_lines(self):
            yield (
                'data: {"status": "failed", "failure_code": "provider_unavailable", '
                '"failure_message": "Adapter circuit breaker is open."}'
            )

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "_FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            _ = exc_type, exc, tb

        def stream(self, method: str, url: str, *, headers: dict[str, str], json: dict[str, Any]):
            _ = method, url, headers, json
            return _FakeStreamResponse()

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _FakeResponse(status_code=200))
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    provider = _build_provider()

    async def _collect() -> list[str]:
        return [chunk async for chunk in provider.generate_stream([{"role": "user", "content": "hello"}])]

    with pytest.raises(ProviderUnavailable) as exc_info:
        asyncio.run(_collect())

    assert exc_info.value.reason == "provider_unavailable"
    assert "Adapter circuit breaker is open." in str(exc_info.value)


def test_gracekelly_provider_reuses_successful_ready_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"health": 0}

    def _fake_get(url: str, *, timeout: float):
        _ = url, timeout
        calls["health"] += 1
        return _FakeResponse(status_code=200)

    monkeypatch.setattr("httpx.get", _fake_get)
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: _FakeResponse(
            payload={
                "answer": "ok",
                "task_type": "support",
                "complexity_level": "simple",
                "pattern_used": "single_call",
                "reliability_level": "quick",
                "was_decomposed": False,
                "used_consensus": False,
                "used_roles": False,
                "total_llm_calls": 1,
                "model_id": "mistral-small",
            }
        ),
    )

    provider = _build_provider()
    provider.generate([{"role": "user", "content": "hello"}])
    provider.generate([{"role": "user", "content": "hello again"}])

    assert calls["health"] == 1


def test_gracekelly_provider_cost_is_always_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _FakeResponse(status_code=200))
    monkeypatch.setattr(
        "httpx.post",
        lambda *args, **kwargs: _FakeResponse(
            payload={
                "answer": "ok",
                "task_type": "support",
                "complexity_level": "simple",
                "pattern_used": "single_call",
                "reliability_level": "quick",
                "was_decomposed": False,
                "used_consensus": False,
                "used_roles": False,
                "total_llm_calls": 3,
                "model_id": "claude-sonnet-4-6-api",
            }
        ),
    )

    provider = _build_provider()
    response = provider.generate([{"role": "user", "content": "hello"}])

    assert response.cost_usd == 0.0
    assert response.model == "claude-sonnet-4-6-api"


def test_gracekelly_provider_routes_tool_requests_to_orchestrate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {"health": 0}

    def _fake_get(url: str, *, timeout: float):
        _ = url, timeout
        captured["health"] += 1
        return _FakeResponse(status_code=200)

    def _fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float):
        captured["post_url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse(
            payload={
                "task_id": "task-165",
                "status": "completed",
                "result": {
                    "answer": "Нужно вызвать поиск по базе.",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "name": "search_kb",
                            "arguments": {"query": "reset password"},
                        }
                    ],
                    "structured_output": {"relevant": True},
                    "consensus_details": {"reliability_level": "standard"},
                },
            }
        )

    monkeypatch.delenv("GRACEKELLY_API_KEY", raising=False)
    monkeypatch.setattr("httpx.get", _fake_get)
    monkeypatch.setattr("httpx.post", _fake_post)

    provider = _build_provider()
    response = provider.generate_with_tools(
        [{"role": "user", "content": "Найди статью про сброс пароля"}],
        [
            {
                "type": "function",
                "function": {
                    "name": "search_kb",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ],
        reliability_level="standard",
        requested_models=["claude-sonnet-4-6-api", "gpt-5-4-api"],
        merge_strategy="consensus",
    )

    assert captured["health"] == 1
    assert captured["post_url"] == "http://127.0.0.1:8011/api/v1/orchestrate"
    assert captured["json"]["tools"][0]["function"]["name"] == "search_kb"
    assert captured["json"]["requested_models"] == ["claude-sonnet-4-6-api", "gpt-5-4-api"]
    assert captured["json"]["reliability_level"] == "standard"
    assert captured["json"]["merge_strategy"] == "consensus"
    assert response.text == "Нужно вызвать поиск по базе."
    assert response.tool_calls is not None
    assert response.tool_calls[0]["name"] == "search_kb"
    assert response.structured_output == {"relevant": True}
    assert response.metadata["status"] == "completed"


def test_gracekelly_provider_routes_simple_requests_to_orchestrate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    monkeypatch.setattr("httpx.get", lambda *args, **kwargs: _FakeResponse(status_code=200))

    def _fake_post(url: str, *, headers: dict[str, str], json: dict[str, Any], timeout: float):
        captured["post_url"] = url
        captured["json"] = json
        _ = headers, timeout
        return _FakeResponse(
            payload={
                "answer": "Простой ответ",
                "task_type": "support",
                "complexity_level": "simple",
                "pattern_used": "single_call",
                "reliability_level": "quick",
                "was_decomposed": False,
                "used_consensus": False,
                "used_roles": False,
                "total_llm_calls": 1,
                "model_id": "mistral-small",
            }
        )

    monkeypatch.setattr("httpx.post", _fake_post)

    provider = _build_provider()
    response = provider.generate([{"role": "user", "content": "hello"}])

    assert captured["post_url"] == "http://127.0.0.1:8011/api/v1/orchestrate"
    assert captured["json"]["model"] == "mistral-small"
    assert captured["json"]["requested_models"] == ["mistral-small"]
    assert "tools" not in captured["json"]
    assert response.text == "Простой ответ"
