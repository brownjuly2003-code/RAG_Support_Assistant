# Session handoff

**Обновлено:** 2026-08-08 — **Update-119** (docs-only full transparency after  
**4.7** @ `6b91a35` + docs Update-118 `b89f197`).  
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей  
истории `AGENT_STATE.md`.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -12 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-119**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — **DoD**, не очередь галочек |

**Не использовать:** старые `✅ START HERE` ниже Update-119; dirty  
`BACKLOG.md` / `README.md` / audits; `_NEXT_SESSION.md` как единственный SoT  
(это pointer only).

**Plan checkboxes:** не править casually. Local slice ≠ section closed ≠ release.

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **implementation** | `6b91a35` — **4.7** graph node status SSE |
| Prior implementations | `11acfec` **4.6** · `c707c46` **6.7** · `69c6fdf` **6.6** · `47e255a` **7.7** |
| Latest **docs before this Update** | `b89f197` — Update-118 |
| This Update-119 docs SHA | **unknown in-file** → `git log -3 --oneline` после коммита |
| Branch advisory | `master...origin/master [ahead 210]` before this docs commit — **refresh mandatory** |
| Active writer / WIP | **none** |
| Locally complete (documented scopes) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.7** + **5.1–5.3** + **6.1–6.7** + **7.1–7.7** + **8.1–8.5** + **DEP-01** |
| Full plan §1–§10 / production | **NOT** complete / **NOT** claimed |
| Plan status | **ACTIVE** |
| Next ordered (default) | provider token residual **or** human sample reissue **or** live execute (opt-in) **or** Astro7 / parity-default product decision |
| Gates | **no** push / deploy / live multi-service / live provider execute / migrate 019–023 without **explicit opt-in** |

**This Update-119 is docs-only:** no code/test/plan-checkbox change; project  
tests **not** re-run here. Implementation state unchanged after `6b91a35`.

**Last known verification (4.7; not re-run this docs turn):** graph node SSE +  
streaming parity **12 passed**; Ruff clean. Full suite / live / push **not**  
claimed.

### Dataset snapshot (7.7)

| Slice | Count |
|-------|------:|
| multi_tenant | 3 (acme/beta/gamma) |
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
5. Read ONLY top Update-119 in AGENT_STATE.md + this file §1–§11
6. Default work: ONE of next picks below. Announce: slice 1/1
7. Tests-first → proportional gate → local commit only (no push)
8. Optional handoff refresh; STOP after one slice
```

**Not authorized without opt-in:** push, deploy, live PostgreSQL/Redis/Celery/  
Chroma, live provider execute with secrets, `alembic upgrade` (incl. **019–023**),  
destructive Git, production claims, bulk plan checkbox edits.

---

## 3. Honest residual (plan sections)

| Plan § | Local | Residual / blockers |
|--------|-------|---------------------|
| **1** live multi-tenant / backup / RPO | partial chart/docs | **opt-in live** — Gate A open |
| **2** index lifecycle | **2.1–2.6g** local residual closed | live PG/Redis/Celery/Chroma + migrate drills |
| **3** execution / session / budget | **3.1a–3.1i** local | multi-replica durable session version |
| **4** pipeline + escalation | **4.1–4.7** local | provider token stream residual; parity default **off** |
| **5** grounding fail-closed | **5.1–5.3** local | live metrics DoD ×3; relevance≠quality residual |
| **6** judge / safety / agentic | **6.1–6.7** local | production human dual-annotator sample residual |
| **7** eval gate | **7.1–7.7** local | live execute with secrets; mock≠release; optional more depth |
| **8** widget / edge | **8.1–8.5** local | live IdP; `WIDGET_ALLOWED_ORIGINS` in prod |
| **9** cache / architecture / SLO | partial + **DEP-01 local** | Astro7 residual; cache/SLO |
| **10** final verification | not started | after 1–9 + opt-in evidence |

**Release / production: NOT claimable** until §1 live + §5 live quality +  
§6–7 residual + §8 residual + §10.

Full matrix: [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md).

---

## 4. Implementation ledgers (impl SHAs only)

### §4 pipeline + escalation (recent focus)

| Slice | SHA | Surface |
|-------|-----|---------|
| **4.1** | `eaf41f3` | single terminal/history when parity succeeds |
| **4.2** | `f1c846e` | graph-only generation when parity on |
| **4.3** | `ad5e435` | durable idempotent escalation |
| **4.4** | `0371971` | auto human-route on normal ask |
| **4.5** | `6453530` | outbox retry without second ticket |
| **4.6** | `11acfec` | Celery beat + CLI outbox schedule |
| **4.7** | **`6b91a35`** | real LangGraph node status SSE on parity path |

### §7 eval gate

| Slice | SHA | Surface |
|-------|-----|---------|
| **7.1** | `94ac64e` | infra/skip/empty → FAIL |
| **7.2** | `25788ee` | mock → `SMOKE_PASS` only; `--release-gate` needs evidence |
| **7.3** | `0d34be2` | merge-base baseline artifact load/write/require |
| **7.4** | `8f4269f` | required slices + min_context_recall; 47 cases |
| **7.5** | `4eceed3` | CI write + upload + require-wire of baseline artifact |
| **7.6** | `d1ae4d6` | scheduled live provider gate scaffold (opt-in) |
| **7.7** | **`47e255a`** | min 3 cases/required slice; **67** total cases |

### §6 judge / safety / agentic

| Slice | SHA | Surface |
|-------|-----|---------|
| **6.1** | `b3494a0` | unmeasured agentic; never fixed 80/85/90 |
| **6.2** | `d0317e9` | pre-response PII + prompt-injection |
| **6.3** | `d6e3a55` | independent judge fail-closed |
| **6.4** | `a7cefc3` | routing calibration artifact (bootstrap-defaults) |
| **6.5** | `431893c` | measured grounding when agentic has KB docs |
| **6.6** | `69c6fdf` | LLM evaluate wire on KB agentic terminals |
| **6.7** | **`c707c46`** | human readiness gate + recalibrate CLI |

### §8 widget / edge

| Slice | SHA | Surface |
|-------|-----|---------|
| **8.1** | `0bee13e` | widget bootstrap JWT, origins, frame-ancestors |
| **8.2** | `756562e` | ASGI received-byte body limits; upload stream/atomic place |
| **8.3** | `13a9a5b` | OIDC email_verified; (issuer, subject); no rebind |
| **8.4** | `68a30b2` | production placeholders rejected; no dev-admin |
| **8.5** | `4d6be52` | Playwright cross-origin E2E; iframe Origin=API |

### DEP-01 / §5 / §3 / §2

| Band | Ends at SHA | Note |
|------|-------------|------|
| DEP-01 | `f622d58` | docs-site high=0; exceptions → **2026-11-07** |
| §5 | `1cdecb2` **5.3** | grader fail-closed |
| §3 | `fe2f0aa` **3.1i** | runtime/session/budget band |
| §2 | `f347feb` **2.6g** | fault-injection residual closed local |

---

## 5. Contracts (recent complete slices — read before touching)

### 4.7 @ `6b91a35`

- `agent/graph_stream.py` — `stream_graph_node_events` (LangGraph updates+values)
- `iter_qa_pipeline_events` + `ConversationSession.iter_ask_events`
- Parity SSE prefers events path: `status {node, source: graph}`
- Tokens still UX chunks of finished graph answer:  
  `token_source=graph_answer_chunks` (not true provider token stream)
- `result.events_source=graph|ask`; `result.graph_nodes` listed
- No second generation; test doubles with only `ask()` keep §4.2 fallback
- Residual: provider token streaming through generate; parity default **off**

### 4.6 @ `11acfec`

- Task `tasks.outbox_retry_task.retry_escalation_outbox`
- Beat `escalation-outbox-retry` (default 300s); env `RAG_OUTBOX_RETRY_*`
- CLI `scripts/outbox_retry.py`; Compose `worker-beat` (schedule-only)
- Single ingest `worker` concurrency unchanged
- Never creates second tickets (§4.5 API)

### 6.7 @ `c707c46`

- `assess_human_calibration_readiness` fail-closed floors
- synthetic `label_source` cannot claim `source=human-labelled`
- `reissue_calibration_from_labels` recomputes agreement/cost
- CLI `scripts/recalibrate_routing.py` readiness/reissue/`--require-human`
- Seed remains synthetic; production human sample still residual

### 6.6 @ `69c6fdf`

- `agent/agentic_evaluate.py` — independent-judge self-eval for agentic
- Measured `quality_source=llm` only on parseable judge score
- Fail-closed quality on judge miss; §6.5 grounding preserved
- Flag `RAG_AGENTIC_QUALITY_EVAL` (default ON)

### 7.7 @ `47e255a`

- `MIN_CASES_PER_REQUIRED_SLICE = 3`; dataset **67** cases
- Every required slice ≥3

### 7.6 / 6.5 / 6.4 / 8.x / DEP-01 (one-liners)

- **7.6** live provider gate scaffold (opt-in; never silent PASS)
- **6.5** KB agentic measured grounding; auto needs quality too
- **6.4** calibration artifact bootstrap-defaults (not full human DoD)
- **8.5–8.1** widget → Playwright E2E; secrets; OIDC; body limits
- **DEP-01** docs-site high=0; exceptions → **2026-11-07**

---

## 6. Module owners (do not reopen without conflict)

| Path | Slices | Role |
|------|--------|------|
| `agent/graph_stream.py` | **4.7** | LangGraph node event stream |
| `agent/graph.py` | **4.7** (+ many) | `iter_qa_pipeline_events`, `iter_ask_events` |
| `api/routers/conversation.py` | **4.1–4.2 / 4.7** | SSE parity + node status |
| `tasks/outbox_retry_task.py` | **4.6** | Celery outbox retry task |
| `scripts/outbox_retry.py` | **4.6** | operator/cron CLI |
| `tasks/celery_app.py` | **4.6** | beat schedule registration |
| `services/escalation.py` | **4.3–4.5** | durable escalation + retry API |
| `evaluation/curated_cases.jsonl` | **7.4 / 7.7** | curated corpus (**67**) |
| `scripts/regression_eval.py` | **7.1–7.7** | eval gate |
| `scripts/live_provider_gate.py` | **7.6** | live gate scaffold |
| `agent/agentic_evaluate.py` | **6.6** | agentic LLM evaluate |
| `agent/agentic_measure.py` | **6.5** | measured agentic KB gate |
| `agent/calibration.py` | **6.4 / 6.7** | routing calibration + human readiness |
| `scripts/recalibrate_routing.py` | **6.7** | recalibrate CLI |
| `evaluation/calibration/` | **6.4 / 6.7** | seed artifact + labelled_routes |
| `agent/judge_policy.py` | **6.3** | independent judge |
| `agent/response_safety.py` | **6.2** | PII / injection |
| `agent/grounding.py` | **5.1–5.2** | factuality / citations |
| `docs-site/*` | **DEP-01** | npm audit posture |
| `api/routers/widget.py` | **8.1 / 8.5** | widget bootstrap |
| job-object / index stack | 2.1–2.6g | **do not re-select** |

---

## 7. Key invariants (do not regress)

1. Failed jobs with `source_path` match → retained; not auto-delete  
2. LLM budget exhaust → `route=human` / never `auto`  
3. Deadline fail-closed at provider/retrieve/tool/rerank  
4. Stream parity on → single graph generation + single terminal/history  
4b. Outbox failed deliveries retried via beat/CLI without second ticket (§4.6)  
4c. Parity SSE status events use real LangGraph node names (§4.7)  
4d. Answer tokens on parity path are graph-answer chunks, not a second LLM  
5. Escalation: no «передан оператору» without durable ticket  
6. No fake factuality 100 on skip/disabled/no-context  
7. Claims need cited `[N]` for auto  
8. Empty graded after grade ≠ silent restore of raw context  
9. Agentic unmeasured ≠ `route=auto` and ≠ fake quality 80/85/90  
10. PII in terminal answer redacted; injection → refuse + human  
11. Judge unavailable/error/parse ≠ auto; ≠ silent score 50 + `quality_source=llm`  
12. Eval: infra/skip/zero-effective → gate FAIL  
13. Mock expected-copy → `SMOKE_PASS` only; never release `PASS`  
14. Widget: empty allowlist → no bootstrap; framing only via allowlisted ancestors  
15. Body limits: trust **received** ASGI bytes, not Content-Length alone  
16. Upload: stream to temp + exclusive immutable place + atomic flat rename  
17. OIDC: verified email + (issuer, subject); no silent rebind  
18. Production: no placeholder secrets; no `ALLOW_DEV_ADMIN_LOGIN`  
19. Widget iframe: API Origin allowed; empty/disallowed parent fail-closed (E2E)  
20. Regression: baseline from artifact for honest release compare  
21. Dataset: required slices covered; `min_context_recall` enforceable  
22. Docs-site: high/critical fail closed; residual only with dated exceptions  
23. CI: write + publish + require-load baseline artifact (smoke; mock≠release)  
24. Routing floors from calibration artifact (bootstrap ok; full human residual)  
25. Agentic + KB docs → measured grounding; auto needs measured quality too  
26. Live provider gate is separate from PR mock smoke; opt-in only; never silent PASS  
27. Required dataset slices need ≥3 cases each (depth floor §7.7)  
28. Agentic KB terminals run LLM evaluate when flag ON; fail-closed quality (§6.6)  
29. Synthetic calibration labels never upgrade to human-labelled without readiness (§6.7)  
30. Single ingest Celery worker concurrency; beat is schedule-only (§4.6)  

---

## 8. Verification recipes (last known green; re-run when coding)

### §4.7 band (latest impl)

```powershell
python -m pytest tests/test_graph_node_sse.py tests/test_streaming_rag_parity.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check agent/graph_stream.py agent/graph.py api/routers/conversation.py tests/test_graph_node_sse.py
```

### §4.6 band

```powershell
python -m pytest tests/test_outbox_retry_schedule.py tests/test_escalation_outbox_retry.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check tasks/outbox_retry_task.py tasks/celery_app.py scripts/outbox_retry.py
python scripts/outbox_retry.py --dry-run-config
```

### §6.7 band

```powershell
python -m pytest tests/test_calibration_artifact.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check agent/calibration.py scripts/recalibrate_routing.py tests/test_calibration_artifact.py
python scripts/recalibrate_routing.py --mode readiness --labels evaluation/calibration/labelled_routes.jsonl
```

### §6.6 band

```powershell
python -m pytest tests/test_agentic_evaluate.py tests/test_agentic_measure.py tests/test_agent_tools.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check agent/agentic_evaluate.py agent/agentic_measure.py agent/graph.py config/settings.py tests/test_agentic_evaluate.py
```

### §7.7 / §7.6 band

```powershell
python -m pytest tests/test_curated_dataset_expansion.py -q -p no:cacheprovider -p no:schemathesis
python -m pytest tests/test_live_provider_gate.py tests/test_github_workflows.py -q -p no:cacheprovider -p no:schemathesis
python scripts/live_provider_gate.py --mode readiness --write-report reports/regression/live-provider-gate-readiness.json
```

Full suite / live / migrate — **not** the default gate for a single slice.

---

## 9. Next named candidate (not started)

**Default picks (one only):**

1. **True provider token streaming** through generate (optional §4 residual;  
   today tokens = finished-answer UX chunks)  
2. **Collect real dual-annotator human sample** then  
   `python scripts/recalibrate_routing.py --mode reissue --require-human --write`  
3. **Live provider execute** with secrets + `RAG_LIVE_PROVIDER_GATE` +  
   `--execute` (**explicit opt-in only**)  
4. **Astro 7** major **or** product decision to default  
   `STREAMING_RAG_PARITY=true`  

### Out without opt-in

- live multi-service / migrate / push / deploy / live provider execute  
- re-select through **8.5** / **4.1–4.7** / **6.1–6.7** / **7.1–7.7** / **DEP-01**  
- OIDC live IdP drill; full browser matrix expansion  
- bulk plan checkbox edits; production claims  

### Alternates (only if user prioritizes)

- live §1 / migrate 019–023 (**explicit opt-in only**)  
- multi-replica durable session version (§3 residual)  
- further curated corpus depth beyond 3/slice  

---

## 10. Protected dirty / untracked (do not touch)

**Dirty tracked (leave alone):**  
`BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`

**Untracked (examples):**  
`.grok-prompts/`, `.pytest_tmp*/`, presentations, `_NEXT_SESSION.md` (pointer),  
`rag-remediation-plan-2026-08-03.md` (active plan — DoD source, no casual  
checkbox edits), architecture HTML, etc.

---

## 11. Cycle budget (workspace rule)

- One user turn → **one named atomic implementation slice** + verify + docs  
- At most 3 delegated runs (impl / QA-batch / docs); one QA follow-up  
- No push/deploy/live without opt-in  
- After hard-stop / cycle complaint: stop; cancel active writer once if needed  

---

## 12. One-screen honesty

| Claim | Truth |
|-------|-------|
| Plan closed? | **No** |
| Production ready? | **No** |
| Local quality path deep? | **Yes** (4.1–4.7, 5.x, 6.1–6.7, 7.1–7.7, 8.x, DEP-01) |
| Human calibration DoD? | **No** (synthetic seed; readiness gate ready) |
| Live provider evidence? | **No** (scaffold only) |
| Graph node SSE? | **Yes local** (4.7) |
| Provider token stream? | **No** (chunks of finished answer) |
| Parity default ON? | **No** (`STREAMING_RAG_PARITY` default false) |
