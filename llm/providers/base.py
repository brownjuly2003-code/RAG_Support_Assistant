from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


Message = dict[str, str]


class ProviderUnavailable(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        provider_id: str | None = None,
        reason: str = "unavailable",
    ) -> None:
        super().__init__(message)
        self.provider_id = provider_id
        self.reason = reason


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def usage_metadata(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
        }


class LLMProvider(Protocol):
    provider_id: str
    model_name: str

    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        ...


def estimate_tokens(text: str) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    return max(1, math.ceil(len(normalized) / 4))


def flatten_messages(messages: list[Message]) -> str:
    parts: list[str] = []
    for message in messages:
        role = str(message.get("role") or "user").strip()
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        parts.append(f"{role.upper()}:\n{content}")
    return "\n\n".join(parts)


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    *,
    input_price_per_1m_tokens: float,
    output_price_per_1m_tokens: float,
) -> float:
    total = (
        (max(0, input_tokens) * max(0.0, input_price_per_1m_tokens))
        + (max(0, output_tokens) * max(0.0, output_price_per_1m_tokens))
    ) / 1_000_000.0
    return round(total, 6)


class ProviderBackedLLM:
    def __init__(
        self,
        provider: LLMProvider,
        fallback_provider: LLMProvider | None = None,
        fallback_cache_is_active: Callable[[], bool] | None = None,
        fallback_cache_activate: Callable[[float], None] | None = None,
        fallback_cache_ttl_sec: float = 0.0,
        on_fallback: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._provider = provider
        self._fallback_provider = fallback_provider
        self._fallback_cache_is_active = fallback_cache_is_active
        self._fallback_cache_activate = fallback_cache_activate
        self._fallback_cache_ttl_sec = fallback_cache_ttl_sec
        self._on_fallback = on_fallback
        self.last_response: LLMResponse | None = None

    @property
    def provider_id(self) -> str:
        return self._provider.provider_id

    @property
    def model_name(self) -> str:
        return self._provider.model_name

    def generate(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        if (
            self._fallback_provider is not None
            and self._fallback_cache_is_active is not None
            and self._fallback_cache_is_active()
        ):
            response = self._fallback_provider.generate(messages, tools=tools, **kwargs)
            self.last_response = response
            return response

        try:
            response = self._provider.generate(messages, tools=tools, **kwargs)
        except ProviderUnavailable as exc:
            if self._fallback_provider is None:
                raise
            if self._fallback_cache_activate is not None and self._fallback_cache_ttl_sec > 0:
                self._fallback_cache_activate(self._fallback_cache_ttl_sec)
            if self._on_fallback is not None:
                self._on_fallback(
                    self._provider.provider_id,
                    self._fallback_provider.provider_id,
                    getattr(exc, "reason", "unavailable") or "unavailable",
                )
            response = self._fallback_provider.generate(messages, tools=tools, **kwargs)
        self.last_response = response
        return response

    def invoke(self, prompt: str) -> str:
        response = self.generate([{"role": "user", "content": prompt}])
        return response.text
