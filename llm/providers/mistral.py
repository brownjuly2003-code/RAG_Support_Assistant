from __future__ import annotations

import json
from collections.abc import AsyncIterator
import os
import time
from typing import Any

import httpx

from llm.providers.base import (
    LLMResponse,
    calculate_cost,
    estimate_tokens,
    parse_structured_output,
)


_PLACEHOLDER_API_KEYS = {"changeme", "change-me", "change_me"}


class ResponseError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


class MistralProvider:
    def __init__(
        self,
        *,
        model_name: str,
        api_key_env: str,
        timeout_sec: float,
        input_price_per_1m_tokens: float,
        output_price_per_1m_tokens: float,
    ) -> None:
        self.provider_id = "mistral"
        self.model_name = model_name
        self._api_key_env = api_key_env
        self._api_key = self._load_api_key()
        self._timeout_sec = timeout_sec
        self._input_price_per_1m_tokens = input_price_per_1m_tokens
        self._output_price_per_1m_tokens = output_price_per_1m_tokens
        self.supports_tool_use = False
        self.supports_structured_output = False
        self.supports_streaming = False
        self.supports_batch = False

    def _load_api_key(self) -> str:
        api_key = (os.getenv(self._api_key_env, "") or "").strip()
        if not api_key or api_key.lower() in _PLACEHOLDER_API_KEYS:
            raise RuntimeError(f"{self._api_key_env} is required for Mistral provider")
        return api_key

    def _post_chat_completion(self, payload: dict[str, Any]) -> httpx.Response:
        response = httpx.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout_sec,
        )
        if response.status_code == 429:
            retry_after = response.headers.get("retry-after")
            detail = response.json() if hasattr(response, "json") else {}
            raise ResponseError(
                f"Mistral rate limit exceeded for model '{self.model_name}'",
                status_code=429,
                retry_after=retry_after or str(detail.get("retry_after") or ""),
            )
        response.raise_for_status()
        return response

    def _build_payload(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [
                {
                    "role": item.get("role") or "user",
                    "content": str(item.get("content") or ""),
                }
                for item in messages
            ],
        }
        if tools:
            payload["tools"] = tools
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            payload["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            payload["max_tokens"] = int(kwargs["max_tokens"])
        if "response_format" in kwargs and kwargs["response_format"] is not None:
            payload["response_format"] = kwargs["response_format"]
        if "tool_choice" in kwargs and kwargs["tool_choice"] is not None:
            payload["tool_choice"] = kwargs["tool_choice"]
        if "stream" in kwargs and kwargs["stream"] is not None:
            payload["stream"] = kwargs["stream"]
        return payload

    def _parse_response(self, data: dict[str, Any], headers: dict[str, str]) -> LLMResponse:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            text = "\n".join(str(item.get("text") or "") for item in content if isinstance(item, dict)).strip()
        else:
            text = str(content).strip()

        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or estimate_tokens(str(data.get("messages") or "")))
        output_tokens = int(usage.get("completion_tokens") or estimate_tokens(text))

        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            tool_calls = None

        return LLMResponse(
            text=text,
            provider=self.provider_id,
            model=self.model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=calculate_cost(
                input_tokens,
                output_tokens,
                input_price_per_1m_tokens=self._input_price_per_1m_tokens,
                output_price_per_1m_tokens=self._output_price_per_1m_tokens,
            ),
            finish_reason=choice.get("finish_reason"),
            tool_calls=tool_calls,
            metadata={
                "rate_limit_remaining_requests": headers.get(
                    "x-ratelimit-remaining-requests"
                ),
                "rate_limit_remaining_tokens": headers.get(
                    "x-ratelimit-remaining-tokens"
                ),
            },
        )

    def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        payload = self._build_payload(messages, tools=tools, **kwargs)

        started = time.perf_counter()
        response = self._post_chat_completion(payload)
        data = response.json()
        parsed = self._parse_response(data, response.headers)
        parsed.latency_ms = int((time.perf_counter() - started) * 1000)
        return parsed

    def generate_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        if "tool_choice" not in kwargs:
            kwargs["tool_choice"] = "auto"
        return self.generate(messages, tools=tools, **kwargs)

    def generate_with_schema(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> LLMResponse:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": kwargs.pop("schema_name", "structured_output"),
                "schema": schema,
            },
        }
        response = self.generate(messages, **kwargs)
        response.structured_output = parse_structured_output(response.text, schema)
        return response

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(messages, **kwargs)
        payload["stream"] = True
        async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
            async with client.stream(
                "POST",
                "https://api.mistral.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data_line = line[6:].strip()
                    if data_line == "[DONE]":
                        break
                    try:
                        event = json.loads(data_line)
                    except json.JSONDecodeError:
                        continue
                    choice = (event.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if isinstance(content, str) and content:
                        yield content
