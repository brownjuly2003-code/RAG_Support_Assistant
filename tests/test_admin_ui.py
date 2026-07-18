import pytest
from fastapi.testclient import TestClient

STATIC_HTML_PATHS = [
    "/static/admin.html",
    "/static/agent.html",
    "/static/analytics.html",
    "/static/chat.html",
    "/static/help.html",
    "/static/login.html",
    "/static/metrics.html",
    "/static/widget.html",
]


def test_admin_html_served(client: TestClient) -> None:
    response = client.get("/static/admin.html")

    assert response.status_code == 200
    assert "RAG Support Assistant" in response.text
    assert "Circuit Breaker" in response.text
    assert "/static/admin.css" in response.text
    assert "/static/admin.js" in response.text


def test_admin_js_served(client: TestClient) -> None:
    response = client.get("/static/admin.js")

    assert response.status_code == 200
    # Cookie-based auth (S1): the UI establishes an httpOnly session and offers
    # logout; tokens must never be persisted in JS-readable storage.
    assert "/api/auth/session" in response.text
    assert "/api/auth/logout" in response.text
    assert "localStorage.setItem" not in response.text
    assert "fetch(" in response.text


def test_widget_assets_served(client: TestClient) -> None:
    script_response = client.get("/static/widget.js")
    html_response = client.get("/static/widget.html")

    assert script_response.status_code == 200
    assert "rag-widget-toggle" in script_response.text
    assert "/static/widget.html" in script_response.text

    assert html_response.status_code == 200
    # Inline script extracted to /static/widget.inline.js for CSP (script-src 'self').
    assert "/static/widget.inline.js" in html_response.text
    inline_response = client.get("/static/widget.inline.js")
    assert inline_response.status_code == 200
    assert "rag-widget-ready" in inline_response.text


@pytest.mark.parametrize("path", STATIC_HTML_PATHS)
def test_static_html_pages_served(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 200
    assert "<html" in response.text
