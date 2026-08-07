# Session handoff

**Обновлено:** 2026-08-07 (Update-83 after **4.1** @ `eaf41f3`; next **4.2**)

**Routing:** top [`AGENT_STATE.md`](../AGENT_STATE.md) **Update-83** only.

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest impl | `eaf41f3` — **4.1** single terminal answer/history on stream parity |
| Previous | `fe2f0aa` — **3.1i** |
| Local complete | **2.1–2.6g** + **3.1a–3.1i** + **4.1** (documented scopes) |
| Full §2/§3/§4 / release | **NOT** complete |
| Next | **4.2** reduce dual generation (graph-only tokens or drop parallel parity) |
| Gates | no push / deploy / live without opt-in |

**Verification 4.1:** 12 passed stream suite; Ruff clean.

### 4.1 contract

When `STREAMING_RAG_PARITY` graph returns non-empty answer:
- SSE `answer` + DB persist = graph answer (`answer_source=graph`)
- No second stream history append
- Metadata still from graph

When parity off/fails: stream answer + stream history (`answer_source=stream`).

Dual token generation (stream UX + parallel full ask) **still residual**.

```powershell
python -m pytest tests/test_streaming_rag_parity.py tests/test_stream_capacity_hold.py tests/test_chat_streaming.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step4-1-<unique>
```

### Next 4.2

Pick one atomic approach after reading plan §4:
1. Stream tokens from graph/node events only, **or**
2. Remove parallel full `session.ask` dual pass toward one path

Out of 4.2 without opt-in: escalation outbox, ticket_id, live multi-service.

### Do not

- Re-select 2.1–2.6g, 3.1a–3.1i, **4.1**
- Claim full §4 complete
- Push / deploy / live without opt-in
