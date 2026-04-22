from __future__ import annotations

import urllib.error

import pytest


class _OkResponse:
    def __enter__(self) -> "_OkResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


def test_settings_validate_allows_latency_first_without_paid_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "latency-first")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _OkResponse())

    settings = Settings()

    settings.validate()

    assert settings.llm_provider_profile == "latency-first"
    assert settings.daily_cost_limit_usd == 5.0


def test_settings_validate_requires_paid_provider_api_key_for_quality_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "quality-first")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(urllib.error.URLError("offline")),
    )

    settings = Settings()

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        settings.validate()


def test_settings_validate_accepts_paid_profile_when_required_keys_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "cost-first")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _OkResponse())

    settings = Settings()

    settings.validate()

    assert settings.llm_provider_profile == "cost-first"


def test_settings_validate_rejects_placeholder_api_keys_for_paid_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from config.settings import Settings

    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "cost-first")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "changeme")
    monkeypatch.setenv("GEMINI_API_KEY", "changeme")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _OkResponse())

    settings = Settings()

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY|GEMINI_API_KEY"):
        settings.validate()
