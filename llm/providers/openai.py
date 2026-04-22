from __future__ import annotations

import os
import time
from typing import Any

import httpx

from llm.providers.base import LLMResponse, calculate_cost, estimate_tokens


class OpenAIProvider:
    def __init__(
        self,
        *,
        model_name: str,
        api_key_env: str,
        timeout_sec: float,
        input_price_per_1m_tokens: float,
        output_price_per_1m_tokens: float,
    ) -> None:
        self.provider_id = "openai"
        self.model_name = model_name
        self._api_key_env = api_key_env
        self._timeout_sec = timeout_sec
        self._input_price_per_1m_tokens = input_price_per_1m_tokens
        self._output_price_per_1m_tokens = output_price_per_1m_tokens

    def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        api_key = (os.getenv(self._api_key_env, "") or "").strip()
        if not api_key:
            raise RuntimeError(f"{self._api_key_env} is required for OpenAI provider")

        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": [
                {
                    "role": item.get("role") or "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": str(item.get("content") or ""),
                        }
                    ],
                }
                for item in messages
            ],
            "text": {"format": {"type": "text"}},
        }
        if tools:
            payload["tools"] = tools
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            payload["temperature"] = kwargs["temperature"]
        if "max_tokens" in kwargs and kwargs["max_tokens"] is not None:
            payload["max_output_tokens"] = int(kwargs["max_tokens"])

        started = time.perf_counter()
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout_sec,
        )
        response.raise_for_status()
        data = response.json()

        text_parts: list[str] = []
        for item in data.get("output") or []:
            for part in item.get("content") or []:
                if part.get("type") == "output_text":
                    text_parts.append(str(part.get("text") or ""))
        text = "\n".join(part for part in text_parts if part).strip()

        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or estimate_tokens(str(payload["input"])))
        output_tokens = int(usage.get("output_tokens") or estimate_tokens(text))
        latency_ms = int((time.perf_counter() - started) * 1000)

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
            latency_ms=latency_ms,
            metadata={
                "request_id": response.headers.get("x-request-id"),
                "rate_limit_remaining_requests": response.headers.get(
                    "x-ratelimit-remaining-requests"
                ),
                "rate_limit_remaining_tokens": response.headers.get(
                    "x-ratelimit-remaining-tokens"
                ),
            },
        )
