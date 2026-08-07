# Session handoff

**Обновлено:** 2026-08-07 (Update-75 records completed **3.1c** @ `d9ba87e`;
previous **3.1b** @ `76179d5`; next **3.1d** max_tokens/temperature per LLM role)

Routing: **только** верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-75**). Plan: untracked `rag-remediation-plan-2026-08-03.md`.

---

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest implementation | `d9ba87e` — **3.1c** per-session serialize |
| Previous | `76179d5` — **3.1b** |
| Locally complete | **2.1–2.6g** + **3.1a–3.1c** |
| Full plan §2 / §3 / prod | **NOT** complete / **NOT** claimed |
| Next ordered | **3.1d** max_tokens / temperature per LLM role |
| Gates | no push / deploy / live without opt-in |

**Verification (3.1c):** 26 passed focused/adjacent; Ruff clean.

### Plan §3 map

| Bullet | Local | Residual |
|--------|-------|----------|
| shared pool + capacity hold | **3.1a** | stream capacity-hold |
| cooperative deadline | **3.1b** (provider) | retriever/reranker/tools |
| per-session serialize | **3.1c** | durable optimistic version |
| max_tokens/temperature per role | not started | **← next 3.1d** |
| per-request LLM token budget | not started | |

### Module owners (3.1c)

| Path | Role |
|------|------|
| `agent/graph.py` `ConversationSession` | turn lock, epoch, pending/history guards |

### Protected

Dirty: `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`

---

## Контракт 3.1c — COMPLETE

At `d9ba87e`:

- Exclusive session turn (`_busy` + `Condition`)
- Epoch invalidation on wall-budget timeout; stale writes discarded
- History snapshot for pipeline; timeout answer force-appended
- Residual: direct `session._history` writes in some API error/cache paths

```powershell
python -m pytest tests/test_session_serialize.py tests/test_ask_wall_budget.py tests/test_request_deadline.py tests/test_agent_tools.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1c-<unique>
```

---

## Следующий: 3.1d max_tokens / temperature per LLM role

**Intent:** configurable `max_tokens` and `temperature` by LLM role
(generate / grade / transform / agentic / …) with safe production defaults;
wire through provider generate kwargs; tests prove defaults + overrides.

**Out of 3.1d:** full per-request token budget (later §3 bullet), live services.

---

## Do not

- Re-select **2.1–2.6g**, **3.1a–3.1c**
- Push / deploy / live without opt-in
