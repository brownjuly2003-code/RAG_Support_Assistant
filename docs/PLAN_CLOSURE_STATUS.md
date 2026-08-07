# Plan closure status — honest residual matrix

**Date:** 2026-08-07  
**Plan:** [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)  
**Routing:** top block of [`AGENT_STATE.md`](../AGENT_STATE.md)  
**Rule:** checkboxes in the plan file stay open until **behavioral DoD + evidence**.  
Local code slices ≠ full plan section complete ≠ production release.

---

## Closure truth (executive)

| Plan § | Local implementation | Full section DoD | Blocks release |
|--------|----------------------|------------------|----------------|
| **1** live multi-tenant / backup / RPO | partial chart/docs only | **OPEN** (opt-in live) | **yes** Gate A |
| **2** index lifecycle | **2.1–2.6g local residual closed** | **OPEN** live PG/Redis/Celery/Chroma | yes for live index ops |
| **3** execution / session / budget | **3.1a–3.1i local** | **OPEN** multi-replica durable version | partial |
| **4** unified pipeline + escalation | **4.1–4.5 local** | **OPEN** true graph tokens; parity default off; schedule wiring | partial |
| **5** grounding fail-closed | **5.1 foundations (this turn)** | **OPEN** live metric thresholds / CI | **yes** quality |
| **6** judge / safety / agentic parity | not started | OPEN | yes |
| **7** eval gate fail-closed | partial historical | OPEN | yes |
| **8** widget / edge security | partial historical | OPEN | yes |
| **9** cache / architecture / SLO | partial historical | OPEN | soft |
| **10** final verification / canary | not started | OPEN | **yes** |

**Project / production release: NOT claimed and not claimable until §1 + §5–7 evidence + §10.**

---

## Quality-first closure order (decision)

User priority: **quality over speed**, close plan thoroughly.

Recommended sequence (local code first, live last):

1. **§5 grounding fail-closed** (5.1 foundations → 5.2 auto citation support → 5.3 grader fail-closed)
2. **§6 judge independence + pre-response safety + remove fixed agentic scores**
3. **§7 regression gate honest skip policy**
4. **§4 residual** graph-only default / true SSE tokens (pipeline honesty)
5. **§2/§3 residual** only if product needs multi-replica or live index drills
6. **§1 + §10** only with **explicit owner opt-in** (live PG, cluster, canary)

Do **not** fake-close §1 or §10 with mock-only evidence.

---

## §4 local ledger (done at documented scopes)

| Slice | SHA | Scope |
|-------|-----|-------|
| 4.1 | `eaf41f3` | single terminal/history when parity on |
| 4.2 | `f1c846e` | graph-only generation when parity on |
| 4.3 | `ad5e435` | durable idempotent escalation |
| 4.4 | `0371971` | auto human-route escalate on ask |
| 4.5 | `6453530` | outbox retry API |

Residual: Celery/cron for 4.5; true LangGraph token events; `STREAMING_RAG_PARITY` default still false.

---

## §5 progress

| Slice | Status | Contract |
|-------|--------|----------|
| **5.1** | **this turn** | `grounding_status` verified/unsupported/not_verified; no fake factuality 100 on skip/none/no-context; auto blocked unless grounding allows |
| 5.2 | not started | auto only when claims semantically supported by cited `[N]` docs |
| 5.3 | not started | grader/top-1/all-rejected fail-closed (no silent context restore) |
| 5.4 | not started | claim budget / evidence truncation → not_verified whole answer |
| Live DoD | opt-in | precision/recall/faithfulness thresholds × 3 runs |

---

## What “plan closed” means (definition used here)

The plan is **closed** only when:

1. Every section’s **Проверка** has fresh evidence artifacts, and  
2. Gate A–D / §10 checklist is signed, and  
3. `unverified auto-rate = 0` on the release gate, and  
4. No production claim rests on graceful skip, fixed agentic scores, or self-judge without calibration.

Until then status remains **ACTIVE** with honest local residual progress.

---

## External gates (never auto)

- `alembic upgrade` 019–023 on real Postgres  
- Live Redis/Celery/Chroma/worker drills  
- Docker/kind install, restore, RPO/RTO  
- Push, deploy, canary, production release  
- Live Mistral/GraceKelly benchmark as sole quality proof  

---

## Protected / process

- One named atomic slice per user turn (workspace cycle budget).  
- Do not casually checkbox the plan file.  
- Dirty `BACKLOG.md` / `README.md` / audits: do not treat as queue.  
- Actual Git wins over embedded SHAs in handoff.
