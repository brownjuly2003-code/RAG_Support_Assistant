from __future__ import annotations

import os
import time
from typing import Any

import httpx

from llm.providers.base import LLMResponse, calculate_cost, estimate_tokens


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

    def _load_api_key(self) -> str:
        api_key = (os.getenv(self._api_key_env, "") or "").strip()
        if not api_key or api_key.lower() in _PLACEHOLDER_API_KEYS:
            raise RuntimeError(f"{self._api_key_env} is required for Mistral provider")
        return api_key

    def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
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

        started = time.perf_counter()
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
        data = response.json()

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            text = "\n".join(str(item.get("text") or "") for item in content if isinstance(item, dict)).strip()
        else:
            text = str(content).strip()

        usage = data.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or estimate_tokens(str(payload["messages"])))
        output_tokens = int(usage.get("completion_tokens") or estimate_tokens(text))
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
            finish_reason=choice.get("finish_reason"),
            metadata={
                "rate_limit_remaining_requests": response.headers.get(
                    "x-ratelimit-remaining-requests"
                ),
                "rate_limit_remaining_tokens": response.headers.get(
                    "x-ratelimit-remaining-tokens"
                ),
            },
        )
