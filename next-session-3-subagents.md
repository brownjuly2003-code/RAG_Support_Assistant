# Next Session: Current Backlog Handoff

## Goal
Continue from the Colab remote benchmark handoff. No non-live autopilot-safe
product backlog remains; do not run live GraceKelly, Mistral, Docker, Ollama,
GraceKelly browser orchestration, local model downloads, or paid/API benchmark
paths unless the user explicitly opts in during that session.

## Current Baseline
- Latest completed work:
  - Colab remote benchmark runbook and notebook were added on
    `colab-remote-benchmark` and pushed to
    `origin/colab-remote-benchmark` for manual Colab opening.
  - Windows laptop and iMac are documented as thin clients for this benchmark
    lane; benchmark compute must happen in Colab/cloud.
  - Notebook clone target is `colab-remote-benchmark` until the branch lands on
    `master`.
  - `.pytest-tmp*/` local pytest basetemp directories are ignored.
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
  Current branch state is summarized in `AGENT_STATE.md`.

## Remaining Work
- [x] Live Batch N benchmark decision: closed 2026-05-07 — mock-provider
      benchmark run is the canonical regression signal (see Recently Closed
      in `docs/plans/2026-05-01-backlog.md`). A live GraceKelly+Mistral run
      remains a discretionary experiment for specific business reasons, not a
      backlog item.
- [x] Colab remote benchmark setup: notebook and runbook are committed and the
      notebook branch was pushed for manual Colab use.

## Suggested Subagents
None for default non-live work. Use subagents only if the session explicitly
opts into planning or running a live benchmark.

## Next Session Plan
- Start with `git status --short --branch` and confirm any dirty state is expected
  before changing files.
- Read `AGENT_STATE.md`, `docs/operations/colab-remote-benchmark.md`,
  `docs/plans/2026-05-01-backlog.md`, and this handoff before changing files.
- If opening the notebook manually, use:
  `https://colab.research.google.com/github/brownjuly2003-code/RAG_Support_Assistant/blob/colab-remote-benchmark/notebooks/rag_support_colab_remote_benchmark.ipynb`
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
- [x] Active handoff docs point future sessions at the Colab runbook branch,
      not the closed Batch N lane.
- [x] `git status --short --branch` was reviewed; state-refresh commits are
      local-only unless a later instruction explicitly permits another push.
