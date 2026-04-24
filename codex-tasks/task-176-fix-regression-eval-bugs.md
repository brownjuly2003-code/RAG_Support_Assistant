# Task 176 — Regression-eval bugs: deeper fix (continuation)

## Status
Continuation of partial landing in commit `324305c`. Bugs 1 and 3 closed and verified; bug 2 reopened with deeper scope; bug 4 added after it surfaced during verification.

## Goal
Drive `scripts/regression_eval.py` through `run_qa_pipeline` on a live RAG stack without any repeating WARNING wall in the log and without losing rows in `trace_evaluations` or `eval_results`. Two remaining defects to close.

## Context
Commit `324305c` landed:
- Bug 1 — `agent/graph.py::grade_docs` relaxed schema (`additionalProperties=True`, `required=["relevant"]`) + try/except fallback. `tests/test_grade_docs.py` added.
- Bug 3 — `INGESTION_CATEGORIZER_MODEL` setting in `config/settings.py`, consumed by `ingestion/categorizer.py`; `.env.example` documents the override.

Verification on disposable Postgres 16 + 3 ingested seed docs (`docs/{warranty,returns_policy,errors_e10_e30}.md`) + `evaluation/curated_cases.jsonl` (10 KB-aligned cases) with `LLM_PROVIDER_PROFILE=external-mistral`, `--baseline ministral-3b-latest --candidate mistral-small-latest --max-cases 3`:
- Grade_docs path: 0 warnings (was wall of `LLM error: $.relevant is required` / `$.type is not allowed`).
- Categorizer path: 0 warnings (was `Categorizer returned invalid payload`).
- Run artefact: `reports/regression/20260424T224009Z-ministral-3b-latest-vs-mistral-small-latest.json` with `aggregate.baseline_pass_rate=1.0`, `aggregate.candidate_pass_rate=0.6667`, 3 cases.

### Bug 2 — online evaluators asyncpg race (NOT closed by first pass)
`evaluation/evaluator_runner.py` was refactored to per-evaluator session + `asyncio.gather` and `tests/test_online_evaluators.py` extended (24/24 pass), but the live run still emits repeated warnings:

```
WARNING agent.graph Online evaluators failed:
  (sqlalchemy.dialects.postgresql.asyncpg.InterfaceError)
  cannot perform operation: another operation is in progress
  [SQL: INSERT INTO trace_evaluations ...]
```

Final `INSERT INTO eval_results` at the end of the run also dies with the same `InterfaceError`.

Unit tests do not reproduce the race because they call `evaluator_runner` standalone against a fresh session, not from inside `run_qa_pipeline`. The race is almost certainly between (a) the session that the LangGraph node in `agent/graph.py` holds during `_persist_trace_evaluation` or similar, and (b) the `_persist_one` sessions opened inside `evaluator_runner`. Whichever of the two acquires a connection first pins it; the next concurrent INSERT hits the same connection and trips `InterfaceError`.

Likely fix axes (pick the least-invasive that passes the new integration test below):
- Ensure `evaluator_runner`'s `async with session_factory() as session` actually pulls a **fresh** connection from the pool, not reuses the caller's. Look at how `session_factory` is constructed and whether it is bound to a request-scoped connection.
- Add an explicit `engine.connect()` / `async with engine.begin() as conn` wrapper per evaluator and issue the INSERT through that connection, bypassing the shared session if `SessionLocal` is scoped.
- Serialize evaluators behind an `asyncio.Lock` when the caller already holds an open session on the same engine. Slower, but simpler.
- Verify `DB_POOL_SIZE` + `DB_POOL_OVERFLOW` in `config/settings.py`; if 5 concurrent evaluators can exhaust the pool when `run_qa_pipeline` already holds a session, bump the default or add overflow.

### Bug 4 — tool_use_efficiency FK violation (new)
Live log contains:

```
WARNING agent.graph Online evaluators failed:
  (sqlalchemy.dialects.postgresql.asyncpg.IntegrityError)
  <class 'asyncpg.exceptions.ForeignKeyViolationError'>:
  insert or update on table "trace_evaluations" violates foreign key
  constraint "trace_evaluations_trace_id_fkey"
  DETAIL: Key (trace_id)=(provider-benchmark-dc1dcb23-...) is not present in table "traces"
```

`tool_use_efficiency` evaluator (one of the evaluators iterated inside `evaluator_runner.persist_online_evaluations`) tries to `INSERT INTO trace_evaluations` for `trace_id = "provider-benchmark-..."` before the matching row in `traces` has been committed by `run_qa_pipeline`. Either:
- (a) Move the evaluator_runner call in `agent/graph.py` so that it runs **after** the trace row is committed (preferred if the call site is a single graph node).
- (b) Have `evaluator_runner.persist_online_evaluations` upsert a stub row into `traces` if the `trace_id` is missing. Riskier — changes FK semantics silently.

Pick (a) unless you find that `run_qa_pipeline` finalises the trace only after evaluators run, in which case (b) with a clear comment is fine.

## Deliverables

### Bug 2 fix
- Actual code change in `evaluation/evaluator_runner.py` and/or `agent/graph.py` or wherever sessions are acquired, driven by the hypothesis above.
- No feature flag — this is an unconditional correctness fix.

### Bug 4 fix
- Ordering fix in `agent/graph.py` (preferred) or stub upsert in `evaluation/evaluator_runner.py`.
- Comment at the fix site explaining **why** the ordering matters (so future refactors don't reintroduce the race).

### Integration test (new, reproduces bugs 2 + 4 against real Postgres)
- `tests/integration/test_regression_eval_live.py` (or colocate under `tests/integration/test_online_evaluators_live.py` if a similar fixture already exists).
- Uses `testcontainers-python` `PostgresContainer` **or** a `docker-compose.test.yml`-style disposable setup (the project already has `docker-compose.test.yml` from task-173 — reuse if applicable).
- Flow: start pg → `alembic upgrade head` → ingest three tiny seed docs via `IngestPipeline` → run `regression_eval.run_regression` (programmatic import, not subprocess) on 2 cases with `mock provider` for LLM (no paid API calls in CI), asserting:
  - Zero `InterfaceError: another operation is in progress` in captured logs.
  - Zero `ForeignKeyViolationError` in captured logs.
  - All expected `trace_evaluations` rows are present for both cases.
  - Final `eval_results` row is persisted.
- Test must fail on `324305c` HEAD (confirming bugs are real) and pass after the fix.
- Skip cleanly if Docker is unavailable (use `pytest.importorskip("docker")` or `shutil.which("docker") is None` → `pytest.skip`).

### Cross-cutting
- `docs/CHANGELOG.md`: append entry `task-176 continuation: close bug 2 (asyncpg race) + bug 4 (FK ordering)` under the existing partial entry from `324305c`.

## Acceptance criteria
- [ ] Live `scripts/regression_eval.py --baseline ministral-3b-latest --candidate mistral-small-latest --allow-paid-apis --max-cases 3` against disposable Postgres 16 + ingested seed docs emits **zero** `Online evaluators failed: InterfaceError: another operation is in progress` warnings.
- [ ] Same run emits **zero** `ForeignKeyViolationError` warnings.
- [ ] Final `INSERT INTO eval_results` succeeds; row is queryable via `SELECT * FROM eval_results ORDER BY created_at DESC LIMIT 1`.
- [ ] `trace_evaluations` contains at least one row per evaluator per trace (check with `SELECT trace_id, evaluator_name FROM trace_evaluations`).
- [ ] Bugs 1 and 3 stay green (grade_docs warnings still zero, categorizer warnings still zero).
- [ ] New `tests/integration/test_regression_eval_live.py` fails on `324305c`, passes after fix.
- [ ] `pytest tests/ --ignore=tests/integration --ignore=tests/test_a11y.py -p no:schemathesis -q --tb=no` — 511 passed / 1 skipped baseline preserved (plus the new test landed if not under `tests/integration`).
- [ ] `ruff check scripts/ tests/ config/ agent/ evaluation/ ingestion/` — clean.

## Notes
- Environment hints for verification:
  - Disposable pg: `docker run -d --rm --name rag-pg -e POSTGRES_DB=rag_assistant -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag_dev_password -p 5432:5432 postgres:16-alpine`.
  - Redis: any `redis:7-alpine` on `:6379` — `REDIS_URL=redis://localhost:6379/0`.
  - Ingest seed: `from ingestion.pipeline import IngestPipeline; IngestPipeline().ingest("docs/", tenant_id="default")` after `alembic upgrade head`.
  - LLM: `LLM_PROVIDER_PROFILE=external-mistral` + `MISTRAL_API_KEY=<key>`.
- Do **not** modify `scripts/regression_eval.py` itself unless the fix requires it. If ordering is the only relevant change for bug 4, it lives in `agent/graph.py`.
- Do **not** expand curated dataset or change providers.yml here — that is task-177 scope.
- Do **not** refactor unrelated code. Surgical fixes only; stay inside the files named above unless absolutely required.
- When deciding between the three fix axes for bug 2: the integration test should **fail** on `324305c` with the current evaluator_runner refactor; if adding `async with engine.begin()` per evaluator makes it pass, stop there. Avoid the lock path unless the pool approach doesn't work — it reduces throughput.
