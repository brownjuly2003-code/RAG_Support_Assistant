from __future__ import annotations

from collections.abc import AsyncIterator
import json
import os
import time
from typing import Any

import httpx

from llm.providers.base import (
    LLMResponse,
    ProviderUnavailable,
    estimate_tokens,
    flatten_messages,
    parse_structured_output,
    validate_structured_output,
)


class GraceKellyProvider:
    def __init__(
        self,
        *,
        model_name: str,
        base_url: str,
        api_key_env: str,
        timeout_sec: float,
        health_check_timeout_sec: float,
        input_price_per_1m_tokens: float,
        output_price_per_1m_tokens: float,
        use_orchestrate_for_tools: bool = True,
    ) -> None:
        _ = input_price_per_1m_tokens, output_price_per_1m_tokens
        self.provider_id = "gracekelly"
        self.model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._api_key_env = api_key_env
        self._timeout_sec = timeout_sec
        self._health_check_timeout_sec = health_check_timeout_sec
        self._use_orchestrate_for_tools = use_orchestrate_for_tools
        self._ready_checked = False
        self.supports_tool_use = False
        self.supports_structured_output = False
        self.supports_streaming = False
        self.supports_batch = False

    def _auth_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        api_key = (os.getenv(self._api_key_env, "") or "").strip()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def _ensure_ready(self) -> None:
        if self._ready_checked:
            return
        try:
            response = httpx.get(
                f"{self._base_url}/healthz/ready",
                timeout=self._health_check_timeout_sec,
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(
                "GraceKelly readiness check timed out",
                provider_id=self.provider_id,
                reason="health_check",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                "GraceKelly readiness check failed",
                provider_id=self.provider_id,
                reason="health_check",
            ) from exc
        if response.status_code != 200:
            raise ProviderUnavailable(
                f"GraceKelly readiness check returned {response.status_code}",
                provider_id=self.provider_id,
                reason="health_check",
            )
        self._ready_checked = True

    def _should_use_orchestrate(
        self,
        *,
        tools: list[dict[str, Any]] | None = None,
        schema: dict[str, Any] | None = None,
        requested_models: list[str] | None = None,
        merge_strategy: str | None = None,
        reliability_level: str = "quick",
    ) -> bool:
        if tools and self._use_orchestrate_for_tools:
            return True
        if schema:
            return True
        if requested_models and len(requested_models) > 1:
            return True
        if merge_strategy:
            return True
        return reliability_level.strip().lower() != "quick"

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = httpx.post(
                f"{self._base_url}{path}",
                headers=self._auth_headers(),
                json=payload,
                timeout=self._timeout_sec,
            )
        except httpx.TimeoutException as exc:
            raise ProviderUnavailable(
                "GraceKelly request timed out",
                provider_id=self.provider_id,
                reason="timeout",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                "GraceKelly request failed",
                provider_id=self.provider_id,
                reason="request_failed",
            ) from exc
        if response.status_code >= 500:
            raise ProviderUnavailable(
                f"GraceKelly returned {response.status_code}",
                provider_id=self.provider_id,
                reason="request_failed",
            )
        response.raise_for_status()
        return response.json()

    def _build_orchestrate_payload(
        self,
        prompt: str,
        *,
        tools: list[dict[str, Any]] | None = None,
        schema: dict[str, Any] | None = None,
        requested_models: list[str] | None = None,
        merge_strategy: str | None = None,
        reliability_level: str = "quick",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        models = list(requested_models or [self.model_name])
        payload: dict[str, Any] = {
            "prompt": prompt,
            "requested_models": models,
            "reliability_level": reliability_level,
            "metadata": dict(metadata or {}),
        }
        if len(models) == 1:
            payload["model"] = models[0]
        else:
            payload["models"] = models
        if merge_strategy:
            payload["merge_strategy"] = merge_strategy
        if tools:
            payload["tools"] = tools
        if schema:
            payload["structured_output_schema"] = schema
        return payload

    def _resolve_model_name(self, data: dict[str, Any]) -> str:
        model = data.get("model")
        if isinstance(model, dict):
            model_id = model.get("id")
            if isinstance(model_id, str) and model_id.strip():
                return model_id.strip()
        for candidate in (
            data.get("model_id"),
            data.get("model"),
            data.get("winning_model"),
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return self.model_name

    def _parse_response(self, data: dict[str, Any], prompt: str) -> LLMResponse:
        status = data.get("status")
        if isinstance(status, str) and status.strip().lower() == "failed":
            failure_code = data.get("failure_code")
            failure_message = data.get("failure_message")
            reason = (
                failure_code.strip()
                if isinstance(failure_code, str) and failure_code.strip()
                else "orchestrate_failed"
            )
            message = (
                failure_message.strip()
                if isinstance(failure_message, str) and failure_message.strip()
                else "GraceKelly orchestrate task failed"
            )
            raise ProviderUnavailable(
                message,
                provider_id=self.provider_id,
                reason=reason,
            )
        raw_result = data.get("result")
        result: dict[str, Any] = raw_result if isinstance(raw_result, dict) else {}
        raw_metadata = data.get("metadata")
        metadata: dict[str, Any] = raw_metadata if isinstance(raw_metadata, dict) else {}
        text = str(
            result.get("answer")
            or data.get("answer")
            or data.get("output_text")
            or metadata.get("answer")
            or ""
        ).strip()
        tool_calls = result.get("tool_calls") or data.get("tool_calls") or metadata.get("tool_calls")
        structured_output = (
            result.get("structured_output")
            or data.get("structured_output")
            or metadata.get("structured_output")
        )
        merged_metadata = {
            **metadata,
            "task_id": data.get("task_id"),
            "status": data.get("status"),
            "task_type": data.get("task_type"),
            "complexity_level": data.get("complexity_level"),
            "pattern_used": data.get("pattern_used"),
            "reliability_level": data.get("reliability_level") or metadata.get("reliability_level"),
            "total_llm_calls": data.get("total_llm_calls"),
            "used_consensus": data.get("used_consensus"),
            "used_roles": data.get("used_roles"),
            "was_decomposed": data.get("was_decomposed"),
            "consensus_details": result.get("consensus_details"),
        }
        return LLMResponse(
            text=text,
            provider=self.provider_id,
            model=self._resolve_model_name(data),
            input_tokens=estimate_tokens(prompt),
            output_tokens=estimate_tokens(text),
            cost_usd=0.0,
            finish_reason=str(result.get("finish_reason") or data.get("finish_reason") or "").strip()
            or None,
            tool_calls=tool_calls if isinstance(tool_calls, list) else None,
            structured_output=structured_output if isinstance(structured_output, (dict, list)) else None,
            metadata=merged_metadata,
        )

    def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        self._ensure_ready()
        prompt = flatten_messages(messages)
        schema = kwargs.pop("schema", None)
        requested_models = kwargs.pop("requested_models", None)
        merge_strategy = kwargs.pop("merge_strategy", None)
        reliability_level = str(kwargs.pop("reliability_level", "quick") or "quick")
        metadata = kwargs.pop("metadata", None)
        started = time.perf_counter()
        payload = self._build_orchestrate_payload(
            prompt,
            tools=tools,
            schema=schema if isinstance(schema, dict) else None,
            requested_models=requested_models,
            merge_strategy=merge_strategy,
            reliability_level=reliability_level,
            metadata=metadata if isinstance(metadata, dict) else None,
        )
        data = self._post_json("/api/v1/orchestrate", payload)

        response = self._parse_response(data, prompt)
        response.latency_ms = int((time.perf_counter() - started) * 1000)
        return response

    def generate_with_tools(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        **kwargs: Any,
    ) -> LLMResponse:
        return self.generate(messages, tools=tools, **kwargs)

    def generate_with_schema(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        **kwargs: Any,
    ) -> LLMResponse:
        response = self.generate(messages, schema=schema, **kwargs)
        if response.structured_output is not None:
            response.structured_output = validate_structured_output(response.structured_output, schema)
            return response
        response.structured_output = parse_structured_output(response.text, schema)
        return response

    async def generate_stream(
        self,
        messages: list[dict[str, str]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        self._ensure_ready()
        prompt = flatten_messages(messages)
        payload = self._build_orchestrate_payload(
            prompt,
            requested_models=kwargs.get("requested_models"),
            merge_strategy=kwargs.get("merge_strategy"),
            reliability_level=str(kwargs.get("reliability_level", "quick") or "quick"),
            metadata=kwargs.get("metadata") if isinstance(kwargs.get("metadata"), dict) else None,
        )
        async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/v1/orchestrate/stream",
                headers=self._auth_headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                buffer = ""
                yielded = False
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue
                    buffer += line[5:].strip()
                    try:
                        payload_data = json.loads(buffer)
                    except json.JSONDecodeError:
                        continue
                    buffer = ""
                    status = payload_data.get("status")
                    if isinstance(status, str) and status.strip().lower() == "failed":
                        failure_code = payload_data.get("failure_code")
                        failure_message = payload_data.get("failure_message")
                        reason = (
                            failure_code.strip()
                            if isinstance(failure_code, str) and failure_code.strip()
                            else "orchestrate_failed"
                        )
                        message = (
                            failure_message.strip()
                            if isinstance(failure_message, str) and failure_message.strip()
                            else "GraceKelly orchestrate task failed"
                        )
                        raise ProviderUnavailable(
                            message,
                            provider_id=self.provider_id,
                            reason=reason,
                        )
                    text = payload_data.get("text")
                    event_type = payload_data.get("type") or payload_data.get("event")
                    if isinstance(text, str) and text and event_type not in {"accepted", "complete"}:
                        yielded = True
                        yield text
                    elif isinstance(text, str) and text and event_type == "complete" and not yielded:
                        yield text
