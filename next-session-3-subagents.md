# Next Session: Current Backlog Handoff

## Goal
Continue only the remaining non-live-service backlog safely. Do not run live
GraceKelly, Mistral, or paid/API benchmark paths unless the user explicitly opts
in during that session.

## Current Baseline
- Latest completed work:
  - Agent Copilot semantic context UI and zero-overlap similar-ticket filtering.
  - Mock-safe benchmark Quickstart example and guardrail test.
  - `static/widget.html` a11y landmark coverage.
- Active source of truth: `docs/plans/2026-05-01-backlog.md`.

## Remaining Work
- [ ] Live Batch N benchmark decision: mock/default docs and guardrails are
      closed. Live GraceKelly/Mistral e2e remains explicit opt-in only.
- [ ] A11y/performance verification: rerun `@axe-core/cli` and Lighthouse only
      when those local CLI tools are installed.

## Suggested Subagents
- [ ] Subagent 1: inspect Batch N live benchmark decision docs/tests for stale
      paid opt-in examples. Verify no command includes `--allow-paid-apis`
      unless it is clearly labeled live/manual.
- [ ] Subagent 2: inspect a11y/performance tooling availability and report
      exactly what is blocked by missing `@axe-core/cli` or Lighthouse.
- [ ] Subagent 3: inspect active docs (`README.md`, `docs/QUICKSTART.md`,
      `codex-tasks/ROADMAP.md`, `docs/plans/2026-05-01-backlog.md`) for stale
      pointers to already-closed follow-up work.

## Done When
- [ ] No live paid/API benchmark has run without explicit opt-in.
- [ ] Active handoff/backlog docs do not point future sessions at closed lanes.
- [ ] `git status --short` contains only intended files before any commit.
