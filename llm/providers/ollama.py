from __future__ import annotations

import time
from typing import Any

from llm.providers.base import LLMResponse, calculate_cost, estimate_tokens, flatten_messages


class OllamaProvider:
    def __init__(
        self,
        *,
        model_name: str,
        base_url: str,
        timeout_sec: float,
        input_price_per_1m_tokens: float,
        output_price_per_1m_tokens: float,
    ) -> None:
        self.provider_id = "ollama"
        self.model_name = model_name
        self._base_url = base_url
        self._timeout_sec = timeout_sec
        self._input_price_per_1m_tokens = input_price_per_1m_tokens
        self._output_price_per_1m_tokens = output_price_per_1m_tokens

    def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        _ = tools, kwargs
        prompt = flatten_messages(messages)
        started = time.perf_counter()

        try:
            from langchain_ollama import OllamaLLM  # type: ignore[import-not-found]

            llm = OllamaLLM(
                model=self.model_name,
                base_url=self._base_url,
                timeout=self._timeout_sec,
            )
        except ImportError:
            from langchain_community.llms import Ollama

            try:
                llm = Ollama(
                    model=self.model_name,
                    base_url=self._base_url,
                    timeout=self._timeout_sec,
                )
            except TypeError:
                llm = Ollama(
                    model=self.model_name,
                    base_url=self._base_url,
                    request_timeout=self._timeout_sec,
                )

        text = str(llm.invoke(prompt))
        input_tokens = estimate_tokens(prompt)
        output_tokens = estimate_tokens(text)
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
            metadata={},
        )
