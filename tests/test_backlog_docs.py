from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_active_backlog_prompts_do_not_target_closed_agent_copilot_lane() -> None:
    content = (PROJECT_ROOT / "docs" / "plans" / "2026-05-01-backlog.md").read_text(
        encoding="utf-8"
    )

    assert "Prompt 1 — Agent Copilot Context" not in content
    assert "implement the remaining Agent Copilot context UI backlog item" not in content


def test_next_session_plan_avoids_closed_streaming_helm_and_a11y_lanes() -> None:
    content = (PROJECT_ROOT / "next-session-3-subagents.md").read_text(encoding="utf-8")

    assert "streaming parity" not in content
    assert "Helm secret split" not in content
    assert "Batch N" in content
    assert "A11y/performance verification" not in content.split("## Remaining Work", 1)[1]


def test_active_backlog_labels_remaining_work_as_blocked_or_opt_in() -> None:
    content = (PROJECT_ROOT / "docs" / "plans" / "2026-05-01-backlog.md").read_text(
        encoding="utf-8"
    )

    assert "Requires Explicit Opt-In" in content
    assert "Live Batch N benchmark" in content
    assert "A11y/performance verification is closed" in content


def test_active_backlog_does_not_treat_closed_lighthouse_as_live_work() -> None:
    content = (PROJECT_ROOT / "docs" / "plans" / "2026-05-01-backlog.md").read_text(
        encoding="utf-8"
    )
    project_status = content.split("## Project Status", 1)[1].split(
        "## Requires Explicit Opt-In", 1
    )[0]

    assert "Lighthouse/performance measurement" not in project_status


def test_historical_roadmap_current_pointer_excludes_closed_a11y_work() -> None:
    content = (PROJECT_ROOT / "codex-tasks" / "ROADMAP.md").read_text(
        encoding="utf-8"
    )
    current_pointer = content.split("## Current follow-up pointer", 1)[1]

    assert "a11y/performance verification" not in current_pointer
