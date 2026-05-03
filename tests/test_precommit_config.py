from __future__ import annotations

from pathlib import Path

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

    assert "pip-audit --strict --disable-pip --require-hashes -r requirements.lock" in security_job
    assert "pip-audit -r requirements.txt" not in security_job
