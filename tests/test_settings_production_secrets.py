"""Production secrets fail-fast guards (Codex audit 2026-04-27 P0).

Without these guards, RAG_ENV=production deploys could silently:
- accept admin/admin (ADMIN_PASSWORD_HASH empty),
- sign JWTs with the public repo default secret,
- sign session cookies with the same dev default.
"""

from __future__ import annotations

import pytest

from config.settings import Settings, get_settings


_STRONG_SECRET = "S" * 48
_DEV_SECRET = "dev-secret-change-in-production!"


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.setenv("RAG_ENV", env.pop("RAG_ENV", "production"))
    monkeypatch.setenv("DB_ENCRYPTION_KEY", env.pop("DB_ENCRYPTION_KEY", _STRONG_SECRET))
    monkeypatch.setenv("CORS_ORIGINS", env.pop("CORS_ORIGINS", "https://example.com"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import config.settings as _s
    _s._settings = None
    return get_settings()


def test_production_rejects_default_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", _DEV_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$dummybcrypthash" + "x" * 36)
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate()


def test_production_rejects_short_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "tooshort")
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$dummybcrypthash" + "x" * 36)
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate()


def test_production_rejects_default_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _DEV_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "$2b$12$dummybcrypthash" + "x" * 36)
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
        settings.validate()


def test_production_rejects_empty_admin_password_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("ALLOW_DEV_ADMIN_LOGIN", raising=False)
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD_HASH"):
        settings.validate()


def test_production_allows_explicit_dev_admin_optin(monkeypatch: pytest.MonkeyPatch) -> None:
    """ALLOW_DEV_ADMIN_LOGIN=1 documents the risk and unlocks empty hash."""
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("ALLOW_DEV_ADMIN_LOGIN", "1")
    settings = _patch_settings(monkeypatch)
    # Should not raise on the admin-hash gate. We only assert the gate;
    # downstream provider/Ollama validation might still fail in CI without
    # a real Ollama, so we test only the secrets gate by catching to a
    # marker error if any.
    try:
        settings.validate()
    except RuntimeError as exc:
        msg = str(exc)
        assert "ADMIN_PASSWORD_HASH" not in msg, msg
        assert "JWT_SECRET" not in msg, msg
        assert "SESSION_SECRET_KEY" not in msg, msg


def test_development_does_not_require_strong_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.delenv("DB_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    import config.settings as _s
    _s._settings = None
    settings = get_settings()
    try:
        settings.validate()
    except RuntimeError as exc:
        msg = str(exc)
        # Dev mode must not raise on missing prod secrets.
        assert "JWT_SECRET" not in msg, msg
        assert "SESSION_SECRET_KEY" not in msg, msg
        assert "ADMIN_PASSWORD_HASH" not in msg, msg
