# Next Session: Current Backlog Handoff

## Goal
Continue from the merged Colab remote benchmark handoff. No non-live
autopilot-safe product backlog remains; do not start GraceKelly, Docker,
Ollama, GraceKelly browser orchestration, local model downloads, or live
external-provider benchmark paths unless the user explicitly opts in during
that session.

## Current Baseline
- Latest completed work:
  - Colab remote benchmark runbook and notebook were added and merged to
    `master` through PR #1.
  - Windows laptop and iMac are documented as thin clients for this benchmark
    lane; benchmark compute must happen in Colab/cloud.
  - Notebook clone target is now `master`.
  - `.pytest-tmp*/` local pytest basetemp directories are ignored.
  - PR #1 is merged:
    `https://github.com/brownjuly2003-code/RAG_Support_Assistant/pull/1`.
  - Master CI and Pages deploy passed on merge commit `415d4c8` after the
    notebook lint fix, ChromaDB locked-audit update, CI security config test
    alignment, Claude trace audit fixes, and the Python 3.11 smoke-report
    compatibility fix.
  - Post-merge handoff commit `f8ffb0f` is on `origin/master`.
  - GitHub Actions action-major refresh `52d16c4` and Weekly Report import
    fix `a86b44c` are on `origin/master`.
  - 2026-05-30 Codex audit and remediation series is recorded in
    `audit_codex_30_05_26.md` and `AGENT_STATE.md`. Completed local fixes:
    Agent UI API-data XSS hardening, docs-site `devalue` lock update, docs-site
    npm audit workflow guard, production security headers and production-only
    FastAPI docs/OpenAPI disabling, local-dev-only default Compose bindings,
    production auto-migration fail-closed behavior with explicit fail-open
    override, safe `tar.extractall(..., filter="data")` restore extraction,
    and docs-site 404 route warning cleanup.
  - 2026-05-30 Claude audit is recorded in `audit_claude_30_05_26.md`. It
    focuses on RAG implementation quality and flags R7/R1/R2/R3/R4/R5:
    unmeasured RAG quality, English default reranker on RU content, LLM fan-out,
    and deferred deprecation/security follow-up.
    R2 is closed by `5c7f3b1`: RRF no longer deduplicates solely by a
    200-character content prefix and has shared-context-prefix regression tests.
    R5's baseline tokenizer fix is closed by `e91c1f1`: BM25 uses Unicode word
    tokens plus `casefold()` for both index and query tokenization; deeper RU
    lemmatization remains optional future tuning.
    R7 has a partial live baseline: commit `7b0d9ee` makes incompatible Chroma
    collections fail closed, and a separate ignored eval collection built from
    the three tracked demo KB docs passed a 3-case live Mistral regression
    (`ministral-3b-latest` vs `mistral-small-latest`, 100%/100%, 0
    regressions). The default local `rag_docs_default` collection is still
    stale/incompatible until rebuilt. Commit `517ec57` fixed live regression
    latency accounting; a 1-case live follow-up reported non-zero latency
    instead of `0.0 ms`.
    R3/R4 per-doc grade fan-out is partially closed by `71367a7`:
    multi-document `grade_docs` now uses one structured batch LLM call with
    JSON/text parsing fallback and the old per-doc path retained when batch
    grading is unavailable. Master CI run `26679982808` and Pages run
    `26679982810` passed.
    R4 fact-verification observability is closed by `c0b6d24`: extract-claims
    and per-claim verification calls now emit trace events with durations
    (`verify_facts.extract_claims`, `verify_facts.verify_claim`). Master CI run
    `26680293620` and Pages run `26680293609` passed.
    R7 local seed coverage was raised by `c964211`: the checked-in curated
    dataset now has 35 unique RU cases over the tracked warranty/returns/error
    KB docs, with a guard test preventing regression below that floor. Local
    mock regression passed 35/35 cases; master CI run `26680554552` passed.
    The final CI guard also updates the PR `regression-eval` paths-filter to
    include `evaluation/curated_cases.jsonl`.
    Local follow-up `676b3e0` adds the ADR 0001 adaptive retrieval seam:
    `RAG_RETRIEVAL_STRATEGY`, `GLOBAL` classification, vector-only retrieval
    for simple routed queries, and simple-query bypass of `grade_docs` and
    `verify_facts`. Local focused graph/retriever/settings tests passed.
    Local follow-ups `32e841f`, `6b7417d`, and `325d63c` expand
    `evaluation/curated_cases_aircargo.jsonl` from 31 to 100 grounded RU
    aircargo cases; mock regression passed 100/100.
  - 2026-05-30 Claude CLI follow-up: read-only full-project `claude -p`
    review prompts were blocked by Anthropic cyber safeguards, and
    `claude ultrareview --timeout 30` returned "Ultrareview is currently
    unavailable." The actual Claude audit file above was supplied separately.
  - 2026-05-30 non-local check: the stale scheduled Weekly Report failures
    were caused by `ModuleNotFoundError: No module named 'config'` when Actions
    ran `python scripts/weekly_report.py --dry-run`. Commit `a86b44c` keeps
    the repository root on `PYTHONPATH`; master CI run `26671830370` and
    manual Weekly Report dispatch `26671836799` both passed.
  - 2026-05-30 readiness/runtime note: local `.env` contains
    `MISTRAL_API_KEY` and Mistral `/v1/models` returned `200`; after explicit
    user opt-in, GraceKelly was started locally on `http://127.0.0.1:8011`,
    `/healthz/ready` returned `ok`, `/api/v1/models` returned a model catalog,
    and a minimal `/api/v1/orchestrate` smoke succeeded. No secret value was
    printed or copied.
  - Agent Copilot semantic context UI and zero-overlap similar-ticket filtering.
  - Mock-safe benchmark Quickstart example and guardrail test.
  - `static/widget.html` a11y landmark coverage and color-contrast fix.
  - Axe/Lighthouse verification: `tests/test_a11y.py` with axe CLI `38 passed`;
    Lighthouse mobile `/static/chat.html` scored performance 99.
  - Local gate and Windows pytest workflow docs.
  - Provider API-key guard tests for missing/placeholder direct-provider keys.
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
- [x] Colab remote benchmark setup: notebook and runbook are committed on
      `master` for manual Colab use.
- [x] Colab remote benchmark PR: PR #1 merged to `master` as `415d4c8`.
      Master CI and Pages deploy passed.
- [x] Weekly Report scheduled workflow import failure: closed 2026-05-30 by
      `a86b44c`; manual workflow_dispatch run `26671836799` passed on
      `master`.
- [x] Chroma embedding compatibility guard: closed 2026-05-30 by `7b0d9ee`;
      CI run `26679263174` and Pages run `26679263187` passed on `master`.
- [x] Live regression latency accounting: closed 2026-05-30 by `517ec57`;
      CI run `26679564874` passed on `master`.
- [x] Batch document grading: closed 2026-05-30 by `71367a7`; CI run
      `26679982808` and Pages run `26679982810` passed on `master`.
- [x] Fact-verification LLM trace coverage: closed 2026-05-30 by `c0b6d24`;
      CI run `26680293620` and Pages run `26680293609` passed on `master`.
- [x] Curated RU seed expansion: closed 2026-05-30 by `c964211`; dataset is
      now 35 cases, local mock regression passed 35/35, and master CI run
      `26680554552` passed.
- [x] Regression-eval dataset path guard: final local change adds
      `evaluation/curated_cases.jsonl` to the PR paths-filter and covers it in
      `tests/test_github_workflows.py`.
- [x] Adaptive retrieval seam: closed locally by `676b3e0`; simple routed
      queries use vector-only retrieval when available and skip grade/verify,
      while `GLOBAL` classification is ready for a future graph retriever.
- [x] Aircargo curated seed expansion: closed locally by `32e841f`, `6b7417d`,
      and `325d63c`; dataset is now 100 cases and local mock regression passed
      100/100.

## Compact Resume Plan
- Close current dirty WIP first, if still dirty.
- If `master` is clean at `a86b44c` or later, do not repeat the Weekly Report
  fix or the action-major refresh merely to update handoff prose.
- With no new failing remote run, open PR/issue, or explicit live opt-in, the
  only default non-destructive local work is branch hygiene or focused follow-up
  from a new failing check. Do not repeat the audit-remediation family merely
  to refresh timestamps or handoff prose.
- If continuing R7 locally, do not assume the default local Chroma store is
  usable. Either rebuild `rag_docs_default` deliberately from the intended KB
  corpus, or keep using an explicit eval prefix such as
  `VECTORDB_COLLECTION_PREFIX=rag_eval_20260530t0835` for non-destructive
  regression runs.

## Suggested Subagents
None for default non-live work. Use subagents only if the session explicitly
opts into planning or running a live benchmark.

## Next Session Plan
- Start with `git status --short --branch` and confirm any dirty state is expected
  before changing files.
- Read `AGENT_STATE.md`, `docs/operations/colab-remote-benchmark.md`,
  `docs/plans/2026-05-01-backlog.md`, and this handoff before changing files.
- If opening the notebook manually, use:
  `https://colab.research.google.com/github/brownjuly2003-code/RAG_Support_Assistant/blob/master/notebooks/rag_support_colab_remote_benchmark.ipynb`
- If no explicit live opt-in is given, keep work read-only or docs-only and do
  not reopen closed AP housekeeping tasks or already-closed Codex audit fixes.
- Do not create new deployment/release/scheduler work without an explicit
  instruction.
- If making changes, keep scope to docs/tests unless a focused failing test
  proves runtime code needs a small fix.
- Do not run GraceKelly, Mistral benchmark calls, scheduler installation,
  deploy, or production data commands without explicit user opt-in in that
  session.
- Verify with focused tests first, then `git diff --check`; run full pytest if
  source or test files changed.

## Current Session Checks
- [x] No live external-provider benchmark has run without explicit opt-in.
- [x] Active handoff docs point future sessions at the Colab runbook on
      `master`, not the closed Batch N lane.
- [x] `git status --short --branch` was reviewed before this post-merge
      handoff refresh; branch was clean against `origin/master` at `415d4c8`.
- [x] PR #1 merged to `master` as `415d4c8`.
- [x] Master CI passed on `415d4c8`.
- [x] Pages docs build and deploy passed on `415d4c8`.
- [x] Weekly Report workflow import failure fixed by `a86b44c`.
- [x] Master CI passed on `a86b44c` (`26671830370`).
- [x] Manual Weekly Report dispatch passed on `a86b44c` (`26671836799`).
- [x] Codex audit remediation focused local checks passed; see `AGENT_STATE.md`
      for command-level evidence.
- [x] Explicit live opt-in was received for GraceKelly/Mistral runtime.
- [x] Live R7 partial baseline ran on a separate eval collection and passed
      3/3 cases with 0 regressions.
- [x] Live latency verification passed on the same eval collection with
      non-zero baseline/candidate latency in the report.
- [x] Batch `grade_docs` fan-out reduction committed and verified on CI
      (`71367a7`, CI `26679982808`).
- [x] `verify_facts` extract/claim LLM calls now have trace events for R4
      latency analysis (`c0b6d24`, CI `26680293620`).
- [x] R7 local curated seed set expanded to 35 RU cases (`c964211`, CI
      `26680554552`); full R7 still requires a larger 100-150 case/RAGAS live
      baseline when explicitly staged.
- [x] Local adaptive retrieval seam committed as `676b3e0`; focused pytest,
      Ruff, py_compile, `mypy --follow-imports=skip`, and `git diff --check`
      passed.
- [x] Local aircargo seed set expanded to 100 RU cases (`32e841f`, `6b7417d`,
      `325d63c`); full `tests/test_curated_dataset.py` passed and mock
      regression passed 100/100.
