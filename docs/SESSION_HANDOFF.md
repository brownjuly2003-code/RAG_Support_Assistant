# Session handoff

**Обновлено:** 2026-08-07 (Update-88 — record completed slice **4.5** @
`6453530`). Next: **§5 / 5.1** grounding **or** **4.6** retry wiring **or**
stream graph-only default.

**Назначение:** самодостаточный next-session handoff.  
**Routing:** только верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md)
(**Update-88**). Любые старые `✅ START HERE` ниже — **archival**.  
**Plan (untracked/protected):**
[`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)
— **не** править checkboxes casually.

---

## Нулевая неоднозначность (сканируй первой)

| Факт | Значение |
|------|----------|
| Latest **implementation** | `6453530` — **4.5** outbox retry for failed deliveries |
| Previous impl | `0371971` — **4.4** auto human-route escalate |
| This Update-88 docs SHA | **unknown in-file** → `git log -5 --oneline` |
| Branch advisory | was `master...origin/master [ahead 154]` after impl — **refresh** |
| Active writer / WIP | **none** |
| Locally complete (documented scopes only) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.5** |
| Full plan §2 / §3 / §4 | **NOT** complete |
| Project / release / production | **NOT** claimed |
| Next ordered | **§5 / 5.1** grounding **or** **4.6** schedule wiring **or** stream default |
| Gates | no push / deploy / live multi-service / migrate 019–023 without **explicit opt-in** |

**Last known verification (4.5):** focused **30 passed** (outbox retry +
escalation service + human-route + pipeline exception + graph error + agent
tools); Ruff clean. Full suite / live drills **not** run.

**Key ingestion invariant (unchanged):** failed jobs with `source_path`-matched
job-objects → `retained_after_failed_transition`; `auto_delete_eligible`
always `False`.

---

## Быстрый старт следующей сессии

1. **One named atomic slice per user turn**.
2. `cd D:\RAG_Support_Assistant`
3. `git status --short --branch` and `git log -8 --oneline` (**actual Git wins**).
4. Read **only** top **Update-88** in `AGENT_STATE.md` + this capsule.
5. Default work: pick next candidate below. Announce `slice 1/1`.
6. Tests-first → proportional gate → local commit only (no push).
7. Optional handoff refresh; **stop/yield** after one slice.

**Not authorized without explicit opt-in:** push, deploy, live
PostgreSQL/Redis/Celery/Chroma, `alembic upgrade` (incl. **019–023**),
destructive Git, production claims.

---

## Plan §4 map (honest)

| Plan §4 bullet | Local | Residual |
|----------------|-------|----------|
| LangGraph sole execution; SSE transmits | partial **4.1–4.2** | true node/token events; legacy stream when parity off |
| one terminal + one history | **4.1–4.2** (parity on) | parity still opt-in |
| idempotent ticket + outbox | **4.3** + **4.5** retry API | Celery/cron/HTTP invoke; multi-row outbox table optional |
| ticket_id + delivery state; no false claim | **4.3–4.4** | live migrate opt-in |
| auto-escalate human/error on normal ask | **4.4** | stream-path parity if needed |

### §4 ledger (impl SHA)

| Slice | SHA | What |
|-------|-----|------|
| 4.1 | `eaf41f3` | single terminal answer/history when parity succeeds |
| 4.2 | `f1c846e` | graph-only generation when parity on |
| 4.3 | `ad5e435` | durable idempotent escalation service |
| 4.4 | `0371971` | auto-escalate terminal human/error on normal ask |
| **4.5** | **`6453530`** | outbox retry without second ticket |

---

## 4.5 contract (COMPLETE @ `6453530`)

- `retry_escalation_delivery(ticket_id)` — one ticket
- `retry_failed_deliveries(limit=…, states=("failed",))` — batch worker pass
- `retry_failed_deliveries_sync` — cron/CLI entry
- Never creates a second ticket; updates `delivery_state` / `delivery_error`
- Skips `delivered` / `duplicate` / missing
- **Not** scheduled in Celery beat; **no** admin HTTP yet

```powershell
python -m pytest tests/test_escalation_outbox_retry.py tests/test_escalation_service.py tests/test_human_route_escalation.py tests/test_pipeline_exception_escalation.py tests/test_graph_error_handling.py tests/test_agent_tools.py -q -p no:cacheprovider -p no:schemathesis --basetemp=.tmp/pytest-step4-5-<unique>
python -m ruff check services/escalation.py tests/test_escalation_outbox_retry.py
```

---

## Module owners (do not reopen without conflict)

| Path | Slice | Role |
|------|-------|------|
| `services/escalation.py` | **4.3–4.5** | create + outbox retry |
| `api/routers/conversation.py` | 4.3–4.4 | ask escalate |
| `api/routers/feedback.py` | 4.3 | manual escalate |
| `agent/graph.py` handle_error | 4.3 | durable escalate |
| job-object / index stack | 2.1–2.6g | do not re-select |

---

## Следующий named candidate (не начат)

**Default preference (product quality):**  
**§5 / 5.1 — grounding fail-closed foundations** (tests-first)

**Ops residual:**  
**4.6** — thin Celery/cron or operator HTTP that calls
`retry_failed_deliveries_sync` (no new delivery logic)

**Pipeline residual:**  
flip `STREAMING_RAG_PARITY` default / remove legacy stream path **or** true
graph token/node SSE

### Explicitly out without opt-in

- full suite as sole gate; live migrate 023; re-select 2.x / 3.1* / 4.1–4.5

---

## Protected dirty / untracked

**Dirty tracked:** `BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`,
`plan_sol_23_07_26`

**Untracked:** plan, `_NEXT_SESSION.md`, pytest temps, presentations, etc.

**Routing:** fresh Git → Update-88 + this capsule → plan direction → never dirty
backlog as queue.

---

## Do not

- Grep old `✅ START HERE` for work selection
- Re-select **2.1–2.6g**, **3.1a–3.1i**, **4.1–4.5**
- Claim full §2 / §3 / §4 / production readiness
- Push / deploy / live / migrate without explicit opt-in
- Edit plan checkboxes casually
