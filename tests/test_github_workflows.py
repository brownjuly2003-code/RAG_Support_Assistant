from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = PROJECT_ROOT / ".github" / "workflows"


def _workflow_paths() -> list[Path]:
    return sorted(
        {
            *WORKFLOWS_DIR.glob("*.yml"),
            *WORKFLOWS_DIR.glob("*.yaml"),
        }
    )


def _workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS_DIR / name).read_text(encoding="utf-8"))


def test_github_actions_use_node24_compatible_majors() -> None:
    workflow_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in _workflow_paths()
    )

    assert "actions/checkout@v4" not in workflow_sources
    assert "actions/setup-python@v5" not in workflow_sources
    assert "actions/setup-node@v4" not in workflow_sources
    assert "actions/upload-pages-artifact@v3" not in workflow_sources
    assert "actions/deploy-pages@v4" not in workflow_sources
    assert "dorny/paths-filter@v3" not in workflow_sources

    for action in (
        "actions/checkout@v6",
        "actions/setup-python@v6",
        "actions/setup-node@v6",
        "actions/upload-pages-artifact@v5",
        "actions/deploy-pages@v5",
        "dorny/paths-filter@v4",
    ):
        assert action in workflow_sources


def test_workflow_major_guard_covers_yml_and_yaml_files(tmp_path: Path) -> None:
    global WORKFLOWS_DIR
    original_workflows_dir = WORKFLOWS_DIR
    (tmp_path / "ci.yml").write_text("name: CI\n", encoding="utf-8")
    (tmp_path / "security.yaml").write_text("name: Security\n", encoding="utf-8")

    try:
        WORKFLOWS_DIR = tmp_path
        assert [path.name for path in _workflow_paths()] == ["ci.yml", "security.yaml"]
    finally:
        WORKFLOWS_DIR = original_workflows_dir


def test_weekly_report_workflow_keeps_project_root_on_pythonpath() -> None:
    workflow = _workflow("weekly-report.yml")
    job = workflow["jobs"]["weekly-report"]
    run_step = next(
        step for step in job["steps"] if step.get("name") == "Run weekly report"
    )
    pythonpath = run_step.get("env", {}).get("PYTHONPATH") or job.get("env", {}).get(
        "PYTHONPATH"
    )

    assert pythonpath in {".", "${{ github.workspace }}"}


def test_weekly_report_workflow_installs_locked_runtime_dependencies() -> None:
    workflow = _workflow("weekly-report.yml")
    steps = workflow["jobs"]["weekly-report"]["steps"]
    setup_python = next(
        step for step in steps if step.get("uses", "").startswith("actions/setup-python")
    )
    install_step = next(step for step in steps if step.get("name") == "Install dependencies")

    assert setup_python["with"]["python-version"] == "3.11"
    assert install_step["run"] == "pip install --require-hashes -r requirements.lock"


def test_docs_site_workflow_audits_npm_dependencies_before_build() -> None:
    workflow = _workflow("docs-site.yml")
    steps = workflow["jobs"]["build"]["steps"]
    step_names = [step.get("name") for step in steps]

    install_index = step_names.index("Install")
    audit_index = step_names.index("Audit npm dependencies")
    type_check_index = step_names.index("Type-check docs site")
    build_index = step_names.index("Build")
    audit_step = steps[audit_index]
    type_check_step = steps[type_check_index]

    assert install_index < audit_index < type_check_index < build_index
    assert audit_step["working-directory"] == "docs-site"
    # 2026-06-16: report-all-but-fail-only-on-critical. The esbuild/vite advisories
    # in the static Astro tree are build-time only and have no non-breaking fix
    # (`npm audit fix --force` breaks Astro), so moderate is reported but only
    # critical fails the build. Do NOT revert to a hard moderate gate.
    audit_run = audit_step["run"]
    assert "npm audit --audit-level=moderate || true" in audit_run
    assert "npm audit --audit-level=critical" in audit_run
    assert type_check_step["working-directory"] == "docs-site"
    assert type_check_step["run"] == "npm run check"


def test_regression_eval_filter_tracks_curated_dataset_changes() -> None:
    workflow = _workflow("ci.yml")
    steps = workflow["jobs"]["regression-eval"]["steps"]
    filter_step = next(step for step in steps if "dorny/paths-filter" in str(step.get("uses", "")))
    filters = str(filter_step["with"]["filters"])

    assert "evaluation/curated_cases.jsonl" in filters


def test_weekly_report_schedule_delivers_and_manual_dispatch_dry_runs_by_default() -> None:
    workflow = _workflow("weekly-report.yml")
    trigger = workflow[True]
    dry_run_input = trigger["workflow_dispatch"]["inputs"]["dry_run"]
    run_step = next(
        step
        for step in workflow["jobs"]["weekly-report"]["steps"]
        if step.get("name") == "Run weekly report"
    )
    run_script = run_step["run"]

    assert dry_run_input["default"] == "true"
    assert "workflow_dispatch" in trigger
    assert re.search(
        r'if \[ "\$\{\{ github\.event_name \}\}" = "schedule" \]; then\s+python scripts/weekly_report\.py\s+elif',
        run_script,
    )
    assert "python scripts/weekly_report.py --dry-run" in run_script
