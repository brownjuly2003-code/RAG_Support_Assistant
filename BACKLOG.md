# Backlog

## Autopilot Task Queue

> No active non-live autopilot-safe tasks remain in this fallback queue.
> `AP-1` (`test: guard historical backlog pointers`) is closed by `d3f8eb7`.
> `AP-2` (`docs: refresh autopilot state snapshot`) is closed by `cd6e7ba`.
> Use `docs/plans/2026-05-01-backlog.md` for context; the live
> GraceKelly/Mistral benchmark lane requires staged runtime and explicit
> opt-in only, and is not an active local backlog item.
> 2026-05-30 branch note: Colab remote benchmark setup is merged to `master`
> through PR #1 at `415d4c8`; current state is in `AGENT_STATE.md` and
> `docs/sessions/next-session-3-subagents.md`. Master CI and Pages deploy passed. No
> additional local backlog item is open.
> 2026-05-30 live opt-in note: commit `7b0d9ee` closed a runtime quality
> blocker by failing closed on incompatible Chroma embedding dimensions. A
> separate ignored eval collection passed a 3-case live Mistral regression; the
> default local `rag_docs_default` collection still needs a deliberate rebuild
> before it should be used for full RAG quality measurement.
> 2026-05-30 R3/R4 note: commit `71367a7` batches multi-document
> `grade_docs` into one structured LLM call with fallback to the old per-doc
> path. Master CI and Pages passed on that commit.
> 2026-05-30 R4 observability note: commit `c0b6d24` adds trace events for
> `verify_facts` extract-claims and per-claim LLM calls. Master CI and Pages
> passed on that commit.
> 2026-05-30 R7 note: commit `c964211` expands the checked-in RU curated seed
> set from 20 to 35 cases and adds a guard test. Local mock regression passed
> 35/35; master CI passed. A final CI guard also makes PR `regression-eval`
> track `evaluation/curated_cases.jsonl` changes.

## Historical Safe Tasks

> Historical safe-task snapshot. The tasks below are closed in current history;
> use `docs/plans/2026-05-01-backlog.md` as the active backlog source. The only
> remaining benchmark lane is live GraceKelly/Mistral work: explicit opt-in only.
> It requires staged runtime and is not an active local backlog item.

## Safe Task 1: Add a Local Gate Wrapper

- Allowed files/directories: `scripts/`, `README.md`, `docs/`
- Acceptance criteria: a non-mutating local gate command documents and runs the same safe checks used by the runner.
- Required verification: run the new wrapper in dry-run or list mode, then run `git diff --check`.
- Forbidden scope: `.env`, `deploy/`, Docker, Helm, live services, dependency changes, production DB, external APIs.

## Safe Task 2: Document Windows Test Workflow

- Allowed files/directories: `README.md`, `docs/`
- Acceptance criteria: Windows-specific pytest guidance is consolidated with the current `-p no:schemathesis` and `.tmp/pytest` basetemp recommendation.
- Required verification: `git diff --check`.
- Forbidden scope: source code, tests, CI, deploy configs, generated reports.

## Safe Task 3: Tighten Provider Settings Tests

- Allowed files/directories: `tests/test_provider_settings.py`, `tests/test_mistral_provider.py`, `config/providers.yml`
- Acceptance criteria: tests cover placeholder or missing direct-provider API keys without making network calls.
- Required verification: `python -m pytest tests/test_provider_settings.py tests/test_mistral_provider.py -q -p no:schemathesis --basetemp=.tmp/pytest` and `ruff check tests/test_provider_settings.py tests/test_mistral_provider.py config/providers.yml`.
- Forbidden scope: `.env`, real API keys, live provider calls, production config, deploy files.

## Safe Task 4: Add Autopilot Runner Tests

- Allowed files/directories: `scripts/autopilot.ps1`, `tests/`, `docs/`
- Acceptance criteria: protocol behavior for PAUSE, BLOCKED, and allowed paths is covered without invoking real `pi` or `codex`.
- Required verification: relevant new tests plus `powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun`.
- Forbidden scope: scheduler installation, production config, secrets, live external services.
