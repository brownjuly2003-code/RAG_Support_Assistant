from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.responses import RedirectResponse
from fastapi.testclient import TestClient

CLIENT_SETTINGS_OVERRIDES = {
    "google_oidc_client_id": "google-client-id",
    "google_oidc_client_secret": "google-client-secret",
    "azure_oidc_tenant": "tenant-123",
    "azure_oidc_client_id": "azure-client-id",
    "azure_oidc_client_secret": "azure-client-secret",
    "tenant_email_domains": "acme.com:tenant-acme,beta.io:tenant-beta",
    "session_secret_key": "test-session-secret",
}


class _SecretValue:
    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        return self._value


def test_oidc_module_import_does_not_emit_authlib_deprecation_warning() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import auth.oidc"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "AuthlibDeprecationWarning" not in result.stderr


def test_list_sso_providers_accepts_secret_value_objects() -> None:
    from auth.oidc import list_sso_providers

    settings = SimpleNamespace(
        google_oidc_client_id="google-client-id",
        google_oidc_client_secret=_SecretValue("google-secret"),
        azure_oidc_tenant="tenant-123",
        azure_oidc_client_id="azure-client-id",
        azure_oidc_client_secret=_SecretValue("azure-secret"),
    )

    assert list_sso_providers(settings) == [
        {"name": "google", "label": "Google"},
        {"name": "azure", "label": "Microsoft"},
    ]


def test_get_oauth_client_registers_enabled_providers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import auth.oidc as oidc

    registrations: list[dict[str, object]] = []

    class _FakeOAuth:
        def register(self, **kwargs):
            registrations.append(dict(kwargs))

        def create_client(self, provider: str) -> dict[str, str]:
            return {"provider": provider}

    settings = SimpleNamespace(
        google_oidc_client_id="google-client-id",
        google_oidc_client_secret=_SecretValue("google-secret"),
        azure_oidc_tenant="tenant-123",
        azure_oidc_client_id="azure-client-id",
        azure_oidc_client_secret=_SecretValue("azure-secret"),
    )

    monkeypatch.setattr(oidc, "_load_oauth_class", lambda: _FakeOAuth)

    client = oidc.get_oauth_client("azure", settings)

    assert client == {"provider": "azure"}
    assert [item["name"] for item in registrations] == ["google", "azure"]
    assert registrations[0]["client_secret"] == "google-secret"
    assert registrations[0]["server_metadata_url"] == (
        "https://accounts.google.com/.well-known/openid-configuration"
    )
    assert registrations[1]["client_secret"] == "azure-secret"
    assert registrations[1]["server_metadata_url"] == (
        "https://login.microsoftonline.com/tenant-123/v2.0/.well-known/openid-configuration"
    )


def test_get_oauth_client_skips_authlib_for_unconfigured_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import auth.oidc as oidc

    settings = SimpleNamespace(
        google_oidc_client_id=None,
        google_oidc_client_secret=None,
        azure_oidc_tenant=None,
        azure_oidc_client_id=None,
        azure_oidc_client_secret=None,
    )

    monkeypatch.setattr(
        oidc,
        "_load_oauth_class",
        lambda: (_ for _ in ()).throw(AssertionError("authlib should not load")),
    )

    assert oidc.get_oauth_client("google", settings) is None


def test_sso_providers_endpoint_lists_enabled_providers(client: TestClient) -> None:
    response = client.get("/api/auth/sso/providers")

    assert response.status_code == 200
    assert response.json() == {
        "providers": [
            {"name": "google", "label": "Google"},
            {"name": "azure", "label": "Microsoft"},
        ]
    }


def test_sso_login_redirects_to_provider(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    class _FakeClient:
        async def authorize_redirect(self, request, redirect_uri):
            return RedirectResponse(
                f"https://idp.example/authorize?redirect_uri={redirect_uri}",
                status_code=307,
            )

    monkeypatch.setattr("api.app.get_oidc_client", lambda provider: _FakeClient())

    response = client.get("/api/auth/sso/google/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"].startswith("https://idp.example/authorize?")


def test_sso_callback_issues_jwt_cookie_for_mapped_tenant(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
) -> None:
    from auth.jwt_handler import verify_token

    class _FakeClient:
        async def authorize_access_token(self, request):
            return {
                "userinfo": {
                    "sub": "google-subject-1",
                    "email": "alex@acme.com",
                    "name": "Alex Example",
                }
            }

    async def _fake_resolve_oidc_user(provider: str, userinfo: dict):
        assert provider == "google"
        assert userinfo["email"] == "alex@acme.com"
        return SimpleNamespace(id="user-123", role="viewer", tenant_id="tenant-acme")

    monkeypatch.setattr("api.app.get_oidc_client", lambda provider: _FakeClient())
    monkeypatch.setattr("api.app.resolve_oidc_user", _fake_resolve_oidc_user)

    response = client.get("/api/auth/sso/google/callback", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/static/chat.html"

    access_token = response.cookies.get("access_token")
    refresh_token = response.cookies.get("refresh_token")
    assert access_token
    assert refresh_token

    access_payload = verify_token(access_token, expected_type="access")
    refresh_payload = verify_token(refresh_token, expected_type="refresh")
    assert access_payload is not None
    assert refresh_payload is not None
    assert access_payload["tenant"] == "tenant-acme"
    assert access_payload["role"] == "viewer"
    assert refresh_payload["tenant"] == "tenant-acme"


def test_tenant_email_domain_mapping_prefers_configured_tenant() -> None:
    from auth.oidc import resolve_tenant_from_email

    assert (
        resolve_tenant_from_email(
            "alex@acme.com",
            "acme.com:tenant-acme,beta.io:tenant-beta",
        )
        == "tenant-acme"
    )

    with pytest.raises(ValueError):
        resolve_tenant_from_email(
            "alex@unknown.org",
            "acme.com:tenant-acme,beta.io:tenant-beta",
        )
