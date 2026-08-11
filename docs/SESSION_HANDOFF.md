# Session handoff

**Обновлено:** 2026-08-11 — **Update-171** (VER-03 wider band blocked by isolated ingestion timeout).
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей
истории `AGENT_STATE.md`.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -12 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-171**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — **DoD**, не очередь галочек |

**Не использовать:** старые `START HERE` ниже Update-171; dirty
`BACKLOG.md` / `README.md` / audits; `_NEXT_SESSION.md` для routing
(это untracked stale pointer на Update-122, не SoT).

**Plan checkboxes:** не править casually. Local slice ≠ section closed ≠ release.

---

### 0A. Transparency snapshot

| Вопрос следующей сессии | Проверяемый ответ |
|-------------------------|-------------------|
| Последний implementation SHA | `c53f724` — §9.5d3 PipelineRunner streaming execution/deadline owner |
| Последний committed test contract | `eb764da` — VER-03 focused deployment reliability assertion closure |
| Последний committed handoff до Update-171 | `3e62849` — Update-170 adjacent order band green; SHA этого docs-коммита всегда брать из Actual Git |
| Actual Git перед этой docs edit | `master...origin/master [ahead 296]` at `3e62849`; refresh remains mandatory |
| Что закрыто локально | §9 telemetry **7/7**, dashboard, Astro 7 / DEP-01, TraceService, EscalationService, API/worker IngestionJobService, PipelineRunner capacity + sync + streaming execution, and VER-07; это не закрывает весь §9 и не означает production ready |
| Последний local gate | wider earlier band timed out before direct CLI in contextual ingestion; the exact contextual node independently repeated the 60-second coverage timeout |
| Известный baseline debt | no full locked-CI claim; ordinary router MyPy retains two pre-existing `no-redef` findings, and older `api/app.py`/legacy formatter debt remains outside recent changed lines |
| Worktree boundary | four protected tracked owner files remain dirty; owned implementation/test WIP **none**; unrelated untracked artifacts are preserved; active writer/test process none |
| Grok route truth | `local_grok_cli`; first run collected 1862 nodes then policy-cancelled at external-log parsing; cause-specific second run used `grok-4.5` (actual `grok-4.5-build`) and returned the timeout evidence |
| Что не запускалось | push, deploy, migration 019–023, Grafana import/provisioning, live service/provider/quality/scrape/alert delivery, scheduler mutation |
| Что осталось в §9 | SessionService deferred pending multi-replica SLA; live scrape/alert delivery; no ungated local architecture owner preselected |
| Следующий slice | distinct contextual-ingestion isolation diagnosis before any VER-03 order retry; do not repeat either timeout command or the full suite |

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **committed implementation** | `c53f724` — §9.5d3 PipelineRunner streaming execution/deadline owner |
| Latest **committed QG evidence** | `5f8bb78` — exact retained five-document E30 grading replay |
| Prior implementations (recent) | `d865b06` **9.5d2 PipelineRunner sync** · `aefcf20` **9.5d1 PipelineRunner capacity** · `890155a` **9.5c2 ingestion worker** · `84fbdf7` **9.5c1 ingestion API** · `03057aa` **9.5b escalation** · `9c207b6` **9.5a tracing** · `344e174` **9.2f** · `5a2f696` **9.2e** · `9817e89` **9.2d** · `64f40b3` **9.2c** · `356a530` **VER-06** · `11e52f1` **9.2b** · `3fe6d6f` **9.2a** · `4b0fba7` **VER-05** · `893efe3` **9.1c** |
| Latest **committed test contract** | `eb764da` — VER-03 focused deployment reliability assertion closure |
| Latest **committed docs before this Update** | `3e62849` — Update-170 adjacent order band green |
| This Update docs identity | Resolve with Actual Git (`git log -1 --oneline -- AGENT_STATE.md docs/SESSION_HANDOFF.md docs/PLAN_CLOSURE_STATUS.md`); never add a follow-up only to embed this file's self-SHA |
| Branch advisory | observed `master...origin/master [ahead 296]` at `3e62849` before this docs edit — **refresh mandatory** |
| Active writer / WIP | active writer/test process **none**; owned implementation/test WIP **none**; if these three handoff files are dirty, Update-171 docs WIP is present |
| Locally complete (documented scopes) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.8** + **5.1–5.7** + **6.1–6.7** + **7.1–7.7** + **8.1–8.5** + **9.1a–9.1c** + **9.2a–9.2f telemetry** + **9.3a dashboard** + **9.4a Astro 7 / DEP-01** + **9.5a–9.5d3 completed owner slices** + **QG-01–QG-04** + **HYBRID-MEM env propagation** + **VER-02/05/06/07** |
| Off-plan local capability | OpenCode Zen `opencode-zen-free` @ `faaa815`; no plan checkbox closed |
| Full plan §1–§10 / production | **NOT** complete / **NOT** claimed |
| Plan status | **ACTIVE** |
| Next ordered | Diagnose the contextual-ingestion test's real categorizer/LLM dependency under coverage before resuming VER-03 order isolation |
| Gates | **no Docker/WSL**; no push / deploy / live multi-service / further paid provider·quality execute / migrate 019–023 without **fresh explicit opt-in** |
| Migrations on disk | **019–023** (not applied here) |

**Update-171 records a different bounded blocker:** the selected 20-file
earlier window did not reach the direct lightweight GraceKelly CLI node. It
timed out after 60 seconds in contextual ingestion while importing the real
Ollama dependency graph; the exact contextual node repeated that timeout alone
under the same coverage settings. No code/test correction or raw retry
occurred; the Update-169 full gate remains red and VER-03 stays open. No live
Grafana import/provisioning, scrape, alert delivery, provider, service, index,
migration, scheduler, push, or deploy action occurs in this Update. The full
open/gated truth remains in §1C and §2A/§12.

**Last known verification:**

| Slice | Last known gate |
|-------|-----------------|
| **VER-03 Python 3.13 unit+coverage gate** | adjacent nine-file band remains green, but the next 20-file earlier window timed out before direct CLI in contextual ingestion; that exact node independently repeated the 60-second coverage timeout. Fresh full run remains **1839 passed / 1 failed / 15 skipped / 187 warnings** at **77.06%** coverage; no root cause/correction or full-suite-green claim |
| **9.5d3 PipelineRunner streaming execution/deadline owner** | Grok TDD transcript **2 failed → 6 passed**, first focused band **32 passed**; QA follow-up added event-worker and exception-fallback ownership; Codex independent owner/provider-token stream band **7 passed**; Ruff/format/scoped MyPy/diff/LF/protected hashes green |
| **9.5d2 PipelineRunner sync execution/deadline owner** | ownership **2 failed / 2 passed → 4 passed**; owner/concurrency/request-timeout/stream-capacity/chat-streaming band **22 passed**; Ruff/format/scoped MyPy/diff/LF/protected hashes green |
| **9.5d1 PipelineRunner capacity lifecycle owner** | ownership **2 failed → 2 passed**; pipeline concurrency/stream-capacity/request-timeout/chat-streaming band **20 passed**; Ruff/narrowed MyPy/format/diff/LF/protected hashes green |
| **9.5c2 IngestionJobService worker owner** | ownership **1 failed → 1 passed**; job-contract/liveness/worker/outage/duplicate-claim band **111 passed**; Ruff/narrowed MyPy/format/signature/diff/LF/protected hashes green |
| **9.5c1 IngestionJobService API owner** | ownership **1 failed → 1 passed**; job-contract/upload-idempotency band **73 passed**; scoped static and boundary gates green |
| **9.5b EscalationService lifecycle owner** | ownership **1 failed → 1 passed**; focused escalation band **32 passed**; scoped static and boundary gates green |
| **VER-07 retention audit tenant contract** | exact stale assertion **1 failed → 1 passed**; adjacent trace-retention/audit-retention/audit-tenant/tenant-enforcement band **22 passed**; Ruff lint + diff/LF + runtime-diff + protected hashes clean; whole-file formatter debt reproduces on clean `HEAD` |
| **9.5a TraceService lifecycle owner** | TDD import error → **3 passed**; adjacent **34 passed / 1 pre-existing failed**; narrowed **34 passed / 1 deselected**; final **13 passed**; scoped Ruff/format + narrowed MyPy + diff/LF + protected hashes clean |
| **9.4a Astro 7 / DEP-01** | independent pytest **5 passed**, one known warning; Astro check **0/0/0**; npm audit **0 vulnerabilities**; static build **59 pages** + Pagefind + sitemap; scoped diff/LF + protected hashes clean |
| **Update-156 transparency** | docs-only Actual Git/Grok/artifact reconciliation; docs quality gate only; no implementation test rerun or new implementation/release claim |
| **9.3a Grafana dashboard artifact** | Grok TDD **7 failed → 7 passed**; QA semantic threshold check **1 failed / 6 passed → 7 passed**; independent **7 passed**, one known warning; scoped Ruff + JSON parse + cached diff/LF + protected hashes clean; no live Grafana/import/scrape/alert-delivery evidence |
| **Update-154 transparency** | docs-only reconciliation against Actual Git; no implementation file changed, no project suite rerun, and no new implementation or release claim |
| **9.2f tenant-denied telemetry** | focused TDD **5 failed → 5 passed**; independent tenant/session/agent/KB/metrics/alerts band first rejected a zero-duration alert, then passed **54 tests** after one narrowed correction, one known warning; scoped Ruff + six-source narrowed MyPy + diff/LF clean; ordinary MyPy retains four pre-existing `api/app.py` errors outside changed lines; formatter debt remains outside added lines; no live scrape/alert delivery |
| **9.2e orphan-work telemetry** | focused TDD **5 failed → 5 passed**; independent pipeline/stream/metrics/alerts/timeout band initially exposed test-isolation leakage, then passed **37 tests** after one narrowed correction, one known warning; scoped Ruff + narrowed metrics MyPy + diff/LF clean; ordinary two-source MyPy retains two pre-existing `no-redef` errors outside changed lines; formatter debt remains only outside added lines; no live scrape/alert delivery |
| **9.2d safety-block telemetry** | focused TDD **5 failed → 5 passed**; full response-safety/metrics/alerts/unverified-auto band **35 passed**, one known warning; post-format focused gate **5 passed**; scoped Ruff + two-source MyPy + diff/LF clean; formatter debt remains only outside added lines; no live scrape/alert delivery |
| **9.2c escalation-delivery telemetry** | Grok focused TDD **8 failed → 8 passed** after one narrowed test-fixture correction; independent four-file band **33 passed**, one known warning; scoped Ruff + two-source MyPy + diff/LF clean; whole-file formatter debt remains only outside added lines; no live scrape/alert delivery |
| **Update-149 docs reconciliation** | docs quality **13 passed**, one known warning; scoped diff/LF clean; no project tests rerun and no new implementation claim |
| **VER-06 agentic safety mock contract** | exact stale test **1 failed** → **1 passed**; independent response-safety/agentic/auto-telemetry band **44 passed**, one known warning; scoped Ruff + diff/LF clean; whole-file formatter debt reproduces on `HEAD` and remains outside scope |
| **9.2b unverified auto-rate telemetry** | focused TDD **4 failed / 5 passed** → **9 passed**; independent band **60 passed / 1 failed**, exact failure reproduced alone as pre-existing VER-06; one narrowed rerun **60 passed**, 1 deselected, one known warning; scoped Ruff + new-file format + narrowed two-source MyPy + diff/LF clean |
| **9.2a index lifecycle failure telemetry** | focused TDD **10 failed / 2 passed** → **12 passed**; final lifecycle/metrics/alert band **75 passed**, 61 deselected, one known warning; docs **13 passed**; scoped Ruff + narrowed two-source MyPy + diff/LF clean; pre-existing whole-file format debt remains |
| **VER-05 retention caller contract** | stale assertion red **1 failed** with exact admin caller → independent retention/admin band **51 passed**, 62 deselected, one known warning; scoped Ruff + diff clean; whole-file format debt reproduces on clean `HEAD` and remains outside scope |
| **9.1c versioned cache namespace** | HTTP settings-source regression **2 failed** → **2 passed**; final namespace/HTTP-cache/Redis/manifest band **40 passed** with two known warnings; Ruff + changed-range format + narrowed MyPy + diff clean; no live Redis/provider/index mutation |
| **9.1b Redis reconnect backoff** | recovery red **2 failed** → green **2 passed**; focused Redis file **9 passed**; final Redis/cache band **15 passed** with two known warnings; Ruff check/format + scoped MyPy + diff clean; no live Redis |
| **9.1a bounded Redis fallback** | TTL/cap red **2 failed** → focused **2 passed**; partial-delete-count red **1 failed** → green **1 passed**; final Redis/cache band **13 passed** with two known deprecation warnings; Ruff check/format + scoped MyPy + diff clean; no live Redis |
| **VER-02 lifecycle fault type debt** | narrowed MyPy red **1 error** → green **1 source**; lifecycle/lock band **11 passed**; Ruff clean; package `vectordb` MyPy **10 source files** under `--follow-imports=skip`; no full/locked-CI claim |
| **HYBRID-MEM child env propagation** | TDD red **1 failed** → focused **2 passed**; independent live-quality/regression band **57 passed**; scoped Ruff + changed-file Mypy + diff clean; real lightweight child observed `RAG_RERANKER_MODEL` present with value `""`; no model/hybrid/live run |
| **QG-04 retained E30 replay** | exact five-document replay **1 passed**; independent grading/fail-closed/relevance/provider/fact-verification band **31 passed**; scoped Ruff + diff clean; production fix shared with `5662ea7`; no live replay |
| **QG-03B contextual-header grading** | TDD red **1 failed** → focused green **1 passed**; independent grading/fail-closed/relevance/provider band **24 passed**; scoped Ruff + changed-file Mypy + diff clean; no live replay |
| **QG-03A verifier-outage routing** | Grok TDD red **1 failed** → focused **6 passed** + Ruff; independent verifier/grounding/citation/graph-error/judge/provider band **49 passed** + Ruff + diff clean; ordinary local Mypy exposed 9 pre-existing `typeddict-item` errors outside changed lines, while the one narrowed run disabling only that code passed both changed source files; no locked/full-Mypy claim |
| **QG-02 generation failure routing** | TDD red **1 failed** → green **1 passed**; final focused **1 passed**; independent provider graph/error/model-routing/judge band **31 passed**; scoped Ruff + changed-file Mypy (`--follow-imports=skip`) + diff clean; full-import Mypy blocked by unlocked local NumPy stubs before project checking |
| **QG-01 vector parent expansion** | TDD red **2 failed / 9 passed** → focused **11 passed**; independent parent/base/reranker **34 passed**; scoped Ruff + changed-file Mypy + diff clean; the former broader `vectordb` debt was closed separately by `3a37fd2` |
| **Native §5 live quality attempt** | seed 42: 20/20 effective, infrastructure failures 0, child evidence valid, gate **FAIL**; candidate pass 65%, baseline 70%, minimum 85%, regressions 4; seeds 43–44 not run |
| **Lightweight GraceKelly/Sonnet 5 smoke** | local **16 passed** + Ruff/Mypy clean; live `claude-sonnet-5` smoke **PASS**; SQLite row verified |
| **OpenCode Zen** | 155 provider/settings/workflow/Helm tests; Ruff + scoped Mypy + Helm render + diff clean |
| **5.7** | independent regression + quality band **83 passed**; Ruff + scoped diff clean |
| **5.6** | Grok focused **25 passed**; independent quality + provider + workflow gate **46 passed**; Ruff and scoped diff clean |
| **5.5** | 33 passed (quality-metrics + provider-gate + workflows); readiness `SKIPPED_NO_OPT_IN`; Ruff clean |
| **5.4** | 56 passed (relevance + agentic + grounding/judge); Ruff clean |
| **4.8** | 16 passed (provider tokens + node SSE + parity); Ruff clean |
| **4.7** | included in 4.8 band |
| **6.7** | 19 passed (calibration); seed readiness NOT_READY (synthetic) |
| **7.7** | 8 passed (curated depth); 67 cases |
| **7.6** | 21 passed (live-gate + workflows) |
| **8.5** | 16 passed (widget + Playwright) |
| **DEP-01** | npm audit high=0 |

Full suite / live multi-service / migrate / push / deploy / formal live
provider gate were **not** run. The live quality gate was attempted only
through failing seed 42; live ×3 / release / production are **not** claimed.

### 1A. Lightweight GraceKelly + SQLite smoke

**Owner contract:** use native GraceKelly paid access with exactly
`claude-sonnet-5`. Do not use or start Docker/WSL, and do not silently fall
back to `sonar-2`, Ollama, or another model. Keep this path independent of
PostgreSQL, Redis, Celery, and the heavy multi-service stack.

**Committed in `99c6be5`:**

- `scripts/lightweight_gracekelly_smoke.py`
- `tests/test_lightweight_gracekelly_smoke.py`

The script reads the existing Chroma collection `rag_docs_default`, performs
lightweight lexical ranking, makes one GraceKelly generation request, and
stores only a successful result in
`.tmp/lightweight-gracekelly-smoke.sqlite3`. The CLI default is
`claude-sonnet-5`; a provider failure must not create a `PASS` row.

**Verification truth:**

- The model-default test first failed because the code still selected
  `sonar-2`, then passed after restoring `claude-sonnet-5`.
- The four non-subprocess tests passed in 0.79 s; the direct CLI + Chroma test
  passed separately in 5.86 s.
- The fresh focused smoke + provider gate passed **16 tests** in 4.95 s using
  an explicit writable `.tmp` basetemp; the slowest test was the direct CLI
  test at 4.36 s. The preceding failure was an access-denied error for the
  system pytest temp directory, not a product assertion failure.
- Scoped Ruff passed; scoped Mypy reported no issues in the two committed files.
- A regression proves a provider exception creates no SQLite result DB or
  `PASS` row. The implementation and tests are committed as `99c6be5`.

**Live evidence:** the historical task
`526243a3-84c5-4150-913e-70a2d21a2d29` exposed Playwright's post-click
navigation wait. GraceKelly commit `886b277` replaced that editor click with
`Locator.focus()`. One subsequent request through a temporary updated listener
selected exactly `claude-sonnet-5` and returned `PASS` with source
`returns_policy.md`. SQLite contains the verified successful row timestamped
`2026-08-09T15:03:21.124037+00:00`.

`D:\GraceKelly` remains an external orchestrator boundary. A read-only
Update-129 refresh found commit `886b277`, `main...origin/main [ahead 1]`, and
unrelated untracked `issues.md`; nothing was pushed. The temporary listener
was stopped. Port `8011` is owned by PID 3048 running the pre-existing uvicorn
command, which was not restarted after `886b277`; do not describe it as
serving the fix.

**Next slice:** none is selected. The lightweight smoke is committed and live
acceptance is already green. Await an explicit owner priority for remaining
gated work; do not repeat the paid request without new authorization/evidence.

### 1B. Native live quality gate attempt (2026-08-09)

This is separate from the lightweight one-call smoke above. The owner
authorized a native live quality attempt without Docker or WSL. The requested
gate was baseline `ministral-3b-latest` versus candidate
`gracekelly-mixed`, 3 runs × 20 cases, seeds 42–44. PostgreSQL, Redis, Celery,
Ollama, and the heavy multi-service stack were not started.

**Prepared native runtime:**

- Remote Mistral embeddings used `mistral-embed`; no secret value was logged.
- The original active `data/vectordb/chroma/rag_docs_default` collection is
  dimension 3 and was left unchanged.
- A compatible retained copy exists at
  `.tmp/live-quality-native-index-20260809/chroma`, collection
  `rag_docs_default`, 6 documents, dimension 1024. Its source was the existing
  collection `rag_eval_20260530t0835_default`.
- The updated external GraceKelly checkout was served temporarily from
  `D:\GraceKelly@886b277` on `127.0.0.1:8012`. The pre-existing listener on
  `8011` was not restarted or modified.

**Attempt chronology:**

1. The first run used the original dimension-3 active collection. The child
   produced 20 infrastructure failures, 0 effective cases, and
   `vector store is not initialized`. Evidence:
   [`live-quality-metrics-gate-result-native-2026-08-09.json`](../reports/regression/live-quality-metrics-gate-result-native-2026-08-09.json)
   and
   [`20260809T165258Z-ministral-3b-latest-vs-gracekelly-mixed.json`](../reports/regression/20260809T165258Z-ministral-3b-latest-vs-gracekelly-mixed.json).
2. The compatible index fixed initialization, but an empty
   `RAG_RERANKER_MODEL` environment value did not propagate to the Windows
   child. The resolved default `BAAI/bge-reranker-v2-m3` loaded and the child
   reached about 2.12 GiB. Only that verified regression child was stopped.
   The outer exit was `4294967295`; see
   [`live-quality-metrics-gate-result-native-2026-08-09-retry.json`](../reports/regression/live-quality-metrics-gate-result-native-2026-08-09-retry.json).
   The installed `PythonMemoryGuard` scheduled task was `Disabled`, so it did
   not enforce the documented 1 GiB limit. Do not repeat this hybrid command.
3. One narrowed retry set `RAG_RETRIEVAL_STRATEGY=vector`, keeping remote
   embeddings and the compatible index while bypassing local hybrid/reranker
   components. Seed 42 completed after about 2 h 9 min and failed quality
   thresholds. Fail-fast correctly prevented seeds 43 and 44 from making more
   paid calls.

Interpretation boundary: the seed-42 evidence is authoritative for the
executed **vector-only** retrieval configuration. It does not prove that the
unexecuted default hybrid path would produce the same quality result; that
path exceeded the local memory limit.

The long run was not a hard hang. A bounded sample showed the regression
process responding with increasing CPU and stable memory around 427 MiB. It
later exited and wrote both reports. The measured average latency explains the
wall time: baseline 81,878.8 ms versus candidate 304,456.7 ms per case.

**Authoritative seed-42 result:**

| Measure | Result | Required | Status |
|---------|-------:|---------:|--------|
| Effective cases | 20/20 | >0 | valid |
| Infrastructure failures | 0 | 0 | pass |
| Candidate pass rate | 65% | ≥85% and ≥baseline 70% | **fail** |
| Regressions | 4 | ≤2 | **fail** |
| Context precision | 0.1499 | ≥0.63 | **fail** |
| Context recall | 0.65 | ≥0.97 | **fail** |
| Full rate | 0.60 | ≥0.97 | **fail** |
| Miss count | 6 | ≤1 | **fail** |
| Faithfulness | 0.30 | ≥0.90 | **fail** |
| Answer relevancy | 0.4855 | ≥0.92 | **fail** |
| Unverified auto rate | 0 | 0 | pass |

The candidate gained three new passes but introduced four regressions:

| Case | Observed candidate outcome |
|------|----------------------------|
| `error-e20-filter-or-pump` | returned escalation-registration fallback; omitted E20 and the requested components |
| `error-e20-hose-kink` | returned a generic internal-error answer; omitted E20, hose, and kink |
| `error-e30` | claimed the KB lacked E30 guidance; omitted the required disconnect instruction |
| `warranty-receipt-storage` | claimed no exact retention period; omitted 12 months |

Do not collapse these into one assumed cause. The first two look like
orchestration/fallback outcomes; the latter two look like missing or rejected
retrieval context. Those are diagnostic hypotheses, not established root
causes.

**Evidence semantics and artifacts:**

- The exact child sidecar
  [`20260809T172531Z-ministral-3b-latest-vs-gracekelly-mixed.json`](../reports/regression/20260809T172531Z-ministral-3b-latest-vs-gracekelly-mixed.json)
  has `evidence_valid=true`, complete Section 5 metrics, `exit_code=1`, and
  `release_passed=false`. Its quality verdict is genuinely **FAIL**.
- The outer report
  [`live-quality-metrics-gate-result-native-2026-08-09-retry-vector.json`](../reports/regression/live-quality-metrics-gate-result-native-2026-08-09-retry-vector.json)
  has `LIVE_EXECUTED_FAIL` and `evidence_valid=false` because only 1 of the
  required 3 runs completed. It is not a valid ×3 aggregate.
- Therefore formal Section 5 live ×3 evidence remains open. Neither release
  nor production readiness is claimable.

**Cleanup and current boundary:** the regression child exited; the temporary
listener on `8012` was verified and stopped, and the port is closed. Port
`8011` still belongs to the pre-existing PID 3048 and was untouched. The
compatible temporary index remains for offline diagnostics. At handoff time,
`PythonMemoryGuard` remained `Disabled`; changing Task Scheduler state was not
authorized.

**QG-01 closure:** `c3ae4f4` fixes the `warranty-receipt-storage` cause only.
The vector fast path now applies bounded same-source parent expansion after
top-k selection, and vector-mode factories retain a lightweight
`HybridRetriever` when expansion has chunks. BM25 and reranker stay disabled.
The other regressions remain separate.

**QG-02 closure:** `1304ff4` fixes the `error-e20-hose-kink` orchestration
cause only. A generation-provider exception now produces the existing graph
error state and routes to error handling instead of returning a normal generic
internal-error answer. The stale independent-judge mock exposed by its gate was
corrected separately at `c157796`. The other two regressions remain separate;
no paid 3×20 rerun or live quality recovery is claimed. A paid retry still
requires fresh explicit opt-in.

### 1C. Authoritative open-problem ledger (Update-171)

This ledger is the next-session source for **known** open problems. `OPEN`
means unresolved locally; `GATED` needs fresh external/live authority;
`DEFERRED` needs a product/SLA decision; `LOCAL-ONLY` means code is fixed but
the relevant live outcome has not been re-proved. Actual Git and newer evidence
override this snapshot.

#### Product / RAG quality

| ID | Status | Problem and evidence | Next safe boundary |
|----|--------|----------------------|--------------------|
| **QG-03A** | **LOCAL-ONLY** | Retained SQLite trace proved `verify_facts` hit `httpx.ReadError`; generic graph error routing then overwrote the generated answer with an escalation-registration fallback. `80c2603` now fails closed to human through response safety while preserving answer/context and bounded error provenance. | No live replay; do not infer E20 keyword recovery or reopen without new code/evidence. |
| **QG-03B** | **LOCAL-ONLY** | Retained current-code reproduction matched the saved verdict pattern: a header-only `errors_e10_e30.md` chunk was kept while its same-logical-source E20 body was filtered. `5662ea7` replaces a positively graded contextual-header shell with its content-bearing chunks. | No live replay; do not infer E20 keyword recovery or reopen without new code/evidence. |
| **QG-04** | **LOCAL-ONLY** | Retained trace showed E30 content at retrieve, then only its header shell at grade; low-quality generation triggered a retry whose retrieval was empty. Current `5662ea7` replay restores the E30 body at the first loss boundary, and `5f8bb78` guards the exact five-document verdict pattern. | No live replay; do not infer E30 keyword recovery or reopen without new code/evidence. |
| **QG-LIVE** | **LOCAL-ONLY** | QG-01 (`c3ae4f4`), QG-02 (`1304ff4`), QG-03A (`80c2603`), QG-03B (`5662ea7`), and QG-04 (`5f8bb78` evidence over `5662ea7`) are locally closed, but no live replay followed. The saved seed-42 report therefore remains FAIL. | Re-evaluate only with fresh owner opt-in; never claim live recovery from local tests. |
| **LIVE-QUALITY** | **OPEN / FAIL** | Only seed 42 of required seeds 42–44 ran. Candidate pass 65% vs baseline 70%/floor 85%; 4 regressions; precision 0.1499, recall 0.65, FULL 0.60, MISS 6, faithfulness 0.30, relevancy 0.4855. The outer 3-run report is not valid aggregate evidence. | Fresh explicit paid/live opt-in for any new seed or 3×20 run. Passing §5 evidence does not exist. |
| **INDEX-DIM** | **OPEN** | Active `rag_docs_default` is dimension 3 and incompatible with remote 1024-dimension embeddings. A compatible six-document diagnostic copy is retained under `.tmp/live-quality-native-index-20260809/chroma`; the active collection was not rebuilt. | Dedicated validated rebuild/publish scope; do not replace or delete collections casually. |
| **HYBRID-MEM** | **LOCAL-ONLY / OPS GATED** | `3c90368` adds explicit `--disable-child-reranker` propagation; two focused tests, the 57-test band, and a real lightweight child prove `RAG_RERANKER_MODEL` reaches the Windows child as present and blank. The earlier default reranker still reached about 2.12 GiB, and the authoritative quality result remains vector-only. | Do not run hybrid while `PythonMemoryGuard` is disabled. Enabling/changing the scheduler guard and any bounded hybrid attempt require fresh explicit authority; no default-hybrid quality recovery is claimed. |
| **LIVE-LATENCY** | **OPEN** | Seed 42 took about 2 h 9 min. Mean latency was 81,878.8 ms baseline vs 304,456.7 ms candidate. | Profile only in a separately authorized bounded run; do not raw-retry the aggregate. |

#### Release / plan DoD

| ID | Status | Problem and evidence | Authority / closure condition |
|----|--------|----------------------|-------------------------------|
| **REL-01** | **GATED** | No real PostgreSQL multi-tenant restart, backup/restore, disposable-namespace, RPO/RTO, image, or live Helm evidence. | Explicit live/deploy authority; Gate A artifacts. |
| **REL-02** | **GATED** | Live PG/Redis/Celery/Chroma lifecycle and advisory-lock drills are open; migrations **019–023** exist on disk and were not applied here. | Explicit migration/live-service authority. |
| **REL-03** | **DEFERRED** | Multi-replica durable session/version ownership is not implemented. | Product SLA/consistency decision before implementation. |
| **REL-04** | **DEFERRED** | `STREAMING_RAG_PARITY` still defaults `false`; local parity/token contracts do not flip production behavior. | Product rollout decision plus acceptance evidence. |
| **REL-05** | **OPEN** | Calibration seed is synthetic; no production dual-annotator human sample or agreement/cost evidence exists. | Collect authorized human-labelled sample and reissue calibration artifact. |
| **REL-06** | **GATED** | Formal §7.6 live provider gate has scaffold/readiness only; mock/smoke is not release evidence. | Secrets + explicit `--execute` opt-in. |
| **REL-07** | **GATED** | Live IdP/OIDC drill and production `WIDGET_ALLOWED_ORIGINS` evidence are absent; widget E2E is Chromium-only local evidence. | Live IdP/prod-config authority and cross-environment acceptance. |
| **REL-08** | **OPEN** | Cache, seven telemetry signals, dashboard, Astro 7 / DEP-01, TraceService, EscalationService, API/worker IngestionJobService, and PipelineRunner capacity + sync + streaming execution owners are local-green. SLA-gated sessions, live scrape/alert delivery, and §10 full verification/canary/rollback remain open. | No ungated local architecture owner is preselected; continue only from an explicit owner request or documented safe residual, then run the required release gates. |

#### Verification / local operations

| ID | Status | Problem and evidence | Safe handling |
|----|--------|----------------------|---------------|
| **VER-01** | **ENV / BASELINE BLOCKER** | Installed `mypy 2.3.0` / `numpy 2.5.1` differ from locks `1.19.1` / `2.4.4`. QG-03A changed-file Mypy with `--follow-imports=skip` reported 9 pre-existing `typeddict-item` errors outside changed lines; a narrowed run disabling only that code passed. The 9.1c ordinary scoped run likewise reported two pre-existing `no-redef` and three `unused-ignore` errors outside changed lines; disabling only those confirmed codes passed the four changed source files. Full-import checking also stops on unlocked NumPy stubs under target 3.11. | Use a locked environment and reconcile existing type debt separately; do not call full or ordinary changed-file MyPy green. |
| **VER-02** | **LOCAL-CLOSED** | `3a37fd2` casts the final runtime-guarded callable to `FaultAction`. The exact failure reproduced before the edit; afterward narrowed MyPy passed, 11 lifecycle tests passed, Ruff passed, and package `vectordb` MyPy checked 10 sources under `--follow-imports=skip`. | Do not reopen without a code/environment change. Do not extrapolate this to VER-01, full imports, the repository, locked Python 3.11, or CI. |
| **VER-03** | **OPEN / FULL GATE RED; WIDER BAND BLOCKED** | Fresh Python 3.13 full gate remains **1839 passed / 1 failed / 15 skipped / 187 warnings** at **77.06%** coverage. The exact CLI node and adjacent nine-file band pass, but the next earlier window timed out first in contextual ingestion; that exact node repeats the timeout alone under coverage while importing the real categorizer/LLM graph. | Diagnose the contextual test boundary as a distinct slice before resuming order isolation. Do not repeat either timeout command, the green adjacent band, or unchanged full suite. |
| **VER-04** | **WARNING** | Focused pytest runs emit `StarletteDeprecationWarning` for `httpx` through `starlette.testclient`; assertions still pass. | Track dependency migration separately; warning is not fixed by QG-03A. |
| **VER-05** | **LOCAL-CLOSED** | `4b0fba7` replaces the stale zero-caller assertion with the exact intentional allowlist `["api/routers/admin_ops.py"]` and renames the test accordingly. The original assert reproduced red; the independent retention/admin band passed 51 tests, scoped Ruff and diff checks passed. | Do not reopen without a new caller or contract change. Whole-file Ruff format debt predates this slice and was not reformatted here. |
| **VER-06** | **LOCAL-CLOSED** | `356a530` updates the exact stale agentic-injection test to patch `agent.tools.search_kb_docs` and return `(formatted_text, raw_docs)`. The failure reproduced before the edit; afterward the exact test and the 44-test response-safety/agentic band passed. | Do not reopen without another agentic KB boundary change. File-wide formatter debt predates this test-only slice. |
| **VER-07** | **LOCAL-CLOSED** | `fd23317` aligns the stale trace-retention assertion with the existing tenant-aware audit contract. The exact failure reproduced **1 failed → 1 passed**; the adjacent retention/tenant/audit band passed **22 tests**. | Do not reopen without a tenant/audit boundary change; this does not establish full-suite or production evidence. |
| **OPS-01** | **DISABLED** | `PythonMemoryGuard` was read-only verified `Disabled` on 2026-08-09; last run was 2026-07-01. The 2.12 GiB child therefore had no configured 1 GiB enforcement. | Enabling/changing Task Scheduler requires explicit authority; do not run memory-heavy hybrid commands meanwhile. |
| **OPS-02** | **ENV LIMIT** | The system pytest temp root can return access denied. | Use a unique writable repository basetemp; do not raw-retry the inaccessible path. |
| **OPS-03** | **ENV LIMIT** | Git/PowerShell commands intermittently exceeded 10 s or timed out; root cause is not established. `login:false`, `git -C`, scoped plumbing commands, and a 30 s read-only timeout completed. | Avoid parallel full-worktree scans and raw retries; preserve the cycle budget. |

#### Workspace / external boundaries

| ID | Status | Problem and evidence | Safe handling |
|----|--------|----------------------|---------------|
| **WS-01** | **UNPUSHED** | Project branch was `master...origin/master [ahead 295]` at `c68911d` before Update-170 docs. No push is authorized. | Actual Git wins; push only with fresh explicit authorization and full gate. |
| **WS-02** | **PROTECTED DIRTY** | `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, and `plan_sol_23_07_26` contain unrelated owner changes. Exact hashes are in §8. | Never stage, rewrite, or use them as current routing authority. |
| **WS-03** | **UNTRACKED SoT RISK** | Active DoD file `rag-remediation-plan-2026-08-03.md` is untracked; `_NEXT_SESSION.md` is a stale untracked pointer. | Preserve both; use this handoff + Actual Git for routing. Do not casually stage or edit plan checkboxes. |
| **WS-04** | **UNTRACKED ARTIFACTS** | Numerous `.pytest_tmp*`, presentation/HTML, report, prompt, and diagnostic artifacts remain; some old Grok temp directories return permission warnings. The two `.grok-prompts/dashboard-artifact-9-3a-*.md` controls remain, while their dashboard pytest basetemps are absent. `cache-namespace-9-1c.md` and its prompt are historical. | They are not implementation WIP. Do not bulk-delete or stage them, and do not relaunch the same Grok prompt without new evidence or a narrowed hypothesis. |
| **WS-05** | **LOCAL-CLOSED** | `eb764da` aligns the deployment assertion with the canonical queue metric and implemented collision-resistant tenant-name marker. The exact test reproduced stale `ten-03`, then passed **1 test** after one narrowed correction; scoped gates were green. | Do not reopen without changed deployment reliability evidence. This focused closure does not close VER-03 or establish a full-suite claim. |
| **EXT-01** | **EXTERNAL / UNPUSHED** | `D:\GraceKelly` is `main...origin/main [ahead 1]` at `886b277`, with untracked `issues.md`. Port `8011` still listens under PID 3048 on the pre-existing command; `8012` is closed. | Do not claim `8011` serves `886b277`; external push/restart needs separate authority. |

### Dataset snapshot (7.7)

| Slice | Count |
|-------|------:|
| multi_tenant | 3 |
| multi_turn | 5 (2 sessions) |
| claim_citation | 3 |
| no_answer | 3 |
| tools | 3 |
| streaming | 3 |
| adversarial | 3 |
| pii | 3 |
| durable_escalation | 3 |
| context_recall | 3 |
| **total cases** | **67** |
| `MIN_CASES_PER_REQUIRED_SLICE` | **3** |

---

## 2. Быстрый старт следующей сессии

```text
1. Cycle-guard: one named atomic slice per user turn.
2. cd D:\RAG_Support_Assistant
3. git status --short --branch
4. git log -12 --oneline          # actual Git wins
5. Read ONLY top Update-170 in AGENT_STATE.md + §0A/§1C in this file
6. Confirm there is no active writer; protect §8 dirty/untracked boundaries
7. VER-03 adjacent order band is green; select at most one wider predecessor window
8. Do not invent another QG item; QG-01–QG-04 are local-only closures
```

### 2A. Decision card (status, not authorization)

| Candidate | Current truth | Boundary before action |
|-----------|---------------|------------------------|
| VER-03 aggregate-only CLI failure | Fresh full gate is red at **1839 passed / 1 failed**; exact CLI node and immediate nine-file predecessor band pass | Run one wider bounded predecessor window ending before the green band; no timeout guess or unchanged full-suite retry |
| §9 residuals | Cache, telemetry (**7/7**), dashboard, Astro 7 / DEP-01, TraceService, EscalationService, API/worker IngestionJobService, and PipelineRunner capacity + sync + streaming execution are local-green | No item preselected; SessionService needs an SLA decision and live alert delivery needs opt-in; no ungated local architecture owner is currently named |
| HYBRID-MEM | Blank child environment propagation is local-green at `3c90368`; default hybrid quality is unproved; memory guard is last known disabled | Fresh explicit authority for Task Scheduler state and a separately bounded hybrid attempt; verify the guard before any model load |
| Live quality ×3 | Only seed 42 ran and **failed**; seeds 43–44 and a valid passing aggregate do not exist | Fresh paid/live opt-in, compatible index, provider prerequisites, and fail-closed evidence collection |
| INDEX-DIM | Active `rag_docs_default` is dimension 3; remote embeddings are 1024; retained compatible copy is diagnostic evidence only | Dedicated validated rebuild/publish scope; never replace/delete the active or retained collection casually |
| Release / migrations / deploy / push | Plan and production remain open | Exact target-specific owner authorization plus the relevant full gate |

The table is routing information only. It grants no permission to execute a
provider call, enable a task, mutate an index, apply migrations, push, or deploy.

**Not authorized without opt-in:** push, deploy, live PostgreSQL/Redis/Celery,
unrelated live provider/quality execute with secrets, `alembic upgrade`
(incl. **019–023**), destructive Git, production claims, bulk plan checkbox
edits. The authorizations for the recorded one-call GraceKelly/Sonnet 5 smoke
and the completed seed-42 quality attempt have been consumed; do not infer
permission for another paid call.

---

## 3. Honest residual (plan sections)

| Plan § | Local | Residual / blockers |
|--------|-------|---------------------|
| **1** live multi-tenant / backup / RPO | partial chart/docs | **opt-in live** — Gate A open |
| **2** index lifecycle | **2.1–2.6g** local residual closed | live PG/Redis/Celery/Chroma + migrate drills |
| **3** execution / session / budget | **3.1a–3.1i** local | multi-replica durable session (**DEFER** without SLA; design exists) |
| **4** pipeline + escalation | **4.1–4.8** local | parity default still **off** (product decision) |
| **5** grounding fail-closed | **5.1–5.7** local | one valid live seed-42 report exists but **FAILS** quality; seeds 43–44 and passing ×3 evidence remain open |
| **6** judge / safety / agentic | **6.1–6.7** local | production human dual-annotator sample |
| **7** eval gate | **7.1–7.7** local | live execute with secrets; mock≠release; optional more depth |
| **8** widget / edge | **8.1–8.5** local | live IdP; `WIDGET_ALLOWED_ORIGINS` in prod |
| **9** cache / architecture / SLO | **9.1a–9.1c + 9.2a–9.2f + 9.3a–9.5d3 owner slices local** | SessionService SLA decision; live alert delivery |
| **10** final verification | not started | after 1–9 + opt-in evidence |

**Release / production: NOT claimable** until §1 live + §5 live quality evidence +
§6–8 residual + §10.

Full matrix: [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md).

**Off-plan capability (does not change the table):** `faaa815` adds explicit
`opencode-zen-free` routing for non-sensitive trial data. It produced no live
evidence and closes no plan DoD.

`99c6be5` adds a separate lightweight operational smoke for existing Chroma +
native GraceKelly + SQLite. Its one-call live acceptance does not substitute
for the formal §5 quality ×3 or §7.6 provider-gate evidence.

The Update-130 seed-42 quality sidecar is formal live §5 evidence, but it is a
failed single run rather than a passing ×3 aggregate. It closes neither §5 DoD
nor release readiness.

---

## 4. Implementation ledgers (impl SHAs only)

### Provider capability outside plan order

| Slice | SHA | Surface |
|-------|-----|---------|
| OpenCode Zen trial/free | `faaa815` | fixed free model/profile, endpoint identity, fail-fast key, live-gate/workflow/Helm plumbing, safety docs |
| Lightweight GraceKelly RAG smoke | `99c6be5` | existing Chroma lexical context → exact `claude-sonnet-5` request → SQLite success record; provider failures persist no PASS row |

### §5 grounding / quality (recent focus)

| Slice | SHA | Surface |
|-------|-----|---------|
| **5.1** | `7c53bdb` | grounding fail-closed statuses |
| **5.2** | `50bb220` | citation-bound claims |
| **5.3** | `1cdecb2` | grader fail-closed |
| **5.4** | `4f95e18` | independent retrieval relevance (≠ quality/100) |
| **5.5** | **`a901692`** | live quality metrics gate scaffold (×3 DoD structure) |
| **5.6** | **`fb72dd2`** | exact child report parse + release-honest §5 DoD wire |
| **5.7** | **`13bf255`** | canonical candidate metric producer + completeness provenance |

### §4 pipeline + escalation

| Slice | SHA | Surface |
|-------|-----|---------|
| **4.1** | `eaf41f3` | single terminal/history when parity succeeds |
| **4.2** | `f1c846e` | graph-only generation when parity on |
| **4.3** | `ad5e435` | durable idempotent escalation |
| **4.4** | `0371971` | auto human-route on normal ask |
| **4.5** | `6453530` | outbox retry without second ticket |
| **4.6** | `11acfec` | Celery beat + CLI outbox schedule |
| **4.7** | `6b91a35` | real LangGraph node status SSE |
| **4.8** | `fc7f07b` | provider token stream through generate |

### §6 judge / safety / agentic

| Slice | SHA | Surface |
|-------|-----|---------|
| **6.1** | `b3494a0` | unmeasured agentic; never fixed 80/85/90 |
| **6.2** | `d0317e9` | pre-response PII + prompt-injection |
| **6.3** | `d6e3a55` | independent judge fail-closed |
| **6.4** | `a7cefc3` | routing calibration artifact (bootstrap-defaults) |
| **6.5** | `431893c` | measured grounding when agentic has KB docs |
| **6.6** | `69c6fdf` | LLM evaluate wire on KB agentic terminals |
| **6.7** | `c707c46` | human readiness gate + recalibrate CLI |

### §7 eval gate

| Slice | SHA | Surface |
|-------|-----|---------|
| **7.1–7.5** | `94ac64e`…`4eceed3` | fail-closed + mock SMOKE + baseline + curated + CI |
| **7.6** | `d1ae4d6` | live provider gate scaffold (opt-in) |
| **7.7** | `47e255a` | depth ≥3/slice; **67** cases |

### §8 + DEP-01

| Slice | SHA | Surface |
|-------|-----|---------|
| **8.1–8.5** | `0bee13e`…`4d6be52` | widget → Playwright E2E |
| **DEP-01** | `cea370b` | Astro 7.2 / Starlight 0.41; npm audit total=0; validated empty exception register |

### Other bands

| Band | Ends at SHA | Note |
|------|-------------|------|
| §3 | `fe2f0aa` **3.1i** | process-local session version; multi-replica DEFER |
| §2 | `f347feb` **2.6g** | fault-injection residual closed local |

---

## 5. Contracts (recent complete slices — read before touching)

### Lightweight GraceKelly smoke @ `99c6be5`

- Use existing `data/vectordb/chroma` collection `rag_docs_default`; do not
  start Docker/WSL, PostgreSQL, Redis, Celery, Ollama, or a fallback model.
- The CLI default is exactly `claude-sonnet-5`. A missing lexical match, failed
  provider call, or empty answer fails closed before a successful SQLite row.
- Successful results go to
  `.tmp/lightweight-gracekelly-smoke.sqlite3`; the verified live row is already
  recorded in §1A and must not be regenerated merely to re-prove history.
- Local regression command needs a unique writable `--basetemp` under `.tmp`
  because the system pytest temp root is inaccessible to this account.
- The GraceKelly browser fix is external commit `886b277`; the listener on
  `8011` was not restarted onto that commit.

### OpenCode Zen @ `faaa815` (off-plan capability)

- `opencode-zen-free` fixes both routing lanes to
  `nemotron-3-ultra-free`; the runtime rejects non-`-free` canonical IDs and
  the profile declares no fallback.
- OpenAI-compatible requests use
  `https://opencode.ai/zen/v1/chat/completions` with server-side
  `OPENCODE_ZEN_API_KEY`; missing/placeholders fail during startup validation.
- `.env.example`, live-gate detectors, opt-in workflows, and optional Helm
  Secret rendering carry the key name only; no credential value is checked in.
- OpenCode documents the endpoint as temporary/logged trial service. Use only
  non-sensitive test data; availability/pricing/terms are external and mutable.
- No live call, quality result, production claim, or plan checkbox followed.

### 5.7 @ `13bf255`

- `regression_eval` emits all seven canonical §5 metrics from candidate
  question/answer/exact generation context and explicit routing/grounding.
- Context selection reuses `resolve_generation_context_docs`; all-rejected
  grade results stay empty while simple-path retrieval context remains visible.
- `quality_metrics_provenance.complete` fails real release runs closed when an
  eligible case lacks finite measurements.
- Top-level/nested release flags satisfy the exact-sidecar consumer contract.
- No substitution from quality/factuality/pass-rate/regression counts.

### 5.6 @ `fb72dd2`

- `scripts/live_quality_metrics_gate.py --mode live --execute` captures each
  argv-only child result and parses only that child's stdout JSON summary.
- The exact `report_json` must resolve to a file inside the workspace; no glob,
  newest-file selection, or path escape is accepted.
- Every sidecar must explicitly prove non-mock release honesty at top level and
  inside `gate`, and must contain all seven finite canonical §5 metrics.
- Invalid exit, summary, path, sidecar, evidence, or metric fails fast before
  remaining potentially paid runs; raw child streams/exception text are not
  copied into the gate report.
- Valid rows use the existing aggregate + DoD evaluator and produce
  `DOD_PASS` / `DOD_FAIL`; readiness/command remain non-live and never pass.
- **Historical 5.6 limitation, closed by 5.7:** sidecars did not yet emit all
  seven metrics. `13bf255` added that producer; real execute still needs
  opt-in evidence. Never substitute `quality_score`, `factuality_score`,
  `candidate_pass_rate`, or counts.
- Files: `scripts/live_quality_metrics_gate.py`,
  `tests/test_live_quality_metrics_gate.py`.

### 5.5 @ `a901692`

- `scripts/live_quality_metrics_gate.py`
  - modes: `readiness` / `command` / `live` / `evaluate-report`
  - plan floors: precision≥0.63, recall≥0.97, full_rate≥0.97, miss≤1,
    faithfulness≥0.90, answer_relevancy≥0.92, unverified_auto_rate=0
  - `MIN_RUNS=3`; multi-seed commands; aggregate means + CI half-width
  - opt-in `RAG_LIVE_QUALITY_METRICS_GATE` / `--live`; fail-closed without keys
  - forbids `--mock-experiment-runtime`; requires `--release-gate` +
    `--allow-paid-apis` + `--no-persist`
  - default readiness: `SKIPPED_NO_OPT_IN`, never `release_passed`
- Workflow: `.github/workflows/live-quality-metrics-gate.yml`
  (weekly + dispatch `enable_live` default **false**)
- Offline: `--mode evaluate-report --metrics-runs <json|dir>` scores supplied runs
- The former report-parse residual is closed by **5.6**; producer metrics are
  closed by **5.7**; actual live ×3 evidence remains open.

### 5.4 @ `4f95e18`

- `agent/relevance.py` — `measure_retrieval_relevance`
- Sources: `empty_context` | `retrieval_scores` | `graded_fraction` |
  `context_kept` | `unmeasured`
- **Never** `quality_score / 100`
- Wired: evaluate node, agentic evaluate, agentic measure
- `relevance_source` on state

### 4.8 @ `fc7f07b`

- LangGraph `custom` stream + `provider_token_stream_enabled`
- Generate streams via `generate_stream` / `.stream` when flag on
- `token_source=provider_generate` live; fallback `graph_answer_chunks`
- Single generation; parity default still **off**

### 4.7 @ `6b91a35`

- Real LangGraph node status SSE on parity path
- `iter_ask_events` / `stream_graph_node_events`

### 6.7 @ `c707c46`

- `assess_human_calibration_readiness` fail-closed floors
- synthetic `label_source` cannot claim `source=human-labelled`
- CLI: `scripts/recalibrate_routing.py` readiness/reissue/`--require-human`
- Seed remains synthetic; production human sample still residual

### 7.6 @ `d1ae4d6`

- `scripts/live_provider_gate.py` + weekly workflow
- Default readiness: `SKIPPED_NO_OPT_IN`; live needs opt-in + secrets + `--execute`

---

## 6. Key CLIs (focused)

```powershell
# Quality metrics gate readiness (no live)
python scripts/live_quality_metrics_gate.py --mode readiness --write-report reports/regression/live-quality-metrics-gate-readiness.json

# Offline DoD on supplied multi-run metrics
python scripts/live_quality_metrics_gate.py --mode evaluate-report --metrics-runs path\to\runs.json

# Human calibration readiness (expect NOT_READY on synthetic seed)
python scripts/recalibrate_routing.py --mode readiness

# Live provider gate readiness (no live)
python scripts/live_provider_gate.py --mode readiness --write-report reports/regression/live-provider-gate-readiness.json

# Focused tests (last known bands)
python -m pytest tests/test_live_quality_metrics_gate.py tests/test_live_provider_gate.py tests/test_github_workflows.py -q -p no:cacheprovider -p no:schemathesis
python -m pytest tests/test_retrieval_relevance.py tests/test_agentic_evaluate.py tests/test_agentic_measure.py -q -p no:cacheprovider -p no:schemathesis
python -m pytest tests/test_provider_token_stream.py tests/test_graph_node_sse.py tests/test_streaming_rag_parity.py -q -p no:cacheprovider -p no:schemathesis
```

Full suite / live / migrate — **not** the default gate for a single slice.

---

## 7. Next named candidate

The fresh VER-03 full gate is red only on the direct lightweight GraceKelly CLI
node, but the next earlier order window cannot yet test that hypothesis: it
times out first in contextual ingestion, and the exact contextual node repeats
the timeout alone under coverage. The sole next local candidate is a distinct
diagnosis of that test boundary and its real categorizer/LLM dependency. Do not
repeat either timed-out command, the green adjacent band, or the whole suite;
do not increase timeouts speculatively.

Completed lifecycle-owner boundaries are TraceService `9c207b6`,
EscalationService `03057aa`, IngestionJobService API `84fbdf7`, ingestion worker
`890155a`, PipelineRunner capacity `aefcf20`, and PipelineRunner sync execution
`d865b06`, plus PipelineRunner streaming execution `c53f724`. Do not reopen
them without a changed boundary. No ungated local architecture owner is
preselected. SessionService requires an explicit multi-replica SLA/consistency
decision and is not an autonomous candidate.

QG-01–QG-04, VER-05/06/07, §9.1a–9.4a, and their focused gates are locally
closed; do not replay them without new code or evidence.

A new paid seed or 3×20 retry needs fresh owner opt-in. Remaining local work
must come from an explicit owner request or one documented residual selected
in a new turn; do not invent another local QG item.

### Out without opt-in

- live multi-service / migrate / push / deploy / live provider·quality execute
- re-select through **8.5** / **4.1–4.8** / **5.1–5.7** / **6.1–6.7** /
  **7.1–7.7** / **9.1a–9.1c** / **9.2a–9.2f** / completed **9.3a–9.5d3** slices
- OIDC live IdP drill; bulk plan checkbox edits; production claims
- multi-replica impl without SLA (design DEFER)
- Docker/WSL or a silent model fallback for the lightweight smoke

### Further alternates (only if user prioritizes)

- live §1 / migrate 019–023 (**explicit opt-in only**)
- further curated corpus depth beyond 3/slice
- multi-replica durable session (**only with explicit SLA/product ask**)

---

## 8. Protected dirty / untracked (do not touch)

**Protected dirty tracked (leave alone):**
`BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`

**Owned handoff paths for Update-171:** `AGENT_STATE.md`, this file, and
`docs/PLAN_CLOSURE_STATUS.md`. Actual Git decides whether their docs-only commit
has already closed the diff; never stage the protected tracked files with them.

**Owned implementation/test WIP:** none. The former topology-test WIP is
committed at `eb764da`; the retained pytest basetemps are evidence/artifacts,
not active WIP.

**Protected SHA-256 snapshot (2026-08-09, before Update-133 edit):**

| File | SHA-256 |
|------|---------|
| `BACKLOG.md` | `95BF4DA93E012EDF3DEDF0525EE364F955F8B5428935D6EE970E27102530E311` |
| `README.md` | `B3364D116E40CD1CB327146AE71152C608A7888F3B0053AF3B4BE2BCD69B8652` |
| `audit_gpt_23_07_26.md` | `71EB338A4772C9C30152AA430C9DD79565E7564F91F670E070B406C52A37F9EF` |
| `plan_sol_23_07_26` | `0E5A8B81FB87D1A1FE888773108F42492C23BB82BD8BFE44CA0546C4FD2FDF8E` |

**Untracked (examples):**
`.grok-prompts/`, `.pytest_tmp*/`, presentations, `_NEXT_SESSION.md` (stale
untracked pointer; never routing authority),
`rag-remediation-plan-2026-08-03.md` (active plan — DoD source, no casual
checkbox edits), architecture HTML, etc. Preserve these unrelated artifacts.

`.tmp/live-quality-native-index-20260809/chroma` is retained diagnostic
evidence, not implementation WIP. It contains the compatible dimension-1024
collection used by seed 42; do not rebuild, stage, or delete it casually.

There is no owned untracked implementation WIP. The retained
`cache-namespace-9-1c.md` and
`.grok-prompts/cache-namespace-9-1c-impl.md` are historical control artifacts
for committed 9.1c, not WIP. The two untracked
`.grok-prompts/dashboard-artifact-9-3a-*.md` files are control artifacts for
committed `1237f3c`, not WIP; dashboard pytest basetemps are absent. The smoke
script and test are tracked in
`99c6be5`; if they appear untracked, stop and reconcile Actual Git instead of
recreating or staging substitutes.

Zen verification created
`.pytest_tmp_codex_opencode_{baseline,red,green,gate}/`; cleanup was blocked by
execution policy. They are not WIP and must never be staged; removal is safe
only when local policy permits. Docs-verification basetemps self-cleaned and
are absent.

---

## 9. Cycle budget (workspace rule)

- One user turn → **one named atomic implementation slice** + verify + docs
- At most 3 delegated runs (impl / QA-batch / docs); one QA follow-up
- No push/deploy/live without opt-in
- After hard-stop / cycle complaint: stop; cancel active writer once if needed

---

## 10. Env opt-in names (do not invent silent ON)

| Gate | Env | Default |
|------|-----|---------|
| Streaming parity | `STREAMING_RAG_PARITY` | **false** |
| Live provider gate | `RAG_LIVE_PROVIDER_GATE` | off |
| Live quality metrics gate | `RAG_LIVE_QUALITY_METRICS_GATE` | off |
| Live-quality child reranker override | CLI `--disable-child-reranker` with `--mode live --execute` | off; when explicit, child receives `RAG_RERANKER_MODEL=""` |
| Provider keys (presence only) | `MISTRAL_API_KEY`, `GRACEKELLY_API_KEY`, `OPENCODE_ZEN_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | unset |

Never log secret values.

---

## 11. Recent session path (this multi-turn arc)

| Order | Slice | SHA | What |
|------:|-------|-----|------|
| 1 | **4.8** | `fc7f07b` | provider token streaming through generate |
| 2 | docs | `cf12230` | Update-120 |
| 3 | **5.4** | `4f95e18` | independent retrieval relevance |
| 4 | docs | `7b86c1f` | Update-121 |
| 5 | **5.5** | `a901692` | live quality metrics gate scaffold |
| 6 | docs | `96ef373` | Update-122 |
| 7 | **5.6** | `fb72dd2` | exact child report → §5 DoD wire |
| 8 | docs | `33949b1` | Update-123 full transparency after 5.6 |
| 9 | **5.7** | `13bf255` | canonical metric producer + provenance |
| 10 | docs | `336b08e` | Update-124 full transparency after 5.7 |
| 11 | provider | `faaa815` | OpenCode Zen trial/free integration |
| 12 | docs | `ddb721c` | Update-125 full transparency after Zen integration |
| 13 | external fix | `D:\GraceKelly@886b277` | Playwright editor focus; local/unpushed |
| 14 | lightweight smoke | `99c6be5` | RAG script + regressions; local/live acceptance green |
| 15 | docs | `79379a6` | Update-129 reconciled GraceKelly smoke handoff |
| 16 | live quality evidence | no code SHA | native seed 42 completed: valid child evidence, quality **FAIL**, seeds 43–44 not run |
| 17 | docs | `9a870f7` | Update-130 after the native live quality attempt |
| 18 | **QG-01** | `c3ae4f4` | preserve bounded parent expansion on the vector lane |
| 19 | docs | `62a1f27` | Update-131 QG-01 verification and residual honesty |
| 20 | routing test | `c157796` | align mock with the independent-judge policy |
| 21 | **QG-02** | `1304ff4` | route generation-provider failures to graph error handling |
| 22 | docs | `b391028` | Update-132 QG-02 verification and residual honesty |
| 23 | docs | `142747d` | Update-133 authoritative problem ledger and next-session transparency |
| 24 | **QG-03A** | `80c2603` | verifier provider outage fails closed to human/safety without answer overwrite |
| 25 | docs | `e1d9ae5` | Update-134 QG-03A evidence and QG-03B residual |
| 26 | **QG-03B** | `5662ea7` | replace relevant contextual-header shells with same-logical-source content |
| 27 | docs | `3f6f652` | Update-135 QG-03B evidence and QG-04 routing |
| 28 | **QG-04 evidence** | `5f8bb78` | exact retained five-document E30 grading replay over shared fix `5662ea7` |
| 29 | docs | `62772d7` | Update-136 QG-04 shared-cause closure and remaining-gate honesty |
| 30 | **HYBRID-MEM env** | `3c90368` | explicitly preserve blank child reranker selection on Windows |
| 31 | docs | `4acdd32` | Update-137 HYBRID-MEM local closure and operational-gate honesty |
| 32 | docs | `1c758bd` | Update-138 reconciliation and next-session decision card |
| 33 | **VER-02** | `3a37fd2` | close lifecycle fault callable MyPy debt without runtime change |
| 34 | docs | `ed1c2fc` | Update-139 VER-02 evidence and retained verification limits |
| 35 | **9.1a** | `db65e37` | bound the process-local Redis fallback by TTL and 1024-entry LRU capacity |
| 36 | docs | `cc7abaa` | Update-140 9.1a evidence and the remaining §9 boundaries |
| 37 | **9.1b** | `eb8466e` | reconnect after Redis outage with serialized bounded exponential backoff |
| 38 | docs | `3528858` | Update-141 9.1b evidence and the separate namespace residual |
| 39 | docs | `a224659` | reconcile Actual Git and make next-session routing self-contained |
| 40 | **9.1c** | `893efe3` | bind response cache to tenant/index/prompt/model/query identity and fail closed when unresolved |
| 41 | docs | `65c82cc` | record 9.1c evidence and remove it from next-session routing |
| 42 | docs | resolve through Actual Git | Update-144 transparency reconciliation; do not add a follow-up solely for its self-SHA |
| 43 | **VER-05** | `4b0fba7` | require the exact intentional admin retention caller without permitting additional production callers |
| 44 | docs | resolve through Actual Git | Update-145 VER-05 closure; do not add a follow-up solely for its self-SHA |
| 45 | **9.2a** | `3fe6d6d` | expose bounded index publish/retention failure telemetry and a warning alert |
| 46 | docs | resolve through Actual Git | Update-146 9.2a closure; do not add a follow-up solely for its self-SHA |
| 47 | **9.2b** | `11e52f1` | expose bounded client-visible auto verification outcomes and a zero-tolerance alert |
| 48 | docs | resolve through Actual Git | Update-147 9.2b evidence plus VER-06 baseline-test disclosure |
| 49 | **VER-06** | `356a530` | align the agentic injection safety test with the tuple-returning `search_kb_docs` boundary |
| 50 | docs | resolve through Actual Git | Update-148 VER-06 closure; do not add a follow-up solely for its self-SHA |
| 51 | docs | resolve through Actual Git | Update-149 next-session transparency reconciliation; no implementation change |
| 52 | **9.2c** | `64f40b3` | expose bounded escalation inbox delivery outcomes and a warning alert at the shared initial/retry boundary |
| 53 | **9.2d** | `9817e89` | expose bounded pre-response redaction/refusal outcomes and a refusal warning alert without changing safety policy |
| 54 | **9.2e** | `5a2f696` | expose label-free orphan-work lifecycle state and a warning for work stuck beyond five minutes |
| 55 | **9.2f** | `344e174` | expose bounded confirmed tenant-ownership denials without identifiers or additional foreign lookups |
| 56 | docs | resolve through Actual Git | Update-154 next-session transparency reconciliation; no implementation change |
| 57 | **9.3a** | `1237f3c` | commit a portable seven-panel Grafana dashboard with bounded PromQL, zero-target thresholds, and offline contract tests |
| 58 | docs | resolve through Actual Git | Update-155 §9.3a closure; do not add a follow-up solely for its self-SHA |
| 59 | docs | resolve through Actual Git | Update-156 owner-requested post-dashboard transparency; records Actual Git, Grok terminal states, and control-artifact boundaries only |
| 60 | **9.4a** | `cea370b` | upgrade the docs site to Astro 7, retain supported Mermaid/whitespace behavior, and clear DEP-01 to zero audit findings |
| 61 | **9.5a** | `9c207b6` | make TraceService the injectable single owner of start/log/finish while preserving SQLite API and PII redaction |
| 62 | **VER-07** | `fd23317` | align the retention audit assertion with the existing tenant-aware endpoint contract |
| 63 | **9.5b** | `03057aa` | make EscalationService the durable ticket + inbox/outbox lifecycle owner |
| 64 | **9.5c1** | `84fbdf7` | make IngestionJobService the API-side durable job lifecycle owner |
| 65 | **9.5c2** | `890155a` | extend IngestionJobService ownership through worker lease and terminal CAS entry points |
| 66 | **9.5d1** | `aefcf20` | make PipelineRunner own capacity release and orphan-future handoff |
| 67 | **9.5d2** | `d865b06` | make PipelineRunner own sync executor submission, wall deadline, and timeout handoff |
| 68 | docs | `a0035bc` | record Update-164 PipelineRunner sync ownership before the canonical reconciliation |
| 69 | **9.5d3** | `c53f724` | make PipelineRunner own streaming graph/event submission, wait deadlines, and timeout handoff |
| 70 | docs | resolve through Actual Git | Update-166 §9.5d3 closure; do not add a follow-up solely for its self-SHA |
| 71 | docs | resolve through Actual Git | Update-167 VER-03 full-gate evidence and dirty-WIP routing; no implementation closure |

---

## 12. One-screen honesty

| Claim | Truth |
|-------|-------|
| Plan closed? | **No** |
| Production ready? | **No** |
| Local quality path deep? | **Yes** (4.1–4.8, 5.1–5.7, 6.1–6.7, 7.1–7.7, 8.x, DEP-01, QG-01, QG-02, QG-03A, QG-03B, QG-04) |
| Graph node SSE? | **Yes local** (4.7) |
| Provider token stream? | **Yes local** (4.8; parity on + stream-capable LLM) |
| OpenCode Zen profile? | **Yes local** (`faaa815`); trial/non-sensitive only; no live evidence |
| Lightweight GraceKelly smoke complete? | **Yes for the scoped smoke**: committed at `99c6be5`; local and one-call live acceptance green |
| Lightweight paid model | Exactly `claude-sonnet-5`; no silent fallback |
| Lightweight persistence | Successful SQLite row verified at `2026-08-09T15:03:21.124037+00:00`; provider failure regression persists no PASS row |
| Docker/WSL for this path? | **No — explicitly forbidden by owner** |
| Relevance ≠ quality/100? | **Yes local** (5.4) |
| Child report → §5 DoD wire? | **Yes local** (5.6; exact sidecar, fail-closed) |
| Current child producer emits all 7 metrics? | **Yes local** (5.7; complete/provenanced or release fails closed) |
| QG-01 vector parent expansion fixed? | **Yes local** (`c3ae4f4`); no claim for unrelated regressions or live recovery |
| QG-02 generation failure routing fixed? | **Yes local** (`1304ff4`); provider exceptions now enter graph error handling; no live recovery claim |
| QG-03 verifier outage routing fixed? | **Yes local** (`80c2603`); answer/context are preserved and route is human via safety/log; no live recovery is claimed |
| QG-03 contextual-header grading fixed? | **Yes local** (`5662ea7`); a relevant header shell resolves to same-logical-source content; no live E20 recovery is claimed |
| QG-04 E30 retained replay fixed? | **Yes local** (`5f8bb78` evidence over `5662ea7`); disconnect evidence reaches graded context; no live E30 recovery is claimed |
| Blank child reranker selection preserved? | **Yes local** (`3c90368`); explicit live-execute flag reaches a real Windows child as present and blank; no hybrid quality replay is claimed |
| `vectordb` lifecycle type debt closed? | **Yes local** (`3a37fd2`); package MyPy passed 10 sources under `--follow-imports=skip`; VER-01/full locked CI remain open |
| Redis fallback bounded? | **Yes local** (`db65e37`): TTL, locking, and 1024-entry LRU cap; live Redis evidence remains open |
| Redis reconnect bounded? | **Yes local** (`eb8466e`): serialized `1→2→4…≤30s` retry schedule resets after recovery; live Redis evidence remains open |
| Response cache namespace versioned? | **Yes local** (`893efe3`): tenant/index/prompt/model/query identity; unresolved identities fail closed; no live Redis evidence |
| Index lifecycle failures observable? | **Yes local** (`3fe6d6d`): bounded publish/retention counter and alert contract; no live metric scrape or alert-delivery evidence |
| Unverified auto-rate observable? | **Yes local** (`11e52f1`): bounded verified/unverified counter at sync/SSE delivery and zero-tolerance alert; no live scrape/alert-delivery evidence |
| Orphan work observable? | **Yes local** (`5a2f696`): label-free current-worker gauge spans all five shared capacity-transfer paths and alerts after five minutes; no live scrape/alert-delivery evidence |
| Tenant-denied access observable? | **Yes local** (`344e174`): ten confirmed session/ticket/KB-draft mismatch branches feed bounded resource labels without tenant/resource IDs; no live scrape/alert-delivery evidence |
| Seven-signal operations dashboard committed? | **Yes local** (`1237f3c`): portable `DS_PROMETHEUS`, seven non-overlapping panels, bounded/adaptive PromQL, and threshold contract tests; no live Grafana/import/scrape evidence |
| Astro 7 / DEP-01 closed? | **Yes local** (`cea370b`): Astro 7.2 / Starlight 0.41, supported unified Mermaid pipeline, 59-page build, and zero audit findings with no exceptions |
| Trace lifecycle has one owner? | **Yes local** (`9c207b6`): TraceService owns start/log/finish and redaction; existing SQLite module-level signatures remain compatible |
| Escalation lifecycle has one owner? | **Yes local** (`03057aa`): EscalationService owns durable ticket creation and inbox/outbox delivery lifecycle |
| Ingestion lifecycle has one owner? | **Yes local** (`84fbdf7`, `890155a`): IngestionJobService owns API durable jobs plus worker lease/terminal entry points; read-only list helpers remain outside the critical lifecycle owner |
| Pipeline capacity has one owner? | **Yes local** (`aefcf20`): PipelineRunner owns release and orphan-future completion handoff; router helpers are compatibility seams |
| Sync pipeline execution has one owner? | **Yes local** (`d865b06`): PipelineRunner owns executor submission, shielded wall deadline, and timeout capacity handoff for sync `/api/ask` |
| Streaming pipeline execution has one owner? | **Yes local** (`c53f724`): PipelineRunner owns graph/event executor submission, queue and shielded-future deadlines, and timeout capacity handoff; router keeps SSE semantics and compatibility seams |
| Agentic injection safety test current? | **Yes local** (`356a530`): mock follows `search_kb_docs(text, docs)` and the full safety/agentic band is green |
| Canonical restart capsule reconciled? | **Yes as of Update-171**; Actual Git remains first authority and `_NEXT_SESSION.md` remains stale/non-authoritative |
| All known open problems indexed? | **Yes in §1C as of Update-171**; Actual Git/new evidence overrides the snapshot |
| Live quality metrics ×3 evidence? | **No passing ×3 evidence**; one formal seed-42 child is valid but **FAILS** quality, and seeds 43–44 were not run |
| Human calibration DoD? | **No** (synthetic seed; readiness gate ready) |
| Formal §7.6 live provider evidence? | **No** (scaffold only); the separate lightweight smoke is not the formal gate |
| Parity default ON? | **No** (`STREAMING_RAG_PARITY` default false) |
| WIP / active writer? | Active writer/test process **none**; owned implementation/test WIP **none**; Update-171 handoff files may be dirty until their docs-only commit |
