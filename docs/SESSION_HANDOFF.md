# Session handoff

**Обновлено:** 2026-08-07 (Update-73 records completed **3.1a** @ `a21f364`;
previous **2.6g** @ `f347feb` / docs `de57323`; next **3.1b** cooperative
deadline at provider boundary)

**Назначение:** самодостаточный next-session handoff после compacted context.
Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-73**). Older blocks with literal `✅ START HERE` are **archival**.
Plan source (untracked/protected):
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

---

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**.

| Факт | Значение |
|------|----------|
| Latest implementation | `a21f364` — **3.1a** shared request executor + capacity hold |
| Previous implementation | `f347feb` — **2.6g** worker outage/recovery |
| Latest known docs before this Update | Update-72 `de57323` |
| This Update-73 docs commit | **unknown in-file**; next session: `git log -5 --oneline` |
| Branch advisory | was `ahead 125` after 3.1a impl — **refresh mandatory** |
| Active writer / unfinished WIP | **none** |
| Locally complete (documented scopes) | **2.1–2.6g** + **3.1a** |
| Full plan §2 / §3 / release / prod | **NOT** complete / **NOT** claimed |
| Next ordered candidate | **3.1b** cooperative deadline at provider boundary |
| Gates | no push / deploy / live services / destructive Git / prod claims |

**Known verification (3.1a):** focused **15 passed** + **5** request-timeout;
Ruff clean. Full suite / live drills **not** run.

**Key invariant (ingestion, unchanged):** failed jobs with `source_path`-matched
job-objects → `retained_after_failed_transition`; `auto_delete_eligible` always
`False`.

### Plan §2 map (local residual closed for fault injection)

| Bullet | Local | Residual |
|--------|-------|----------|
| fault injection expand | **2.6a–2.6g** | live multi-service **opt-in** |
| live PG/Redis/Celery/Chroma + migrations 019–022 | not started | **opt-in only** |

### Plan §3 map (started)

| Bullet | Local | Residual |
|--------|-------|----------|
| nested executor → shared pool; capacity until work done | **3.1a** | stream path; cooperative cancel |
| cooperative cancel / deadline through boundaries | not started | **← next 3.1b** |
| session serialize / sticky experiment ids | not started | |
| max_tokens/temperature per LLM role | not started | |
| per-request LLM call/token budget | not started | |

### Module owners (3.1a)

| Path | Role |
|------|------|
| `utils/request_executor.py` | process-wide bounded pool + nested-inline guard |
| `agent/graph.py` `_run_within_budget` | uses shared pool (no per-call TPE) |
| `api/routers/conversation.py` `/api/ask` | shared executor + capacity hold past 504 |
| `config/settings.py` | `request_executor_max_workers` |

### Protected state

- **Dirty tracked:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
  `plan_sol_23_07_26`
- **Untracked:** plan, pytest temps, presentations, `_NEXT_SESSION.md`, etc.

**Routing rule:** first/topmost Update in `AGENT_STATE.md` only.

---

## Быстрый старт следующей сессии

1. `cd D:\RAG_Support_Assistant`
2. `git status --short --branch` + `git log -5 --oneline`
3. Read top **Update-73** + this capsule. Do **not** reselect **2.1–2.6g** or **3.1a**.
4. Execute **one** named slice: default **3.1b**.
5. Local commit only; stop after one slice.

**Not authorized without opt-in:** push, deploy, live multi-service drills.

---

## Контракт 3.1a — COMPLETE (latest impl)

At `a21f364`:

- Shared `utils/request_executor.py` (`REQUEST_EXECUTOR_MAX_WORKERS`, 0 → mirror pipelines)
- No per-request `ThreadPoolExecutor` in `ConversationSession._run_within_budget`
- Nested worker runs inline (no same-pool deadlock)
- `/api/ask` capacity (semaphore + inflight) held until orphaned worker done after 504
- Graph still not cooperatively cancellable

### Reference commands

```powershell
python -m pytest tests/test_request_executor.py tests/test_ask_wall_budget.py tests/test_pipeline_concurrency.py tests/test_request_timeout.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1a-<unique>
python -m ruff check utils/request_executor.py agent/graph.py api/routers/conversation.py
```

---

## Следующий named candidate: 3.1b cooperative deadline (не начат)

**Name:** **3.1b — cooperative deadline / cancellation at provider boundary**.

### Intent

1. Introduce a request-scoped deadline object (monotonic deadline from outer budget/timeout).
2. Check at LLM/provider call entry (and preferably exit) so new provider work is not started after deadline.
3. Tests with blocking fake provider prove fail-closed behaviour without inventing full graph preemption.
4. Still **no** push/live multi-service; still **no** plan checkbox bulk-edit.

### Explicitly out of 3.1b

- full cooperative cancel through every retriever/reranker/tool (may be 3.1c+)
- streaming path capacity-hold (can be adjacent later)
- per-request token budget (later §3 bullet)
- live services

---

## Что остаётся открытым

- **3.1b+** cooperative deadlines / session serialize / LLM role limits / token budget
- plan §2 live multi-service (**opt-in**)
- job-object FS delete / age-budget / execute HTTP
- full suite, release, production readiness

**Superseded:** any handoff saying next is only 2.6g or “begin §3” without **3.1b**.

---

## Do not

- Re-select **2.1–2.6g** or **3.1a**
- Claim cooperative cancellation complete after 3.1a
- Push / deploy / live services without opt-in
