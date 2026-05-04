# Autopilot Applicability Verdict

Status: READY_WITH_GUARDRAILS

## Runtime

- Planner: pi.dev via `pi` CLI, available as `pi 0.72.1`.
- Executor: Codex via `codex` CLI, available as `codex-cli 0.128.0`.
- Runner: local PowerShell script at `scripts/autopilot.ps1`.

## Evidence

- Repository is a Git repo on branch `master`, baseline HEAD `1d8ee96`, with clean status at assessment time.
- Stack is Python/FastAPI with LangGraph, ChromaDB, GraceKelly/Ollama provider routing, Postgres, Redis, OpenTelemetry, and static HTML UI.
- Documentation exists in `README.md` and `docs/`; CI exists in `.github/workflows/ci.yml`.
- Local and CI gates are identifiable: `ruff check .`, strict-scope `mypy`, unit tests, integration tests, Helm lint/render, Bandit, pip-audit, and pre-commit.
- Tests exist under `tests/` and `tests/integration/`.
- The project has explicit production hardening and secret validation tests.

## Safe Scope

- Docs and planning files: `README.md`, `docs/`, `AGENT_STATE.md`, `BACKLOG.md`.
- Unit-test-only changes under `tests/`, excluding generated `tests/pytest-cache-files-*`.
- Non-deploy operational helper scripts under `scripts/` when they do not touch live services, secrets, or production data.
- Static UI-only edits under `static/` with local browser or unit verification.
- Small, bounded Python refactors when the planner provides exact allowed files and relevant tests.

## Forbidden Scope

- `.env`, `.env.*`, local secret stores, and any values from environment variables.
- `deploy/`, Helm values, Docker Compose, Kubernetes, scheduler, or production config changes unless explicitly allowed for a single task.
- Live database, Redis, vector store, object storage, email, Bitrix, Telegram, GraceKelly, Mistral, OpenAI, or other external account actions.
- Destructive scripts or commands, including key rotation, reindexing, migration downgrade, purge, delete, deploy, push, or production smoke against live URLs.
- Generated/runtime data under `.autopilot/`, `.tmp/`, `data/`, `cache/`, `reports/`, `htmlcov/`, and local pytest cache folders.

## Required Gates

The runner must execute only commands available on the local machine.

- Always: `git diff --check`.
- Python source changes: `ruff check .`.
- Strict-scope code changes: the two CI `mypy` commands from `.github/workflows/ci.yml`.
- Unit-testable changes: `python -m pytest tests/ -q --ignore=tests/integration -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest`.
- `deploy/helm/` changes, only when explicitly allowed: `helm lint deploy/helm/ --strict`.
- Dependency lock changes, only when explicitly allowed: `pip-audit --strict --disable-pip --require-hashes -r requirements.lock`.

## Protocol

### Mission Source Order

1. `AGENT_STATE.md`
2. `BACKLOG.md`
3. `README.md`
4. `docs/`
5. Current `git status` and recent diff

### pi.dev Planner

The planner runs through `pi` and must:

- choose exactly one bounded task;
- edit only `.autopilot/NEXT_TASK.md`, `.autopilot/allowed-paths.txt`, `.autopilot/commit-message.txt`, or `.autopilot/BLOCKED.md`;
- never edit product code;
- never ask the user questions;
- set allowed files or directories narrowly enough for runner enforcement.

Required planner output in `.autopilot/NEXT_TASK.md`:

- task title;
- why this is next;
- allowed files or directories;
- acceptance criteria;
- required verification;
- `commit allowed: yes` or `commit allowed: no`;
- suggested commit message.

### Codex Executor

The executor runs through `codex exec` and must:

- read `.autopilot/NEXT_TASK.md`;
- perform only that task;
- stay inside `.autopilot/allowed-paths.txt`;
- write tests before backend behavior changes;
- run relevant verification;
- update `AGENT_STATE.md` and `BACKLOG.md` only if they are in the allowed paths;
- never commit, push, deploy, read secrets, or call live external services;
- write `.autopilot/BLOCKED.md` when blocked.

### Local Runner

The runner must:

- set a lock before work and remove it on exit;
- stop when `.autopilot/PAUSE` exists;
- stop when `.autopilot/BLOCKED.md` exists;
- invoke `pi` for planning and wait for `.autopilot/NEXT_TASK.md`;
- invoke `codex exec` for execution;
- check changed files against `.autopilot/allowed-paths.txt`;
- run required gates;
- commit only with explicit pathspecs from the verified changed-file list;
- never use `git add .` or `git add -A`;
- never push.

## Hard Stops

- Dirty git tree before a run.
- Missing `pi` or `codex`.
- Missing `.autopilot/allowed-paths.txt` or empty allowed scope.
- Any changed file outside allowed scope.
- Any gate failure.
- Any attempt to touch forbidden scope.
- Any need for secrets, deploy, live external services, or paid API calls.

## PAUSE and BLOCKED

- Pause: create `.autopilot/PAUSE`.
- Resume: remove `.autopilot/PAUSE` after reviewing state.
- Blocked: inspect `.autopilot/BLOCKED.md`; remove it only after resolving the listed blocker.

## Scheduler

Scheduling is opt-in only. Use `scripts/install-autopilot-task.ps1` after a clean dry-run if autonomous local scheduling is desired. The scheduler must not push or deploy.

## Exit Instructions

1. Check `.autopilot/BLOCKED.md`.
2. Run `git status --short`.
3. Inspect `.autopilot/run.log`.
4. Remove `.autopilot/PAUSE` only when the next run is intentionally allowed.
