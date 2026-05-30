# Agent State

## Current Project State

- Project: RAG Support Assistant.
- Stack: Python 3.13, FastAPI, LangGraph, ChromaDB, Postgres, Redis, static HTML UI, Helm/Docker deploy artifacts.
- Branch source: `master` tracks `origin/master`; current history includes the
  2026-05-30 Codex audit remediation series after the weekly-report fixes.
- Snapshot date: 2026-05-30 (Europe/Bucharest).
- Baseline HEAD before the 2026-05-30 audit/remediation run:
  `4d60479` (`ci: clarify weekly report delivery workflow`).
- Baseline file count: 698 tracked files from `git ls-files`.
- Baseline JS bundle size: not applicable; no frontend bundler config was found.
- Baseline i18n key count: not applicable; no i18n JSON catalog was found.
- Baseline generated bundle/artifact size: 0 bytes for searched bundle-like
  artifacts outside ignored dependency/cache directories.
- Git status before this durable-state refresh: clean, with local remediation
  commits ahead of the initial `origin/master` baseline.
- Origin sync at audit start: `origin/master` was at `4d60479`.

## Runtime

- Shell context: Windows PowerShell 5.1 in `D:\RAG_Support_Assistant`.
- pi CLI: available, `pi 0.72.1`.
- codex CLI: available, `codex-cli 0.128.0`.
- Python: available, `Python 3.13.7`.
- Local gate tools observed: `ruff`, `pytest`, `mypy`, `helm`, `bandit`, `pip-audit`, `pre-commit`.

## Last Verified Gates

- `git status --short --branch`: clean on `post-merge-handoff...origin/master` before this `AGENT_STATE.md` refresh.
- `git rev-parse HEAD`: `415d4c88baf52d4696987d5e2546dd7ce3ce576c`.
- `git ls-files | Measure-Object`: 697 tracked files.
- `python -c "import json, pathlib; json.loads(pathlib.Path(r'notebooks\\rag_support_colab_remote_benchmark.ipynb').read_text(encoding='utf-8')); print('notebook json ok')"`: passed before commit `a461fba`.
- `git diff --check`: passed before commit `a461fba`.
- `git fetch origin master`: updated `origin/master` to `415d4c8` after PR #1 merge.
- `Get-Command pi`: available.
- `Get-Command codex`: available.
- `pi --version`: `0.72.1`.
- `codex --version`: `codex-cli 0.128.0`.
- `python -m pytest tests/test_agent_endpoints.py -q -p no:schemathesis -p no:cacheprovider`:
  9 passed, 1 warning after the Agent UI text-rendering XSS fix.
- `node -e "... new Function(agent inline script) ..."`: agent inline script
  syntax OK after the XSS fix.
- `npm --prefix docs-site audit --audit-level=moderate`: found 0
  vulnerabilities after the `devalue` lock update and again after the CI audit
  workflow guard was added.
- `npm --prefix docs-site run astro -- build`: passed after the docs-site lock
  update and again after marking `docs/404` as draft; the earlier `/404`
  catch-all conflict warning no longer appears.
- `python -m pytest tests/test_request_id.py tests/test_production_entrypoint.py tests/test_cors_hardening.py -q -p no:schemathesis -p no:cacheprovider`:
  21 passed, 1 warning after browser security headers and production
  docs/OpenAPI controls.
- `python -m pytest tests/test_docker_compose_hardening.py -q -p no:schemathesis -p no:cacheprovider`:
  3 passed, 1 warning after scoping default Compose to local development.
- `python -m pytest tests/test_production_entrypoint.py tests/test_settings_production_secrets.py tests/test_docs_quality.py -q -p no:schemathesis -p no:cacheprovider`:
  29 passed, 1 warning after the production auto-migration fail-closed change.
- `python -m pytest tests/test_github_workflows.py -q -p no:schemathesis -p no:cacheprovider`:
  5 passed, 1 warning after adding the docs-site npm audit workflow guard.
- `python -m pytest tests/test_restore_verify.py -q -p no:schemathesis -p no:cacheprovider`:
  7 passed, 1 warning after switching restore tar extraction to `filter="data"`.
- Targeted `ruff check` entries for changed Python test/source files passed
  during the 2026-05-30 audit remediation series.
- `powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun`: not rerun on 2026-05-30 because the current WIP is docs/notebook-only and local resource constraints forbid unnecessary heavy gates.
- PAUSE protocol dry-run simulation: passed (last verified 2026-05-04).
- BLOCKED protocol dry-run simulation: passed (last verified 2026-05-04).
- `python -m pytest -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-may07-snapshot --ignore=tests/integration`: 735 passed, 4 skipped (verified 2026-05-07 at `d0016c2`; 16:20 wall time).
- `python -m mypy auth db/models.py db/engine.py llm/providers/ config/settings.py agent/state.py agent/prompts.py agent/prompt_registry.py agent/tools.py agent/graph.py --no-incremental`: 18 source files clean (verified 2026-05-07).
- `python -m mypy api/app.py --no-incremental --follow-imports=skip`: clean (verified 2026-05-07).
- `python -m pytest tests/test_precommit_config.py -q -p no:schemathesis -p no:cacheprovider`: 9 passed, 1 warning (verified 2026-05-30 at `6755403`).
- `ruff check tests/test_precommit_config.py`: All checks passed (verified 2026-05-30 at `6755403`).
- `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path(r'.github\\workflows\\ci.yml').read_text(encoding='utf-8')); yaml.safe_load(pathlib.Path(r'.pre-commit-config.yaml').read_text(encoding='utf-8')); print('yaml ok')"`: passed (verified 2026-05-30 at `6755403`).
- `python -m pytest tests/test_root_routes.py tests/test_admin_view.py tests/test_production_entrypoint.py tests/test_docs_quality.py tests/test_precommit_config.py tests/test_a11y.py::test_all_table_headers_define_scope tests/test_a11y.py::test_pages_define_one_main_landmark tests/test_a11y.py::test_widget_page_is_covered_by_a11y_landmark_checks tests/test_a11y.py::test_removed_trace_ui_templates_are_not_a11y_targets tests/test_a11y.py::test_a11y_templates_render_for_snapshot tests/test_a11y.py::test_a11y_template_heading_order_is_sequential -q -p no:schemathesis -p no:cacheprovider`: 56 passed (verified 2026-05-30 at `1ff5ff3` before commit).
- `python -m pytest tests/test_mobile_responsive.py -q -p no:schemathesis -p no:cacheprovider`: 3 passed (verified 2026-05-30 at `1ff5ff3` before commit).
- `python -m pytest tests/test_post_deploy_smoke.py::test_smoke_script_keeps_python_311_compatible_fstrings -q -p no:schemathesis -p no:cacheprovider`: failed before the smoke-report fix with one Python 3.11 f-string compatibility finding, then passed after the fix.
- `python -m pytest tests/test_post_deploy_smoke.py -q -p no:schemathesis -p no:cacheprovider`: 7 passed, 1 warning (verified 2026-05-30 before `69d8e95`).
- `ruff check scripts/post_deploy_smoke.py tests/test_post_deploy_smoke.py`: All checks passed (verified 2026-05-30 before `69d8e95`).
- `python -m py_compile scripts/post_deploy_smoke.py`: passed (verified 2026-05-30 before `69d8e95`).
- `python scripts\weekly_report.py --help` with `PYTHONPATH` set to the
  repository root: passed after commit `a86b44c`.
- `python -m pytest tests/test_precommit_config.py tests/test_weekly_report.py -q -p no:schemathesis -p no:cacheprovider`: 17 passed, 1 warning (verified 2026-05-30 before `a86b44c`).
- `ruff check tests/test_precommit_config.py`: All checks passed (verified
  2026-05-30 before `a86b44c`).
- `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path(r'.github\\workflows\\weekly-report.yml').read_text(encoding='utf-8')); print('weekly workflow yaml ok')"`:
  passed before `a86b44c`.
- `python -m ruff check .`: All checks passed (verified 2026-05-30 before `6755403`; later code/test changes were checked with targeted Ruff entries above).
- `python -m bandit -r . -ll -c pyproject.toml -x ./tests,./.venv,./reports,./data,./archive-legacy,./.tmp`: 0 medium / 0 high (39 low informational), verified 2026-05-07.
- `pip-audit --strict --disable-pip --require-hashes --timeout 15 --progress-spinner off --cache-dir .tmp/pip-audit-cache --ignore-vuln CVE-2026-45829 --ignore-vuln GHSA-f4j7-r4q5-qw2c -r requirements.lock`: no known vulnerabilities found, 1 ignored (verified 2026-05-30 after the ChromaDB lock update).
- `gh pr checks 1`: all non-skipped CI jobs passed on PR #1 code head `11add63` before merge (helm, lint, migrations, pre-commit, regression-eval, security, test-integration 3.11/3.13, test-unit 3.11/3.13, type-check). Duplicate push/PR jobs were expected for that branch.
- `gh pr merge 1 --merge`: merged PR #1 into `master` at `415d4c8`.
- `gh run watch 26670103203 --exit-status`: master CI passed on `415d4c8` (migrations, type-check, integration 3.11/3.13, unit 3.11/3.13, lint, pre-commit, security, helm; regression-eval skipped because inputs did not change).
- `gh run watch 26670103209 --exit-status`: Pages docs build and deploy passed on `415d4c8`.
- `gh run watch 26671830370 --exit-status`: master CI passed on
  `a86b44c` (regression-eval skipped because inputs did not change).
- `gh workflow run weekly-report.yml --ref master` followed by
  `gh run watch 26671836799 --exit-status`: manual Weekly Report dispatch
  passed on `a86b44c`.
- `python -m pytest tests/test_startup_concurrency.py -q -p no:schemathesis -p no:cacheprovider`:
  2 passed, 1 warning after commit `7b0d9ee` added the Chroma
  embedding-compatibility startup guard.
- `ruff check api/app.py tests/test_startup_concurrency.py`: All checks
  passed after commit `7b0d9ee`.
- `python -m pytest tests/test_startup_concurrency.py tests/test_health.py tests/test_magic_numbers_settings.py -q -p no:schemathesis -p no:cacheprovider`:
  15 passed, 2 warnings after commit `7b0d9ee`.
- `python -m py_compile api/app.py`: passed after commit `7b0d9ee`.
- Live diagnostic regression before commit `7b0d9ee`:
  `python scripts/regression_eval.py --baseline ministral-3b-latest --candidate mistral-small-latest --dataset evaluation/curated_cases.jsonl --tenant all --max-cases 1 --seed 42 --allow-paid-apis --no-persist`
  reached live Mistral but failed the gate with 0% pass because the default
  local Chroma collection expected embedding dimension 3 while `BAAI/bge-m3`
  produced 1024.
- Same live regression after commit `7b0d9ee`: failed fast before answer
  generation with `vector store is not initialized` plus a clear log that the
  existing Chroma store is incompatible and must be rebuilt.
- Non-destructive live eval collection setup: copied `docs/warranty.md`,
  `docs/returns_policy.md`, and `docs/errors_e10_e30.md` into
  `.tmp/live-eval-seed-docs-20260530T0835`, then ingested them with
  `VECTORDB_COLLECTION_PREFIX=rag_eval_20260530t0835` and
  `INGESTION_BATCH_ENABLED=false`; ingestion loaded 3 documents and produced
  6 chunks. No tracked data or existing default Chroma collection was deleted.
- Live Mistral regression with the eval collection:
  `VECTORDB_COLLECTION_PREFIX=rag_eval_20260530t0835 ONLINE_EVALUATORS_ENABLED=false python scripts/regression_eval.py --baseline ministral-3b-latest --candidate mistral-small-latest --dataset evaluation/curated_cases.jsonl --tenant all --max-cases 3 --seed 42 --allow-paid-apis --no-persist`
  passed the gate: 3 effective cases, baseline pass rate 100%, candidate pass
  rate 100%, 0 regressions, 0 infrastructure failures, baseline cost
  `$0.000042`, candidate cost `$0.000228`.
- `gh run list --branch master --limit 5`: CI run `26679263174` and Pages run
  `26679263187` passed on pushed commit `7b0d9ee`.
- `python -m pytest tests/test_regression_runner.py tests/test_provider_benchmark.py -q -p no:schemathesis -p no:cacheprovider`:
  22 passed, 1 warning after commit `517ec57` added live regression wall-clock
  latency fallback.
- `ruff check scripts/regression_eval.py tests/test_regression_runner.py tests/test_provider_benchmark.py`:
  All checks passed after commit `517ec57`.
- `python -m py_compile scripts/regression_eval.py`: passed after commit
  `517ec57`.
- Live latency verification with the eval collection:
  `VECTORDB_COLLECTION_PREFIX=rag_eval_20260530t0835 ONLINE_EVALUATORS_ENABLED=false python scripts/regression_eval.py --baseline ministral-3b-latest --candidate mistral-small-latest --dataset evaluation/curated_cases.jsonl --tenant all --max-cases 1 --seed 43 --allow-paid-apis --no-persist`
  passed the gate and reported non-zero latency: baseline avg latency
  `59015.0 ms`, candidate avg latency `29661.0 ms`.
- `gh run watch 26679564874 --exit-status`: master CI passed on pushed commit
  `517ec57`.
- R3/R4 batch grading follow-up:
  `python -m pytest tests/test_grade_docs.py tests/test_provider_graph_integration.py tests/test_graph_error_handling.py tests/test_prompt_registry_integration.py tests/test_otel.py tests/test_langfuse_trace.py -q -p no:schemathesis -p no:cacheprovider`:
  29 passed, 1 warning after commit `71367a7` batched multi-document
  `grade_docs` into one structured LLM call with fallback to the old per-doc
  path.
- `ruff check .`: All checks passed after commit `71367a7`.
- `python -m py_compile agent/graph.py agent/prompts.py`: passed after commit
  `71367a7`.
- `python -m mypy agent/prompts.py agent/graph.py --no-incremental --show-error-codes --follow-imports=skip`:
  passed after commit `71367a7`. The same local two-file command without
  `--follow-imports=skip` timed out at 180s; GitHub CI run `26679982808`
  completed successfully on the pushed commit.
- `gh run list --branch master --limit 5`: CI run `26679982808` and Pages run
  `26679982810` passed on pushed commit `71367a7`.
- R4 fact-verification tracing follow-up:
  `python -m pytest tests/test_grade_docs.py tests/test_fact_verification.py tests/test_provider_graph_integration.py tests/test_graph_error_handling.py tests/test_langfuse_trace.py tests/test_otel.py -q -p no:schemathesis -p no:cacheprovider`:
  31 passed, 1 warning after commit `c0b6d24` added `trace_llm_call`
  instrumentation for `verify_facts.extract_claims` and
  `verify_facts.verify_claim`.
- `ruff check .`: All checks passed after commit `c0b6d24`.
- `python -m py_compile agent/graph.py tests/test_fact_verification.py`: passed
  after commit `c0b6d24`.
- `python -m mypy agent/graph.py tests/test_fact_verification.py --no-incremental --show-error-codes --follow-imports=skip`:
  passed after commit `c0b6d24`.
- `gh run watch 26680293620 --exit-status`: master CI passed on pushed commit
  `c0b6d24`.
- `gh run view 26680293609 --json status,conclusion,name,headSha,url`: Pages
  deploy passed on pushed commit `c0b6d24`.
- R7 curated seed expansion:
  `python -m pytest tests/test_curated_dataset.py tests/test_regression_runner.py tests/test_detect_stale_curated_cases.py -q -p no:schemathesis -p no:cacheprovider`:
  38 passed, 1 warning after commit `c964211` expanded
  `evaluation/curated_cases.jsonl` from 20 to 35 checked-in RU cases.
- `python scripts/regression_eval.py --baseline current --candidate current --dataset evaluation/curated_cases.jsonl --tenant all --max-cases 100 --seed 42 --mock-experiment-runtime --no-persist`:
  passed the local mock gate on 35/35 cases with 0 regressions, 0
  infrastructure failures, and 100%/100% baseline/candidate pass rate.
- `ruff check .`: All checks passed after commit `c964211`.
- `python -m py_compile tests/test_curated_dataset.py scripts/regression_eval.py`:
  passed after commit `c964211`.
- `gh run watch 26680554552 --exit-status`: master CI passed on pushed commit
  `c964211`; the `regression-eval` job is PR-only and was skipped on this
  push.
- Final CI guard follow-up: `.github/workflows/ci.yml` now includes
  `evaluation/curated_cases.jsonl` in the `regression-eval` paths-filter, with
  `tests/test_github_workflows.py::test_regression_eval_filter_tracks_curated_dataset_changes`
  covering the guard. The red test failed before the workflow update and passed
  after it.
- Adaptive retrieval routing seam:
  `python -m pytest tests/test_model_routing.py tests/test_base_manager.py tests/test_provider_graph_integration.py tests/test_graph_error_handling.py tests/test_magic_numbers_settings.py tests/test_new_features.py tests/test_structural_chunking.py tests/test_experiment_registry.py -q -p no:schemathesis -p no:cacheprovider`:
  66 passed, 2 warnings after commit `676b3e0` added `RAG_RETRIEVAL_STRATEGY`,
  `global` query classification, vector-only simple-query retrieval, and
  simple-query graph bypass for `grade_docs`/`verify_facts`.
- `ruff check agent/graph.py agent/state.py agent/prompts.py config/settings.py vectordb/_base_manager.py tests/test_model_routing.py tests/test_base_manager.py`:
  All checks passed before `676b3e0`.
- `python -m mypy agent/graph.py agent/state.py config/settings.py vectordb/_base_manager.py --no-incremental --show-error-codes --follow-imports=skip`:
  passed before `676b3e0`.
- Aircargo curated seed expansion to the local R7 lower bound:
  `python -m pytest tests/test_curated_dataset.py -q -p no:schemathesis -p no:cacheprovider`:
  12 passed, 1 warning after commit `325d63c` expanded
  `evaluation/curated_cases_aircargo.jsonl` from 31 to 100 checked-in RU cases
  across the `32e841f`, `6b7417d`, and `325d63c` seed commits.
- `python -c "... evaluation/curated_cases_aircargo.jsonl ..."`: confirmed 100
  total rows and 100 unique `case_id` values after commit `325d63c`.
- `python scripts/regression_eval.py --baseline current --candidate current --dataset evaluation/curated_cases_aircargo.jsonl --tenant aircargo --max-cases 150 --seed 42 --mock-experiment-runtime --no-persist`:
  passed the mock gate on 100/100 aircargo cases with 0 regressions and 0
  infrastructure failures.
- `ruff check tests/test_curated_dataset.py`: All checks passed after
  `325d63c`.
- `python -m py_compile tests/test_curated_dataset.py`: passed after
  `325d63c`.
- Ahead-series focused verification after commit `db61488`:
  `python -m pytest tests/test_model_routing.py tests/test_base_manager.py tests/test_provider_graph_integration.py tests/test_graph_error_handling.py tests/test_magic_numbers_settings.py tests/test_new_features.py tests/test_structural_chunking.py tests/test_experiment_registry.py tests/test_curated_dataset.py tests/test_manager_semantic_chunking.py tests/test_ingestion_contextual.py tests/test_per_tenant_vectorstore.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-ahead-focused-2`:
  95 passed, 2 warnings.
- `python -m mypy agent/graph.py agent/state.py config/settings.py vectordb/_base_manager.py vectordb/manager.py --no-incremental --show-error-codes --follow-imports=skip`:
  passed after commit `db61488` fixed the tenant-aware manager's `Document`
  type alias for mypy while keeping runtime `manager.Document` compatibility.
- `ruff check agent/graph.py agent/prompts.py agent/state.py config/settings.py vectordb/_base_manager.py vectordb/manager.py tests/test_base_manager.py tests/test_curated_dataset.py tests/test_model_routing.py tests/test_structural_chunking.py tests/test_manager_semantic_chunking.py tests/test_ingestion_contextual.py tests/test_per_tenant_vectorstore.py`:
  All checks passed after `db61488`.
- `python -m py_compile agent/graph.py agent/prompts.py agent/state.py config/settings.py vectordb/_base_manager.py vectordb/manager.py tests/test_base_manager.py tests/test_curated_dataset.py tests/test_model_routing.py tests/test_structural_chunking.py tests/test_manager_semantic_chunking.py tests/test_ingestion_contextual.py tests/test_per_tenant_vectorstore.py`:
  passed after `db61488`.
- Ahead-series docs/config verification:
  `python -m pytest tests/test_docs_quality.py tests/test_quickstart_docs.py tests/test_backlog_docs.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-docs-ahead`:
  19 passed, 1 warning after commit `8c70cf9`.
- `ruff check tests/test_docs_quality.py tests/test_quickstart_docs.py tests/test_backlog_docs.py`:
  All checks passed after `8c70cf9`.
- `git diff --check origin/master..HEAD`: passed after `8c70cf9`.
- Ahead-series CI/meta verification:
  `python -m pytest tests/test_precommit_config.py tests/test_github_workflows.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-meta-ahead`:
  16 passed, 1 warning after commit `f6efe4f`.
- `python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path(r'.github\\workflows\\ci.yml').read_text(encoding='utf-8')); yaml.safe_load(pathlib.Path(r'.pre-commit-config.yaml').read_text(encoding='utf-8')); print('yaml ok')"`:
  passed after `f6efe4f`.
- Ahead-series regression-tooling verification:
  `python -m pytest tests/test_regression_runner.py tests/test_provider_benchmark.py tests/test_detect_stale_curated_cases.py -q -p no:schemathesis -p no:cacheprovider --basetemp=.tmp/pytest-regression-tooling-ahead`:
  34 passed, 1 warning after `f6efe4f`.
- `ruff check tests/test_regression_runner.py tests/test_provider_benchmark.py tests/test_detect_stale_curated_cases.py scripts/regression_eval.py`:
  All checks passed after `f6efe4f`.
- `python -m py_compile scripts/regression_eval.py tests/test_regression_runner.py tests/test_provider_benchmark.py tests/test_detect_stale_curated_cases.py`:
  passed after `f6efe4f`.

## Operating Mode

- Applicability status: READY_WITH_GUARDRAILS.
- Scheduler status: not installed by this setup; scheduler installation is opt-in only.
- Allowed default safe work: `docs/plans/2026-05-01-backlog.md`, bounded local tasks with exact allowed paths, and local verification.
- Default forbidden work: secrets, deploy, push, production data, live external
  services, live external-provider/API benchmark calls, destructive commands.

## Next Step

All `docs/plans/2026-05-01-backlog.md` items remain closed. The Colab remote
benchmark PR is merged into `master`:

- `905a65e` adds `docs/operations/colab-remote-benchmark.md` and
  `notebooks/rag_support_colab_remote_benchmark.ipynb`.
- `b5eb848` records the Windows laptop thin-client boundary.
- `a461fba` aligns the notebook to clone `colab-remote-benchmark` and ignores
  `.pytest-tmp*/` local pytest basetemp directories.
- `fe9a474` clears notebook Ruff and security CI issues.
- `965ccd5` documents the narrow unfixed ChromaDB audit ignore.
- `6755403` aligns the CI security config test with the multiline locked
  `pip-audit` command.
- `1ff5ff3` closes the Claude trace audit findings: protected root trace
  redirect, registered API trace target, stale `/traces-ui` docs removal,
  a11y target cleanup, authenticated review-queue trace fetch, and Python
  3.11/3.13 CI coverage for unit/integration tests.
- `69d8e95` fixes the Python 3.11-only smoke-report f-string syntax failure
  found by the new CI matrix and adds a local source guard.
- `11add63` refreshes durable handoff/status docs before merge.
- `415d4c8` is the merge commit on `master`.
- `52d16c4` refreshes GitHub Actions action majors, docs wording, and the
  pre-commit config guard test.
- `a86b44c` fixes the scheduled Weekly Report workflow import path by keeping
  the repository root on `PYTHONPATH`; master CI and a manual Weekly Report
  dispatch passed on that commit.
- `7b0d9ee` fails closed when a persisted Chroma collection is incompatible
  with the active embedding model, with a regression test for dimension
  mismatch.
- `517ec57` records wall-clock case latency in live regression reports when
  trace storage has no duration, so live benchmark summaries no longer show
  `0.0 ms` latency.
- `71367a7` reduces R3/R4 LLM fan-out by batching multi-document
  `grade_docs` into one structured call, while preserving the old per-doc
  fallback and top-ranked-doc preservation guard. Master CI run `26679982808`
  and Pages run `26679982810` passed.
- `c0b6d24` records per-call trace events for fact verification extraction and
  claim checks (`verify_facts.extract_claims`, `verify_facts.verify_claim`),
  so R4 latency/cost analysis can see that fan-out explicitly. Master CI run
  `26680293620` and Pages run `26680293609` passed.
- `c964211` expands the checked-in curated RAG seed set from 20 to 35 RU cases
  over the tracked warranty/returns/error KB docs and adds a guard test for the
  minimum local seed coverage. Master CI run `26680554552` passed; local mock
  regression on all 35 cases passed 35/35.
- `676b3e0` adds the local adaptive retrieval seam: `RAG_RETRIEVAL_STRATEGY`,
  `GLOBAL` classification, vector-only retrieval for simple routed questions,
  and graph bypass of `grade_docs`/`verify_facts` on simple questions.
- `32e841f`, `6b7417d`, and `325d63c` expand the aircargo checked-in eval seed
  from 31 to 100 RU cases over HR/legal/logistics/compliance docs; local mock
  regression passed 100/100.
- `db61488` fixes the tenant-aware vector manager's `Document` typing so the
  full ahead-series focused mypy command passes with `vectordb/manager.py`
  included.
- `8c70cf9` records the focused ahead-series verification; a follow-up
  docs/config gate passed `tests/test_docs_quality.py`,
  `tests/test_quickstart_docs.py`, and `tests/test_backlog_docs.py`.
- `f6efe4f` records that docs/config gate; subsequent local meta and regression
  tooling gates also passed without live APIs.

PR #1 (`https://github.com/brownjuly2003-code/RAG_Support_Assistant/pull/1`) is
merged. Master CI and Pages deploy passed on `415d4c8`; post-merge handoff
commit `f8ffb0f` is on `origin/master`.

2026-05-30 compact-resume note:

- This compact refresh is intentionally limited to GitHub Actions action-major
  refresh, docs wording, and the pre-commit config guard test.
- `MISTRAL_API_KEY` is present in local `.env` and Mistral `/v1/models`
  returned `200`; no secret value was printed or copied. `D:\TXT\GMAIL.txt`
  had no relevant Mistral key names.
- GraceKelly was not reachable at `http://127.0.0.1:8011/healthz/ready`; no
  local GraceKelly, Docker, Ollama, or model process was started because of
  the current resource boundary.
- No non-live local backlog item remains open. A live GraceKelly/Mistral run
  is a staged/manual runtime experiment only, not an active backlog item.
- If these refresh files are already clean in `git status`, do not repeat this
  family of checks just to refresh handoff prose. The next safe local action is
  non-destructive branch hygiene only if stale local branches still exist.
- 2026-05-30 non-local follow-up: stale scheduled Weekly Report failures from
  May 2026 were traced to `ModuleNotFoundError: No module named 'config'` when
  GitHub Actions ran `python scripts/weekly_report.py --dry-run`. Commit
  `a86b44c` adds `PYTHONPATH: ${{ github.workspace }}` and a regression guard;
  manual dispatch run `26671836799` passed.
- 2026-05-30 Codex audit remediation follow-up: `audit_codex_30_05_26.md`
  records the audit. Closed local items include Agent UI API-data text
  rendering, docs-site `devalue` audit fix plus CI audit guard, production
  security headers/docs route controls, local-dev-only default Compose
  bindings, production auto-migration fail-closed behavior with explicit
  fail-open override, safe tar extraction in restore verification, and the
  docs-site 404 route warning.
- 2026-05-30 Claude audit follow-up: `audit_claude_30_05_26.md` records a
  Claude Opus 4.8 audit focused on the RAG pipeline and current
  implementation. It identifies R7/R1/R2/R3/R4/R5 follow-up work: measure RAG
  quality on a larger RU eval set, switch the default reranker after A/B,
  reduce LLM fan-out, and address deferred
  deprecations/security hardening. R2 is closed by `5c7f3b1`: RRF now keys by
  stable metadata ids when available and otherwise includes a full content hash,
  with regression tests for shared contextual-header prefixes. R5's baseline
  tokenizer fix is closed by `e91c1f1`: BM25 now uses Unicode word tokens plus
  `casefold()` for index and query tokenization; deeper RU lemmatization remains
  optional future tuning.
- 2026-05-30 R7 live baseline follow-up: user explicitly opted into
  GraceKelly/Mistral local runtime. Commit `7b0d9ee` makes startup fail closed
  for an incompatible persisted Chroma collection instead of running retrieval
  with dimension errors and empty citations. The default local
  `rag_docs_default` collection remains stale/incompatible until rebuilt. A
  separate ignored eval collection `rag_eval_20260530t0835_default` was built
  from the three tracked demo KB docs and produced a passing 3-case live
  Mistral baseline. Commit `517ec57` also fixed live regression latency
  accounting; a follow-up 1-case live report showed non-zero baseline/candidate
  latency. This is only a partial R7 signal; full R7 still requires a larger RU
  eval set and a larger live run.
- 2026-05-30 R3/R4 fan-out follow-up: commit `71367a7` changes
  multi-document `grade_docs` from one LLM call per document to one batch
  structured LLM call, with JSON/text parsing fallback and the previous
  per-document path retained when batch grading is unavailable. This addresses
  the per-doc grade fan-out locally; follow-up latency proof should use the
  larger R7 eval set rather than another tiny smoke.
- 2026-05-30 R4 observability follow-up: commit `c0b6d24` adds Langfuse/SQLite
  trace events with durations for `verify_facts` claim extraction and each
  claim verification call. The audit's fan-out can now be measured from traces;
  it does not change factuality behavior.
- 2026-05-30 R7 seed expansion follow-up: commit `c964211` grows the
  checked-in curated dataset from 20 to 35 RU cases and adds a guard against
  shrinking it below 35 unique case IDs. This is not the full 100-150 case
  RAGAS baseline from the audit, but it raises the local regression floor and
  keeps the next full R7 run grounded in tracked KB content.
- 2026-05-30 final CI guard: the regression-eval PR paths-filter now tracks
  `evaluation/curated_cases.jsonl`, so future dataset edits trigger the mock
  regression gate on PRs.
- 2026-05-30 local routing follow-up: commit `676b3e0` implements the ADR 0001
  retrieval seam locally without enabling heavy graph retrieval. Simple routed
  queries use vector-only retrieval when available and skip per-doc grading and
  fact verification; `global` classification is recognized but falls back to
  hybrid unless a graph retriever is configured.
- 2026-05-30 aircargo R7 seed follow-up: commits `32e841f`, `6b7417d`, and
  `325d63c` grow `evaluation/curated_cases_aircargo.jsonl` from 31 to 100
  grounded RU cases and raise the guard to 100 unique RU queries. Mock
  regression on the aircargo set passed 100/100 with no live APIs. The next
  R7 step is no longer local seed growth to 100; it is a staged Colab/RAGAS
  baseline or optional expansion toward 150 cases if that baseline needs more
  coverage.
- 2026-05-30 Claude CLI follow-up: `claude -p` read-only full-project review
  prompts were blocked by Anthropic cyber safeguards, and
  `claude ultrareview --timeout 30` returned "Ultrareview is currently
  unavailable." No token or safeguard adjustment URL from the CLI error was
  copied into project files. The actual Claude audit exists in
  `audit_claude_30_05_26.md`.

Notebook URL for manual Colab use:
`https://colab.research.google.com/github/brownjuly2003-code/RAG_Support_Assistant/blob/master/notebooks/rag_support_colab_remote_benchmark.ipynb`

To run another dry-run of the autopilot guardrails:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/autopilot.ps1 -DryRun
```

Default safe work should come from `docs/plans/2026-05-01-backlog.md`; scheduler installation remains opt-in only.
