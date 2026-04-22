from __future__ import annotations

import os
import time
from typing import Any

import httpx

from llm.providers.base import (
    LLMResponse,
    ProviderUnavailable,
    estimate_tokens,
    flatten_messages,
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
    ) -> None:
        _ = input_price_per_1m_tokens, output_price_per_1m_tokens
        self.provider_id = "gracekelly"
        self.model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._api_key_env = api_key_env
        self._timeout_sec = timeout_sec
        self._health_check_timeout_sec = health_check_timeout_sec
        self._ready_checked = False

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

    def generate(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        _ = tools, kwargs
        self._ensure_ready()

        prompt = flatten_messages(messages)
        payload = {
            "prompt": prompt,
            "model": self.model_name,
            "reliability_level": "quick",
            "dry_run": False,
        }
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self._base_url}/api/v1/smart",
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
        data = response.json()
        text = str(data.get("answer") or "").strip()
        latency_ms = int((time.perf_counter() - started) * 1000)

        return LLMResponse(
            text=text,
            provider=self.provider_id,
            model=str(data.get("model_id") or self.model_name),
            input_tokens=estimate_tokens(prompt),
            output_tokens=estimate_tokens(text),
            cost_usd=0.0,
            latency_ms=latency_ms,
            metadata={
                "task_type": data.get("task_type"),
                "complexity_level": data.get("complexity_level"),
                "pattern_used": data.get("pattern_used"),
                "reliability_level": data.get("reliability_level"),
                "total_llm_calls": data.get("total_llm_calls"),
                "used_consensus": data.get("used_consensus"),
                "used_roles": data.get("used_roles"),
                "was_decomposed": data.get("was_decomposed"),
            },
        )
