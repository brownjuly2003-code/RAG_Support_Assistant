"""S1: admin/agent auth via httpOnly cookie (no token in localStorage).

Covers the session_auth cookie channel added for finding S1:
- login sets an httpOnly Secure(prod) SameSite=Strict cookie with the right flags,
- a request authenticates via the cookie alone (through the cookie bridge),
- classic Authorization-header auth is unchanged (backward compatible),
- POST /auth/session mints the cookie from a pasted bearer token,
- POST /auth/logout clears the cookies.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

# Dev-mode login (admin/admin) requires no configured password hash.
CLIENT_DELETE_ENV = ("ADMIN_PASSWORD_HASH",)
# The cookie/bridge auth proofs run with an API key configured so the
# anonymous-admin fallback is OFF and a 200 really means "the cookie
# authenticated the request" (with the fallback on, /api/metrics answers 200
# even with no credentials at all).
CLIENT_WITH_KEY_DELETE_ENV = ("ADMIN_PASSWORD_HASH",)

# A protected endpoint that requires the admin role and no request body.
PROTECTED_URL = "/api/metrics"
# A state-changing admin endpoint with no body (form-POST reachable): the
# cookie bridge must refuse to authenticate it from a cross-site Origin.
UNSAFE_URL = "/api/admin/circuit-breaker/reset"


def _set_cookie_header(response: object, name: str) -> str | None:
    """Return the raw Set-Cookie header line for ``name`` (or None)."""
    for key, value in response.headers.multi_items():  # type: ignore[attr-defined]
        if key.lower() == "set-cookie" and value.startswith(name + "="):
            return value
    return None


def _login(client: TestClient) -> dict:
    resp = client.post("/api/auth/login", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200, resp.text
    return resp


def test_login_sets_httponly_cookie_with_flags(client: TestClient) -> None:
    resp = _login(client)

    # Body contract is unchanged: tokens are still returned for API clients/tests.
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body

    access_cookie = _set_cookie_header(resp, "access_token")
    refresh_cookie = _set_cookie_header(resp, "refresh_token")
    assert access_cookie is not None
    assert refresh_cookie is not None

    lowered = access_cookie.lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert "path=/" in lowered
    assert "max-age=3600" in lowered  # ACCESS_TOKEN_TTL default
    # Not Secure in development (so the flag never blocks local http testing).
    assert "secure" not in lowered

    assert "max-age=604800" in refresh_cookie.lower()  # REFRESH_TOKEN_TTL default


def test_login_cookie_is_secure_in_production(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api import app as api_app

    settings = api_app.get_settings()
    monkeypatch.setattr(settings, "rag_env", "production", raising=False)

    resp = _login(client)
    access_cookie = _set_cookie_header(resp, "access_token")
    assert access_cookie is not None
    assert "secure" in access_cookie.lower()


def test_request_authenticated_via_cookie_only(client_with_key: TestClient) -> None:
    # Without credentials the endpoint is closed (anonymous fallback is OFF
    # under this fixture) — this makes the cookie assertion below meaningful.
    assert client_with_key.get(PROTECTED_URL).status_code == 401

    # login stores the cookie in the client jar.
    _login(client_with_key)
    assert client_with_key.cookies.get("access_token")

    # No Authorization header -> the cookie bridge authenticates the request.
    resp = client_with_key.get(PROTECTED_URL)
    assert resp.status_code == 200, resp.text

    # Dropping the cookie closes the endpoint again.
    client_with_key.cookies.clear()
    assert client_with_key.get(PROTECTED_URL).status_code == 401


def test_header_auth_still_works_without_cookie(client_with_key: TestClient) -> None:
    token = _login(client_with_key).json()["access_token"]
    client_with_key.cookies.clear()

    resp = client_with_key.get(PROTECTED_URL, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text


def test_establish_session_sets_cookie_from_bearer_token(client_with_key: TestClient) -> None:
    token = _login(client_with_key).json()["access_token"]
    client_with_key.cookies.clear()

    established = client_with_key.post(
        "/api/auth/session",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert established.status_code == 200, established.text
    assert established.json() == {"status": "ok"}
    assert _set_cookie_header(established, "access_token") is not None
    assert client_with_key.cookies.get("access_token")

    # The freshly minted cookie authenticates a follow-up request on its own
    # (the anonymous fallback is off, so this is the cookie's doing).
    resp = client_with_key.get(PROTECTED_URL)
    assert resp.status_code == 200, resp.text


def test_cookie_auth_refused_for_cross_site_post(client_with_key: TestClient) -> None:
    """CSRF gate: a state-changing POST with a foreign Origin must not be
    authenticated from the cookie (the SSO writer sets the same cookie name
    with SameSite=Lax, so the bridge cannot rely on SameSite alone)."""
    _login(client_with_key)
    assert client_with_key.cookies.get("access_token")

    cross_site = client_with_key.post(UNSAFE_URL, headers={"Origin": "https://evil.example"})
    assert cross_site.status_code == 401, cross_site.text

    # Same-origin fetch (Origin matches Host) keeps working: authentication
    # succeeds and the endpoint answers 200 (breaker reset) or 409 (no breaker
    # built in this test app) — anything but 401.
    same_origin = client_with_key.post(UNSAFE_URL, headers={"Origin": "http://testserver"})
    assert same_origin.status_code in (200, 409), same_origin.text

    # Origin-less requests (curl, non-browser clients) are unaffected.
    no_origin = client_with_key.post(UNSAFE_URL)
    assert no_origin.status_code in (200, 409), no_origin.text


def test_establish_session_rejects_missing_token(client: TestClient) -> None:
    client.cookies.clear()
    resp = client.post("/api/auth/session")
    assert resp.status_code == 401


def test_establish_session_rejects_invalid_token(client: TestClient) -> None:
    client.cookies.clear()
    resp = client.post(
        "/api/auth/session",
        headers={"Authorization": "Bearer not-a-real-jwt"},
    )
    assert resp.status_code == 401


def test_logout_clears_cookies(client: TestClient) -> None:
    _login(client)
    assert client.cookies.get("access_token")

    resp = client.post("/api/auth/logout")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}

    cleared = _set_cookie_header(resp, "access_token")
    assert cleared is not None
    assert "max-age=0" in cleared.lower()
    # httpx honours Max-Age=0 and drops the cookie from the jar.
    assert not client.cookies.get("access_token")
