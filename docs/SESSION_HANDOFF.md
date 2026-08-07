# Session handoff

**Обновлено:** 2026-08-07 (Update-86 docs-only transparency after **4.3** @
`ad5e435` + Update-85 docs `82d9a17`). Next ordered candidate **4.4**.

**Назначение:** самодостаточный next-session handoff.  
**Routing:** только верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-86**). Любые старые `✅ START HERE` ниже — **archival**.  
**Plan (untracked/protected):**
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)
— **не** править checkboxes casually.

---

## Нулевая неоднозначность (сканируй первой)

| Факт | Значение |
|------|----------|
| Latest **implementation** | `ad5e435` — **4.3** durable idempotent escalation |
| Latest **docs** before this Update | `82d9a17` — Update-85 |
| This Update-86 docs SHA | **unknown in-file** → `git log -5 --oneline` |
| Branch advisory | was `master...origin/master [ahead 150]` — **refresh mandatory** |
| Active writer / WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.3** |
| Full plan §2 / §3 / §4 | **NOT** complete |
| Project / release / production | **NOT** claimed |
| Next ordered | **4.4** auto-escalate terminal human/error **or** outbox retry worker |
| Gates | no push / deploy / live multi-service / migrate 019–023 without **explicit opt-in** |

**Transparency-only Update-86:** no code/test/plan-checkbox change; project
tests **not** re-run here. Implementation state unchanged after `ad5e435`.

**Last known verification (4.3; not re-run this docs turn):** focused **21
passed** (`test_escalation_service` + pipeline exception + graph error + agent
tools); Ruff clean on scoped paths. Full suite / live drills **not** run.

**Key ingestion invariant (unchanged):** failed jobs with `source_path`-matched
job-objects → `retained_after_failed_transition` (not GC);
`auto_delete_eligible` always `False`.

---

## Быстрый старт следующей сессии

1. Cycle-guard / one-slice rule: **one named atomic slice per user turn**.
2. `cd D:\RAG_Support_Assistant`
3. `git status --short --branch` and `git log -8 --oneline` (**actual Git wins**).
4. Read **only** top **Update-86** in `AGENT_STATE.md` + this capsule.
5. Default work: **4.4** (below). Announce `slice 1/1`.
6. Tests-first → proportional gate → local commit only (no push).
7. Optional handoff refresh; **stop/yield** after one slice.

**Not authorized without explicit opt-in:** push, deploy, live
PostgreSQL/Redis/Celery/Chroma, `alembic upgrade` (incl. **019–023**),
destructive Git, production claims.

---

## Plan §2 map (honest — live DoD open)

| Plan §2 bullet | Local work | Residual |
|----------------|------------|----------|
| inventory under lock | 2.1 + related | live DoD open |
| bounded retention | 2.2, 2.3f–2.3i | live DoD open |
| operator surface | index 2.3b–2.3i; job-objects 2.4i–2.5a | no job-object delete execute HTTP |
| immutable originals + lifecycle | 2.4a–2.5b | no real FS delete / age-budget |
| fault injection expand | **2.6a–2.6g** | **local residual closed** |
| live PG/Redis/Celery/Chroma + migrations | not started | **opt-in**; migrations **019–023** on disk |

Last §2 fault-injection impl: `f347feb` (**2.6g**). Do **not** re-select 2.x.

---

## Plan §3 map (honest)

| Plan §3 bullet | Local slices | Residual |
|----------------|--------------|----------|
| shared executor + capacity until work done | **3.1a** + **3.1f** | — documented |
| cooperative deadline provider/retriever/reranker/tools | **3.1b** + **3.1f–h** | cooperative only (no mid-call kill) |
| session serialize / optimistic version + sticky | **3.1c** + **3.1i** | multi-replica durable version store; optional HTTP If-Match |
| max_tokens/temperature per LLM role | **3.1d** | — |
| per-request LLM call/token budget | **3.1e** + **3.1f** | — |

### §3 ledger (impl SHA)

| Slice | SHA | What |
|-------|-----|------|
| 3.1a | `a21f364` | shared request executor; `/api/ask` capacity hold |
| 3.1b | `76179d5` | ContextVar deadline; provider entry fail-closed |
| 3.1c | `d9ba87e` | per-session turn lock + epoch |
| 3.1d | `48c2381` | per-role temperature/max_tokens |
| 3.1e | `b98b917` | per-request LLM budget → `route=human` |
| 3.1f | `2581855` | stream capacity hold + shared budget/deadline bind |
| 3.1g | `ae13000` | retrieve + tools + stream.retrieve deadline |
| 3.1h | `ab7b417` | hybrid `_rerank` deadline fail-closed |
| 3.1i | `fe2f0aa` | `mutation_version` / `expected_version` CAS; sticky ids → pipeline |

---

## Plan §4 map (honest)

| Plan §4 bullet | Local | Residual |
|----------------|-------|----------|
| LangGraph sole execution; SSE transmits | partial **4.1–4.2** | true node/token events from graph; legacy direct stream when `STREAMING_RAG_PARITY=false` (default) |
| remove dual generation; one terminal answer + one history mutation | **4.1** + **4.2** (when parity **on**) | parity still opt-in; dual path exists when parity off |
| idempotent ticket + inbox outbox | **4.3** `services/escalation.py` + migration **023** | background outbox **retry worker**; transactional multi-row outbox table optional |
| `ticket_id` + delivery state; no false “передан оператору” | **4.3** on wired paths | **auto-escalate every terminal human/error** from normal ask (not only exception/manual/handle_error) |

### §4 ledger (impl SHA)

| Slice | SHA | What |
|-------|-----|------|
| **4.1** | `eaf41f3` | single terminal answer + single history when graph parity succeeds |
| **4.2** | `f1c846e` | parity on → graph-only generation; SSE tokens = chunks of graph answer; fail-closed on graph fail |
| **4.3** | `ad5e435` | idempotent durable escalation; `ticket_id` / `delivery_state` |

---

## Contracts (latest slices) — COMPLETE

### 4.3 @ `ad5e435` (latest impl)

- Module: `services/escalation.py` — `create_escalation` / `create_escalation_sync`
- Durable ticket insert **first**; inbox JSONL/sink **second**
- `idempotency_key` → duplicate → `delivery_state=duplicate`, no second ticket
- User copy **never** claims operator handoff without durable ticket
- Wired: `/api/escalate`, `/api/ask` pipeline **exception** path, graph
  `handle_error`, agentic `create_ticket`
- `AskResponse.ticket_id` / `delivery_state`; graph state fields same
- Migration **023** on disk (**not applied** in this workspace session)
- **Not** wired: normal successful ask with `route=human` (low quality) —
  still may only bump metrics without ticket

```powershell
python -m pytest tests/test_escalation_service.py tests/test_pipeline_exception_escalation.py tests/test_graph_error_handling.py tests/test_agent_tools.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step4-3-<unique>
python -m ruff check services/escalation.py api/routers/feedback.py api/routers/conversation.py agent/graph.py agent/tools.py
```

### 4.2 @ `f1c846e`

- `STREAMING_RAG_PARITY=true` → only `session.ask` generates
- SSE tokens = `_chunk_text_for_sse(graph_answer)`; `generation_source=graph_only`
- Graph fail/timeout → SSE `type=error`, no second stream LLM

### 4.1 @ `eaf41f3`

- `_resolve_stream_terminal`: non-empty graph answer owns SSE + DB + history

### 3.1i @ `fe2f0aa`

- `mutation_version` / `ask(expected_version=…)` → `route=conflict` on mismatch
- `user_id`/`session_id` forwarded to `run_qa_pipeline` (sticky experiments)
- Process-local only (no multi-replica durable store)

---

## Module owners (do not reopen without proven conflict)

| Path | Slice | Role |
|------|-------|------|
| `utils/request_executor.py` | 3.1a | bounded pool |
| `utils/request_deadline.py` | 3.1b | ContextVar deadline |
| `llm/request_budget.py` | 3.1e–f | call/token budget |
| `llm/role_params.py` | 3.1d | role generation params |
| `llm/providers/base.py` | 3.1b–e | provider deadline/budget |
| `agent/graph.py` ConversationSession | 3.1a–e, 3.1i | turn/version/deadline/budget |
| `agent/graph.py` retrieve / handle_error | 3.1g, 4.3 | retrieve deadline; durable escalate |
| `agent/tools.py` | 3.1g, 4.3 | tool deadline; create_ticket → service |
| `vectordb/_base_manager.py` `_rerank` | 3.1h | reranker deadline |
| `api/routers/conversation.py` | 3.1a/f, 4.1–4.3 | ask/stream + pipeline exception escalate |
| `api/routers/feedback.py` | 4.3 | `/api/escalate` |
| `services/escalation.py` | **4.3** | idempotent durable escalation |
| `db/models.py` EscalatedTicket | 4.3 | idempotency/delivery columns |
| job-object / index stack | 2.1–2.6g | do not re-select |

---

## Следующий named candidate: 4.4 (не начат)

**Name:** **4.4 — auto-escalate terminal human/error on normal ask path**  
**(recommended default)**  
*or* **4.4b — outbox retry worker for `delivery_state=failed`**.

### Intent (default 4.4)

1. When `/api/ask` returns `route=human` (or error terminal) from **normal**
   pipeline success (not only exception), call `create_escalation` once with
   stable idempotency (session + question + route/source).
2. Response always includes `ticket_id` + `delivery_state` on those routes.
3. Still no false operator claim without durable ticket.
4. Tests-first; still **no** live multi-service / push / migrate without opt-in.

### Alternate 4.4b

- Retry/deliver pending or failed inbox deliveries without re-creating tickets.

### Explicitly out of 4.4 without opt-in

- full suite as sole gate; plan §5 grounding rewrite; live migrate 023;
  re-select 2.x / 3.1a–i / 4.1–4.3

---

## Что остаётся открытым (после 4.3 / Update-86)

- **4.4** auto human-route escalate / outbox retry
- multi-replica durable session version
- true LangGraph token/node SSE (not chunked finished answer)
- default graph-only stream (flip or remove legacy parity-off path)
- plan §2 live multi-service + migrations **019–023** (**opt-in**)
- real FS deletion / age-budget auto-delete / retention execute HTTP
- plan **§5+** grounding / routing fail-closed
- full suite, release gates, production readiness

---

## Protected dirty / untracked (do not touch without request)

**Dirty tracked:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
`plan_sol_23_07_26`

**Untracked (incl.):** `rag-remediation-plan-2026-08-03.md` (active plan),
`_NEXT_SESSION.md` (pointer only), `.grok-prompts/`, `.pytest_tmp*/`,
presentations / architecture HTML, etc.

**Routing priority:** fresh Git → Update-86 + this capsule → plan file direction
→ never dirty backlog as queue.

---

## Do not

- Grep old `✅ START HERE` for work selection
- Re-select **2.1–2.6g**, **3.1a–3.1i**, **4.1–4.3**
- Claim full §2 / §3 / §4 / production readiness
- Treat failed job-objects as deletable orphans
- Apply migrations / push / deploy / live services without explicit opt-in
- Edit plan checkboxes casually
