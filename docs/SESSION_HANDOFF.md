# Session handoff

**Обновлено:** 2026-08-07 (Update-76 records completed **3.1d** @ `48c2381`;
next **3.1e** per-request LLM call/token budget)

Routing: top [`AGENT_STATE.md`](../AGENT_STATE.md) **Update-76** only.

---

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest implementation | `48c2381` — **3.1d** per-role max_tokens/temperature |
| Locally complete | **2.1–2.6g** + **3.1a–3.1d** |
| Full plan §2 / §3 / prod | **NOT** complete |
| Next ordered | **3.1e** per-request LLM call/token budget |
| Gates | no push / deploy / live without opt-in |

### Plan §3 map

| Bullet | Local | Residual |
|--------|-------|----------|
| shared pool + capacity | **3.1a** | stream capacity-hold |
| cooperative deadline | **3.1b** | retriever/reranker/tools |
| per-session serialize | **3.1c** | durable optimistic version |
| max_tokens/temperature per role | **3.1d** | — |
| per-request LLM token budget | not started | **← next 3.1e** |

### 3.1d contract

- `llm/role_params.py` + `RAG_LLM_ROLE_PARAMS`
- Defaults: grade/evaluate/classify `temperature=0`; generate `0.2` / `1024`
- `graph._invoke_llm(role=…)` on all main node invokes; agentic tools kwargs
- Ollama: `temperature` + `num_predict`; Mistral: existing kwargs path

```powershell
python -m pytest tests/test_llm_role_params.py tests/test_session_serialize.py tests/test_request_deadline.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1d-<unique>
```

---

## Next: 3.1e per-request LLM call/token budget

**Intent:** shared per-request budget for LLM calls and input/output tokens
across retries, grading, fact claims, agentic tools, streaming; exhaustion
must not finish as route=`auto`.

**Out of 3.1e:** live multi-service, push/deploy, inventing auto-delete.

---

## Do not

- Re-select **2.1–2.6g**, **3.1a–3.1d**
- Push / deploy / live without opt-in
