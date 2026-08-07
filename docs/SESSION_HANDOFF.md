# Session handoff

**Обновлено:** 2026-08-07 (Update-89 — **5.1** grounding fail-closed @
`7c53bdb`). Closure matrix: [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md).

**Routing:** only top block of [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-89**). Plan file checkboxes — **do not** casual-edit.

---

## Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest impl | `7c53bdb` — **5.1** grounding fail-closed |
| Previous | `6453530` — 4.5 outbox retry |
| Local bands | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.5** + **5.1** |
| Full plan / production | **NOT** complete / **NOT** claimed |
| Next (quality path) | **5.2** citation-bound claim support for auto |
| Gates | no push / deploy / live / migrate without **opt-in** |

**Verification (5.1):** 45 focused tests passed; Ruff clean. Full suite not run.

---

## Почему план ещё не «закрыт»

См. [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md). Кратко:

- **§1 / §10** требуют live evidence + owner opt-in  
- **§5** full DoD = live metrics (precision/recall/faithfulness) — 5.1 только foundations  
- **§6–§7** judge/safety/eval gate — not started  
- Local slices ≠ production release  

Quality-first order: **5.2 → 5.3 → §6 → §7 → §4 residual → live §1/§10**.

---

## 5.1 contract (COMPLETE)

- `agent/grounding.py` + `grounding_status` on `GraphState`
- No fake factuality 100 on skip/disabled/no-context/short/truncation
- `NONE` → verified + score 0 (vacuous)
- `route_or_retry` auto only with `grounding_allows_auto`

```powershell
python -m pytest tests/test_grounding_fail_closed.py tests/test_fact_verification.py tests/test_graph_helpers.py tests/test_graph_error_handling.py tests/test_agent_tools.py tests/test_human_route_escalation.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step5-1-<unique>
python -m ruff check agent/grounding.py agent/state.py agent/graph.py
```

---

## Next: 5.2 only (default)

**Name:** citation-bound claim support for auto  
**Intent:** substantial claims must map to supporting cited documents `[N]`;
mismatched or missing citation support → `not_verified` / not auto.  
**Out:** live benchmarks as sole gate; re-select 5.1/4.x/3.x/2.x.

---

## Do not

- Claim plan closed / production ready after 5.1  
- Grep old `START HERE` for work selection  
- Push / deploy / live multi-service / migrate without opt-in  
