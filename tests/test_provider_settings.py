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


def test_settings_validate_rejects_placeholder_api_key_for_external_mistral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "external-mistral")
    monkeypatch.setenv("MISTRAL_API_KEY", "changeme")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _OkResponse())

    settings = Settings()

    with pytest.raises(RuntimeError, match="MISTRAL_API_KEY"):
        settings.validate()
