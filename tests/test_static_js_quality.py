from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
JSDELIVR_NPM_PREFIX = "https://cdn.jsdelivr.net/npm/"


class _ScriptTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            self.scripts.append({key: value or "" for key, value in attrs})


def _checked_js_files() -> list[Path]:
    docs_site_scripts = sorted((PROJECT_ROOT / "docs-site" / "scripts").glob("*.mjs"))
    # Inline page scripts extracted out of static/*.html for CSP (script-src 'self').
    inline_page_scripts = sorted((PROJECT_ROOT / "static").glob("*.inline*.js"))
    return [
        PROJECT_ROOT / "static" / "admin.js",
        PROJECT_ROOT / "static" / "widget.js",
        *inline_page_scripts,
        PROJECT_ROOT / "docs-site" / "astro.config.mjs",
        *docs_site_scripts,
    ]


def _script_tags(path: Path) -> list[dict[str, str]]:
    parser = _ScriptTagParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.scripts


def _jsdelivr_package_spec(src: str) -> str:
    package_path = src.removeprefix(JSDELIVR_NPM_PREFIX)
    if package_path.startswith("@"):
        return "/".join(package_path.split("/", 2)[:2])
    return package_path.split("/", 1)[0]


def test_checked_in_javascript_files_parse_with_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not available")

    files = _checked_js_files()
    missing = [path.relative_to(PROJECT_ROOT).as_posix() for path in files if not path.exists()]
    assert not missing

    for path in files:
        result = subprocess.run(
            [node, "--check", str(path)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, (
            f"{path.relative_to(PROJECT_ROOT).as_posix()} failed node --check\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


def test_external_cdn_scripts_are_pinned_and_integrity_checked() -> None:
    violations: list[str] = []

    for path in [PROJECT_ROOT / "static" / "analytics.html"]:
        for attrs in _script_tags(path):
            src = attrs.get("src", "")
            if not src.startswith(JSDELIVR_NPM_PREFIX):
                continue

            package_spec = _jsdelivr_package_spec(src)
            relative_path = path.relative_to(PROJECT_ROOT).as_posix()
            if "@" not in package_spec.lstrip("@"):
                violations.append(f"{relative_path}: {src} is not version-pinned")
            if not attrs.get("integrity"):
                violations.append(f"{relative_path}: {src} has no SRI integrity")
            if attrs.get("crossorigin") != "anonymous":
                violations.append(f"{relative_path}: {src} must use crossorigin=anonymous")

    assert not violations
