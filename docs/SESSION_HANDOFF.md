# Session handoff

**Обновлено:** 2026-08-08 — **Update-120** after **4.8** @ `fc7f07b`  
(provider token streaming through generate).  
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей  
истории `AGENT_STATE.md`.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -12 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-120**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — **DoD**, не очередь галочек |

**Не использовать:** старые `✅ START HERE` ниже Update-120; dirty  
`BACKLOG.md` / `README.md` / audits; `_NEXT_SESSION.md` как единственный SoT  
(это pointer only).

**Plan checkboxes:** не править casually. Local slice ≠ section closed ≠ release.

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **implementation** | `fc7f07b` — **4.8** provider token stream through generate |
| Prior implementations | `6b91a35` **4.7** · `11acfec` **4.6** · `c707c46` **6.7** · `69c6fdf` **6.6** |
| Latest **docs before this Update** | `18fbd18` — Update-119 |
| This Update-120 docs SHA | **unknown in-file** → `git log -3 --oneline` после коммита |
| Branch advisory | `master...origin/master [ahead 212]` before this docs commit — **refresh mandatory** |
| Active writer / WIP | **none** |
| Locally complete (documented scopes) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.8** + **5.1–5.3** + **6.1–6.7** + **7.1–7.7** + **8.1–8.5** + **DEP-01** |
| Full plan §1–§10 / production | **NOT** complete / **NOT** claimed |
| Plan status | **ACTIVE** |
| Next ordered (default) | human sample reissue **or** live execute (opt-in) **or** Astro7 / parity-default product decision |
| Gates | **no** push / deploy / live multi-service / live provider execute / migrate 019–023 without **explicit opt-in** |

**Last known verification (4.8):** provider token + graph node SSE + streaming  
parity **16 passed**; Ruff clean. Full suite / live / push **not** claimed.

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
5. Read ONLY top Update-120 in AGENT_STATE.md + this file §1–§11
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
| **4** pipeline + escalation | **4.1–4.8** local | parity default still **off** (product) |
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
| **4.7** | `6b91a35` | real LangGraph node status SSE on parity path |
| **4.8** | **`fc7f07b`** | provider token stream through generate |

### §7 eval gate

| Slice | SHA | Surface |
|-------|-----|---------|
| **7.1** | `94ac64e` | infra/skip/empty → FAIL |
| **7.2** | `25788ee` | mock → `SMOKE_PASS` only; `--release-gate` needs evidence |
| **7.3** | `0d34be2` | merge-base baseline artifact load/write/require |
| **7.4** | `8f4269f` | curated slices (47) |
| **7.5** | `4eceed3` | CI write + upload + require-wire of baseline artifact |
| **7.6** | `d1ae4d6` | scheduled live provider gate scaffold |
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
| **8.1–8.5** | `0bee13e`…`4d6be52` | widget → Playwright E2E |
| **DEP-01** | **`f622d58`** | docs-site high=0 audit gate |

---

## 5. Contracts (recent complete slices — read before touching)

### 4.8 @ `fc7f07b`

- `agent/graph_stream.py` — `custom` stream mode + `provider_token_stream_enabled`
- Generate node streams via `generate_stream` / `.stream` when flag on;
  writes tokens with LangGraph `get_stream_writer`
- `token_source=provider_generate` on live tokens; SSE relays them
- No post-hoc `graph_answer_chunks` when provider tokens already seen
- Fallback UX chunks when stream unavailable
- `result.token_source` reported; single generation; parity default **off**
- Residual after 4.8: product decision to flip `STREAMING_RAG_PARITY` default

### 4.7 @ `6b91a35`

- `stream_graph_node_events` (LangGraph updates+values)
- `iter_qa_pipeline_events` + `ConversationSession.iter_ask_events`
- Parity SSE: `status {node, source: graph}`
- (Tokens upgraded in **4.8**)

### 4.6 @ `11acfec`

- Task `tasks.outbox_retry_task.retry_escalation_outbox`
- Beat `escalation-outbox-retry` (default 300s); env `RAG_OUTBOX_RETRY_*`
- CLI `scripts/outbox_retry.py`; Compose `worker-beat` (schedule-only)

### 6.7 @ `c707c46`

- `assess_human_calibration_readiness` fail-closed floors
- synthetic `label_source` cannot claim `source=human-labelled`
- CLI: `scripts/recalibrate_routing.py` readiness/reissue/`--require-human`
- Seed remains synthetic; production human sample still residual

---

## 6. Migrations on disk (not applied)

**019–023** — require explicit opt-in to `alembic upgrade`.

---

## 7. Focused verification commands (last slice)

```powershell
python -m pytest tests/test_provider_token_stream.py tests/test_graph_node_sse.py tests/test_streaming_rag_parity.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check agent/graph_stream.py agent/graph.py api/routers/conversation.py tests/test_provider_token_stream.py
```

Full suite / live / migrate — **not** the default gate for a single slice.

---

## 8. Next named candidate (not started)

**Default picks (one only):**

1. **Collect real dual-annotator human sample** then  
   `python scripts/recalibrate_routing.py --mode reissue --require-human --write`  
2. **Live provider execute** with secrets + `RAG_LIVE_PROVIDER_GATE` +  
   `--execute` (**explicit opt-in only**)  
3. **Astro 7** major **or** product decision to default  
   `STREAMING_RAG_PARITY=true`  

### Out without opt-in

- live multi-service / migrate / push / deploy / live provider execute  
- re-select through **8.5** / **4.1–4.8** / **6.1–6.7** / **7.1–7.7** / **DEP-01**  
- OIDC live IdP drill; full browser matrix expansion  
- bulk plan checkbox edits; production claims  

### Alternates (only if user prioritizes)

- live §1 / migrate 019–023 (**explicit opt-in only**)  
- multi-replica durable session version (§3 residual)  
- further curated corpus depth beyond 3/slice  

---

## 9. Protected dirty / untracked (do not touch)

**Dirty tracked (leave alone):**  
`BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`

**Untracked (examples):**  
`.grok-prompts/`, `.pytest_tmp*/`, presentations, `_NEXT_SESSION.md` (pointer),  
`rag-remediation-plan-2026-08-03.md` (active plan — DoD source, no casual  
checkbox edits), architecture HTML, etc.

---

## 10. Cycle budget (workspace rule)

- One user turn → **one named atomic implementation slice** + verify + docs  
- At most 3 delegated runs (impl / QA-batch / docs); one QA follow-up  
- No push/deploy/live without opt-in  
- After hard-stop / cycle complaint: stop; cancel active writer once if needed  

---

## 11. One-screen honesty

| Claim | Truth |
|-------|-------|
| Plan closed? | **No** |
| Production ready? | **No** |
| Local quality path deep? | **Yes** (4.1–4.8, 5.x, 6.1–6.7, 7.1–7.7, 8.x, DEP-01) |
| Human calibration DoD? | **No** (synthetic seed; readiness gate ready) |
| Live provider evidence? | **No** (scaffold only) |
| Graph node SSE? | **Yes local** (4.7) |
| Provider token stream? | **Yes local** (4.8; when LLM supports stream + parity on) |
| Parity default ON? | **No** (`STREAMING_RAG_PARITY` default false) |
