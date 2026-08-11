"""Plan DEP-01: docs-site npm audit posture and dated exceptions register."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_SITE = PROJECT_ROOT / "docs-site"
EXCEPTIONS = DOCS_SITE / "npm-audit-exceptions.json"
CHECK_SCRIPT = DOCS_SITE / "scripts" / "check-npm-audit.mjs"
PACKAGE_JSON = DOCS_SITE / "package.json"

# Reachability notes that only papered over Astro 6 residual moderates/lows.
# After the Astro 7 upgrade these packages must not keep stale exceptions.
ASTRO6_RESIDUAL_EXCEPTION_PACKAGES = frozenset(
    {
        "astro",
        "@astrojs/mdx",
        "@astrojs/starlight",
        "astro-expressive-code",
        "esbuild",
    }
)


def _caret_version(spec: str) -> tuple[int, int, int]:
    """Parse leading major.minor.patch from a caret/range npm version specifier."""
    match = re.match(r"^\^?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(spec).strip())
    assert match, f"unparseable version spec: {spec!r}"
    major, minor, patch = match.groups()
    return int(major), int(minor or 0), int(patch or 0)


def test_npm_audit_exceptions_register_is_valid() -> None:
    raw = json.loads(EXCEPTIONS.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw.get("updated")
    assert isinstance(raw.get("notes"), str) and raw["notes"].strip()
    exceptions = raw["exceptions"]
    # Empty list is valid after a clean Astro 7 audit; structure still enforced.
    assert isinstance(exceptions, list)

    today = date.today().isoformat()
    packages: set[str] = set()
    for entry in exceptions:
        assert entry["package"]
        assert entry["package"] not in packages
        packages.add(entry["package"])
        assert entry["max_severity"] in {"low", "moderate", "high"}
        assert entry["reason"] and len(entry["reason"]) >= 20
        assert entry["expires"] >= today, f"expired exception for {entry['package']}"
        assert entry.get("owner")
        assert isinstance(entry.get("advisories"), list)
        assert entry["package"] not in ASTRO6_RESIDUAL_EXCEPTION_PACKAGES, (
            f"stale Astro-6 residual exception for {entry['package']}"
        )


def test_docs_site_audit_script_and_package_script_exist() -> None:
    assert CHECK_SCRIPT.is_file()
    text = CHECK_SCRIPT.read_text(encoding="utf-8")
    assert "DEP-01" in text
    assert "npm-audit-exceptions.json" in text

    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    assert pkg["scripts"]["audit:deps"] == "node scripts/check-npm-audit.mjs"
    deps = pkg["dependencies"]

    # Lock refresh targets: Astro 7.2+, Starlight 0.41+, sharp 0.35+ (no high residual).
    astro_ver = _caret_version(deps["astro"])
    assert astro_ver[0] == 7, f"astro major must be 7, got {deps['astro']!r}"
    assert deps["astro"].startswith("^7.")

    starlight_ver = _caret_version(deps["@astrojs/starlight"])
    assert starlight_ver[0] == 0 and starlight_ver[1] >= 41, (
        f"@astrojs/starlight must be ^0.41+, got {deps['@astrojs/starlight']!r}"
    )

    # Astro 7 requires direct ownership of @astrojs/markdown-remark when using
    # markdown.rehypePlugins (unified processor is imported from this package).
    md_spec = deps.get("@astrojs/markdown-remark")
    assert md_spec, (
        "direct @astrojs/markdown-remark dependency required for rehypePlugins on Astro 7"
    )
    md_ver = _caret_version(md_spec)
    assert md_ver[0] == 7 and md_ver[1] >= 2, (
        f"@astrojs/markdown-remark must be ^7.2+, got {md_spec!r}"
    )

    assert deps["sharp"].startswith("^0.35")


def test_docs_site_package_lock_present() -> None:
    lock = DOCS_SITE / "package-lock.json"
    assert lock.is_file()
    assert lock.stat().st_size > 10_000
