from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Protocol


Message = dict[str, str]


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
    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider
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
        response = self._provider.generate(messages, tools=tools, **kwargs)
        self.last_response = response
        return response

    def invoke(self, prompt: str) -> str:
        response = self.generate([{"role": "user", "content": prompt}])
        return response.text
