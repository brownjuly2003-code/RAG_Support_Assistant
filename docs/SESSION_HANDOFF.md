# Session handoff

**Обновлено:** 2026-08-07 (Update-87 — record completed slice **4.4** @
`0371971`). Next ordered candidate **4.5** (outbox retry) **or** plan **§5**.

**Назначение:** самодостаточный next-session handoff.  
**Routing:** только верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-87**). Любые старые `✅ START HERE` ниже — **archival**.  
**Plan (untracked/protected):**
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)
— **не** править checkboxes casually.

---

## Нулевая неоднозначность (сканируй первой)

| Факт | Значение |
|------|----------|
| Latest **implementation** | `0371971` — **4.4** auto-escalate terminal human/error on normal ask |
| Previous impl | `ad5e435` — **4.3** durable escalation service |
| This Update-87 docs SHA | **unknown in-file** → `git log -5 --oneline` |
| Branch advisory | was `master...origin/master [ahead 152]` after impl — **refresh mandatory** |
| Active writer / WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.4** |
| Full plan §2 / §3 / §4 | **NOT** complete |
| Project / release / production | **NOT** claimed |
| Next ordered | **4.5** outbox retry worker **or** plan **§5** grounding |
| Gates | no push / deploy / live multi-service / migrate 019–023 without **explicit opt-in** |

**Last known verification (4.4):** focused **25 passed**
(`test_human_route_escalation` + pipeline exception + escalation service +
graph error + agent tools); Ruff clean on scoped paths. Full suite / live
drills **not** run.

**Key ingestion invariant (unchanged):** failed jobs with `source_path`-matched
job-objects → `retained_after_failed_transition` (not GC);
`auto_delete_eligible` always `False`.

---

## Быстрый старт следующей сессии

1. Cycle-guard / one-slice rule: **one named atomic slice per user turn**.
2. `cd D:\RAG_Support_Assistant`
3. `git status --short --branch` and `git log -8 --oneline` (**actual Git wins**).
4. Read **only** top **Update-87** in `AGENT_STATE.md` + this capsule.
5. Default work: **4.5** (below). Announce `slice 1/1`.
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
| idempotent ticket + inbox outbox | **4.3** `services/escalation.py` + migration **023** | background outbox **retry worker** |
| `ticket_id` + delivery state; no false “передан оператору” | **4.3–4.4** on wired paths | live PG migrate opt-in |
| auto-escalate terminal human/error on normal ask | **4.4** | stream-path parity if needed |

### §4 ledger (impl SHA)

| Slice | SHA | What |
|-------|-----|------|
| **4.1** | `eaf41f3` | single terminal answer + single history when graph parity succeeds |
| **4.2** | `f1c846e` | parity on → graph-only generation; SSE tokens = chunks of graph answer |
| **4.3** | `ad5e435` | idempotent durable escalation; `ticket_id` / `delivery_state` |
| **4.4** | `0371971` | auto-escalate `route=human|error|error_escalation` on normal `/api/ask` success |

---

## Contracts (latest slices) — COMPLETE

### 4.4 @ `0371971` (latest impl)

- `/api/ask` success path auto-calls `create_escalation(source=human_route)`
  when route ∈ `{human, error, error_escalation}` and no graph `ticket_id`
- Graph-owned tickets passed through (no second insert)
- AI draft answer kept; never false operator claim when durable fails
- `route=auto` does not escalate
- Exception / manual / handle_error paths remain on 4.3 wiring

```powershell
python -m pytest tests/test_human_route_escalation.py tests/test_pipeline_exception_escalation.py tests/test_escalation_service.py tests/test_graph_error_handling.py tests/test_agent_tools.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step4-4-<unique>
python -m ruff check api/routers/conversation.py services/escalation.py tests/test_human_route_escalation.py
```

### 4.3 @ `ad5e435`

- Module: `services/escalation.py` — `create_escalation` / `create_escalation_sync`
- Durable ticket insert **first**; inbox JSONL/sink **second**
- Migration **023** on disk (**not applied** in this workspace session)

### 4.2 @ `f1c846e` / 4.1 @ `eaf41f3`

- Stream parity on → single graph generation + single terminal/history

### 3.1i @ `fe2f0aa`

- Process-local session version CAS (no multi-replica durable store)

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
| `api/routers/conversation.py` | 3.1a/f, **4.1–4.4** | ask/stream + exception + **auto human-route** |
| `api/routers/feedback.py` | 4.3 | `/api/escalate` |
| `services/escalation.py` | **4.3** | idempotent durable escalation |
| `db/models.py` EscalatedTicket | 4.3 | idempotency/delivery columns |
| job-object / index stack | 2.1–2.6g | do not re-select |

---

## Следующий named candidate: 4.5 (не начат)

**Name:** **4.5 — outbox retry worker for `delivery_state=failed`**  
**(recommended default)**  
*or* begin plan **§5** grounding / routing fail-closed.

### Intent (default 4.5)

1. Select durable tickets with `delivery_state=failed` (or pending too long).
2. Re-attempt inbox delivery **without** creating a second ticket.
3. Update `delivery_state` / `delivery_error` honestly.
4. Tests-first; still **no** live multi-service / push / migrate without opt-in.

### Alternate §5

- Fail-closed grounding / verified claims / auto only when calibrated.

### Explicitly out of 4.5 without opt-in

- full suite as sole gate; live migrate 023; re-select 2.x / 3.1a–i / 4.1–4.4

---

## Что остаётся открытым (после 4.4 / Update-87)

- **4.5** outbox retry worker
- multi-replica durable session version
- true LangGraph token/node SSE (not chunked finished answer)
- default graph-only stream (flip or remove legacy parity-off path)
- stream-path auto-escalate parity (if needed)
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

**Routing priority:** fresh Git → Update-87 + this capsule → plan file direction
→ never dirty backlog as queue.

---

## Do not

- Grep old `✅ START HERE` for work selection
- Re-select **2.1–2.6g**, **3.1a–3.1i**, **4.1–4.4**
- Claim full §2 / §3 / §4 / production readiness
- Treat failed job-objects as deletable orphans
- Apply migrations / push / deploy / live services without explicit opt-in
- Edit plan checkboxes casually
