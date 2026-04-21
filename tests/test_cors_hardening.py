from __future__ import annotations

import importlib

import pytest


def _reload_settings() -> object:
    import config.settings as settings_module

    settings_module = importlib.reload(settings_module)
    settings_module._settings = None
    return settings_module.get_settings()


def test_wildcard_cors_ok_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "*")

    settings = _reload_settings()

    settings.validate()


def test_wildcard_cors_fails_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")

    settings = _reload_settings()

    with pytest.raises(RuntimeError) as exc_info:
        settings.validate()

    assert "CORS_ORIGINS" in str(exc_info.value)


def test_explicit_origins_ok_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENV", "production")
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "https://app.example.com,https://admin.example.com",
    )
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "test-key-prod-cors-happy-path")

    settings = _reload_settings()

    settings.validate()

    assert "https://app.example.com" in settings.cors_origins
    assert "https://admin.example.com" in settings.cors_origins


def test_empty_origins_fails_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "")

    settings = _reload_settings()

    with pytest.raises(RuntimeError):
        settings.validate()


def test_cors_max_age_passed_to_middleware(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_MAX_AGE_SEC", "1234")

    _reload_settings()

    import api.app as app_module
    from starlette.middleware.cors import CORSMiddleware

    app_module = importlib.reload(app_module)

    cors_middleware = None
    for middleware in app_module.app.user_middleware:
        if middleware.cls is CORSMiddleware:
            cors_middleware = middleware
            break

    assert cors_middleware is not None
    kwargs = getattr(cors_middleware, "kwargs", None) or getattr(
        cors_middleware,
        "options",
        {},
    )
    assert kwargs.get("max_age") == 1234
