from __future__ import annotations

import re
from pathlib import Path

import yaml
from packaging.requirements import Requirement

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


def test_local_dependency_gates_match_ci_pip_audit_exception_policy() -> None:
    for relative_path in ("scripts/local-gate.ps1", "scripts/autopilot.ps1"):
        normalized_script = " ".join(
            (PROJECT_ROOT / relative_path).read_text(encoding="utf-8").split()
        )

        for dependency_file in (
            "requirements.txt",
            "requirements-dev.txt",
            "requirements.lock",
            "requirements-dev.lock",
        ):
            assert dependency_file in normalized_script

        if relative_path == "scripts/local-gate.ps1":
            assert "dependency files unchanged" in normalized_script
            assert "lock files unchanged" not in normalized_script

        for arg in (
            "--strict",
            "--disable-pip",
            "--require-hashes",
            "--timeout",
            "15",
            "--progress-spinner",
            "off",
            "--cache-dir",
            ".tmp/pip-audit-cache",
            "--ignore-vuln",
            "CVE-2026-45829",
            "GHSA-f4j7-r4q5-qw2c",
            "-r",
            "requirements.lock",
        ):
            assert arg in normalized_script


# Every justified pip-audit suppression, with the reason it stays ignored.
# Each entry is an unfixed upstream advisory whose affected code path is not
# reachable in this app (verified 2026-06-12): torch.jit.script is never
# called, and Chroma runs as an embedded PersistentClient, never the server
# API. Drop an entry the moment an upstream fix is released.
EXPECTED_PIP_AUDIT_IGNORES = {
    "CVE-2026-45829",       # unfixed ChromaDB server advisory
    "GHSA-f4j7-r4q5-qw2c",  # GHSA alias of the same ChromaDB advisory
    "CVE-2025-3000",        # unfixed torch advisory (torch.jit.script memory corruption)
}

_IGNORE_VULN_RE = re.compile(r"--ignore-vuln[\"',\s]+([A-Za-z0-9-]+)")


def test_pip_audit_ignore_set_is_synced_and_minimal() -> None:
    # Every pip-audit invocation must carry EXACTLY the justified ignore set.
    # This locks two things at once: (1) no silent suppression — adding an
    # ignore forces an intentional update to EXPECTED_PIP_AUDIT_IGNORES with a
    # reason; (2) no drift between the pre-commit hook, the CI security job,
    # and the local gates — a desync previously shipped a red CI when only the
    # pre-commit hook was updated.
    for relative_path in (
        ".pre-commit-config.yaml",
        ".github/workflows/ci.yml",
        "scripts/local-gate.ps1",
        "scripts/autopilot.ps1",
    ):
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        found = set(_IGNORE_VULN_RE.findall(text))
        assert found == EXPECTED_PIP_AUDIT_IGNORES, (
            f"{relative_path}: pip-audit --ignore-vuln set is {sorted(found)}, "
            f"expected {sorted(EXPECTED_PIP_AUDIT_IGNORES)}"
        )


# The strict-scope mypy command is duplicated across three gates: the CI
# type-check job, the local gate, and the autopilot gate. They MUST list the
# identical module path set, or a module keeps strict enforcement on one path
# while silently losing it on another. This guard locks the scope in sync and
# pins the promoted modules so a path cannot be dropped by accident — the same
# desync-prevention rationale as the pip-audit ignore-set guard above.
EXPECTED_MYPY_STRICT_PATHS = {
    "auth",
    "db",
    "llm/providers/",
    "config/settings.py",
    "agent/state.py",
    "agent/prompts.py",
    "agent/prompt_registry.py",
    "agent/tools.py",
    "agent/graph.py",
    "tasks",
    "utils",
    "monitoring",
    "channels",
    "tracing",
    "ingestion",
    "evaluation",
}


def _mypy_strict_scope_paths(text: str) -> set[str]:
    # Locate the strict-scope mypy invocation — the one carrying
    # --no-incremental and --show-error-codes but NOT --follow-imports=skip
    # (that flag marks the separate api.app command) — and return its module
    # path arguments (the tokens between `mypy` and `--no-incremental`).
    for line in text.splitlines():
        if (
            "mypy" in line
            and "--no-incremental" in line
            and "--show-error-codes" in line
            and "follow-imports" not in line
        ):
            tokens = re.findall(r"[\w./-]+", line)
            end = tokens.index("--no-incremental")
            mypy_idx = max(i for i, tok in enumerate(tokens[:end]) if tok == "mypy")
            return set(tokens[mypy_idx + 1 : end])
    raise AssertionError("strict-scope mypy command not found")


def test_mypy_strict_scope_is_synced_across_gates() -> None:
    for relative_path in (
        ".github/workflows/ci.yml",
        "scripts/local-gate.ps1",
        "scripts/autopilot.ps1",
    ):
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        paths = _mypy_strict_scope_paths(text)
        assert paths == EXPECTED_MYPY_STRICT_PATHS, (
            f"{relative_path}: mypy strict scope is {sorted(paths)}, "
            f"expected {sorted(EXPECTED_MYPY_STRICT_PATHS)}"
        )


def test_ci_tests_cover_docker_python_target_and_current_python() -> None:
    ci = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    unit_job = ci["jobs"]["test-unit"]
    integration_job = ci["jobs"]["test-integration"]
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    runtime_lock = (PROJECT_ROOT / "requirements.lock").read_text(encoding="utf-8")
    dev_lock = (PROJECT_ROOT / "requirements-dev.lock").read_text(encoding="utf-8")

    assert dockerfile.startswith("FROM python:3.11-slim")
    assert "--python-version 3.11" in runtime_lock
    assert "--python-version 3.11" in dev_lock
    for job in (unit_job, integration_job):
        assert job["strategy"]["matrix"]["python-version"] == ["3.11", "3.13"]
        setup_step = next(
            step
            for step in job["steps"]
            if step.get("uses", "").startswith("actions/setup-python")
        )
        assert setup_step["with"]["python-version"] == "${{ matrix.python-version }}"


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
            "docs/audits/audit_opus_27_04_26.md",
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
