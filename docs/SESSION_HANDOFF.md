# Session handoff

**Обновлено:** 2026-08-07 — **Update-95** after **6.3** @ `d6e3a55`.

---

## 0. Routing

| Pri | Source |
|-----|--------|
| 1 | Actual Git |
| 2 | `AGENT_STATE.md` **Update-95** |
| 3 | This file + `PLAN_CLOSURE_STATUS.md` |
| 4 | `rag-remediation-plan-2026-08-03.md` (DoD direction) |

---

## 1. Facts

| | |
|--|--|
| Latest impl | `d6e3a55` — **6.3** independent judge fail-closed |
| Prior | `d0317e9` 6.2; `b3494a0` 6.1; `1cdecb2` 5.3 |
| Local complete | 2.1–2.6g + 3.1a–i + 4.1–4.5 + 5.1–5.3 + **6.1–6.3** |
| Production | **NOT** claimed |
| Next | **7.1** eval gate fail-closed on skip/infra |
| Gates | no push/deploy/live/migrate without opt-in |
| WIP | none |

**Verification (6.3):** 38+ focused passed; Ruff clean. Full suite not run.

---

## 2. Start next session

```text
1. One atomic slice per turn
2. cd D:\RAG_Support_Assistant ; git status ; git log -8
3. Read Update-95 + this §1–§6
4. Default: 7.1
5. Tests-first → gate → local commit → handoff → STOP
```

---

## 3. Residual

| § | Local | Open |
|---|-------|------|
| 1–5 | as before | live DoD / metrics |
| **6** | **6.1–6.3** | calibration; measured agentic eval |
| **7** | partial historical | **← 7.1** honest skip / infra fail-closed |
| 8–10 | partial / not started | as plan |

---

## 4. Recent ledger

| Slice | SHA |
|-------|-----|
| 6.1 | `b3494a0` |
| 6.2 | `d0317e9` |
| **6.3** | **`d6e3a55`** |

---

## 5. Contract 6.3 @ `d6e3a55`

- `agent/judge_policy.py`: `resolve_judge_llm`, `judge_fail_closed_fields`,
  `parse_judge_score` (no silent default)
- Setting `judge_independence_required` / `JUDGE_INDEPENDENCE_REQUIRED`
  (default true if `RAG_ENV=production`)
- Evaluate: both fast+strong; independent prefer; complex→judge fast
- Fail-closed: unavailable / LLM error / parse → quality 0, `unmeasured`,
  `not_verified`, `judge_status`
- `route_or_retry`: broken judge → **human** (no retry)
- State: `judge_status`, `judge_reason`, `judge_independent`

---

## 6. Owners

| Path | Role |
|------|------|
| `agent/judge_policy.py` | **6.3** |
| `agent/graph.py` | evaluate + route_or_retry |
| `config/settings.py` | `judge_independence_required` |
| `agent/response_safety.py` | 6.2 |

---

## 7. Invariants

…prior 1–13…  
14. **Judge unavailable/error/parse ≠ auto; ≠ silent score 50 with quality_source=llm**  
15. **When independence required, judge identity ≠ generator identity**  

---

## 8. Verify 6.3

```powershell
python -m pytest tests/test_judge_policy.py tests/test_grounding_fail_closed.py tests/test_citation_bound_grounding.py tests/test_graph_error_handling.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step6-3
python -m ruff check agent/judge_policy.py agent/graph.py agent/state.py config/settings.py tests/test_judge_policy.py
```

---

## 9. Next: 7.1 (not started)

**Name:** **7.1 — eval gate fail-closed on skip / infrastructure error**  
**Intent:** release/regression gate must not treat graceful skip or
evaluator/provider import failures as PASSED; no substituted 1.0 scores.

Out of scope without opt-in: live providers, full dataset expansion, push.

---

## 10–11. Protected / Do not

Dirty: BACKLOG, README, audit, plan_sol.  
Do not re-select **6.1–6.3** or earlier closed local slices. No push/live/migrate
without opt-in. One slice per turn.
