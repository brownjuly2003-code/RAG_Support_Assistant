# Next Session: Current Backlog Handoff

## Goal
Continue only the remaining non-live-service backlog safely. Do not run live
GraceKelly, Mistral, or paid/API benchmark paths unless the user explicitly opts
in during that session.

## Current Baseline
- Latest completed work:
  - Agent Copilot semantic context UI and zero-overlap similar-ticket filtering.
  - Mock-safe benchmark Quickstart example and guardrail test.
  - `static/widget.html` a11y landmark coverage and color-contrast fix.
  - Axe/Lighthouse verification: `tests/test_a11y.py` with axe CLI `38 passed`;
    Lighthouse mobile `/static/chat.html` scored performance 99.
  - Local gate and Windows pytest workflow docs.
  - Provider API-key guard tests for missing/placeholder paid-provider keys.
  - Autopilot runner protocol tests for PAUSE, BLOCKED, and allowed-path
    enforcement without invoking real `pi` or `codex`.
  - Active benchmark-doc guardrail: any `--allow-paid-apis` example in active
    benchmark docs must be explicitly labeled live and opt-in/manual.
- Active source of truth: `docs/plans/2026-05-01-backlog.md`.

## Remaining Work
- [ ] Live Batch N benchmark decision: mock/default docs and guardrails are
      closed. Live GraceKelly/Mistral e2e remains explicit opt-in only.

## Suggested Subagents
- [ ] Subagent 1: inspect active docs (`README.md`, `docs/QUICKSTART.md`,
      `codex-tasks/ROADMAP.md`, `docs/plans/2026-05-01-backlog.md`) for stale
      pointers to already-closed follow-up work.
- [ ] Subagent 2: inspect Batch N live benchmark docs/tests read-only and
      confirm the new doc guardrail covers every active `--allow-paid-apis`
      example. Do not run live benchmark commands.

## Next Session Plan
- Start with `git status --short` and confirm the branch is clean.
- Read `docs/plans/2026-05-01-backlog.md` and this handoff before changing
  files.
- Prefer read-only audit first: stale docs, stale backlog pointers, or missing
  guardrails only.
- If making changes, keep scope to docs/tests unless a focused failing test
  proves runtime code needs a small fix.
- Do not run GraceKelly, Mistral, paid/API benchmarks, scheduler installation,
  deploy, or production data commands without explicit user opt-in in that
  session.
- Verify with focused tests first, then `git diff --check`; run full pytest if
  source or test files changed.

## Done When
- [ ] No live paid/API benchmark has run without explicit opt-in.
- [ ] Active handoff/backlog docs do not point future sessions at closed lanes.
- [ ] `git status --short` contains only intended files before any commit.
