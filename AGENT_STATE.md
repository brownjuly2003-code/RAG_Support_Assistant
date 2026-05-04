# Agent State

## Current Project State

- Project: RAG Support Assistant.
- Stack: Python 3.13, FastAPI, LangGraph, ChromaDB, Postgres, Redis, static HTML UI, Helm/Docker deploy artifacts.
- Branch: `master`.
- Snapshot date: 2026-05-04 (Europe/Bucharest).
- Baseline HEAD: `ace8a2b1a91892f8a1513f63e8501b23679b68b8`.
- Baseline file count: 603 repo files from `rg --files`.
- Baseline JS bundle size: not applicable; no frontend bundler config was found.
- Baseline i18n key count: not applicable; no i18n JSON catalog was found.
- Git status at snapshot time: no tracked changes; unrestricted untracked scans may emit local access warnings for user-level git ignore and `.pytest-tmp-*` directories.

## Runtime

- Shell context: Windows PowerShell 5.1 in `D:\RAG_Support_Assistant`.
- pi CLI: available, `pi 0.72.1`.
- codex CLI: available, `codex-cli 0.128.0`.
- Python: available, `Python 3.13.7`.
- Local gate tools observed: `ruff`, `pytest`, `mypy`, `helm`, `bandit`, `pip-audit`, `pre-commit`.

## Last Verified Gates

- `git -c core.excludesfile= -c status.showUntrackedFiles=no status --short`: no entries.
- `git -c core.excludesfile= status --short -- AGENT_STATE.md`: no entries before this snapshot refresh.
- `git rev-parse --short HEAD`: `ace8a2b`.
- `rg --files`: 603 repo files.
- `Get-Command pi`: available.
- `Get-Command codex`: available.
- `pi --version`: `0.72.1`.
- `codex --version`: `codex-cli 0.128.0`.
- `powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun`: passed.
- PAUSE protocol dry-run simulation: passed.
- BLOCKED protocol dry-run simulation: passed.
- `python -m pytest -p no:schemathesis --basetemp=.tmp/pytest`: 716 passed, 4 skipped.

## Operating Mode

- Applicability status: READY_WITH_GUARDRAILS.
- Scheduler status: not installed by this setup; scheduler installation is opt-in only.
- Allowed default safe work: `docs/plans/2026-05-01-backlog.md`, bounded local tasks with exact allowed paths, and local verification.
- Default forbidden work: secrets, deploy, push, production data, live external services, paid API calls, destructive commands.

## Next Step

Dry-run has passed. To run another dry-run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun
```

Default safe work should come from `docs/plans/2026-05-01-backlog.md`; scheduler installation remains opt-in only.
