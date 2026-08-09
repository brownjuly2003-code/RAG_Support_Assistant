# Session handoff

**Обновлено:** 2026-08-09 — **Update-131** (QG-01 vector parent-expansion
root cause fixed locally at `c3ae4f4`; no live retry).
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей
истории `AGENT_STATE.md`.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -12 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-131**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — **DoD**, не очередь галочек |

**Не использовать:** старые `START HERE` ниже Update-131; dirty
`BACKLOG.md` / `README.md` / audits; `_NEXT_SESSION.md` для routing
(это untracked stale pointer на Update-122, не SoT).

**Plan checkboxes:** не править casually. Local slice ≠ section closed ≠ release.

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **committed implementation** | `c3ae4f4` — QG-01 vector parent-expansion preservation |
| Prior implementations (recent) | `99c6be5` lightweight GraceKelly smoke · `faaa815` OpenCode Zen · `13bf255` **5.7** · `fb72dd2` **5.6** · `a901692` **5.5** · `4f95e18` **5.4** · `fc7f07b` **4.8** |
| Latest **committed docs before this Update** | `9a870f7` — Update-130 |
| This Update-131 docs SHA | Commit containing this file if present; otherwise owned docs WIP — resolve through Actual Git |
| Branch advisory | observed `master...origin/master [ahead 227]` at `c3ae4f4` before this docs edit — **refresh mandatory** |
| Active writer / WIP | active writer **none**; QG-01 code committed; only Update-131 docs WIP may remain |
| Locally complete (documented scopes) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.8** + **5.1–5.7** + **6.1–6.7** + **7.1–7.7** + **8.1–8.5** + **DEP-01** + **QG-01** |
| Off-plan local capability | OpenCode Zen `opencode-zen-free` @ `faaa815`; no plan checkbox closed |
| Full plan §1–§10 / production | **NOT** complete / **NOT** claimed |
| Plan status | **ACTIVE** |
| Next ordered | no new implementation slice selected; do not reopen QG-01; remaining seed-42 regressions require separate RCA slices |
| Gates | **no Docker/WSL**; no push / deploy / live multi-service / further paid provider·quality execute / migrate 019–023 without **fresh explicit opt-in** |
| Migrations on disk | **019–023** (not applied here) |

**Update-131 is docs-only:** it records committed QG-01 implementation
`c3ae4f4`. It changes no code, workflow, migration, or plan checkbox; it makes
no paid call and performs no push or deploy.

**Last known verification (not re-run this docs turn):**

| Slice | Last known gate |
|-------|-----------------|
| **QG-01 vector parent expansion** | TDD red **2 failed / 9 passed** → focused **11 passed**; independent parent/base/reranker **34 passed**; scoped Ruff + changed-file Mypy + diff clean; broader `vectordb` Mypy has one unchanged-file error at `index_lifecycle_faults.py:128` |
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
The other three regressions remain separate; no paid 3×20 rerun or live quality
recovery is claimed. A paid retry still requires fresh explicit opt-in.

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
5. Read ONLY top Update-130 in AGENT_STATE.md + this file §1–§12
6. Confirm there is no active writer; read §1B before touching live-quality code
7. Start QG-01 from the saved seed-42 sidecar; select one root cause only
8. Add one focused failing test, make the smallest local fix, verify, then STOP
```

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
| **9** cache / architecture / SLO | partial + **DEP-01 local** | Astro7 residual; cache/SLO |
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
| **DEP-01** | `f622d58` | docs-site npm audit high=0; exceptions → **2026-11-07** |

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

There is **no active implementation WIP**. QG-01 is locally closed at
`c3ae4f4`; do not reopen it or repeat its focused gates without a code or
environment change.

No new implementation slice was selected in Update-131. The remaining
seed-42 regressions are distinct and must not be collapsed into the QG-01
parent-expansion cause:

- `error-e20-filter-or-pump`: escalation/fallback path; original error node is
  absent from the sidecar;
- `error-e20-hose-kink`: retrieval context was present, but generation returned
  an internal-error answer;
- `error-e30`: empty generation context; intermediate grade outcome is absent.

If a later turn selects one, perform a fresh single-cause RCA and test-first
local slice. A new paid seed or 3×20 retry needs fresh owner opt-in; do not use
a live rerun as the diagnostic tool.

### Out without opt-in

- live multi-service / migrate / push / deploy / live provider·quality execute
- re-select through **8.5** / **4.1–4.8** / **5.1–5.7** / **6.1–6.7** /
  **7.1–7.7** / **DEP-01**
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

**Owned handoff paths:** `AGENT_STATE.md` and this file belong to Update-130.
Actual Git decides whether their docs-only commit has already closed the diff;
never stage the protected tracked files with them.

**Untracked (examples):**
`.grok-prompts/`, `.pytest_tmp*/`, presentations, `_NEXT_SESSION.md` (stale
untracked pointer; never routing authority),
`rag-remediation-plan-2026-08-03.md` (active plan — DoD source, no casual
checkbox edits), architecture HTML, etc. Preserve these unrelated artifacts.

`.tmp/live-quality-native-index-20260809/chroma` is retained diagnostic
evidence, not implementation WIP. It contains the compatible dimension-1024
collection used by seed 42; do not rebuild, stage, or delete it casually.

There is no owned untracked implementation WIP. The smoke script and test are
tracked in `99c6be5`; if they appear untracked, stop and reconcile Actual Git
instead of recreating or staging substitutes.

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
| 19 | docs | **this Update-131 commit, if present in Actual Git** | QG-01 verification and residual honesty |

---

## 12. One-screen honesty

| Claim | Truth |
|-------|-------|
| Plan closed? | **No** |
| Production ready? | **No** |
| Local quality path deep? | **Yes** (4.1–4.8, 5.1–5.7, 6.1–6.7, 7.1–7.7, 8.x, DEP-01, QG-01) |
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
| QG-01 vector parent expansion fixed? | **Yes local** (`c3ae4f4`); no claim for the other three regressions or live recovery |
| Live quality metrics ×3 evidence? | **No passing ×3 evidence**; one formal seed-42 child is valid but **FAILS** quality, and seeds 43–44 were not run |
| Human calibration DoD? | **No** (synthetic seed; readiness gate ready) |
| Formal §7.6 live provider evidence? | **No** (scaffold only); the separate lightweight smoke is not the formal gate |
| Parity default ON? | **No** (`STREAMING_RAG_PARITY` default false) |
| WIP / active writer? | Implementation WIP **none** / active writer **none**; only Update-131 docs WIP may remain — check Actual Git |
