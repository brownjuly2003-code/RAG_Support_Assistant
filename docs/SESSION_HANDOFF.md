# Session handoff

**Обновлено:** 2026-08-07 (Update-79 docs-only / transparency after completed
**3.1f** @ `2581855` + Update-78 docs `70dce00`; next ordered candidate
**3.1g cooperative deadline at retriever/tool boundaries**)

**Назначение:** самодостаточный next-session handoff после compacted context.
Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-79**). Older blocks with literal `✅ START HERE` are **archival**.
Plan source (untracked/protected):
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

---

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**.

| Факт | Значение |
|------|----------|
| Latest implementation | `2581855` — **3.1f** stream capacity-hold + budget/deadline bind |
| Latest impl docs (Update-78) | `70dce00` |
| This Update-79 docs commit | **unknown in-file**; next session: `git log -5 --oneline` |
| Previous implementation | `b98b917` — **3.1e** per-request LLM budget |
| §2 last fault-injection impl | `f347feb` — **2.6g** |
| Branch advisory | was `ahead 137` before Update-79 — **refresh mandatory** |
| Active writer / unfinished WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.6g** + **3.1a–3.1f** |
| Full plan §2 / §3 / project / release / prod | **NOT** complete / **NOT** claimed |
| Next ordered candidate | **3.1g** retriever/tool cooperative deadline (**not started**) |
| Gates | no push / deploy / live services / destructive Git / prod claims |

**Transparency-only Update-79:** no implementation/test/plan-checkbox/backlog
change; project tests **not** rerun here. Implementation state unchanged after
`2581855` / **3.1f**.

**Known verification (3.1f; last impl gate):** focused **17 passed**
(`tests/test_stream_capacity_hold.py` + `tests/test_chat_streaming.py` +
`tests/test_pipeline_concurrency.py` + `tests/test_llm_request_budget.py`);
Ruff clean on scoped paths. Full suite / live drills **not** run.

**Key ingestion invariant:** failed jobs with `source_path`-matched job-objects →
`retained_after_failed_transition` (intentional retention, **not** GC).
`auto_delete_eligible` is always `False`.

### Plan §2 map (honest — plan checkboxes stay open)

| Plan §2 bullet (order) | Local work | Residual |
|------------------------|------------|----------|
| 2.1 inventory under lock | 2.1 (+ related) | live DoD open |
| 2.2 bounded retention | 2.2, 2.3f–2.3i | live DoD open |
| operator surface rollback/retention | index 2.3b–2.3i; job-objects 2.4i–2.5a | no job-object delete HTTP |
| immutable originals + lifecycle bind | 2.4a–2.5b | no real FS delete / age-budget |
| **fault injection expand** | **2.6a–2.6g** | **local residual closed** |
| live PG/Redis/Celery/Chroma + migrations | not started | **opt-in only**; migrations **019–022** |

### Plan §3 map (honest)

| Plan §3 bullet (order) | Local work | Residual |
|------------------------|------------|----------|
| nested executor → shared pool; capacity until work done | **3.1a** + **3.1f** | — (documented scopes) |
| cooperative cancel / deadline through boundaries | **3.1b** (provider) + stream bind | **← next 3.1g** retriever/tools |
| per-session serialize / sticky experiment ids | **3.1c** | durable optimistic version |
| max_tokens/temperature per LLM role | **3.1d** | — |
| per-request LLM call/token budget | **3.1e** + **3.1f** share | — |

### §3 ledger (impl SHA → surface)

| Slice | SHA | What |
|-------|-----|------|
| **3.1a** | `a21f364` | shared request executor; `/api/ask` capacity hold past 504 |
| **3.1b** | `76179d5` | ContextVar deadline; provider entry fail-closed |
| **3.1c** | `d9ba87e` | per-session turn lock + epoch; stale history/pending discard |
| **3.1d** | `48c2381` | per-role temperature/max_tokens (`RAG_LLM_ROLE_PARAMS`) |
| **3.1e** | `b98b917` | per-request LLM call/token budget; exhaust → `route=human` |
| **3.1f** | `2581855` | stream capacity hold + shared deadline/budget on SSE |

### Module owners (do not reopen without proven conflict)

| Module / path | Slice | Role |
|---------------|-------|------|
| `utils/request_executor.py` | 3.1a | process-wide bounded pool |
| `utils/request_deadline.py` | 3.1b | ContextVar wall deadline |
| `llm/request_budget.py` | 3.1e–f | thread-safe call/token budget |
| `llm/role_params.py` | 3.1d | role generation params |
| `llm/providers/base.py` | 3.1b–e | deadline + budget on provider entry |
| `agent/graph.py` `ConversationSession` | 3.1a–e | turn lock; bind deadline/budget; map budget fail |
| `api/routers/conversation.py` `/api/ask` | 3.1a–b | executor + capacity hold + `deadline_sec` |
| `api/routers/conversation.py` `/api/ask/stream` | **3.1f** | capacity hold; bind; shared budget object |
| job-object / index stack | 2.x | **do not re-select 2.1–2.6g** |

### Protected state (do not touch/stage/remove without request)

- **Dirty tracked:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
  `plan_sol_23_07_26`
- **Untracked (incl.):** `.grok-prompts/`, `.pytest_tmp*/`, presentations,
  `_NEXT_SESSION.md` (**pointer only — not routing authority**),
  `rag-remediation-plan-2026-08-03.md` (active plan — **no checkbox edits**
  casually), architecture HTML, etc.

**Routing rule:** first/topmost Update in `AGENT_STATE.md` only. Never grepping
historical `START HERE`. Never treating dirty backlog/legacy plan as queue.

---

## Быстрый старт следующей сессии

1. Cycle-guard preflight on the latest user message.
2. `cd D:\RAG_Support_Assistant`
3. `git status --short --branch` and `git log -5 --oneline` (**actual Git wins**
   over hashes below; known impl `2581855` / **3.1f**; known Update-78
   `70dce00`; Update-79 SHA from fresh log).
4. Read **only** top **Update-79** in `AGENT_STATE.md` + this capsule.
   Do **not** reselect **2.1–2.6g** or **3.1a–3.1f**.
5. Execute **one** named slice: default **3.1g** (below). Announce
   `slice 1/1`, `delegated run N/3`, `QA follow-up N/1`.
6. Tests-first → proportional gate → explicit-path local commit only (no push).
7. Optional handoff refresh; **stop/yield** after one slice.

**Not authorized without explicit opt-in:** push, deploy, live
PostgreSQL/Redis/Celery/Chroma drills, destructive Git, production claims.

---

## Назначение и приоритет источников

1. Fresh `git status` / `git log` — filesystem/Git truth.
2. Top `AGENT_STATE.md` (**Update-79**) + this capsule.
3. Dirty `BACKLOG.md` / `README.md` / `audit_gpt_*` / `plan_sol_23_07_26` —
   protected user state; **stale**; do not override Update-79.
4. `_NEXT_SESSION.md` — pointer only.
5. `rag-remediation-plan-2026-08-03.md` — active plan direction; **do not**
   edit checkboxes casually.
6. One user turn = one named atomic slice.

**Authoritative implementation:** `2581855` (**3.1f**). Do not invent future
docs SHAs inside content.

---

## Контракт 3.1f (stream) — COMPLETE (latest impl)

At `2581855`:

- `/api/ask/stream` holds pipeline semaphore + inflight until orphaned parity
  `run_in_executor` future completes (mirror of 3.1a `/api/ask` hold)
- Parity/fallback ask uses `get_request_executor()` (not default pool)
- Stream binds `request_deadline` + `LLMRequestBudget`; worker installs the
  **same budget object** (thread-safe counters) so stream ∥ parity share one
  request budget
- `session.ask` receives `deadline_sec`, `session_id`, `user_id`, `confirm`
- Removed ineffective `graph_task.cancel()` on parity timeout
- Helpers: `_release_pipeline_capacity`, `_hold_capacity_until_future_done`

**Boundary:** streaming capacity + bind only. Retriever/tool deadline is **3.1g**.

**Verification:** 17 passed focused/adjacent; Ruff clean.

### Reference commands (3.1f)

```powershell
python -m pytest tests/test_stream_capacity_hold.py tests/test_chat_streaming.py tests/test_pipeline_concurrency.py tests/test_llm_request_budget.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1f-<unique>
python -m ruff check api/routers/conversation.py llm/request_budget.py agent/graph.py
```

---

## Краткие контракты 3.1a–3.1e (COMPLETE)

### 3.1a @ `a21f364`

Shared `utils/request_executor.py`; no per-call `ThreadPoolExecutor` in ask
wall-budget; `/api/ask` capacity held past outer 504 until worker done.

### 3.1b @ `76179d5`

`utils/request_deadline.py`; `ProviderBackedLLM` checks before generate/tools;
ask maps deadline exceed → `route=timeout`. Cooperative only.

### 3.1c @ `d9ba87e`

`ConversationSession` exclusive turn + mutation epoch; wall-budget orphan
cannot write history/pending after invalidate.

### 3.1d @ `48c2381`

`llm/role_params.py` + `RAG_LLM_ROLE_PARAMS`; `_invoke_llm(role=…)`; safe
defaults (grade/evaluate temperature 0).

### 3.1e @ `b98b917`

`llm/request_budget.py`; defaults 24 calls / 48k in / 8k out / 50k total;
exhaustion → `route=human`, `error_node=llm_budget` (**never auto**).

---

## Следующий named candidate: 3.1g retriever/tool deadline (не начат)

**Plan order:** residual of §3 cooperative-deadline bullet after provider + stream.
**Name:** **3.1g — cooperative deadline at retriever / tool boundaries**.

### Intent

1. Call `check_request_deadline` (and fail closed) before expensive retrieve
   work (`get_relevant_documents` / graph retrieve path).
2. Tool side effects (e.g. `create_ticket`, agentic tools) refuse after deadline.
3. Prefer tests-first with bound deadline + fake slow retriever/tool.
4. Still cooperative: no mid-call kill of blocking I/O.
5. Still **no** live multi-service, push, deploy, plan checkbox bulk-edit.

### Suggested acceptance (tests-first)

1. Focused tests: deadline expired → retriever not called / tool not executed.
2. Graph/ask path returns fail-closed non-success route when retrieve blocked
   (do not invent silent empty success as `auto` without explicit product rule).
3. Scoped Ruff + proportional adjacent green (deadline + budget + session).
4. Local commit only; optional handoff Update after slice.

### Candidate ownership (confirm before edits)

| Surface | Likely modules | Notes |
|---------|----------------|-------|
| Deadline API | `utils/request_deadline.py` | reuse; avoid reinvent |
| Graph retrieve | `agent/graph.py` retrieve nodes | primary |
| Tools | `agent/tools.py`, agentic loop | fail closed after deadline |
| Stream retriever | `api/routers/conversation.py` | stream path `get_relevant_documents` |
| Provider | already 3.1b | do not reopen without conflict |

### Explicitly out of 3.1g

- full mid-call preemption of blocking HTTP/socket
- plan §4 LangGraph-only SSE rewrite (separate)
- live multi-service recovery drill
- re-selecting 3.1a–3.1f or 2.1–2.6g

### Reference commands (3.1g — after work lands)

```powershell
python -m pytest tests/<new_or_targeted> tests/test_request_deadline.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1g-<unique>
```

---

## Что остаётся открытым (после 3.1f / Update-79)

- **3.1g** retriever/tool deadline (next ordered)
- durable optimistic session version / multi-replica sticky
- plan §2 live multi-service + migrations **019–022** (**opt-in**)
- real job-object / legacy-previous **FS deletion** (product opt-in)
- age/budget auto-delete thresholds; orphan cleanup **mutations**
- job-object retention **execute** HTTP
- plan **§4+** (unified LangGraph sync/SSE, durable escalation)
- full suite, release gates, project/production readiness

**Superseded next-work text:** any handoff still saying next is 3.1e, 3.1f,
or “begin §3” without naming **3.1g** is **stale**.

---

## Windows / tooling notes

- Unique ignored basetemp: `--basetemp=.tmp/pytest-<slice>`
- Full `requirements-dev.lock` may hit Linux-only wheel issues — do not
  blind-retry install without portability task
- One atomic slice per user turn; stop after commit + optional docs
- Avoid concurrent full-ingest threads that load real embedding models in tests
- Stream/parity tests: prefer fakes; do not require live Ollama

---

## Do not

- Re-select **2.1–2.6g** or **3.1a–3.1f**
- Claim full cooperative cancel through all boundaries after 3.1b/3.1f
- Treat failed job-objects as deletable orphans
- Invent auto-delete / age-budget without opt-in
- Push / deploy / live services without explicit opt-in
- Grep old `✅ START HERE` for work selection
