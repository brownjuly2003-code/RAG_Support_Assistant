# Session handoff

**Обновлено:** 2026-08-07 (Update-85 after **4.3** @ `ad5e435`; next **4.4**)

**Routing:** top [`AGENT_STATE.md`](../AGENT_STATE.md) **Update-85** only.

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest impl | `ad5e435` — **4.3** durable idempotent escalation |
| Previous | `f1c846e` — **4.2** graph-only stream parity |
| Local complete | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.3** (documented scopes) |
| Full §2/§3/§4 / release | **NOT** complete |
| Next | **4.4** auto-escalate human routes **or** outbox retry worker |
| Gates | no push / deploy / live / migrate without opt-in |

**Verification 4.3:** 21 passed focused; Ruff clean. Migration **023** not applied.

### 4.3 contract

- `services/escalation.create_escalation` — durable ticket first, inbox second
- `idempotency_key` — retry does not double-create
- `delivery_state`: pending | delivered | failed | duplicate
- No "передан оператору" without durable ticket
- Wired: manual `/api/escalate`, pipeline exception `/api/ask`, graph `handle_error`, agentic `create_ticket`
- Response fields: `ticket_id`, `delivery_state`

```powershell
python -m pytest tests/test_escalation_service.py tests/test_pipeline_exception_escalation.py tests/test_graph_error_handling.py tests/test_agent_tools.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step4-3-<unique>
```

### Next 4.4

- Auto-call escalation service on terminal `route=human` from normal ask (not only exceptions), **or**
- Background outbox retry for `delivery_state=failed`

### Do not

- Re-select 4.1–4.3 or 3.1*
- Apply migration 023 / live PG without opt-in
- Push / deploy without opt-in
