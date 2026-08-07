# Session handoff

**Обновлено:** 2026-08-07 (Update-90 — **5.2** citation-bound claims @
`50bb220`). Matrix: [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md).

**Routing:** top block [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-90**).

---

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest impl | `50bb220` — **5.2** citation-bound claim support |
| Previous | `7c53bdb` — **5.1** |
| Local bands | **2.x + 3.1* + 4.1–4.5 + 5.1–5.2** |
| Full plan / production | **NOT** complete / **NOT** claimed |
| Next (quality) | **5.3** grader / top-1 / all-rejected fail-closed |
| Gates | no push / deploy / live / migrate without **opt-in** |

**Verification (5.2):** 54 focused tests passed; Ruff clean.

---

## 5.2 contract (COMPLETE)

- Answer factual claims require `[N]` citations
- Evidence/claim text must match **cited** docs only (not uncited hits)
- Missing/invalid citations → `not_verified`; unbound claims block `auto`
- Helpers: `apply_citation_bound_claims`, `parse_answer_citation_indices`

```powershell
python -m pytest tests/test_citation_bound_grounding.py tests/test_grounding_fail_closed.py tests/test_fact_verification.py tests/test_graph_helpers.py tests/test_graph_error_handling.py tests/test_agent_tools.py tests/test_human_route_escalation.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step5-2-<unique>
python -m ruff check agent/grounding.py agent/graph.py
```

---

## Next: 5.3 only

Grader error, forced top-1, all-docs-rejected must not silently restore
original context as success → controlled rewrite / `not_verified` / human.

---

## Do not

- Claim plan closed after 5.2  
- Re-select 5.1–5.2 / 4.x / 3.x / 2.x  
- Push / deploy / live without opt-in  
