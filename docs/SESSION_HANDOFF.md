# Session handoff

**Обновлено:** 2026-08-07 (Update-77 records completed **3.1e** @ `b98b917`;
next **3.1f** streaming capacity-hold + budget/deadline bind)

Routing: top [`AGENT_STATE.md`](../AGENT_STATE.md) **Update-77** only.

---

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest implementation | `b98b917` — **3.1e** per-request LLM budget |
| Locally complete | **2.1–2.6g** + **3.1a–3.1e** |
| Full plan §2 / §3 / prod | **NOT** complete |
| Next ordered | **3.1f** stream capacity-hold + budget/deadline |
| Gates | no push / deploy / live without opt-in |

### Plan §3 map

| Bullet | Local | Residual |
|--------|-------|----------|
| shared pool + capacity | **3.1a** | stream capacity-hold |
| cooperative deadline | **3.1b** | retriever/reranker/tools |
| per-session serialize | **3.1c** | durable optimistic version |
| role max_tokens/temperature | **3.1d** | — |
| per-request LLM budget | **3.1e** | stream must bind same budget |

### 3.1e contract

- `llm/request_budget.py` ContextVar (calls + tokens)
- Defaults: 24 / 48k / 8k / 50k (`0` = off for that limit)
- Provider precheck+charge; no failover on budget
- ask → `route=human`, `error_node=llm_budget` (never `auto`)

```powershell
python -m pytest tests/test_llm_request_budget.py tests/test_llm_role_params.py tests/test_request_deadline.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1e-<unique>
```

---

## Next: 3.1f streaming path capacity-hold + budget/deadline

**Intent:** `/api/ask/stream` holds pipeline semaphore until orphan work finishes
(mirror 3.1a); binds request deadline + LLM request budget for stream/parity.

**Out of 3.1f:** plan §4 full LangGraph-only stream rewrite; live multi-service.

---

## Do not

- Re-select **2.1–2.6g**, **3.1a–3.1e**
- Push / deploy / live without opt-in
