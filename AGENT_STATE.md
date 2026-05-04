# Agent State

## Current Project State

- Project: RAG Support Assistant.
- Stack: Python 3.13, FastAPI, LangGraph, ChromaDB, Postgres, Redis, static HTML UI, Helm/Docker deploy artifacts.
- Branch: `master`.
- Baseline HEAD: `1d8ee96`.
- Baseline file count: 593 repo files from `rg --files`.
- Baseline JS bundle size: not applicable; no frontend bundler config was found.
- Baseline i18n key count: not applicable; no i18n JSON catalog was found.
- Git status at audit time: clean.

## Runtime

- pi CLI: available, `pi 0.72.1`.
- codex CLI: available, `codex-cli 0.128.0`.
- Python: available, `Python 3.13.7`.
- Local gate tools observed: `ruff`, `pytest`, `mypy`, `helm`, `bandit`, `pip-audit`, `pre-commit`.

## Last Verified Gates

- `git status --short`: clean at audit time.
- `git rev-parse --short HEAD`: `1d8ee96`.
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
- Scheduler status: not installed by this setup; opt-in only.
- Allowed default work: bounded local tasks with exact allowed paths and local verification.
- Default forbidden work: secrets, deploy, push, production data, live external services, paid API calls, destructive commands.

## Next Step

Dry-run has passed. To run another dry-run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun
```

If dry-run passes and autonomous scheduling is desired, install the opt-in scheduled task with `scripts/install-autopilot-task.ps1`.
