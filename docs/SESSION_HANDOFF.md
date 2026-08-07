# Session handoff

**Обновлено:** 2026-08-07 (Update-78 records completed **3.1f** @ `2581855`;
next **3.1g** cooperative deadline at retriever/tool boundaries)

Routing: top [`AGENT_STATE.md`](../AGENT_STATE.md) **Update-78** only.

---

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest implementation | `2581855` — **3.1f** stream capacity-hold + budget/deadline |
| Locally complete | **2.1–2.6g** + **3.1a–3.1f** |
| Full plan §2 / §3 / prod | **NOT** complete |
| Next ordered | **3.1g** retriever/tool deadline checks |
| Gates | no push / deploy / live without opt-in |

### Plan §3 map

| Bullet | Local | Residual |
|--------|-------|----------|
| shared pool + capacity | **3.1a** + **3.1f** | — |
| cooperative deadline | **3.1b** + stream bind | **retriever/reranker/tools** |
| per-session serialize | **3.1c** | durable optimistic version |
| role params | **3.1d** | — |
| per-request LLM budget | **3.1e** + **3.1f** share | — |

### 3.1f contract

- Stream parity uses shared request executor + `deadline_sec`
- Capacity held until orphaned parity future completes (no fake cancel)
- Stream binds deadline + thread-safe LLM budget; worker reuses same budget object
- Helpers: `_release_pipeline_capacity`, `_hold_capacity_until_future_done`

```powershell
python -m pytest tests/test_stream_capacity_hold.py tests/test_chat_streaming.py tests/test_pipeline_concurrency.py tests/test_llm_request_budget.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1f-<unique>
```

---

## Next: 3.1g cooperative deadline at retriever / tool boundaries

**Intent:** `check_request_deadline` before retriever `get_relevant_documents`
and tool side effects; fail-closed without claiming full preemption.

**Out of 3.1g:** plan §4 full LangGraph-only SSE rewrite; live multi-service.

---

## Do not

- Re-select **2.1–2.6g**, **3.1a–3.1f**
- Push / deploy / live without opt-in
