from __future__ import annotations

import os
import time
from typing import Any

import httpx

from llm.providers.base import LLMResponse, calculate_cost, estimate_tokens


class GeminiProvider:
    def __init__(
        self,
        *,
        model_name: str,
        api_key_env: str,
        timeout_sec: float,
        input_price_per_1m_tokens: float,
        output_price_per_1m_tokens: float,
    ) -> None:
        self.provider_id = "gemini"
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
            raise RuntimeError(f"{self._api_key_env} is required for Gemini provider")

        system_parts = [str(item.get("content") or "") for item in messages if item.get("role") == "system"]
        contents = [
            {
                "role": "model" if (item.get("role") or "") == "assistant" else "user",
                "parts": [{"text": str(item.get("content") or "")}],
            }
            for item in messages
            if (item.get("role") or "user") != "system"
        ]
        payload: dict[str, Any] = {"contents": contents}
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        if "temperature" in kwargs and kwargs["temperature"] is not None:
            payload["generationConfig"] = {"temperature": kwargs["temperature"]}
        if tools:
            payload["tools"] = tools

        started = time.perf_counter()
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_name}:generateContent",
            headers={
                "x-goog-api-key": api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self._timeout_sec,
        )
        response.raise_for_status()
        data = response.json()

        candidates = data.get("candidates") or []
        first_candidate = candidates[0] if candidates else {}
        text = "\n".join(
            str(part.get("text") or "")
            for part in (first_candidate.get("content") or {}).get("parts") or []
            if part.get("text")
        ).strip()
        usage = data.get("usageMetadata") or {}
        input_tokens = int(
            usage.get("promptTokenCount")
            or usage.get("inputTokenCount")
            or estimate_tokens(str(contents))
        )
        output_tokens = int(
            usage.get("candidatesTokenCount")
            or usage.get("outputTokenCount")
            or estimate_tokens(text)
        )
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
                "finish_reason": first_candidate.get("finishReason"),
                "rate_limit_remaining_requests": response.headers.get(
                    "x-ratelimit-remaining-requests"
                ),
                "rate_limit_remaining_tokens": response.headers.get(
                    "x-ratelimit-remaining-tokens"
                ),
            },
        )
