from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTOPILOT_SCRIPT = PROJECT_ROOT / "scripts" / "autopilot.ps1"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy2(AUTOPILOT_SCRIPT, scripts / "autopilot.ps1")
    (repo / ".gitignore").write_text(".autopilot/\n", encoding="utf-8", newline="\n")

    _run(["git", "init"], cwd=repo)
    _run(["git", "config", "user.email", "tests@example.invalid"], cwd=repo)
    _run(["git", "config", "user.name", "Tests"], cwd=repo)
    _run(["git", "add", ".gitignore", "scripts/autopilot.ps1"], cwd=repo)
    _run(["git", "commit", "-m", "init"], cwd=repo)
    return repo


def _run_autopilot(
    repo: Path,
    *,
    env: dict[str, str] | None = None,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    if POWERSHELL is None:
        pytest.skip("PowerShell is unavailable")
    return subprocess.run(
        [
            POWERSHELL,
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repo / "scripts" / "autopilot.ps1"),
            *(args or []),
        ],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )


def test_autopilot_runner_pause_file_exits_before_locking(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    autopilot_dir = repo / ".autopilot"
    autopilot_dir.mkdir()
    (autopilot_dir / "PAUSE").write_text("", encoding="utf-8")

    result = _run_autopilot(repo)

    assert result.returncode == 0, result.stderr
    assert "PAUSE exists; exiting." in result.stdout
    assert not (autopilot_dir / "LOCK").exists()


def test_autopilot_runner_blocked_file_exits_before_planner(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    autopilot_dir = repo / ".autopilot"
    autopilot_dir.mkdir()
    (autopilot_dir / "BLOCKED.md").write_text("blocked", encoding="utf-8")

    result = _run_autopilot(repo)

    assert result.returncode == 1
    assert "BLOCKED.md exists; exiting." in result.stdout
    assert not (autopilot_dir / "LOCK").exists()


def test_autopilot_runner_blocks_executor_changes_outside_allowed_paths(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "pi.cmd").write_text(
        "\n".join(
            [
                "@echo off",
                "if not exist .autopilot mkdir .autopilot",
                "echo test task> .autopilot\\NEXT_TASK.md",
                "echo docs/> .autopilot\\allowed-paths.txt",
                "echo test commit> .autopilot\\commit-message.txt",
                "exit /b 0",
            ]
        ),
        encoding="utf-8",
        newline="\r\n",
    )
    (tools / "codex.cmd").write_text(
        "\n".join(
            [
                "@echo off",
                "echo outside> outside.txt",
                "exit /b 0",
            ]
        ),
        encoding="utf-8",
        newline="\r\n",
    )
    env = os.environ.copy()
    env["PATH"] = f"{tools}{os.pathsep}{env['PATH']}"

    result = _run_autopilot(repo, env=env)

    assert result.returncode == 1
    assert "Changed file outside allowed paths: outside.txt" in result.stdout
    assert (repo / "outside.txt").read_text(encoding="utf-8").strip() == "outside"
    assert "outside.txt" in (repo / ".autopilot" / "BLOCKED.md").read_text(encoding="utf-8")


def test_autopilot_runner_falls_back_to_backlog_task_when_pi_planner_fails(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "## Autopilot Task Queue",
                "",
                "### AP-1: Docs task",
                "",
                "- Allowed files/directories: `docs/`",
                "- Acceptance criteria: docs are updated.",
                "- Required verification: `git diff --check`.",
                "- Commit allowed: yes.",
                "- Suggested commit message: `docs: update backlog task`",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    _run(["git", "add", "BACKLOG.md"], cwd=repo)
    _run(["git", "commit", "-m", "add backlog"], cwd=repo)
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "pi.cmd").write_text("@echo off\nexit /b 1\n", encoding="utf-8", newline="\r\n")
    (tools / "codex.cmd").write_text(
        "\n".join(
            [
                "@echo off",
                "echo outside> outside.txt",
                "exit /b 0",
            ]
        ),
        encoding="utf-8",
        newline="\r\n",
    )
    env = os.environ.copy()
    env["PATH"] = f"{tools}{os.pathsep}{env['PATH']}"

    result = _run_autopilot(repo, env=env)

    assert result.returncode == 1
    assert "Falling back to BACKLOG.md autopilot task queue." in result.stdout
    assert "Changed file outside allowed paths: outside.txt" in result.stdout
    allowed = (repo / ".autopilot" / "allowed-paths.txt").read_text(encoding="utf-8")
    assert allowed.strip() == "docs/"


def test_autopilot_runner_accepts_planner_artifacts_when_pi_hangs(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "pi.cmd").write_text(
        "\n".join(
            [
                "@echo off",
                "if not exist .autopilot mkdir .autopilot",
                "echo test task> .autopilot\\NEXT_TASK.md",
                "echo docs/> .autopilot\\allowed-paths.txt",
                "echo test commit> .autopilot\\commit-message.txt",
                "ping -n 4 127.0.0.1 >nul",
                "exit /b 0",
            ]
        ),
        encoding="utf-8",
        newline="\r\n",
    )
    for name, body in {
        "codex.cmd": "@echo off\nexit /b 0\n",
        "ruff.cmd": "@echo off\nexit /b 0\n",
        "python.cmd": "@echo off\nexit /b 0\n",
    }.items():
        (tools / name).write_text(body, encoding="utf-8", newline="\r\n")
    env = os.environ.copy()
    env["PATH"] = f"{tools}{os.pathsep}{env['PATH']}"

    result = _run_autopilot(repo, env=env, args=["-PlannerTimeoutSec", "1"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Planner timed out after 1s after writing artifacts; stopped planner process." in result.stdout
    assert not (repo / ".autopilot" / "LOCK").exists()
    allowed = (repo / ".autopilot" / "allowed-paths.txt").read_text(encoding="utf-8")
    assert allowed.strip() == "docs/"


def test_autopilot_runner_falls_back_to_local_executor_when_codex_fails(
    tmp_path: Path,
) -> None:
    repo = _init_repo(tmp_path)
    (repo / "BACKLOG.md").write_text(
        "\n".join(
            [
                "# Backlog",
                "",
                "## Autopilot Task Queue",
                "",
                "### AP-1: Guard Historical Backlog Notes",
                "",
                "- Allowed files/directories: `tests/test_docs_quality.py`, `BACKLOG.md`, `2026-05-02-non-live-backlog.md`",
                "- Acceptance criteria: docs quality tests assert that both top-level backlog notes are marked historical and point at `docs/plans/2026-05-01-backlog.md`; live GraceKelly/Mistral work remains explicit opt-in only.",
                "- Required verification: `python -m pytest -p no:schemathesis tests/test_docs_quality.py tests/test_quickstart_docs.py` and `git diff --check`.",
                "- Commit allowed: yes.",
                "- Suggested commit message: `test: guard historical backlog pointers`",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    (repo / "2026-05-02-non-live-backlog.md").write_text(
        "\n".join(
            [
                "# Non-Live Backlog Continuation - 2026-05-02",
                "",
                "> Historical completion note. This non-live continuation is complete; the active",
                "> backlog source is now `docs/plans/2026-05-01-backlog.md`, with live",
                "> GraceKelly/Mistral benchmark work requiring explicit opt-in.",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_docs_quality.py").write_text(
        "from pathlib import Path\n\nPROJECT_ROOT = Path(__file__).resolve().parent.parent\n",
        encoding="utf-8",
        newline="\n",
    )
    _run(
        ["git", "add", "BACKLOG.md", "2026-05-02-non-live-backlog.md", "tests/test_docs_quality.py"],
        cwd=repo,
    )
    _run(["git", "commit", "-m", "add backlog and docs tests"], cwd=repo)
    tools = tmp_path / "tools"
    tools.mkdir()
    for name, body in {
        "pi.cmd": "@echo off\nexit /b 1\n",
        "codex.cmd": "@echo off\nexit /b 2\n",
        "ruff.cmd": "@echo off\nexit /b 0\n",
        "python.cmd": "@echo off\nexit /b 0\n",
    }.items():
        (tools / name).write_text(body, encoding="utf-8", newline="\r\n")
    env = os.environ.copy()
    env["PATH"] = f"{tools}{os.pathsep}{env['PATH']}"

    result = _run_autopilot(repo, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Falling back to local executor." in result.stdout
    docs_test = (tests_dir / "test_docs_quality.py").read_text(encoding="utf-8")
    assert "test_top_level_backlog_notes_are_historical" in docs_test
    log = _run(["git", "log", "-1", "--pretty=%s"], cwd=repo)
    assert log.stdout.strip() == "test: guard historical backlog pointers"
