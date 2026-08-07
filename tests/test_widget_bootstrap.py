"""Plan §8.1: widget bootstrap token, origin allowlist, path-specific framing."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from api.routers.widget import (
    frame_ancestors_csp,
    is_widget_static_path,
    normalize_origin,
    origin_allowed,
)
from auth.dependencies import get_current_user
from auth.jwt_handler import create_widget_token, verify_token


def test_normalize_origin_strips_path() -> None:
    assert normalize_origin("https://shop.example.com/app") == "https://shop.example.com"
    with pytest.raises(ValueError):
        normalize_origin("*")
    with pytest.raises(ValueError):
        normalize_origin("")


def test_origin_allowed_allowlist() -> None:
    allowed = ["https://shop.example.com", "https://help.example.com"]
    assert origin_allowed("https://shop.example.com", allowed) is True
    assert origin_allowed("https://evil.example.com", allowed) is False
    assert origin_allowed("https://shop.example.com", []) is False


def test_frame_ancestors_csp() -> None:
    assert frame_ancestors_csp([]) == "frame-ancestors 'none'"
    assert "https://shop.example.com" in frame_ancestors_csp(
        ["https://shop.example.com"]
    )
    assert is_widget_static_path("/static/widget.html") is True
    assert is_widget_static_path("/static/widget.inline.js") is True
    assert is_widget_static_path("/api/health/live") is False


def test_create_and_verify_widget_token() -> None:
    token = create_widget_token(
        tenant="acme",
        origin="https://shop.example.com",
        session_id="11111111-1111-1111-1111-111111111111",
        ttl_sec=300,
    )
    payload = verify_token(token, expected_type="widget")
    assert payload is not None
    assert payload["aud"] == "widget"
    assert payload["role"] == "widget"
    assert payload["tenant"] == "acme"
    assert payload["origin"] == "https://shop.example.com"
    assert payload["sid"] == "11111111-1111-1111-1111-111111111111"
    assert verify_token(token, expected_type="access") is None


def test_bootstrap_rejects_when_allowlist_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIDGET_ALLOWED_ORIGINS", "")
    # Force settings reload if cached
    import config.settings as settings_mod

    if hasattr(settings_mod, "get_settings"):
        cache_clear = getattr(settings_mod.get_settings, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()

    api_app = importlib.import_module("api.app")
    client = TestClient(api_app.app)
    resp = client.post(
        "/api/widget/bootstrap",
        json={
            "parent_origin": "https://shop.example.com",
            "tenant_id": "acme",
        },
    )
    assert resp.status_code == 403
    assert "WIDGET_ALLOWED_ORIGINS" in resp.json()["detail"]


def test_bootstrap_issues_token_for_allowed_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import config.settings as settings_mod

    monkeypatch.setenv("WIDGET_ALLOWED_ORIGINS", "https://shop.example.com")
    monkeypatch.setenv("WIDGET_TOKEN_TTL_SEC", "600")
    cache_clear = getattr(settings_mod.get_settings, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()

    api_app = importlib.import_module("api.app")
    client = TestClient(api_app.app)
    resp = client.post(
        "/api/widget/bootstrap",
        json={
            "parent_origin": "https://shop.example.com/path",
            "tenant_id": "acme",
            "handshake_nonce": "n-1",
        },
        headers={"Origin": "https://shop.example.com"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["token"]
    assert data["session_id"]
    assert data["parent_origin"] == "https://shop.example.com"
    assert data["expires_in"] == 600
    assert data["handshake_nonce"] == "n-1"

    payload = verify_token(data["token"], expected_type="widget")
    assert payload is not None
    assert payload["tenant"] == "acme"


def test_bootstrap_rejects_origin_header_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import config.settings as settings_mod

    monkeypatch.setenv("WIDGET_ALLOWED_ORIGINS", "https://shop.example.com")
    cache_clear = getattr(settings_mod.get_settings, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()

    api_app = importlib.import_module("api.app")
    client = TestClient(api_app.app)
    resp = client.post(
        "/api/widget/bootstrap",
        json={"parent_origin": "https://shop.example.com"},
        headers={"Origin": "https://evil.example.com"},
    )
    assert resp.status_code == 403


def test_widget_html_has_path_specific_frame_ancestors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import config.settings as settings_mod

    monkeypatch.setenv("WIDGET_ALLOWED_ORIGINS", "https://shop.example.com")
    cache_clear = getattr(settings_mod.get_settings, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()

    api_app = importlib.import_module("api.app")
    client = TestClient(api_app.app)
    resp = client.get("/static/widget.html")
    assert resp.status_code == 200
    assert "X-Frame-Options" not in resp.headers
    csp = resp.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors https://shop.example.com" in csp

    other = client.get("/api/health/live")
    assert other.headers.get("X-Frame-Options") == "DENY"


def test_widget_token_authenticates_as_widget_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.requests import Request

    token = create_widget_token(
        tenant="acme",
        origin="https://shop.example.com",
        session_id="22222222-2222-2222-2222-222222222222",
    )

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }
    request = Request(scope)
    user = get_current_user(request)
    assert user["role"] == "widget"
    assert user["tenant"] == "acme"
    assert user["session_id"] == "22222222-2222-2222-2222-222222222222"


def test_widget_inline_js_has_bootstrap_and_session_contract() -> None:
    from pathlib import Path

    text = Path("static/widget.inline.js").read_text(encoding="utf-8")
    assert "/api/widget/bootstrap" in text
    assert "session_id" in text or "sessionId" in text
    assert "Authorization" in text
    assert "rag-widget-ack" in text
    assert "parentOrigin === '*'" not in text or "isValidOrigin" in text

    parent = Path("static/widget.js").read_text(encoding="utf-8")
    assert "handshake_nonce" in parent
    assert "event.origin !== iframeOrigin" in parent
