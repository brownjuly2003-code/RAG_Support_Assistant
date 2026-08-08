"""Plan DEP-01: docs-site npm audit posture and dated exceptions register."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_SITE = PROJECT_ROOT / "docs-site"
EXCEPTIONS = DOCS_SITE / "npm-audit-exceptions.json"
CHECK_SCRIPT = DOCS_SITE / "scripts" / "check-npm-audit.mjs"
PACKAGE_JSON = DOCS_SITE / "package.json"


def test_npm_audit_exceptions_register_is_valid() -> None:
    raw = json.loads(EXCEPTIONS.read_text(encoding="utf-8"))
    assert raw["schema_version"] == 1
    assert raw.get("updated")
    exceptions = raw["exceptions"]
    assert isinstance(exceptions, list) and exceptions

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


def test_docs_site_audit_script_and_package_script_exist() -> None:
    assert CHECK_SCRIPT.is_file()
    text = CHECK_SCRIPT.read_text(encoding="utf-8")
    assert "DEP-01" in text
    assert "npm-audit-exceptions.json" in text

    pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    assert pkg["scripts"]["audit:deps"] == "node scripts/check-npm-audit.mjs"
    # Lock refresh targets: Astro 6.4+ and sharp 0.35+ (no high residual).
    assert pkg["dependencies"]["astro"].startswith("^6.4")
    assert pkg["dependencies"]["sharp"].startswith("^0.35")


def test_docs_site_package_lock_present() -> None:
    lock = DOCS_SITE / "package-lock.json"
    assert lock.is_file()
    assert lock.stat().st_size > 10_000
