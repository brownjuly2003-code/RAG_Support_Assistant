from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_quickstart_no_quota_burn_regression_example_stays_mock_only() -> None:
    content = (PROJECT_ROOT / "docs" / "QUICKSTART.md").read_text(encoding="utf-8")
    section = content.split("# Mock provider benchmark (no GK, no quota burn)", 1)[1]
    section = section.split("# Live GK mixed routing", 1)[0]

    assert "--allow-paid-apis" not in section
    assert "--no-persist" in section
