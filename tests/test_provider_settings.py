from __future__ import annotations

import urllib.error

import pytest


class _OkResponse:
    def __enter__(self) -> "_OkResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_settings_validate_allows_local_first_without_paid_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "local-first")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _OkResponse())

    settings = Settings()

    settings.validate()

    assert settings.llm_provider_profile == "local-first"
    assert settings.daily_cost_limit_usd == 5.0


def test_settings_defaults_to_gracekelly_primary_without_implicit_ollama_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    calls: list[object] = []

    def _fail_if_ollama_is_probed(*args, **kwargs):
        calls.append((args, kwargs))
        raise urllib.error.URLError("offline")

    monkeypatch.delenv("LLM_PROVIDER_PROFILE", raising=False)
    monkeypatch.delenv("REQUIRE_OLLAMA", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", _fail_if_ollama_is_probed)

    settings = Settings()

    settings.validate()

    assert settings.llm_provider_profile == "gracekelly-primary"
    assert calls == []


def test_settings_validate_requires_mistral_api_key_for_external_mistral_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "external-mistral")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )

    settings = Settings()

    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        settings.validate()


def test_settings_validate_requires_mistral_api_key_for_mixed_paid_fast_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    calls: list[object] = []

    def _fail_if_network_is_probed(*args, **kwargs):
        calls.append((args, kwargs))
        raise urllib.error.URLError("offline")

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "gracekelly-mixed")
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", _fail_if_network_is_probed)

    settings = Settings()

    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        settings.validate()

    assert calls == []


def test_settings_validate_accepts_gracekelly_primary_without_paid_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "gracekelly-primary")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _OkResponse())

    settings = Settings()

    settings.validate()

    assert settings.llm_provider_profile == "gracekelly-primary"


@pytest.mark.parametrize("placeholder", ["changeme", "change-me", "change_me"])
def test_settings_validate_rejects_placeholder_api_key_for_external_mistral(
    monkeypatch: pytest.MonkeyPatch, placeholder: str
) -> None:
    from config.settings import Settings

    calls: list[object] = []

    def _fail_if_network_is_probed(*args, **kwargs):
        calls.append((args, kwargs))
        raise urllib.error.URLError("offline")

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "external-mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", placeholder)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", _fail_if_network_is_probed)

    settings = Settings()

    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        settings.validate()

    assert calls == []
