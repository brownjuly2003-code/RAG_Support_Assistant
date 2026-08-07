# Session handoff

**Обновлено:** 2026-08-07 — **Update-93** after **6.1** @ `b3494a0`.  
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей
истории AGENT_STATE.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -8 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-93**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — **направление DoD**, не очередь галочек |

**Не использовать:** старые `✅ START HERE` ниже Update-93; dirty
`BACKLOG.md` / `README.md` / audits; `_NEXT_SESSION.md` как единственный SoT
(это pointer only).

**Plan checkboxes:** не править casually. Local slice ≠ section closed ≠ release.

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **implementation** | `b3494a0` — **6.1** agentic unmeasured fail-closed |
| Previous quality path | `1cdecb2` — **5.3** grader fail-closed |
| Branch advisory | was `master...origin/master [ahead 163]` — **refresh mandatory** |
| Active writer / WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.5** + **5.1–5.3** + **6.1** |
| Full plan §1–§10 / production | **NOT** complete / **NOT** claimed |
| Plan status | **ACTIVE** |
| Next ordered (quality path) | **6.2** pre-response PII / prompt-injection |
| Gates | **no** push / deploy / live multi-service / migrate 019–023 without **explicit opt-in** |

**Last known verification (6.1):** focused **45 passed** (`test_agent_tools` +
graph helpers + human-route + grounding fail-closed + citation-bound); Ruff
clean on touched paths. Full suite / live drills **not** run.

---

## 2. Быстрый старт следующей сессии

```text
1. Cycle-guard: one named atomic slice per user turn.
2. cd D:\RAG_Support_Assistant
3. git status --short --branch
4. git log -8 --oneline          # actual Git wins
5. Read ONLY top Update-93 in AGENT_STATE.md + this file §1–§6
6. Default work: 6.2 (below). Announce: slice 1/1
7. Tests-first → proportional gate → local commit only (no push)
8. Optional handoff refresh; STOP after one slice
```

**Not authorized without opt-in:** push, deploy, live PostgreSQL/Redis/Celery/
Chroma, `alembic upgrade` (incl. **019–023**), destructive Git, production
claims, bulk plan checkbox edits.

---

## 3. Honest residual (plan sections)

| Plan § | Local | Residual / blockers |
|--------|-------|---------------------|
| **1** live multi-tenant / backup / RPO | partial chart/docs | **opt-in live** — Gate A open |
| **2** index lifecycle | **2.1–2.6g** local residual closed | live PG/Redis/Celery/Chroma drills |
| **3** execution / session / budget | **3.1a–3.1i** local | multi-replica durable session version |
| **4** pipeline + escalation | **4.1–4.5** local | true graph tokens; parity default off; Celery/cron for outbox retry |
| **5** grounding fail-closed | **5.1–5.3** local | live metrics DoD; relevance≠quality residual |
| **6** judge / safety / agentic | **6.1** local | **6.2** PII/injection; independent judge; measured agentic evaluate |
| **7** eval gate | partial historical | honest skip policy; dataset expansion |
| **8–9** widget / cache / SLO | partial historical | as plan |
| **10** final verification | not started | after 1–9 + opt-in evidence |

**Release / production: NOT claimable** until §1 + §5 live quality + §6–7 + §10.

Full matrix: [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md).

---

## 4. Implementation ledgers (impl SHAs only)

### §3 runtime

| Slice | SHA | Surface |
|-------|-----|---------|
| 3.1a | `a21f364` | shared request executor; `/api/ask` capacity hold |
| 3.1b | `76179d5` | ContextVar deadline; provider fail-closed |
| 3.1c | `d9ba87e` | per-session turn lock + epoch |
| 3.1d | `48c2381` | per-role temperature/max_tokens |
| 3.1e | `b98b917` | per-request LLM budget → `route=human` |
| 3.1f | `2581855` | stream capacity hold + budget/deadline bind |
| 3.1g | `ae13000` | retrieve + tools + stream.retrieve deadline |
| 3.1h | `ab7b417` | hybrid `_rerank` deadline |
| 3.1i | `fe2f0aa` | session version CAS + sticky ids |

### §4 pipeline + escalation

| Slice | SHA | Surface |
|-------|-----|---------|
| 4.1 | `eaf41f3` | single terminal answer/history when stream parity on |
| 4.2 | `f1c846e` | graph-only generation when parity on |
| 4.3 | `ad5e435` | durable idempotent escalation service |
| 4.4 | `0371971` | auto-escalate terminal human/error on normal ask |
| 4.5 | `6453530` | outbox retry API (`retry_failed_deliveries`) |

### §5 grounding

| Slice | SHA | Surface |
|-------|-----|---------|
| **5.1** | `7c53bdb` | `grounding_status`; no fake factuality 100; auto gate |
| **5.2** | `50bb220` | claims bound to answer `[N]` cited docs only |
| **5.3** | `1cdecb2` | grader fail-closed; no top-1 force; no empty→raw restore |

### §6 judge / safety / agentic

| Slice | SHA | Surface |
|-------|-----|---------|
| **6.1** | **`b3494a0`** | agentic unmeasured gate; no fixed 80/85/90; never auto unmeasured |

---

## 5. Contracts (latest complete slices)

### 6.1 @ `b3494a0`

- Helper: `agent/graph.py::_agentic_unmeasured_gate()`
- All agentic terminals set:
  - `quality_source="unmeasured"`
  - `quality_score=0`, `relevance_score=0.0`
  - `grounding_status="not_verified"`, `factuality_score=0`
  - `route="agentic"` (**never** `auto` without measured evaluate/grounding)
- Removed hardcoded 80/85/90 and `quality_source="fixed"` from agentic flow
- Ticket confirm/cancel and keyword order path no longer claim `route=auto`
- `GraphState.quality_source` allows `"unmeasured"`
- Static AST/string guard in `tests/test_agent_tools.py`

### 5.3 @ `1cdecb2`

- Module: `agent/doc_grade.py`
- Grader LLM error → **reject** document (not accept)
- No forced top-1 re-injection after rejection
- Outcomes: `ok` | `empty_retrieval` | `all_rejected` | `grader_error` | `partial_grader_error`
- Empty graded after grade ≠ silent restore of raw context

### 5.2 / 5.1

- Citation-bound claims; `verified` | `unsupported` | `not_verified`
- Never factuality 100 on skip/disabled/no-context/short/truncation

---

## 6. Module owners (do not reopen without conflict)

| Path | Slices | Role |
|------|--------|------|
| `agent/grounding.py` | 5.1–5.2 | grounding status + citation bind + auto gate |
| `agent/doc_grade.py` | **5.3** | grade outcomes + generation doc selection |
| `agent/graph.py` | 3.1*, 4.3, 5.1–5.3, **6.1** | nodes + agentic unmeasured gate |
| `agent/state.py` | 3.1i, 4.3, 5.1, 5.3, **6.1** | GraphState fields |
| `services/escalation.py` | 4.3–4.5 | durable ticket + outbox retry |
| `api/routers/conversation.py` | 3.1a/f, 4.1–4.4, 6.1 note | ask/stream + escalate |
| job-object / index stack | 2.1–2.6g | **do not re-select** |

---

## 7. Key invariants (do not regress)

1. Failed jobs with `source_path` match → `retained_after_failed_transition`; not auto-delete  
2. LLM budget exhaust → `route=human` / never `auto`  
3. Deadline fail-closed at provider/retrieve/tool/rerank  
4. Stream parity on → single graph generation + single terminal/history  
5. Escalation: no «передан оператору» without durable ticket  
6. Normal ask `route=human` → durable ticket (`human_route`)  
7. No fake factuality 100 on skip/disabled/no-context  
8. Claims need cited `[N]` docs for auto  
9. Empty graded after grade ≠ silent restore of raw context  
10. Simple path without verify ≠ auto  
11. **Agentic unmeasured path ≠ `route=auto` and ≠ fake quality 80/85/90**  

---

## 8. Verification recipes (last known green; re-run when coding)

### §6.1 band

```powershell
python -m pytest tests/test_agent_tools.py tests/test_graph_helpers.py tests/test_human_route_escalation.py tests/test_grounding_fail_closed.py tests/test_citation_bound_grounding.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step6-1-<unique>
python -m ruff check agent/graph.py agent/state.py api/routers/conversation.py tests/test_agent_tools.py
```

### §5 band (5.1–5.3)

```powershell
python -m pytest tests/test_doc_grade_fail_closed.py tests/test_grade_docs.py tests/test_provider_graph_integration.py tests/test_model_routing.py tests/test_grounding_fail_closed.py tests/test_fact_verification.py tests/test_citation_bound_grounding.py tests/test_graph_error_handling.py tests/test_agent_tools.py tests/test_human_route_escalation.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step5-band-<unique>
```

Full suite / live / migrate — **not** the default gate for a single slice.

---

## 9. Next named candidate: 6.2 (not started)

**Name:** **6.2 — pre-response PII / document prompt-injection checks**  
**Why next:** plan §6; runtime protection before terminal answer, not only
post-response monitoring.

### Intent

1. Run PII + document prompt-injection checks **before** delivering terminal
   answer (normal + agentic paths as applicable).  
2. Policy explicitly chooses redact / refuse / human.  
3. Tests-first fail-closed: injected or PII-leaking answer cannot silently
   ship as clean `auto`.  
4. Do **not** invent full independent judge or live calibration in the same
   slice.

### Out of 6.2 without opt-in

- independent production judge policy (later 6.x)  
- live benchmarks  
- re-select 2.x / 3.1* / 4.1–4.5 / 5.1–5.3 / **6.1**  

### Alternates (only if user prioritizes)

- independent judge policy  
- **4.6** Celery/cron wiring for `retry_failed_deliveries`  
- stream graph-only default (`STREAMING_RAG_PARITY`)  
- live §1 / migrate 019–023 (**explicit opt-in only**)  

---

## 10. Protected dirty / untracked

**Dirty tracked (do not stage without request):**  
`BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`

**Untracked (do not treat as queue):**  
`rag-remediation-plan-2026-08-03.md` (active plan), `_NEXT_SESSION.md` (pointer),
`.pytest_tmp*/`, presentations, architecture HTML, `.grok-prompts/`, etc.

---

## 11. Do not

- Grep old `✅ START HERE` for work selection  
- Re-select **2.1–2.6g**, **3.1a–3.1i**, **4.1–4.5**, **5.1–5.3**, **6.1**  
- Claim full plan §2/§3/§4/§5/§6 or production readiness  
- Edit plan checkboxes casually  
- Push / deploy / live multi-service / migrate without explicit opt-in  
- Start a second named slice in the same user turn  
