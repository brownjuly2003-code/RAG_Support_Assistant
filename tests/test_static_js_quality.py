from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _checked_js_files() -> list[Path]:
    docs_site_scripts = sorted((PROJECT_ROOT / "docs-site" / "scripts").glob("*.mjs"))
    return [
        PROJECT_ROOT / "static" / "admin.js",
        PROJECT_ROOT / "static" / "widget.js",
        PROJECT_ROOT / "docs-site" / "astro.config.mjs",
        *docs_site_scripts,
    ]


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
