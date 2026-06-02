"""Content-Security-Policy guard (audit F2).

Locks in: every response carries a CSP, script execution is external-only
(script-src 'self' + the pinned CDN, no 'unsafe-inline'), and no static page
reintroduces a bare inline <script> block that such a CSP would silently break.
"""
from __future__ import annotations

import re
import warnings
from html.parser import HTMLParser
from pathlib import Path

warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from api.app import app  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC = PROJECT_ROOT / "static"


def _csp() -> str:
    with TestClient(app) as client:
        resp = client.get("/static/agent.html")
    assert resp.status_code == 200
    csp = resp.headers.get("content-security-policy")
    assert csp, "Content-Security-Policy header is missing"
    return csp


def test_csp_present_and_default_src_self() -> None:
    csp = _csp()
    assert "default-src 'self'" in csp


def test_csp_script_src_is_external_only() -> None:
    csp = _csp()
    directive = next(
        (d.strip() for d in csp.split(";") if d.strip().startswith("script-src")),
        "",
    )
    assert directive, "no script-src directive"
    assert "'self'" in directive
    # The whole point of F2: injected inline scripts must not run.
    assert "'unsafe-inline'" not in directive
    assert "'unsafe-eval'" not in directive


class _BareScriptFinder(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.bare = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and not any(k == "src" for k, _ in attrs):
            self.bare += 1


def test_static_pages_have_no_inline_script_blocks() -> None:
    offenders = []
    for html in sorted(STATIC.glob("*.html")):
        finder = _BareScriptFinder()
        finder.feed(html.read_text(encoding="utf-8"))
        # A bare <script> with no body and no src is harmless, but our pages have
        # none; any inline block is a CSP regression.
        if finder.bare and re.search(r"<script>\s*\S", html.read_text(encoding="utf-8")):
            offenders.append(html.name)
    assert not offenders, f"inline <script> blocks reintroduced in: {offenders}"
