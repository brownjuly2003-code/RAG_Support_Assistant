from __future__ import annotations

import os
import time
from typing import Any

import httpx

from llm.providers.base import LLMResponse, calculate_cost, estimate_tokens


class ClaudeProvider:
    def __init__(
        self,
        *,
        model_name: str,
        api_key_env: str,
        timeout_sec: float,
        input_price_per_1m_tokens: float,
        output_price_per_1m_tokens: float,
    ) -> None:
        self.provider_id = "claude"
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
            raise RuntimeError(f"{self._api_key_env} is required for Claude provider")

        max_tokens = int(kwargs.get("max_tokens") or 1024)
        system_parts = [str(item.get("content") or "") for item in messages if item.get("role") == "system"]
        chat_messages = [
            {"role": item.get("role") or "user", "content": str(item.get("content") or "")}
            for item in messages
            if (item.get("role") or "user") != "system"
        ]
        payload: dict[str, Any] = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "messages": chat_messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(part for part in system_parts if part)
        if tools:
            payload["tools"] = tools

        started = time.perf_counter()
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
            timeout=self._timeout_sec,
        )
        response.raise_for_status()
        data = response.json()

        content = data.get("content") or []
        text = "\n".join(
            str(item.get("text") or "")
            for item in content
            if item.get("type") == "text"
        ).strip()
        usage = data.get("usage") or {}
        input_tokens = int(usage.get("input_tokens") or estimate_tokens("\n".join(system_parts)))
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
                "request_id": response.headers.get("request-id"),
                "rate_limit_remaining_requests": response.headers.get(
                    "anthropic-ratelimit-requests-remaining"
                ),
                "rate_limit_remaining_tokens": response.headers.get(
                    "anthropic-ratelimit-tokens-remaining"
                ),
            },
        )
