# Plan closure status — honest residual matrix

**Date:** 2026-08-07 (Update-95 after 6.3)  
**Plan file:** [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)  
**Routing:** top block of [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-95**)  
**Session capsule:** [`SESSION_HANDOFF.md`](SESSION_HANDOFF.md)

**Rules:**

1. Checkboxes in the plan file stay open until **behavioral DoD + evidence**.  
2. Local code slice ≠ full plan section complete ≠ production release.  
3. Actual Git wins over any SHA embedded here.  
4. Quality > speed; one named atomic slice per user turn.

---

## Closure truth (executive)

| Plan § | Local implementation | Full section DoD | Blocks release |
|--------|----------------------|------------------|----------------|
| **1** live multi-tenant / backup / RPO | partial chart/docs only | **OPEN** (opt-in live) | **yes** Gate A |
| **2** index lifecycle | **2.1–2.6g local residual closed** | **OPEN** live PG/Redis/Celery/Chroma | yes for live index ops |
| **3** execution / session / budget | **3.1a–3.1i local** | **OPEN** multi-replica durable version | partial |
| **4** unified pipeline + escalation | **4.1–4.5 local** | **OPEN** true graph tokens; parity default off; schedule wiring | partial |
| **5** grounding fail-closed | **5.1–5.3 local** | **OPEN** live metric thresholds ×3 runs | **yes** quality |
| **6** judge / safety / agentic parity | **6.1–6.3 local** | OPEN (calibration / measured agentic) | **yes** |
| **7** eval gate fail-closed | partial historical | OPEN | **yes** |
| **8** widget / edge security | partial historical | OPEN | yes |
| **9** cache / architecture / SLO | partial historical | OPEN | soft |
| **10** final verification / canary | not started | OPEN | **yes** |

**Project / production release: NOT claimed.**

Not claimable until §1 live evidence + §5 live quality metrics + §6–7 + §10.

---

## Quality-first closure order (standing decision)

User priority: **quality over speed**, close plan thoroughly and honestly.

| Order | Work | Status |
|-------|------|--------|
| 1 | §5.1 grounding foundations | **done** `7c53bdb` |
| 2 | §5.2 citation-bound claims | **done** `50bb220` |
| 3 | §5.3 grader fail-closed | **done** `1cdecb2` |
| 4 | §6.1 remove agentic fixed quality scores | **done** `b3494a0` |
| 5 | §6.2 pre-response PII / prompt-injection | **done** `d0317e9` |
| 6 | §6.3 independent judge policy | **done** `d6e3a55` |
| 7 | §6.x calibration + measured agentic evaluate | not started |
| 8 | **§7.1 eval gate fail-closed skip/infra** | **← next** |
| 9 | §4 residual (graph-only default / true SSE tokens) | residual |
| 10 | §2/§3 residual if product needs | residual |
| 11 | §1 + §10 | **opt-in live only** |

Do **not** fake-close §1 or §10 with mock-only evidence.

---

## §2 map (honest — live DoD open)

| Bullet | Local | Residual |
|--------|-------|----------|
| inventory / retention / operator / lifecycle | through 2.5b + related | live DoD; no job-object delete execute HTTP; no real FS delete |
| fault injection | **2.6a–2.6g** | local residual closed |
| live PG/Redis/Celery/Chroma + migrations | not started | **opt-in**; migrations **019–023** on disk |

**Invariant:** failed jobs with `source_path`-matched job-objects →
`retained_after_failed_transition`; `auto_delete_eligible` always false.

Last §2 fault-injection impl: `f347feb` (**2.6g**). **Do not re-select 2.x.**

---

## §3 map + ledger

| Bullet | Local slices | Residual |
|--------|--------------|----------|
| shared executor + capacity until work done | 3.1a, 3.1f | — documented |
| cooperative deadline provider/retrieve/tool/rerank | 3.1b, 3.1f–h | cooperative only |
| session serialize / version / sticky | 3.1c, 3.1i | multi-replica durable store; optional HTTP If-Match |
| max_tokens/temperature per role | 3.1d | — |
| per-request LLM budget | 3.1e, 3.1f | — |

| Slice | SHA |
|-------|-----|
| 3.1a | `a21f364` |
| 3.1b | `76179d5` |
| 3.1c | `d9ba87e` |
| 3.1d | `48c2381` |
| 3.1e | `b98b917` |
| 3.1f | `2581855` |
| 3.1g | `ae13000` |
| 3.1h | `ab7b417` |
| 3.1i | `fe2f0aa` |

---

## §4 map + ledger

| Bullet | Local | Residual |
|--------|-------|----------|
| LangGraph sole path; SSE transmits | partial 4.1–4.2 | true node/token events; legacy stream when parity **off** (default) |
| one terminal + one history | 4.1–4.2 when parity **on** | dual path when parity off |
| idempotent ticket + outbox | 4.3 + 4.5 retry API | Celery/cron/HTTP invoke; multi-row outbox table optional |
| ticket_id + delivery_state; no false claim | 4.3–4.4 | live migrate 023 opt-in |
| auto-escalate human/error on normal ask | 4.4 | stream-path parity if needed |

| Slice | SHA | What |
|-------|-----|------|
| 4.1 | `eaf41f3` | single terminal/history when parity succeeds |
| 4.2 | `f1c846e` | graph-only generation when parity on |
| 4.3 | `ad5e435` | durable idempotent escalation |
| 4.4 | `0371971` | auto human-route on normal ask |
| 4.5 | `6453530` | outbox retry without second ticket |

---

## §5 map + ledger (quality path)

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **5.1** | **done** | `7c53bdb` | `grounding_status`; no fake factuality 100; auto requires grounding_allows_auto |
| **5.2** | **done** | `50bb220` | claims bound to answer `[N]`; cited docs only |
| **5.3** | **done** | `1cdecb2` | grader error rejects; no forced top-1; no empty-graded→raw restore |
| 5.4 | largely covered by 5.1 truncation + 5.2 | — | claim-budget truncation already forces not_verified; no separate slice unless gaps found |
| Live DoD | **open** | — | precision ≥0.63, recall ≥0.97, FULL≥97, faithfulness≥0.90, … ×3 runs |

**§5 local residual (not live):**

- `relevance_score` still derived from quality/100 in evaluate (plan wants split)  
- simple path skips verify → cannot auto (by design after 5.1–5.3)  

---

## §6 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **6.1** | **done local** | `b3494a0` | unmeasured agentic gate; no fixed 80/85/90; never auto without measure |
| **6.2** | **done local** | `d0317e9` | pre-response PII redact + injection refuse→human; graph + agentic |
| **6.3** | **done local** | `d6e3a55` | independent judge policy; fail-closed on unavailable/error/parse |
| 6.x | not started | — | calibration; measured agentic evaluate when context exists |

**6.1 residual:** agentic not yet full evaluate/grounding when KB context exists.  
**6.2 residual:** pattern-based injection (not ML); online evaluators monitoring-only.  
**6.3 residual:** dual-model profiles cannot fully separate judge vs fact-checker
vs generator three ways; calibration artifact not built.

---

## What “plan closed” means

The plan is **closed** only when:

1. Every section’s **Проверка** has fresh evidence artifacts, and  
2. Gate A–D / §10 checklist is signed, and  
3. `unverified auto-rate = 0` on the release gate, and  
4. No production claim rests on graceful skip, fixed agentic scores, or
   self-judge without calibration.

Until then status remains **ACTIVE**.

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
- Dirty `BACKLOG.md` / `README.md` / audits: **not** the work queue.  
- Actual Git wins over embedded SHAs.  
- Prefer Grok implements; local commit only unless user opts into push.  
