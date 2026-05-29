from __future__ import annotations

from pathlib import Path
import re

from packaging.requirements import Requirement
import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _pip_audit_hook() -> dict:
    config = yaml.safe_load(
        (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )

    for repo in config["repos"]:
        if repo["repo"] == "https://github.com/pypa/pip-audit":
            for hook in repo["hooks"]:
                if hook["id"] == "pip-audit":
                    return hook

    raise AssertionError("pip-audit pre-commit hook is missing")


def test_pip_audit_uses_locked_requirements_without_pip_resolution() -> None:
    hook = _pip_audit_hook()
    args = hook["args"]
    requirement_files = [
        args[index + 1] for index, arg in enumerate(args[:-1]) if arg == "-r"
    ]

    assert requirement_files == ["requirements.lock"]
    assert "--disable-pip" in args
    assert "--require-hashes" in args
    assert "--cache-dir" in args
    assert ".tmp/pip-audit-cache" in args
    assert "requirements.txt" not in args
    assert hook["pass_filenames"] is False
    assert "requirements" in hook["files"]


def test_locked_audit_input_covers_direct_runtime_requirements() -> None:
    direct_requirements = {
        Requirement(line).name.lower().replace("_", "-")
        for line in (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    locked_packages = {
        line.split("==", 1)[0].lower().replace("_", "-")
        for line in (PROJECT_ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
        if "==" in line and not line.lstrip().startswith("#")
    }

    assert direct_requirements - locked_packages == set()


def test_ci_security_audits_locked_requirements_without_pip_resolution() -> None:
    content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    security_job = content.split("  security:", 1)[1].split("  regression-eval:", 1)[0]
    normalized_security_job = " ".join(security_job.split())

    assert "pip-audit" in normalized_security_job
    for arg in (
        "--strict",
        "--disable-pip",
        "--require-hashes",
        "--timeout 15",
        "--progress-spinner off",
        "--cache-dir .tmp/pip-audit-cache",
        "--ignore-vuln CVE-2026-45829",
        "--ignore-vuln GHSA-f4j7-r4q5-qw2c",
        "-r requirements.lock",
    ):
        assert arg in normalized_security_job
    assert "pip-audit -r requirements.txt" not in security_job


def test_runtime_session_dependency_is_locked() -> None:
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    locked = (PROJECT_ROOT / "requirements.lock").read_text(encoding="utf-8")

    assert re.search(r"^itsdangerous>=", requirements, flags=re.MULTILINE)
    assert re.search(r"^itsdangerous==", locked, flags=re.MULTILINE)


def test_type_check_tooling_is_locked_for_ci() -> None:
    requirements = (PROJECT_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    locked = (PROJECT_ROOT / "requirements-dev.lock").read_text(encoding="utf-8")

    assert re.search(r"^mypy==", requirements, flags=re.MULTILINE)
    assert re.search(r"^mypy==", locked, flags=re.MULTILINE)


def test_pytest_plugins_are_locked_for_ci() -> None:
    requirements = (PROJECT_ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    locked = (PROJECT_ROOT / "requirements-dev.lock").read_text(encoding="utf-8")

    for package in ["pytest-asyncio", "pytest-timeout"]:
        assert re.search(fr"^{package}==", requirements, flags=re.MULTILINE)
        assert re.search(fr"^{package}==", locked, flags=re.MULTILINE)


def test_precommit_repo_wide_hooks_skip_tracked_legacy_outputs() -> None:
    config = yaml.safe_load(
        (PROJECT_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    )
    precommit_hooks = next(
        repo["hooks"]
        for repo in config["repos"]
        if repo["repo"] == "https://github.com/pre-commit/pre-commit-hooks"
    )
    hooks = {hook["id"]: hook for hook in precommit_hooks}

    excluded_paths = {
        "trailing-whitespace": [
            "archive-legacy/rag_poc_architecture.md",
            "audit_opus_27_04_26.md",
        ],
        "end-of-file-fixer": [
            "archive-legacy/prompt_for_github.md",
            "reports/regression/20260425T044732Z-ministral-3b-latest-vs-mistral-small-latest.json",
        ],
        "detect-private-key": [
            "codex-tasks/cleanup-report.md",
            "codex-tasks/Archive/task-126-hygiene-consistency-audit.md",
        ],
    }

    for hook_id, paths in excluded_paths.items():
        exclude = hooks[hook_id]["exclude"]
        for path in paths:
            assert re.search(exclude, path)


def test_ci_helm_render_uses_validation_placeholders() -> None:
    content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    helm_job = content.split("  helm:", 1)[1].split("  lint:", 1)[0]

    assert "--set secrets.existingSecret=ci-placeholder" in helm_job
    assert "--set env.CORS_ORIGINS=https://support.example.com" in helm_job
    assert "--set postgresql.auth.password=ci-placeholder" in helm_job


def test_ci_integration_tests_are_bounded_without_nested_testcontainers() -> None:
    content = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    integration_job = content.split("  test-integration:", 1)[1].split("  pre-commit:", 1)[0]
    regression_test = (
        PROJECT_ROOT / "tests" / "integration" / "test_regression_eval_live.py"
    ).read_text(encoding="utf-8")

    assert "timeout-minutes: 20" in integration_job
    assert "pytest tests/integration -q --timeout=120 --timeout-method=thread" in integration_job
    assert "GITHUB_ACTIONS" in regression_test
    assert "RAG_RUN_TESTCONTAINERS_IN_CI" in regression_test
