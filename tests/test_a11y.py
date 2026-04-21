from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLE_PAGES = [
    PROJECT_ROOT / "static" / "help.html",
    PROJECT_ROOT / "static" / "admin.html",
    PROJECT_ROOT / "templates" / "index.html",
    PROJECT_ROOT / "templates" / "escalations.html",
    PROJECT_ROOT / "templates" / "traces.html",
]


def test_all_table_headers_define_scope() -> None:
    missing: dict[str, int] = {}

    for path in TABLE_PAGES:
        html = path.read_text(encoding="utf-8")
        th_without_scope = [
            match.group(0)
            for match in re.finditer(r"<th\b(?![^>]*\bscope=)[^>]*>", html)
        ]
        if th_without_scope:
            missing[path.name] = len(th_without_scope)

    assert not missing, f"Headers without scope: {missing}"


def test_chat_upload_dropzone_is_keyboard_accessible() -> None:
    html = (PROJECT_ROOT / "static" / "chat.html").read_text(encoding="utf-8")

    assert 'id="uploadDropzone"' in html
    assert 'role="button"' in html
    assert 'tabindex="0"' in html
    assert 'aria-label="Загрузить документы"' in html


def test_components_css_defines_focus_visible_styles() -> None:
    css = (PROJECT_ROOT / "static" / "styles" / "components.css").read_text(encoding="utf-8")

    assert ":focus-visible" in css
    assert "outline" in css

