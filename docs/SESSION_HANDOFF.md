# Session handoff

**Обновлено:** 2026-08-09 — **Update-125** (docs-only full transparency after
OpenCode Zen provider integration @ `faaa815`; latest prior docs Update-124
`336b08e`).
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей
истории `AGENT_STATE.md`.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -12 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-125**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — **DoD**, не очередь галочек |

**Не использовать:** старые `✅ START HERE` ниже Update-125; dirty
`BACKLOG.md` / `README.md` / audits; `_NEXT_SESSION.md` для routing
(это untracked stale pointer на Update-122, не SoT).

**Plan checkboxes:** не править casually. Local slice ≠ section closed ≠ release.

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **implementation** | `faaa815` — OpenCode Zen trial/free provider integration |
| Prior implementations (recent) | `13bf255` **5.7** · `fb72dd2` **5.6** · `a901692` **5.5** · `4f95e18` **5.4** · `fc7f07b` **4.8** |
| Latest **docs before this Update** | `336b08e` — Update-124 |
| This Update-125 docs SHA | **unknown in-file** → `git log -3 --oneline` после коммита |
| Branch advisory | last observed `master...origin/master [ahead 222]` before this docs commit — **refresh mandatory** |
| Active writer / WIP | **none** |
| Locally complete (documented scopes) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.8** + **5.1–5.7** + **6.1–6.7** + **7.1–7.7** + **8.1–8.5** + **DEP-01** |
| Off-plan local capability | OpenCode Zen `opencode-zen-free` @ `faaa815`; no plan checkbox closed |
| Full plan §1–§10 / production | **NOT** complete / **NOT** claimed |
| Plan status | **ACTIVE** |
| Next ordered | **No ungated local plan default**; choose opt-in live ×3 evidence, human sample, or Astro7/parity decision |
| Gates | **no** push / deploy / live multi-service / live provider·quality execute / migrate 019–023 without **explicit opt-in** |
| Migrations on disk | **019–023** (not applied here) |

**This Update-125 is docs-only:** no code/test/workflow/plan-checkbox change;
project tests are not re-run in this docs turn. Implementation state remains
`faaa815`; latest prior docs remain `336b08e`.

**Last known verification (not re-run this docs turn):**

| Slice | Last known gate |
|-------|-----------------|
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

Full suite / live multi-service / migrate / push / deploy / live provider
or quality execute **not** run / **not** claimed.

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
5. Read ONLY top Update-125 in AGENT_STATE.md + this file §1–§12
6. Default work: ONE of next picks below. Announce: slice 1/1
7. Tests-first → proportional gate → local commit only (no push)
8. Optional handoff refresh; STOP after one slice
```

**Not authorized without opt-in:** push, deploy, live PostgreSQL/Redis/Celery/
Chroma, live provider/quality execute with secrets, `alembic upgrade`
(incl. **019–023**), destructive Git, production claims, bulk plan checkbox edits.

---

## 3. Honest residual (plan sections)

| Plan § | Local | Residual / blockers |
|--------|-------|---------------------|
| **1** live multi-tenant / backup / RPO | partial chart/docs | **opt-in live** — Gate A open |
| **2** index lifecycle | **2.1–2.6g** local residual closed | live PG/Redis/Celery/Chroma + migrate drills |
| **3** execution / session / budget | **3.1a–3.1i** local | multi-replica durable session (**DEFER** without SLA; design exists) |
| **4** pipeline + escalation | **4.1–4.8** local | parity default still **off** (product decision) |
| **5** grounding fail-closed | **5.1–5.7** local | **actual** live ×3 evidence still open |
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

---

## 4. Implementation ledgers (impl SHAs only)

### Provider capability outside plan order

| Slice | SHA | Surface |
|-------|-----|---------|
| OpenCode Zen trial/free | `faaa815` | fixed free model/profile, endpoint identity, fail-fast key, live-gate/workflow/Helm plumbing, safety docs |

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

## 7. Next named candidate (not started)

There is **no ungated default local-only plan candidate** after 5.7. The
off-plan Zen integration is complete locally. Choose one only with the required
authority:

1. Run provider/quality evidence ×3 with secrets + explicit opt-in +
   `--execute`; retain exact sidecars and the aggregate report.
2. Collect a real dual-annotator human sample, then run recalibration with
   `--require-human --write`.
3. Astro 7 major or product decision to default `STREAMING_RAG_PARITY=true`.

### Out without opt-in

- live multi-service / migrate / push / deploy / live provider·quality execute
- re-select through **8.5** / **4.1–4.8** / **5.1–5.7** / **6.1–6.7** /
  **7.1–7.7** / **DEP-01**
- OIDC live IdP drill; bulk plan checkbox edits; production claims
- multi-replica impl without SLA (design DEFER)

### Further alternates (only if user prioritizes)

- live §1 / migrate 019–023 (**explicit opt-in only**)
- further curated corpus depth beyond 3/slice
- multi-replica durable session (**only with explicit SLA/product ask**)

---

## 8. Protected dirty / untracked (do not touch)

**Dirty tracked (leave alone):**
`BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`

**Untracked (examples):**
`.grok-prompts/`, `.pytest_tmp*/`, presentations, `_NEXT_SESSION.md` (stale
untracked pointer; never routing authority),
`rag-remediation-plan-2026-08-03.md` (active plan — DoD source, no casual
checkbox edits), architecture HTML, etc.

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
| 12 | docs | **this** | Update-125 full transparency after Zen integration |

---

## 12. One-screen honesty

| Claim | Truth |
|-------|-------|
| Plan closed? | **No** |
| Production ready? | **No** |
| Local quality path deep? | **Yes** (4.1–4.8, 5.1–5.7, 6.1–6.7, 7.1–7.7, 8.x, DEP-01) |
| Graph node SSE? | **Yes local** (4.7) |
| Provider token stream? | **Yes local** (4.8; parity on + stream-capable LLM) |
| OpenCode Zen profile? | **Yes local** (`faaa815`); trial/non-sensitive only; no live evidence |
| Relevance ≠ quality/100? | **Yes local** (5.4) |
| Child report → §5 DoD wire? | **Yes local** (5.6; exact sidecar, fail-closed) |
| Current child producer emits all 7 metrics? | **Yes local** (5.7; complete/provenanced or release fails closed) |
| Live quality metrics ×3 evidence? | **No** — no paid/live runs claimed |
| Human calibration DoD? | **No** (synthetic seed; readiness gate ready) |
| Live provider evidence? | **No** (7.6 scaffold only) |
| Parity default ON? | **No** (`STREAMING_RAG_PARITY` default false) |
| WIP / active writer? | **None** |
