# Session handoff

**Обновлено:** 2026-08-07 (Update-74 records completed **3.1b** @ `76179d5`;
previous **3.1a** @ `a21f364` / docs `4583047`; next **3.1c** per-session serialize)

**Назначение:** самодостаточный next-session handoff после compacted context.
Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-74**). Older blocks with literal `✅ START HERE` are **archival**.
Plan source (untracked/protected):
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

---

## Нулевая неоднозначность: состояние на входе

| Факт | Значение |
|------|----------|
| Latest implementation | `76179d5` — **3.1b** cooperative provider deadline |
| Previous implementation | `a21f364` — **3.1a** shared executor + capacity hold |
| Latest known docs before this Update | Update-73 `4583047` |
| This Update-74 docs commit | **unknown in-file**; next session: `git log -5 --oneline` |
| Active writer / unfinished WIP | **none** |
| Locally complete | **2.1–2.6g** + **3.1a** + **3.1b** |
| Full plan §2 / §3 / release / prod | **NOT** complete / **NOT** claimed |
| Next ordered candidate | **3.1c** per-session serialize / optimistic version |
| Gates | no push / deploy / live services / destructive Git / prod claims |

**Known verification (3.1b):** focused **8 passed** + adjacent green; Ruff clean.
Full suite / live drills **not** run.

### Plan §3 map

| Bullet | Local | Residual |
|--------|-------|----------|
| shared pool + capacity hold | **3.1a** | stream capacity-hold |
| cooperative deadline through boundaries | **3.1b** (provider) | retriever/reranker/tools |
| per-session serialize / sticky ids | not started | **← next 3.1c** |
| max_tokens/temperature per role | not started | |
| per-request LLM token budget | not started | |

### Module owners (3.1a–3.1b)

| Path | Slice | Role |
|------|-------|------|
| `utils/request_executor.py` | 3.1a | shared pool |
| `utils/request_deadline.py` | 3.1b | ContextVar deadline |
| `llm/providers/base.py` `ProviderBackedLLM` | 3.1b | check before provider work |
| `agent/graph.py` `ConversationSession.ask` | 3.1a+b | bind deadline; map exceed → timeout |
| `api/routers/conversation.py` `/api/ask` | 3.1a+b | capacity hold + `deadline_sec` |

### Protected state

Dirty tracked: `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`  
Untracked: plan, temps, presentations, `_NEXT_SESSION.md`

---

## Быстрый старт следующей сессии

1. `cd D:\RAG_Support_Assistant`
2. `git status` + `git log -5 --oneline`
3. Read top **Update-74** + this capsule. Do **not** reselect **2.1–2.6g / 3.1a / 3.1b**.
4. One named slice: default **3.1c**.
5. Local commit only; stop after one slice.

---

## Контракт 3.1b — COMPLETE (latest impl)

At `76179d5`:

- ContextVar deadline from tighter of `ask_budget_sec` + `deadline_sec`
- Provider entry fail-closed (`RequestDeadlineExceeded`), no failover after deadline
- ask maps exceed → `route=timeout` degraded state
- Cooperative only — no mid-call preemption

### Reference commands

```powershell
python -m pytest tests/test_request_deadline.py tests/test_ask_wall_budget.py tests/test_request_executor.py tests/test_pipeline_concurrency.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1b-<unique>
python -m ruff check utils/request_deadline.py llm/providers/base.py agent/graph.py
```

---

## Следующий named candidate: 3.1c per-session serialize (не начат)

**Name:** **3.1c — per-session serialize / optimistic version**.

### Intent

1. Concurrent same-session asks must not corrupt `_history` / `_pending_action`.
2. Tests with parallel `session.ask` (or HTTP) prove ordered history / fail-closed.
3. Prefer a per-session lock (threading) first; durable optimistic version later if needed.
4. Still no live multi-service / push.

### Explicitly out of 3.1c

- full LLM token budget
- max_tokens per role
- stream capacity-hold (can be adjacent)
- live services

---

## Do not

- Re-select **2.1–2.6g**, **3.1a**, **3.1b**
- Claim full cooperative cancel through all boundaries after 3.1b
- Push / deploy / live without opt-in
