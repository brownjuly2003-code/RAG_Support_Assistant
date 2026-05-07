# Next Session: Current Backlog Handoff

## Goal
Track the remaining live Batch N benchmark decision only. No non-live
autopilot-safe backlog remains; do not run live GraceKelly, Mistral, or
paid/API benchmark paths unless the user explicitly opts in during that session.

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
  - Top-level AP housekeeping tasks are closed: `test: guard historical backlog
    pointers` and `docs: refresh autopilot state snapshot`.
- Active source of truth: `docs/plans/2026-05-01-backlog.md`.

## Remaining Work
- [x] Live Batch N benchmark decision: closed 2026-05-07 — mock-provider
      benchmark run is the canonical regression signal (see Recently Closed
      in `docs/plans/2026-05-01-backlog.md`). A live GraceKelly+Mistral run
      remains a discretionary experiment for specific business reasons, not a
      backlog item.

## Suggested Subagents
None for default non-live work. Use subagents only if the session explicitly
opts into planning or running the live Batch N benchmark.

## Next Session Plan
- Start with `git status --short` and confirm any dirty state is expected
  before changing files.
- Read `docs/plans/2026-05-01-backlog.md` and this handoff before changing
  files.
- If no explicit live opt-in is given, keep work read-only or docs-only and do
  not reopen closed AP housekeeping tasks.
- If making changes, keep scope to docs/tests unless a focused failing test
  proves runtime code needs a small fix.
- Do not run GraceKelly, Mistral, paid/API benchmarks, scheduler installation,
  deploy, or production data commands without explicit user opt-in in that
  session.
- Verify with focused tests first, then `git diff --check`; run full pytest if
  source or test files changed.

## Current Session Checks
- [x] No live paid/API benchmark has run without explicit opt-in.
- [x] Active handoff/backlog docs do not point future sessions at closed lanes.
- [x] `git status --short` was reviewed; tracked changes are limited to the
      backlog/handoff docs, and the known untracked research note remains
      untouched.
