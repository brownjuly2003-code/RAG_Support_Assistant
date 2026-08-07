# Session handoff

**Обновлено:** 2026-08-07 (Update-81 after completed **3.1h** @ `ab7b417`;
next ordered candidate **3.1i durable optimistic session version**)

**Назначение:** самодостаточный next-session handoff после compacted context.
Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-81**). Older blocks with literal `✅ START HERE` are **archival**.
Plan source (untracked/protected):
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md).

---

## Нулевая неоднозначность: состояние на входе

Сканируй эту капсулу **первой**.

| Факт | Значение |
|------|----------|
| Latest implementation | `ab7b417` — **3.1h** hybrid reranker deadline |
| Previous implementation | `ae13000` — **3.1g** retrieve/tool/stream.retrieve deadline |
| Latest known docs before Update-81 | `1259417` — Update-80 |
| This Update-81 docs commit | **unknown in-file**; next session: `git log -5 --oneline` |
| §2 last fault-injection impl | `f347feb` — **2.6g** |
| Branch advisory | was `ahead 141` before Update-81 — **refresh mandatory** |
| Active writer / unfinished WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.6g** + **3.1a–3.1h** |
| Full plan §2 / §3 / project / release / prod | **NOT** complete / **NOT** claimed |
| Next ordered candidate | **3.1i** durable optimistic session version (**not started**) |
| Gates | no push / deploy / live services / destructive Git / prod claims |

**Known verification (3.1h; last impl gate):** focused **40 passed**
(`tests/test_reranker_deadline.py` + request/retriever deadline + base_manager);
Ruff clean. Full suite / live drills **not** run.

**Key ingestion invariant:** failed jobs with `source_path`-matched job-objects →
`retained_after_failed_transition` (intentional retention, **not** GC).
`auto_delete_eligible` is always `False`.

### Plan §3 map (honest)

| Plan §3 bullet (order) | Local work | Residual |
|------------------------|------------|----------|
| nested executor → shared pool; capacity until work done | **3.1a** + **3.1f** | — |
| cooperative cancel / deadline through boundaries | **3.1b** + **3.1f** + **3.1g** + **3.1h** | — (cooperative scopes) |
| per-session serialize / sticky experiment ids | **3.1c** | **← next 3.1i** durable version |
| max_tokens/temperature per LLM role | **3.1d** | — |
| per-request LLM call/token budget | **3.1e** + **3.1f** | — |

### §3 ledger (impl SHA → surface)

| Slice | SHA | What |
|-------|-----|------|
| **3.1a** | `a21f364` | shared request executor; `/api/ask` capacity hold |
| **3.1b** | `76179d5` | ContextVar deadline; provider entry fail-closed |
| **3.1c** | `d9ba87e` | per-session turn lock + epoch |
| **3.1d** | `48c2381` | per-role temperature/max_tokens |
| **3.1e** | `b98b917` | per-request LLM budget → `route=human` |
| **3.1f** | `2581855` | stream capacity hold + shared deadline/budget |
| **3.1g** | `ae13000` | retrieve node + tools + stream.retrieve deadline |
| **3.1h** | `ab7b417` | hybrid `_rerank` deadline fail-closed |

### Module owners (do not reopen without proven conflict)

| Module / path | Slice | Role |
|---------------|-------|------|
| `utils/request_deadline.py` | 3.1b | ContextVar wall deadline |
| `agent/graph.py` `make_retrieve_node` | 3.1g | retrieve deadline |
| `agent/tools.py` | 3.1g | tool deadline |
| `vectordb/_base_manager.py` `HybridRetriever._rerank` | **3.1h** | rerank deadline |
| `api/routers/conversation.py` stream | 3.1f + 3.1g | capacity + stream.retrieve |
| job-object / index stack | 2.x | **do not re-select 2.1–2.6g** |

### Protected state

- **Dirty tracked:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
  `plan_sol_23_07_26`
- **Untracked:** plan, pytest temps, presentations, `_NEXT_SESSION.md`, etc.

---

## Быстрый старт следующей сессии

1. `cd D:\RAG_Support_Assistant`
2. `git status --short --branch` and `git log -5 --oneline`
3. Read top **Update-81** + this capsule. Do **not** reselect **3.1a–3.1h**.
4. Default next: **3.1i** (below). One named slice per turn.
5. Local commit only; no push/deploy/live without opt-in.

---

## Контракт 3.1h (reranker) — COMPLETE

At `ab7b417`:

- `HybridRetriever._rerank` calls `check_request_deadline("retriever.rerank")`
  before cross-encoder `predict`
- Deadline is **re-raised** (not top-k silent fallback used for ordinary errors)
- Ask path maps to `route=timeout` when wall bound
- Vector fast path still skips rerank

**Verification:** 40 passed focused/adjacent; Ruff clean.

```powershell
python -m pytest tests/test_reranker_deadline.py tests/test_request_deadline.py tests/test_retriever_tool_deadline.py tests/test_base_manager.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1h-<unique>
python -m ruff check vectordb/_base_manager.py tests/test_reranker_deadline.py
```

---

## Краткие контракты 3.1g / earlier

- **3.1g** @ `ae13000`: retrieve + tools + stream.retrieve deadline
- **3.1f** @ `2581855`: stream capacity hold + shared budget/deadline
- **3.1e** @ `b98b917`: LLM budget → human
- **3.1b** @ `76179d5`: provider deadline
- **3.1a** @ `a21f364`: shared executor + ask capacity hold

---

## Следующий named candidate: 3.1i durable session version (не начат)

**Name:** **3.1i — durable optimistic session version / multi-replica sticky**.

### Intent

1. Residual of plan §3 after in-process 3.1c lock+epoch.
2. Read existing session store / mutation epoch before design.
3. Tests-first; no live multi-service without opt-in.
4. Alternate if user prioritizes: plan **§4** LangGraph sync/SSE.

### Explicitly out of 3.1i without opt-in

- push / deploy / live PG/Redis/Celery drills
- re-selecting 3.1a–3.1h or 2.1–2.6g
- plan checkbox bulk-edit

---

## Что остаётся открытым

- **3.1i** durable session version (next)
- plan §2 live multi-service + migrations **019–022** (**opt-in**)
- real FS deletion / age-budget auto-delete / retention execute HTTP
- plan **§4+**
- full suite, release, production readiness

---

## Do not

- Re-select **2.1–2.6g** or **3.1a–3.1h**
- Claim full plan §3 complete (durable version residual)
- Push / deploy / live services without explicit opt-in
- Grep old `✅ START HERE` for work selection
