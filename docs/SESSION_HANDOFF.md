# Session handoff

**Обновлено:** 2026-08-07 (Update-82 after completed **3.1i** @ `fe2f0aa`;
next ordered candidate **§4 first atomic slice / 4.1**)

**Routing:** top block [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-82** only).
Plan: untracked `rag-remediation-plan-2026-08-03.md` (no casual checkbox edits).

---

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest implementation | `fe2f0aa` — **3.1i** version CAS + sticky ids |
| Previous | `ab7b417` — **3.1h** reranker deadline |
| Locally complete | **2.1–2.6g** + **3.1a–3.1i** (documented scopes) |
| Full plan §2 / §3 / release | **NOT** complete (durable multi-replica store residual; live DoD open) |
| Next default | **§4 / 4.1** unified LangGraph sync/SSE (read DoD first) |
| Gates | no push / deploy / live services without opt-in |

**Verification (3.1i):** 34 passed focused/adjacent; Ruff clean.

### Plan §3 (honest)

| Bullet | Local | Residual |
|--------|-------|----------|
| executor + capacity | 3.1a, 3.1f | — |
| cooperative deadlines | 3.1b, 3.1f–h | — cooperative |
| session serialize / version / sticky | 3.1c + **3.1i** | multi-replica durable store; optional HTTP If-Match |
| role params | 3.1d | — |
| LLM budget | 3.1e–f | — |

### 3.1i contract @ `fe2f0aa`

- `mutation_version` property; `ask(expected_version=…)` CAS → `route=conflict` on mismatch
- Results stamp `session_version`; never `auto` on conflict
- `user_id`/`session_id` → `run_qa_pipeline` for sticky experiments
- Process-local only

```powershell
python -m pytest tests/test_session_version.py tests/test_session_serialize.py tests/test_agent_tools.py tests/test_request_deadline.py tests/test_llm_request_budget.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step3-1i-<unique>
```

### Next: §4.1 (default)

Read plan §4 DoD; pick **one** atomic boundary (e.g. remove parallel stream parity path **or** single history mutation rule). Tests-first. Alternate: durable multi-replica session version store design if user prioritizes.

### Do not

- Re-select 2.1–2.6g or **3.1a–3.1i**
- Claim full §3 complete (multi-replica durable residual)
- Push / deploy / live without opt-in
