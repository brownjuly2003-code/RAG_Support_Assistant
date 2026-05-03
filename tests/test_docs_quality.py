from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _active_markdown_docs() -> list[Path]:
    return [
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "next-session-3-subagents.md",
        *(PROJECT_ROOT / "docs").rglob("*.md"),
        *(PROJECT_ROOT / "codex-tasks").glob("*.md"),
    ]


def test_active_docs_do_not_contain_common_mojibake_markers() -> None:
    markers = ("\ufffd", "\u00e2\u20ac", "\u00d0", "\u00d1")

    offenders = [
        str(path.relative_to(PROJECT_ROOT))
        for path in _active_markdown_docs()
        if any(marker in path.read_text(encoding="utf-8") for marker in markers)
    ]

    assert offenders == []


def test_accessibility_docs_record_completed_tooling_verification() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    audit = (PROJECT_ROOT / "docs" / "a11y" / "axe-audit-2026-04-21.md").read_text(
        encoding="utf-8"
    )
    backlog = (
        PROJECT_ROOT / "docs" / "plans" / "2026-05-01-backlog.md"
    ).read_text(encoding="utf-8")

    assert "Axe/Lighthouse verification 2026-05-03" in readme
    assert "Lighthouse mobile `/static/chat.html`: performance `99`" in readme
    assert "Post-audit source updates" in audit
    assert "Verification refresh 2026-05-03" in audit
    assert "`38 passed`" in audit
    assert "`static/widget.html`" in audit
    assert "A11y/performance verification is closed" in backlog
    assert "moderate landmark/region cleanup can be handled as polish" not in backlog


def test_next_session_handoff_points_at_live_batch_n_decision_only() -> None:
    content = (PROJECT_ROOT / "next-session-3-subagents.md").read_text(
        encoding="utf-8"
    )

    assert "Live Batch N benchmark decision" in content
    assert "A11y/performance verification" not in content.split("## Remaining Work", 1)[1]
    assert "run or document only mock/default benchmark flows" not in content


def test_readme_web_ui_points_to_current_chat_route() -> None:
    content = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    web_ui = content.split("## Web UI", 1)[1].split("## Accessibility", 1)[0]

    assert "`/static/chat.html` - main chat UI" in web_ui
    assert "`/` - main chat UI" not in web_ui


def test_readme_provider_profiles_include_gracekelly_mixed() -> None:
    content = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    providers = content.split("## Providers", 1)[1].split("## Regression eval", 1)[0]

    assert "`gracekelly-mixed`" in providers
    assert "browser-backed strong answer generation" in providers


def test_old_arc_verification_report_is_marked_historical() -> None:
    content = (PROJECT_ROOT / "codex-tasks" / "verification-report.md").read_text(
        encoding="utf-8"
    )

    assert "Historical snapshot" in content
    assert "docs/plans/2026-05-01-backlog.md" in content


def test_live_gracekelly_docs_require_explicit_user_opt_in() -> None:
    smoke = (PROJECT_ROOT / "docs" / "operations" / "gracekelly-smoke.md").read_text(
        encoding="utf-8"
    )
    task_177 = (
        PROJECT_ROOT
        / "codex-tasks"
        / "task-177-regression-via-gracekelly-claude.md"
    ).read_text(encoding="utf-8")

    assert "explicit user opt-in" in smoke
    assert "live GraceKelly" in smoke
    assert "explicit user opt-in" in task_177
    assert "live GraceKelly/Mistral" in task_177
