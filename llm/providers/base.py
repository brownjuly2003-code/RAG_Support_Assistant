from __future__ import annotations

import json
import math
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field, replace
from typing import Any, Protocol

Message = dict[str, Any]


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


class ProviderCapabilityError(RuntimeError):
    pass


class StructuredOutputValidationError(ValueError):
    pass


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
    tool_calls: list[dict[str, Any]] | None = None
    structured_output: dict[str, Any] | list[Any] | None = None
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

    def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        ...

    def generate_with_schema(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> LLMResponse:
        ...

    async def generate_stream(
        self,
        messages: list[Message],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        ...

    def generate_batch(
        self,
        batches: list[list[Message]],
        **kwargs: Any,
    ) -> list[LLMResponse]:
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
        name = str(message.get("name") or "").strip()
        content = message.get("content")
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False)
        content = str(content or "").strip()
        if not content:
            continue
        prefix = f"{role.upper()} ({name}):" if name else f"{role.upper()}:"
        parts.append(f"{prefix}\n{content}")
    return "\n\n".join(parts)


def _format_schema_path(path: tuple[str, ...]) -> str:
    if not path:
        return "$"
    return "$." + ".".join(path)


def _validate_json_schema_value(
    value: Any,
    schema: dict[str, Any],
    *,
    path: tuple[str, ...] = (),
) -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            raise StructuredOutputValidationError(
                f"{_format_schema_path(path)} must be an object"
            )
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        additional_properties = schema.get("additionalProperties", True)
        for key in required:
            if key not in value:
                raise StructuredOutputValidationError(
                    f"{_format_schema_path(path + (str(key),))} is required"
                )
        if isinstance(properties, dict):
            for key, item in value.items():
                child_schema = properties.get(key)
                if child_schema is None:
                    if additional_properties is False:
                        raise StructuredOutputValidationError(
                            f"{_format_schema_path(path + (str(key),))} is not allowed"
                        )
                    continue
                if isinstance(child_schema, dict):
                    _validate_json_schema_value(item, child_schema, path=path + (str(key),))
    elif expected_type == "array":
        if not isinstance(value, list):
            raise StructuredOutputValidationError(
                f"{_format_schema_path(path)} must be an array"
            )
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _validate_json_schema_value(item, item_schema, path=path + (str(index),))
    elif expected_type == "string":
        if not isinstance(value, str):
            raise StructuredOutputValidationError(
                f"{_format_schema_path(path)} must be a string"
            )
    elif expected_type == "boolean":
        if not isinstance(value, bool):
            raise StructuredOutputValidationError(
                f"{_format_schema_path(path)} must be a boolean"
            )
    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise StructuredOutputValidationError(
                f"{_format_schema_path(path)} must be an integer"
            )
    elif expected_type == "number":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise StructuredOutputValidationError(
                f"{_format_schema_path(path)} must be a number"
            )

    enum = schema.get("enum")
    if isinstance(enum, list) and value not in enum:
        raise StructuredOutputValidationError(
            f"{_format_schema_path(path)} must be one of {enum}"
        )


def validate_structured_output(
    value: Any,
    schema: dict[str, Any],
) -> dict[str, Any] | list[Any]:
    if not isinstance(schema, dict):
        raise StructuredOutputValidationError("schema must be an object")
    _validate_json_schema_value(value, schema)
    if not isinstance(value, (dict, list)):
        raise StructuredOutputValidationError("structured output must be a JSON object or array")
    return value


def parse_structured_output(
    text: str,
    schema: dict[str, Any],
) -> dict[str, Any] | list[Any]:
    normalized = (text or "").strip()
    if not normalized:
        raise StructuredOutputValidationError("structured output is empty")
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if len(lines) >= 3:
            normalized = "\n".join(lines[1:-1]).strip()
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError as exc:
        raise StructuredOutputValidationError("structured output is not valid JSON") from exc
    return validate_structured_output(parsed, schema)


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
    def supports_tool_use(self) -> bool:
        return bool(
            _provider_implements_method(self._provider, "generate_with_tools")
            or getattr(self._provider, "supports_tool_use", False)
        )

    @property
    def supports_structured_output(self) -> bool:
        return bool(
            _provider_implements_method(self._provider, "generate_with_schema")
            or getattr(self._provider, "supports_structured_output", False)
        )

    @property
    def supports_streaming(self) -> bool:
        return bool(
            _provider_implements_method(self._provider, "generate_stream")
            or getattr(self._provider, "supports_streaming", False)
        )

    @property
    def supports_batch(self) -> bool:
        return bool(
            _provider_implements_method(self._provider, "generate_batch")
            or getattr(self._provider, "supports_batch", False)
        )

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

    def _fallback_response(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> LLMResponse:
        if (
            self._fallback_provider is not None
            and self._fallback_cache_is_active is not None
            and self._fallback_cache_is_active()
        ):
            method = getattr(self, f"_call_{method_name}")
            response = method(self._fallback_provider, *args, **kwargs)
            self.last_response = response
            return response

        try:
            method = getattr(self, f"_call_{method_name}")
            response = method(self._provider, *args, **kwargs)
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
            response = getattr(self, f"_call_{method_name}")(self._fallback_provider, *args, **kwargs)
        self.last_response = response
        return response

    def _call_generate(
        self,
        provider: LLMProvider,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        return provider.generate(messages, tools=tools, **kwargs)

    def _call_generate_with_tools(
        self,
        provider: LLMProvider,
        messages: list[Message],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        method = getattr(provider, "generate_with_tools", None)
        if _provider_implements_method(provider, "generate_with_tools") and callable(method):
            return method(messages, tools, **kwargs)
        if not bool(getattr(provider, "supports_tool_use", False)):
            raise ProviderCapabilityError(f"Provider '{provider.provider_id}' does not support tool use")
        return provider.generate(messages, tools=tools, **kwargs)

    def _call_generate_with_schema(
        self,
        provider: LLMProvider,
        messages: list[Message],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> LLMResponse:
        method = getattr(provider, "generate_with_schema", None)
        if _provider_implements_method(provider, "generate_with_schema") and callable(method):
            return method(messages, schema, **kwargs)
        if not bool(getattr(provider, "supports_structured_output", False)):
            raise ProviderCapabilityError(
                f"Provider '{provider.provider_id}' does not support structured output"
            )
        response = provider.generate(messages, **kwargs)
        return replace(
            response,
            structured_output=parse_structured_output(response.text, schema),
        )

    def generate_with_tools(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        return self._fallback_response("generate_with_tools", messages, tools, **kwargs)

    def generate_with_schema(
        self,
        messages: list[Message],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> LLMResponse:
        return self._fallback_response("generate_with_schema", messages, schema, **kwargs)

    async def generate_stream(
        self,
        messages: list[Message],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        provider = self._provider
        method = getattr(provider, "generate_stream", None)
        if not _provider_implements_method(provider, "generate_stream") or not callable(method):
            raise ProviderCapabilityError(
                f"Provider '{provider.provider_id}' does not support streaming"
            )
        async for chunk in method(messages, **kwargs):
            yield chunk

    def generate_batch(
        self,
        batches: list[list[Message]],
        **kwargs: Any,
    ) -> list[LLMResponse]:
        method = getattr(self._provider, "generate_batch", None)
        if _provider_implements_method(self._provider, "generate_batch") and callable(method):
            responses = method(batches, **kwargs)
        else:
            responses = [self.generate(messages, **kwargs) for messages in batches]
        if responses:
            self.last_response = responses[-1]
        return responses

    def invoke(self, prompt: str) -> str:
        response = self.generate([{"role": "user", "content": prompt}])
        return response.text


def _provider_implements_method(provider: Any, method_name: str) -> bool:
    method = provider.__class__.__dict__.get(method_name)
    return callable(method)
