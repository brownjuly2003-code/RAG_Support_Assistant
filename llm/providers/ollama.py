from __future__ import annotations

import json
from collections.abc import AsyncIterator
import time
from typing import Any

from llm.providers.base import (
    LLMResponse,
    calculate_cost,
    estimate_tokens,
    flatten_messages,
    parse_structured_output,
)


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
        self.supports_tool_use = False
        self.supports_structured_output = False
        self.supports_streaming = False
        self.supports_batch = False

    def generate(
        self,
        messages: list[dict[str, Any]],
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

    def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        _ = kwargs
        prompt = flatten_messages(messages)
        started = time.perf_counter()

        try:
            from langchain_ollama import ChatOllama  # type: ignore[import-not-found]

            chat = ChatOllama(
                model=self.model_name,
                base_url=self._base_url,
                timeout=self._timeout_sec,
            )
        except ImportError:
            from langchain_community.chat_models import ChatOllama

            try:
                chat = ChatOllama(
                    model=self.model_name,
                    base_url=self._base_url,
                    timeout=self._timeout_sec,
                )
            except TypeError:
                chat = ChatOllama(
                    model=self.model_name,
                    base_url=self._base_url,
                    request_timeout=self._timeout_sec,
                )

        response = chat.bind_tools(tools).invoke(prompt)
        content = getattr(response, "content", "")
        if isinstance(content, list):
            text = "\n".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict)
            ).strip()
        else:
            text = str(content or "").strip()
        tool_calls = getattr(response, "tool_calls", None)
        if not isinstance(tool_calls, list):
            tool_calls = None
        response_metadata = getattr(response, "response_metadata", None)
        finish_reason = None
        if isinstance(response_metadata, dict):
            finish_reason = str(
                response_metadata.get("done_reason")
                or response_metadata.get("finish_reason")
                or ""
            ).strip() or None

        output_basis = text or json.dumps(tool_calls or [], ensure_ascii=False)
        return LLMResponse(
            text=text,
            provider=self.provider_id,
            model=self.model_name,
            input_tokens=estimate_tokens(prompt),
            output_tokens=estimate_tokens(output_basis),
            cost_usd=calculate_cost(
                estimate_tokens(prompt),
                estimate_tokens(output_basis),
                input_price_per_1m_tokens=self._input_price_per_1m_tokens,
                output_price_per_1m_tokens=self._output_price_per_1m_tokens,
            ),
            latency_ms=int((time.perf_counter() - started) * 1000),
            finish_reason=finish_reason,
            tool_calls=tool_calls,
            metadata=response_metadata if isinstance(response_metadata, dict) else {},
        )

    def generate_with_schema(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> LLMResponse:
        response = self.generate(
            [
                {
                    "role": "system",
                    "content": (
                        "Return only valid JSON that matches this JSON Schema exactly.\n"
                        f"{json.dumps(schema, ensure_ascii=False)}"
                    ),
                },
                *messages,
            ],
            **kwargs,
        )
        response.structured_output = parse_structured_output(response.text, schema)
        return response

    async def generate_stream(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        _ = kwargs
        prompt = flatten_messages(messages)

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

        async for chunk in llm.astream(prompt):
            if isinstance(chunk, str):
                text = chunk
            else:
                content = getattr(chunk, "content", chunk)
                if isinstance(content, list):
                    text = "\n".join(
                        str(item.get("text") or "")
                        for item in content
                        if isinstance(item, dict)
                    )
                else:
                    text = str(content or "")
            if text:
                yield text
