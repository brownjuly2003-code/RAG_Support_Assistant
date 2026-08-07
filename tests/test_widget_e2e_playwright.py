"""Plan §8.5: Playwright cross-origin widget bootstrap E2E.

Covers embed under allowlisted parent origin, bootstrap JWT + session_id,
and fail-closed paths (empty allowlist / disallowed parent). Requires a real
Chromium via Playwright; skips cleanly when the package or browser is missing.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import uvicorn

from auth.jwt_handler import verify_token

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_http_ok(url: str, *, timeout_sec: float = 20.0) -> None:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout_sec
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:  # noqa: S310
                if 200 <= int(resp.status) < 500:
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(0.1)
    raise RuntimeError(f"server not ready at {url}: {last_err}")


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


@pytest.fixture
def parent_origin_and_dir(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    port = _free_port()
    origin = f"http://127.0.0.1:{port}"
    site = tmp_path / "parent-site"
    site.mkdir()
    yield origin, site

    # Server fixture below owns the listener; this fixture only provides paths.


@pytest.fixture
def widget_api_base(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    parent_origin_and_dir: tuple[str, Path],
    request: pytest.FixtureRequest,
) -> Iterator[str]:
    """Live uvicorn of api.app with widget allowlist pointed at the parent origin."""
    parent_origin, _ = parent_origin_and_dir
    allowlist = getattr(request, "param", parent_origin)

    # Isolate data paths and keep startup light for browser E2E.
    data_dir = tmp_path / "widget-e2e-data"
    data_dir.mkdir()
    monkeypatch.setenv("RAG_ENV", "development")
    monkeypatch.setenv("AUTO_MIGRATE", "false")
    monkeypatch.setenv("OTEL_ENABLED", "false")
    monkeypatch.setenv("WIDGET_ALLOWED_ORIGINS", allowlist)
    monkeypatch.setenv("WIDGET_TOKEN_TTL_SEC", "600")
    monkeypatch.setenv("JWT_SECRET", "dev-secret-change-in-production-test-32chars!!")
    monkeypatch.setenv("SESSION_SECRET_KEY", "dev-session-secret-key-change-me-32!!")
    monkeypatch.setenv("DB_ENCRYPTION_KEY", "dev-db-encryption-key")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.setenv("ALLOW_ANONYMOUS_ADMIN", "1")

    import api.app as api_app
    import config.settings as settings_mod

    settings_mod._settings = None
    cache_clear = getattr(settings_mod.get_settings, "cache_clear", None)
    if callable(cache_clear):
        cache_clear()

    monkeypatch.setattr(api_app, "initialize_vector_store", lambda: None)
    monkeypatch.setattr(api_app, "_run_alembic_upgrade", lambda: None)

    port = _free_port()
    config = uvicorn.Config(
        api_app.app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = False
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    try:
        _wait_http_ok(f"{base}/api/health/live")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        settings_mod._settings = None
        if callable(cache_clear):
            cache_clear()


@pytest.fixture
def parent_base(
    parent_origin_and_dir: tuple[str, Path],
    widget_api_base: str,
) -> Iterator[str]:
    parent_origin, site = parent_origin_and_dir
    port = int(parent_origin.rsplit(":", 1)[-1])
    host_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Widget host</title>
</head>
<body>
  <h1>Widget host</h1>
  <pre id="log"></pre>
  <script>
    window.__ragEvents = [];
    window.addEventListener('message', function (event) {{
      if (!event.data || typeof event.data !== 'object' || !event.data.type) {{
        return;
      }}
      if (String(event.data.type).indexOf('rag-widget-') !== 0) {{
        return;
      }}
      window.__ragEvents.push(event.data);
      var node = document.getElementById('log');
      if (node) {{
        node.textContent = JSON.stringify(window.__ragEvents);
      }}
    }});
  </script>
  <script
    src="{widget_api_base}/static/widget.js"
    data-api="{widget_api_base}"
    data-tenant="acme"
    data-title="E2E Support"
  ></script>
</body>
</html>
"""
    (site / "index.html").write_text(host_html, encoding="utf-8")
    handler = partial(_QuietStaticHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield parent_origin
    finally:
        server.shutdown()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def browser_chromium():
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception as exc:  # noqa: BLE001
                pytest.skip(f"Chromium unavailable for Playwright: {exc}")
            try:
                yield browser
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Playwright runtime unavailable: {exc}")


def _open_widget(page, parent_base: str):
    page.goto(f"{parent_base}/", wait_until="domcontentloaded")
    page.locator("#rag-widget-toggle").click()
    page.wait_for_selector("#rag-widget-container iframe", state="attached", timeout=10_000)


def test_cross_origin_widget_bootstrap_issues_jwt_and_session(
    browser_chromium,
    parent_base: str,
    widget_api_base: str,
) -> None:
    """Allowlisted parent embeds widget → handshake → bootstrap JWT + session_id."""
    with browser_chromium.new_context() as context:
        page = context.new_page()
        with page.expect_response(
            lambda r: "/api/widget/bootstrap" in r.url and r.request.method == "POST",
            timeout=15_000,
        ) as bootstrap_info:
            _open_widget(page, parent_base)

        response = bootstrap_info.value
        assert response.status == 200, response.text()
        data = response.json()
        assert data.get("token")
        assert data.get("session_id")
        assert data.get("parent_origin") == parent_base
        assert data.get("tenant_id") == "acme"

        payload = verify_token(data["token"], expected_type="widget")
        assert payload is not None
        assert payload["aud"] == "widget"
        assert payload["role"] == "widget"
        assert payload["tenant"] == "acme"
        assert payload["origin"] == parent_base
        assert payload["sid"] == data["session_id"]

        page.wait_for_function(
            """() => window.__ragEvents.some(
                (e) => e.type === 'rag-widget-bootstrapped' && e.sessionId
            )""",
            timeout=10_000,
        )
        page.wait_for_function(
            """() => window.__ragEvents.some((e) => e.type === 'rag-widget-ack')""",
            timeout=5_000,
        )
        events = page.evaluate("window.__ragEvents")
        boot = next(e for e in events if e.get("type") == "rag-widget-bootstrapped")
        assert boot["sessionId"] == data["session_id"]

        # Iframe is framed under allowlisted parent (not blocked by frame-ancestors).
        iframe = page.frame_locator("#rag-widget-container iframe")
        iframe.locator("#input").wait_for(state="visible", timeout=10_000)

        # session_id reuse: second bootstrap from service Origin keeps the same sid.
        import json as _json
        import urllib.request

        reuse_body = _json.dumps(
            {
                "parent_origin": parent_base,
                "tenant_id": "acme",
                "session_id": data["session_id"],
            }
        ).encode("utf-8")
        reuse_req = urllib.request.Request(  # noqa: S310
            f"{widget_api_base}/api/widget/bootstrap",
            data=reuse_body,
            headers={
                "Content-Type": "application/json",
                "Origin": widget_api_base,
            },
            method="POST",
        )
        with urllib.request.urlopen(reuse_req, timeout=5) as reuse_resp:  # noqa: S310
            assert reuse_resp.status == 200
            reused = _json.loads(reuse_resp.read().decode("utf-8"))
        assert reused["session_id"] == data["session_id"]
        reused_payload = verify_token(reused["token"], expected_type="widget")
        assert reused_payload is not None
        assert reused_payload["sid"] == data["session_id"]


def _post_bootstrap(api_base: str, *, parent_origin: str, origin_header: str) -> tuple[int, dict]:
    import json as _json
    import urllib.error
    import urllib.request

    body = _json.dumps(
        {"parent_origin": parent_origin, "tenant_id": "acme"}
    ).encode("utf-8")
    req = urllib.request.Request(  # noqa: S310
        f"{api_base}/api/widget/bootstrap",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Origin": origin_header,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            return int(resp.status), _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = _json.loads(raw) if raw else {}
        except _json.JSONDecodeError:
            payload = {"detail": raw}
        return int(exc.code), payload


@pytest.mark.parametrize("widget_api_base", [""], indirect=True)
def test_empty_allowlist_fail_closed(
    browser_chromium,
    parent_base: str,
    widget_api_base: str,
) -> None:
    """Empty WIDGET_ALLOWED_ORIGINS → CSP none + bootstrap 403 + no bootstrapped event."""
    import urllib.request

    req = urllib.request.Request(f"{widget_api_base}/static/widget.html")  # noqa: S310
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
        headers = {k.lower(): v for k, v in resp.headers.items()}
        csp = headers.get("content-security-policy", "")
        assert "frame-ancestors 'none'" in csp

    status, body = _post_bootstrap(
        widget_api_base,
        parent_origin=parent_base,
        origin_header=widget_api_base,
    )
    assert status == 403
    assert "WIDGET_ALLOWED_ORIGINS" in str(body.get("detail", ""))

    with browser_chromium.new_context() as context:
        page = context.new_page()
        _open_widget(page, parent_base)
        page.wait_for_timeout(1200)
        events = page.evaluate("window.__ragEvents || []")
        assert not any(e.get("type") == "rag-widget-bootstrapped" for e in events)


@pytest.mark.parametrize(
    "widget_api_base",
    ["https://other-allowed.example.com"],
    indirect=True,
)
def test_disallowed_parent_origin_fail_closed(
    browser_chromium,
    parent_base: str,
    widget_api_base: str,
) -> None:
    """Parent outside allowlist → bootstrap 403; browser never reports bootstrapped."""
    import urllib.request

    req = urllib.request.Request(f"{widget_api_base}/static/widget.html")  # noqa: S310
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
        headers = {k.lower(): v for k, v in resp.headers.items()}
        csp = headers.get("content-security-policy", "")
        # Parent is not listed — only the unrelated allowlisted origin.
        assert parent_base not in csp
        assert "https://other-allowed.example.com" in csp

    status, body = _post_bootstrap(
        widget_api_base,
        parent_origin=parent_base,
        origin_header=widget_api_base,
    )
    assert status == 403
    assert "not in" in str(body.get("detail", "")).lower() or "WIDGET" in str(
        body.get("detail", "")
    )

    with browser_chromium.new_context() as context:
        page = context.new_page()
        _open_widget(page, parent_base)
        page.wait_for_timeout(1200)
        events = page.evaluate("window.__ragEvents || []")
        assert not any(e.get("type") == "rag-widget-bootstrapped" for e in events)


def test_widget_html_frame_ancestors_match_allowlist(
    widget_api_base: str,
    parent_base: str,
) -> None:
    """Path-specific CSP allows the parent and does not set X-Frame-Options DENY."""
    import urllib.request

    req = urllib.request.Request(f"{widget_api_base}/static/widget.html")  # noqa: S310
    with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
        headers = {k.lower(): v for k, v in resp.headers.items()}
        assert "x-frame-options" not in headers
        csp = headers.get("content-security-policy", "")
        assert f"frame-ancestors {parent_base}" in csp
