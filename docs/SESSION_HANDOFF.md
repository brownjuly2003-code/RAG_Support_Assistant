# Session handoff

**Обновлено:** 2026-08-07 — **Update-94** after **6.2** @ `d0317e9`.  
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей
истории AGENT_STATE.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -8 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-94**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — DoD, не очередь галочек |

**Не использовать:** старые `✅ START HERE` ниже Update-94; dirty
`BACKLOG.md` / audits; `_NEXT_SESSION.md` как единственный SoT.

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **implementation** | `d0317e9` — **6.2** pre-response PII/injection |
| Previous | `b3494a0` — **6.1**; `1cdecb2` — **5.3** |
| Locally complete | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.5** + **5.1–5.3** + **6.1–6.2** |
| Full plan / production | **NOT** complete / **NOT** claimed |
| Next ordered | **6.3** independent judge policy fail-closed |
| Gates | **no** push / deploy / live / migrate without **explicit opt-in** |
| WIP | **none** |

**Last known verification (6.2):** focused **50+15 passed**; Ruff clean.
Full suite / live **not** run.

---

## 2. Быстрый старт следующей сессии

```text
1. One named atomic slice per user turn.
2. cd D:\RAG_Support_Assistant
3. git status --short --branch ; git log -8 --oneline
4. Read Update-94 + this file §1–§6
5. Default work: 6.3. Announce: slice 1/1
6. Tests-first → proportional gate → local commit only
7. Handoff refresh; STOP after one slice
```

---

## 3. Honest residual (plan sections)

| Plan § | Local | Residual |
|--------|-------|----------|
| **1** | partial | opt-in live Gate A |
| **2–3** | 2.1–2.6g, 3.1a–i | live drills; multi-replica |
| **4** | 4.1–4.5 | graph tokens; parity default off; outbox schedule |
| **5** | 5.1–5.3 | live metrics DoD |
| **6** | **6.1–6.2** | **6.3** judge; calibration; measured agentic eval |
| **7–10** | partial / not started | as plan |

---

## 4. Implementation ledgers (recent)

| Slice | SHA | Surface |
|-------|-----|---------|
| 5.3 | `1cdecb2` | grader fail-closed |
| **6.1** | `b3494a0` | agentic unmeasured gate |
| **6.2** | **`d0317e9`** | pre-response PII + prompt-injection |

---

## 5. Contracts (latest)

### 6.2 @ `d0317e9`

- Module: `agent/response_safety.py`
- `evaluate_pre_response_safety` / `apply_pre_response_safety`
- **PII only** → `safety_action=redact`, answer via `utils.pii.redact_pii`,
  route may stay `auto`/`agentic`
- **Injection** (answer or context docs) → `refuse` + `route=human`,
  quality 0, `not_verified`, fixed refusal text
- Graph: `route_or_retry` → `response_safety` → suggest|log
- Agentic: `_finalize_agentic_terminal` on all terminals
- Confirmation UX: PII redact only (skip injection refuse)
- State: `safety_action`, `safety_reasons`

### 6.1 @ `b3494a0`

- `_agentic_unmeasured_gate()` — never auto on unmeasured scores

---

## 6. Module owners

| Path | Role |
|------|------|
| `agent/response_safety.py` | **6.2** pre-response safety |
| `agent/graph.py` | safety node + agentic finalize |
| `utils/pii.py` | PII detect/redact (reused) |
| `agent/grounding.py` | 5.1–5.2 |

---

## 7. Key invariants (do not regress)

1–11 as before (budget, grounding, agentic unmeasured, …)  
12. **PII in terminal answer must be redacted before delivery**  
13. **Prompt-injection markers in answer/context → refuse + human, never auto**  

---

## 8. Verification recipes

### §6.2 band

```powershell
python -m pytest tests/test_response_safety.py tests/test_agent_tools.py tests/test_pii.py tests/test_graph_error_handling.py tests/test_grounding_fail_closed.py tests/test_human_route_escalation.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step6-2-<unique>
python -m ruff check agent/response_safety.py agent/graph.py agent/state.py tests/test_response_safety.py
```

---

## 9. Next named candidate: 6.3 (not started)

**Name:** **6.3 — independent judge policy fail-closed**  
**Why next:** plan §6; same-model self-approval and judge outage must not yield
heuristic auto.

### Intent

1. Production policy: judge independent of generator/fact-checker (model/provider).  
2. Judge unavailable → `not_verified` / human, not auto.  
3. Tests-first; no full live calibration artifact in the same slice unless
   scoped tightly.  
4. Do not re-select 6.1/6.2.

### Out of 6.3 without opt-in

- live multi-service / migrate / push / deploy  
- full human-labelled calibration set (can be later 6.x)  

---

## 10. Protected dirty / untracked

**Dirty:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`  
**Untracked:** plan file, `_NEXT_SESSION.md`, pytest temps, presentations  

---

## 11. Do not

- Re-select **2.x / 3.1* / 4.1–4.5 / 5.1–5.3 / 6.1 / 6.2**  
- Claim plan closed or production ready  
- Push / deploy / live / migrate without opt-in  
- Second named slice in the same user turn  
