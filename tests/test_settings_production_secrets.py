"""Production secrets fail-fast guards (SEC-02 / plan §8.4).

Without these guards, RAG_ENV=production deploys could silently:
- accept admin/admin (empty ADMIN_PASSWORD_HASH + dev-admin bypass),
- sign JWTs / sessions with public repo defaults or placeholders,
- use .env.example DB_ENCRYPTION_KEY placeholders for encrypted columns.
"""

from __future__ import annotations

import pytest

from config.settings import (
    Settings,
    get_settings,
    is_known_insecure_secret,
    production_secret_rejection_reason,
)

_STRONG_SECRET = "S" * 48
_DEV_SECRET = "dev-secret-change-in-production!"
_ENV_EXAMPLE_ENC = "changeme-generate-with-secrets-token_urlsafe"
_ADMIN_HASH = "$2b$12$dummybcrypthash" + "x" * 36


def _patch_settings(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.setenv("RAG_ENV", env.pop("RAG_ENV", "production"))
    monkeypatch.setenv("DB_ENCRYPTION_KEY", env.pop("DB_ENCRYPTION_KEY", _STRONG_SECRET))
    monkeypatch.setenv("CORS_ORIGINS", env.pop("CORS_ORIGINS", "https://example.com"))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    import config.settings as _s

    _s._settings = None
    return get_settings()


def _assert_secret_gate(exc: BaseException, *needles: str) -> None:
    msg = str(exc)
    assert any(n in msg for n in needles), msg


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_known_insecure_secret_helpers() -> None:
    assert is_known_insecure_secret("") is True
    assert is_known_insecure_secret("   ") is True
    assert is_known_insecure_secret(_ENV_EXAMPLE_ENC) is True
    assert is_known_insecure_secret(_DEV_SECRET) is True
    assert is_known_insecure_secret("changeme") is True
    assert is_known_insecure_secret(_STRONG_SECRET) is False

    assert production_secret_rejection_reason(
        _ENV_EXAMPLE_ENC, min_length=16, label="DB_ENCRYPTION_KEY"
    )
    assert production_secret_rejection_reason(
        "short", min_length=32, label="JWT_SECRET"
    )
    assert (
        production_secret_rejection_reason(
            _STRONG_SECRET, min_length=32, label="JWT_SECRET"
        )
        is None
    )


# ---------------------------------------------------------------------------
# Production gates
# ---------------------------------------------------------------------------


def test_production_rejects_default_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", _DEV_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _ADMIN_HASH)
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="JWT_SECRET") as exc_info:
        settings.validate()
    _assert_secret_gate(exc_info.value, "JWT_SECRET", "placeholder", "dev default")


def test_production_rejects_short_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "tooshort")
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _ADMIN_HASH)
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        settings.validate()


def test_production_rejects_default_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _DEV_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _ADMIN_HASH)
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
        settings.validate()


def test_production_rejects_short_session_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", "session-too-short")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _ADMIN_HASH)
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
        settings.validate()


def test_production_rejects_placeholder_db_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`.env.example` placeholder must not pass production validation."""
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _ADMIN_HASH)
    settings = _patch_settings(
        monkeypatch, DB_ENCRYPTION_KEY=_ENV_EXAMPLE_ENC
    )
    with pytest.raises(RuntimeError, match="DB_ENCRYPTION_KEY"):
        settings.validate()


def test_production_rejects_empty_db_encryption_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _ADMIN_HASH)
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "")
    import config.settings as _s

    _s._settings = None
    # Empty env still yields empty SecretStr on Settings construction.
    monkeypatch.setenv("RAG_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://example.com")
    settings = get_settings()
    with pytest.raises(RuntimeError, match="DB_ENCRYPTION_KEY"):
        settings.validate()


def test_production_rejects_empty_admin_password_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("ALLOW_DEV_ADMIN_LOGIN", raising=False)
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="ADMIN_PASSWORD_HASH"):
        settings.validate()


def test_production_rejects_dev_admin_bypass_even_with_optin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ALLOW_DEV_ADMIN_LOGIN must never unlock production (SEC-02)."""
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("ALLOW_DEV_ADMIN_LOGIN", "1")
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="ALLOW_DEV_ADMIN_LOGIN"):
        settings.validate()


def test_production_rejects_dev_admin_flag_even_when_hash_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag itself is forbidden in production (misconfiguration fail-closed)."""
    monkeypatch.setenv("JWT_SECRET", _STRONG_SECRET)
    monkeypatch.setenv("SESSION_SECRET_KEY", _STRONG_SECRET)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", _ADMIN_HASH)
    monkeypatch.setenv("ALLOW_DEV_ADMIN_LOGIN", "true")
    settings = _patch_settings(monkeypatch)
    with pytest.raises(RuntimeError, match="ALLOW_DEV_ADMIN_LOGIN"):
        settings.validate()


def test_ollama_health_rejects_non_http_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    """file:/ and other schemes must not reach urllib.urlopen (B310)."""
    monkeypatch.setenv("RAG_ENV", "development")
    monkeypatch.setenv("REQUIRE_OLLAMA", "true")
    monkeypatch.setenv("OLLAMA_BASE_URL", "file:///etc/passwd")
    monkeypatch.setenv("LLM_PROVIDER_PROFILE", "local-first")
    import config.settings as _s

    _s._settings = None
    settings = get_settings()
    with pytest.raises(RuntimeError, match="http/https|scheme"):
        settings.validate()


def test_development_does_not_require_strong_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_ENV", "development")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.delenv("DB_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("ALLOW_DEV_ADMIN_LOGIN", "1")
    import config.settings as _s

    _s._settings = None
    settings = get_settings()
    try:
        settings.validate()
    except RuntimeError as exc:
        msg = str(exc)
        # Dev mode must not raise on missing prod secrets / dev-admin flag.
        assert "JWT_SECRET" not in msg, msg
        assert "SESSION_SECRET_KEY" not in msg, msg
        assert "ADMIN_PASSWORD_HASH" not in msg, msg
        assert "ALLOW_DEV_ADMIN_LOGIN" not in msg, msg
        assert "DB_ENCRYPTION_KEY" not in msg or "required in production" not in msg, msg
