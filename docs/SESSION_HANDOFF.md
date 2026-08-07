# Session handoff

**Обновлено:** 2026-08-07 (Update-84 after **4.2** @ `f1c846e`; next **4.3**)

**Routing:** top [`AGENT_STATE.md`](../AGENT_STATE.md) **Update-84** only.

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest impl | `f1c846e` — **4.2** graph-only generation when parity on |
| Previous | `eaf41f3` — **4.1** terminal ownership |
| Local complete | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.2** (documented scopes) |
| Full §2/§3/§4 / release | **NOT** complete |
| Next | **4.3** durable escalation / outbox (+ ticket_id delivery) |
| Gates | no push / deploy / live without opt-in |

**Verification 4.2:** 13 passed stream suite; Ruff clean.

### 4.2 contract

`STREAMING_RAG_PARITY=true`:
- Only `session.ask` generates (no parallel stream retrieve/LLM)
- SSE tokens = chunks of graph answer (`generation_source=graph_only`)
- Graph fail/timeout → SSE error, no dual-generation fallback

Parity off: legacy direct stream (`generation_source=stream`).

```powershell
python -m pytest tests/test_streaming_rag_parity.py tests/test_stream_capacity_hold.py tests/test_chat_streaming.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step4-2-<unique>
```

### Next 4.3

Plan §4 escalation: idempotent ticket/inbox service + transactional outbox;
return `ticket_id` + delivery state; no operator-sent claim before durable insert.

### Do not

- Re-select 2.1–2.6g, 3.1a–3.1i, **4.1**, **4.2**
- Claim full §4 complete
- Push / deploy / live without opt-in
