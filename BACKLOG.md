# Backlog

## Active source (2026-08-03) — step 4.8c locally verified @ `8594675`

**Sole active backlog:** [`plan_sol_23_07_26`](plan_sol_23_07_26)
(status matrix in [`audit_gpt_23_07_26.md`](audit_gpt_23_07_26.md)).

The 2026-07-27 «project closure / empty queue» narrative remains **revoked**.
Plan remains **ACTIVE**; project/production release is **not** complete.
P0 **implementation** is locally remediated; **OBS-01** is locally remediated
at `5a9f857`. Plan step 1 is **locally complete**. Plan step 4 is **in
progress**: slices **4.1** (`b7faa19`), **4.2** (`4f93038`), **4.3**
(`6dc6fe4`), **4.4** (`1cebd14`), **4.5** (`35e4bb9`), **4.6**
(`d13804b`), **4.7** (`705a3cc`), **4.8a** (`c015ba8`, `ca15c1a`), and
**4.8b** (`74d187c`) and **4.8c** (`8594675`) are locally verified (ING-01
further partially locally remediated; TEN-03 locally remediated; ING-02 lock +
manifest + staging + runtime-publish contracts partially locally remediated).
Full plan DoD / production release / project closure are **not** complete.
Historical autopilot/safe tasks below remain evidence only — not the active
queue.

### Latest atomic slice (local code)

**Plan step 4.8c runtime publish/cache integration is locally complete at
`8594675`.**

Document rebuild now validates and publishes a versioned candidate under one
tenant lock without deleting the former active collection. Retrieval resolves
the active manifest before cache reuse and invalidates by directory, active
name, and generation; API startup/session and KB draft publication follow the
same active-version contract. The exact closure gate passed **73 tests** with
two expected warnings; scoped Ruff, locked Mypy, and diff checks are clean.
Rollback/retention/fault injection (4.8d) remains the next local code slice and
was not started in this turn.

### Live / external P0 gates (not local-complete)

Track separately from the next code slice — do **not** list as done work:

- **TEN-01/02:** real PostgreSQL migration upgrade/downgrade; live two-tenant
  restart drill
- **OPS-01:** Docker image build + pg/age tool smoke; live PostgreSQL; kind/live
  cluster install; app pod recreation; clean-namespace restore to a
  **disposable** DB (never production DSN for `pg_restore --clean`); known-query
  smoke; measured RPO/RTO
- **ING-01 remaining:** live Redis/Postgres/Celery worker-outage/recovery drill;
  real PostgreSQL
  upgrade/downgrade through migrations `019`/`020`/`021`

Step 4 remains **in progress** (4.1–4.8c locally done; rollback and live
step-4 DoD open). Step 5 remains **open / partially
remediated** (trace identity done; timeout cancellation, bounded capacity,
session concurrency/history ordering, sticky experiment propagation still open).
Steps 6–10 remain open. ING-02 is **partially locally remediated** by the
same-tenant mutation lock plus manifest/staging/runtime-publish contracts;
rollback remains open.
Live GraceKelly/Mistral benchmarks remain explicit opt-in only and are **not**
this slice.

## Project Closure note (2026-07-27) — historical

Superseded by the 2026-08-02 audit revalidation. See
[`docs/PROJECT_CLOSURE.md`](docs/PROJECT_CLOSURE.md) banner. Deferred
runtime/benchmark/refactor dispositions in that file remain historical context
only until re-decided under the audit plan.

## Autopilot Task Queue

> Historical autopilot snapshot (pre-audit reopen). Former note: no active
> non-live autopilot-safe tasks; `AP-1` closed by `d3f8eb7`, `AP-2` by `cd6e7ba`.
> Use `docs/plans/2026-05-01-backlog.md` for older product context. The live
> GraceKelly/Mistral benchmark lane requires staged runtime and explicit
> opt-in only, and is not the current audit-plan next slice.
> 2026-05-30 branch note: Colab remote benchmark setup is merged to `master`
> through PR #1 at `415d4c8`; current state is in `AGENT_STATE.md` and
> `docs/sessions/next-session-3-subagents.md`. Master CI and Pages deploy passed.
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
> use `docs/plans/2026-05-01-backlog.md` for older product context. The only
> remaining benchmark lane is live GraceKelly/Mistral work: explicit opt-in only.
> It requires staged runtime and is not an active local backlog item.
> **Active remediation source (2026-08-02+):** `plan_sol_23_07_26`.

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
