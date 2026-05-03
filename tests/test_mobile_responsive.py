from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATIC_PAGES = {
    "chat": PROJECT_ROOT / "static" / "chat.html",
    "help": PROJECT_ROOT / "static" / "help.html",
    "metrics": PROJECT_ROOT / "static" / "metrics.html",
    "admin": PROJECT_ROOT / "static" / "admin.html",
}
TEMPLATE_PAGES = sorted((PROJECT_ROOT / "templates").glob("*.html"))


def test_static_pages_define_480_768_1024_breakpoints() -> None:
    missing: dict[str, list[str]] = {}

    for name, path in STATIC_PAGES.items():
        html = path.read_text(encoding="utf-8")
        page_missing = [
            breakpoint
            for breakpoint in ("480", "768", "1024")
            if breakpoint not in html
        ]
        if page_missing:
            missing[name] = page_missing

    assert not missing, f"Missing breakpoints: {missing}"


def test_chat_input_uses_safe_area_inset_bottom() -> None:
    html = (PROJECT_ROOT / "static" / "chat.html").read_text(encoding="utf-8")

    assert "safe-area-inset-bottom" in html


def test_all_templates_include_viewport_meta() -> None:
    missing = [
        path.name
        for path in TEMPLATE_PAGES
        if 'name="viewport"' not in path.read_text(encoding="utf-8")
    ]

    assert not missing, f"Templates without viewport meta: {missing}"
