# Backlog

## Autopilot Task Queue

### AP-1: Guard Historical Backlog Notes

- Allowed files/directories: `tests/test_docs_quality.py`, `BACKLOG.md`, `2026-05-02-non-live-backlog.md`
- Acceptance criteria: docs quality tests assert that both top-level backlog notes are marked historical and point at `docs/plans/2026-05-01-backlog.md`; live GraceKelly/Mistral work remains explicit opt-in only.
- Required verification: `python -m pytest -p no:schemathesis tests/test_docs_quality.py tests/test_quickstart_docs.py` and `git diff --check`.
- Commit allowed: yes.
- Suggested commit message: `test: guard historical backlog pointers`
- Forbidden scope: GraceKelly, Mistral, paid/API benchmark commands, scheduler installation, deploy, production data, `.env`, secrets, dependency changes.

### AP-2: Refresh Autopilot State Snapshot

- Allowed files/directories: `AGENT_STATE.md`
- Acceptance criteria: state snapshot names the current HEAD, says scheduler installation is opt-in only, and points default safe work at `docs/plans/2026-05-01-backlog.md`.
- Required verification: `git diff --check`.
- Commit allowed: yes.
- Suggested commit message: `docs: refresh autopilot state snapshot`
- Forbidden scope: GraceKelly, Mistral, paid/API benchmark commands, scheduler installation, deploy, production data, `.env`, secrets, dependency changes.

## Historical Safe Tasks

> Historical safe-task snapshot. The tasks below are closed in current history;
> use `docs/plans/2026-05-01-backlog.md` as the active backlog source. The only
> remaining benchmark lane is live GraceKelly/Mistral work: explicit opt-in only.

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
- Acceptance criteria: tests cover placeholder or missing paid-provider API keys without making network calls.
- Required verification: `python -m pytest tests/test_provider_settings.py tests/test_mistral_provider.py -q -p no:schemathesis --basetemp=.tmp/pytest` and `ruff check tests/test_provider_settings.py tests/test_mistral_provider.py config/providers.yml`.
- Forbidden scope: `.env`, real API keys, live provider calls, production config, deploy files.

## Safe Task 4: Add Autopilot Runner Tests

- Allowed files/directories: `scripts/autopilot.ps1`, `tests/`, `docs/`
- Acceptance criteria: protocol behavior for PAUSE, BLOCKED, and allowed paths is covered without invoking real `pi` or `codex`.
- Required verification: relevant new tests plus `powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun`.
- Forbidden scope: scheduler installation, production config, secrets, live external services.
