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


def _run_autopilot(repo: Path, *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    if POWERSHELL is None:
        pytest.skip("PowerShell is unavailable")
    return subprocess.run(
        [POWERSHELL, "-ExecutionPolicy", "Bypass", "-File", str(repo / "scripts" / "autopilot.ps1")],
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
