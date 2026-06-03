from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ACTIVE_BENCHMARK_DOCS = [
    PROJECT_ROOT / "README.md",
    PROJECT_ROOT / "docs" / "QUICKSTART.md",
    PROJECT_ROOT / "docs" / "plans" / "2026-05-01-backlog.md",
    PROJECT_ROOT / "codex-tasks" / "task-177-regression-via-gracekelly-claude.md",
]


def test_quickstart_no_quota_burn_regression_example_stays_mock_only() -> None:
    content = (PROJECT_ROOT / "docs" / "QUICKSTART.md").read_text(encoding="utf-8")
    section = content.split("# Mock provider benchmark (no GK, no quota burn)", 1)[1]
    section = section.split("# Live GK mixed routing", 1)[0]

    assert "--allow-paid-apis" not in section
    assert "--no-persist" in section


def test_active_benchmark_docs_label_paid_api_examples_as_live_opt_in() -> None:
    for path in ACTIVE_BENCHMARK_DOCS:
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            if "--allow-paid-apis" not in line:
                continue
            context = "\n".join(lines[max(0, index - 5) : index + 6]).lower()

            assert "live" in context, f"{path}:{index + 1} must label paid API use as live"
            assert (
                "opt-in" in context or "manual" in context
            ), f"{path}:{index + 1} must require explicit opt-in/manual context"


def test_active_runtime_docs_install_from_hashed_locks() -> None:
    for path in (
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs" / "QUICKSTART.md",
        PROJECT_ROOT / "docs" / "disaster-recovery.md",
    ):
        content = path.read_text(encoding="utf-8")

        assert "pip install -r requirements.txt" not in content
        assert "pip install -r requirements-dev.txt" not in content
