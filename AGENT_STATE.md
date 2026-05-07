# Agent State

## Current Project State

- Project: RAG Support Assistant.
- Stack: Python 3.13, FastAPI, LangGraph, ChromaDB, Postgres, Redis, static HTML UI, Helm/Docker deploy artifacts.
- Branch: `master`.
- Snapshot date: 2026-05-07 (Europe/Bucharest).
- Baseline HEAD: `277a97a50a11f183de68e9440037d1b5d33229b6`.
- Baseline file count: 653 tracked files from `git ls-files`.
- Baseline JS bundle size: not applicable; no frontend bundler config was found.
- Baseline i18n key count: not applicable; no i18n JSON catalog was found.
- Git status at snapshot time: research note relocated from repo root to `docs/research/pi-coding-agent-windows-noninteractive-hang-2026-05-04.md`; no other tracked changes.
- Origin sync: master is +18 ahead of `origin/master` (push pending explicit user approval).

## Runtime

- Shell context: Windows PowerShell 5.1 in `D:\RAG_Support_Assistant`.
- pi CLI: available, `pi 0.72.1`.
- codex CLI: available, `codex-cli 0.128.0`.
- Python: available, `Python 3.13.7`.
- Local gate tools observed: `ruff`, `pytest`, `mypy`, `helm`, `bandit`, `pip-audit`, `pre-commit`.

## Last Verified Gates

- `git -c core.excludesfile= -c status.showUntrackedFiles=no status --short`: research-note rename only at this snapshot.
- `git -c core.excludesfile= status --short -- AGENT_STATE.md`: refresh in flight as of this snapshot.
- `git rev-parse --short HEAD`: `277a97a`.
- `git ls-files | wc -l`: 653 tracked files (relative to baseline 603 — net +50 from May follow-ups).
- `Get-Command pi`: available.
- `Get-Command codex`: available.
- `pi --version`: `0.72.1`.
- `codex --version`: `codex-cli 0.128.0`.
- `powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun`: passed (last verified 2026-05-04).
- PAUSE protocol dry-run simulation: passed (last verified 2026-05-04).
- BLOCKED protocol dry-run simulation: passed (last verified 2026-05-04).
- `python -m pytest -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-may07-snapshot --ignore=tests/integration`: 735 passed, 4 skipped (verified 2026-05-07 at `d0016c2`; 16:20 wall time).
- `python -m mypy auth db/models.py db/engine.py llm/providers/ config/settings.py agent/state.py agent/prompts.py agent/prompt_registry.py agent/tools.py agent/graph.py --no-incremental`: 18 source files clean (verified 2026-05-07).
- `python -m mypy api/app.py --no-incremental --follow-imports=skip`: clean (verified 2026-05-07).
- `python -m ruff check .`: All checks passed (verified 2026-05-07).
- `python -m bandit -r . -ll -c pyproject.toml -x ./tests,./.venv,./reports,./data,./archive-legacy,./.tmp`: 0 medium / 0 high (39 low informational), verified 2026-05-07.
- `python -m pip_audit -r requirements.txt`: not re-verified for the 2026-05-07 snapshot (network probe stalled past 20 minutes and was cancelled). The pre-commit `pip-audit` hook remains the authoritative gate; rerun before push if dependency drift is suspected.

## Operating Mode

- Applicability status: READY_WITH_GUARDRAILS.
- Scheduler status: not installed by this setup; scheduler installation is opt-in only.
- Allowed default safe work: `docs/plans/2026-05-01-backlog.md`, bounded local tasks with exact allowed paths, and local verification.
- Default forbidden work: secrets, deploy, push, production data, live external services, paid API calls, destructive commands.

## Next Step

Non-live autopilot-safe backlog is empty. The single remaining plan item is the
Live Batch N benchmark (GraceKelly+Mistral regression) — explicit user opt-in
only because of paid-API cost. See `docs/plans/2026-05-01-backlog.md` and
`next-session-3-subagents.md` for the opt-in surface.

Untracked-state pending decision: 18 local commits ahead of `origin/master`
(push requires explicit user approval).

To run another dry-run of the autopilot guardrails:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun
```

Default safe work should come from `docs/plans/2026-05-01-backlog.md`; scheduler installation remains opt-in only.
