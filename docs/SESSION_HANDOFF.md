# Session handoff

**Обновлено:** 2026-08-08 — **Update-121** after **5.4** @ `4f95e18`  
(independent retrieval relevance).  
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей  
истории `AGENT_STATE.md`.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -12 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-121**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — **DoD**, не очередь галочек |

**Не использовать:** старые `✅ START HERE` ниже Update-121; dirty  
`BACKLOG.md` / `README.md` / audits; `_NEXT_SESSION.md` как единственный SoT.

**Plan checkboxes:** не править casually. Local slice ≠ section closed ≠ release.

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **implementation** | `4f95e18` — **5.4** independent retrieval relevance |
| Prior implementations | `fc7f07b` **4.8** · `6b91a35` **4.7** · `c707c46` **6.7** |
| Latest **docs before this Update** | `cf12230` — Update-120 |
| Branch advisory | refresh `git status` / `git log` — **actual Git wins** |
| Active writer / WIP | **none** |
| Locally complete | **2.1–2.6g** + **3.1a–i** + **4.1–4.8** + **5.1–5.4** + **6.1–6.7** + **7.1–7.7** + **8.1–8.5** + **DEP-01** |
| Full plan / production | **NOT** complete / **NOT** claimed |
| Next ordered (default) | human sample **or** live execute (opt-in) **or** live metrics ×3 **or** Astro7 / parity-default |
| Gates | **no** push / deploy / live / migrate without **explicit opt-in** |

**Last known verification (5.4):** relevance + agentic + grounding/judge  
**56 passed**; Ruff clean. Full suite / live / push **not** claimed.

---

## 2. Быстрый старт следующей сессии

```text
1. One named atomic slice per user turn.
2. cd D:\RAG_Support_Assistant
3. git status --short --branch ; git log -12 --oneline
4. Read ONLY top Update-121 in AGENT_STATE.md + this file
5. ONE next pick → tests-first → local commit only
6. STOP after one slice
```

---

## 3. Honest residual

| Plan § | Local | Residual |
|--------|-------|----------|
| **1** | partial | opt-in live Gate A |
| **2** | 2.1–2.6g | live multi-service |
| **3** | 3.1a–i | multi-replica (DEFER without SLA) |
| **4** | **4.1–4.8** | parity default still **off** |
| **5** | **5.1–5.4** | live precision/recall/faithfulness ×3 |
| **6** | **6.1–6.7** | production human dual-annotator sample |
| **7** | **7.1–7.7** | live execute; mock≠release |
| **8** | **8.1–8.5** | live IdP; prod origins |
| **9** | partial + DEP-01 | Astro7; cache/SLO |
| **10** | not started | after 1–9 |

---

## 4. Recent impl ledger

| Slice | SHA |
|-------|-----|
| **5.4** | **`4f95e18`** independent retrieval relevance |
| **4.8** | `fc7f07b` provider token stream |
| **4.7** | `6b91a35` graph node SSE |
| **6.7** | `c707c46` human calibration readiness |
| **7.7** | `47e255a` curated depth |
| **8.5** | `4d6be52` Playwright E2E |
| DEP-01 | `f622d58` docs-site high=0 |

### 5.4 contract

- `agent/relevance.py` — never `quality/100`
- Sources: empty / retrieval_scores / graded_fraction / context_kept / unmeasured
- Wired: evaluate, agentic evaluate, agentic measure
- Residual: live metrics DoD ×3

---

## 5. Next pick (one only)

1. **Real dual-annotator human sample** →  
   `python scripts/recalibrate_routing.py --mode reissue --require-human --write`
2. **Live provider execute** (opt-in + secrets + `--execute`)
3. **Live quality metrics** scaffold/runs (×3 DoD)
4. **Astro 7** / product decision `STREAMING_RAG_PARITY=true`

### Do not re-select

2.x–3.x, **4.1–4.8**, **5.1–5.4**, 6.1–6.7, 7.1–7.7, 8.1–8.5, DEP-01

### Out without opt-in

push · deploy · live multi-service · live provider · alembic 019–023 · production claims

---

## 6. Protected dirty / untracked

Dirty: `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`  
Untracked: plan file, `_NEXT_SESSION.md`, pytest temps, presentations

---

## 7. One-screen honesty

| Claim | Truth |
|-------|-------|
| Plan closed? | **No** |
| Production ready? | **No** |
| Relevance ≠ quality/100? | **Yes local** (5.4) |
| Live quality metrics ×3? | **No** |
| Human calibration DoD? | **No** |
| Provider token stream? | **Yes local** (4.8) |
| Parity default ON? | **No** |
