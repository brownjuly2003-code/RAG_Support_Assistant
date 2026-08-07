"""3.1d — per-LLM-role temperature / max_tokens."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from llm.providers.base import LLMResponse, ProviderBackedLLM
from llm import role_params as rp


def test_default_roles_have_safe_params() -> None:
    defaults = rp.default_role_params()
    for role in rp.LLM_ROLES:
        assert role in defaults
        assert 0.0 <= float(defaults[role]["temperature"]) <= 2.0
        assert int(defaults[role]["max_tokens"]) >= 1
    # Judges stay deterministic by default.
    assert defaults["grade"]["temperature"] == 0.0
    assert defaults["evaluate"]["temperature"] == 0.0
    assert defaults["classify"]["temperature"] == 0.0
    # Free-form answer is slightly warmer but capped.
    assert defaults["generate"]["temperature"] == 0.2
    assert defaults["generate"]["max_tokens"] == 1024


def test_resolve_merges_json_override() -> None:
    settings = SimpleNamespace(
        llm_role_params_json='{"generate":{"temperature":0.05,"max_tokens":2048}}'
    )
    params = rp.resolve_role_params("generate", settings=settings)
    assert params["temperature"] == 0.05
    assert params["max_tokens"] == 2048
    # Untouched role stays default.
    grade = rp.resolve_role_params("grade", settings=settings)
    assert grade["temperature"] == 0.0


def test_unknown_role_falls_back_to_default() -> None:
    params = rp.resolve_role_params("not-a-real-role")
    assert params == rp.resolve_role_params("default")


def test_invalid_json_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(llm_role_params_json="{not-json")
    params = rp.resolve_role_params("generate", settings=settings)
    assert params == rp.default_role_params()["generate"]


def test_clamps_out_of_range_overrides() -> None:
    settings = SimpleNamespace(
        llm_role_params_json='{"generate":{"temperature":9.9,"max_tokens":999999}}'
    )
    params = rp.resolve_role_params("generate", settings=settings)
    assert params["temperature"] == 2.0
    assert params["max_tokens"] == 128_000


def test_provider_backed_invoke_forwards_generation_kwargs() -> None:
    seen: dict[str, Any] = {}

    class _Prov:
        provider_id = "fake"
        model_name = "m"

        def generate(self, messages, tools=None, **kwargs):  # noqa: ANN001
            seen.update(kwargs)
            return LLMResponse(text="ok", provider="fake", model="m")

    llm = ProviderBackedLLM(provider=_Prov())  # type: ignore[arg-type]
    text = llm.invoke("hi", temperature=0.1, max_tokens=64)
    assert text == "ok"
    assert seen["temperature"] == 0.1
    assert seen["max_tokens"] == 64


def test_graph_invoke_llm_passes_role_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import agent.graph as graph

    captured: dict[str, Any] = {}

    class _Fake:
        def invoke(self, prompt: str, **kwargs: Any) -> str:
            captured["prompt"] = prompt
            captured["kwargs"] = dict(kwargs)
            return "ANSWER"

    monkeypatch.setattr(
        "llm.role_params.generation_kwargs_for_role",
        lambda role, settings=None: {"temperature": 0.0, "max_tokens": 128},
    )
    out = graph._invoke_llm(_Fake(), "prompt-text", role="evaluate")
    assert out == "ANSWER"
    assert captured["kwargs"]["temperature"] == 0.0
    assert captured["kwargs"]["max_tokens"] == 128


def test_graph_invoke_llm_fallback_without_kwargs() -> None:
    import agent.graph as graph

    class _Legacy:
        def invoke(self, prompt: str) -> str:
            return f"echo:{prompt}"

    assert graph._invoke_llm(_Legacy(), "x", role="generate") == "echo:x"


def test_settings_has_llm_role_params_json_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_LLM_ROLE_PARAMS", raising=False)
    from config.settings import Settings

    assert Settings().llm_role_params_json == ""
