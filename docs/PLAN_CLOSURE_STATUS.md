# Plan closure status — honest residual matrix

**Date:** 2026-08-11 (Update-157 Astro 7 / DEP-01 zero-audit)
**Plan file:** [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)  
**Routing:** top block of [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-157**)
**Session capsule:** [`SESSION_HANDOFF.md`](SESSION_HANDOFF.md), especially the
authoritative open-problem ledger in §1C.

> Actual Git note: the active plan file was observed **untracked** before
> Update-157. Preserve it as DoD input, but use Actual Git + the committed
> handoff for next-session routing; do not casually stage or bulk-check its
> historical checkboxes.

**Rules:**

1. Checkboxes in the plan file stay open until **behavioral DoD + evidence**.  
2. Local code slice ≠ full plan section complete ≠ production release.  
3. Actual Git wins over any SHA embedded here.  
4. Quality > speed; one named atomic slice per user turn.

**Update-157:** implementation `cea370b` upgrades the docs site to Astro 7,
keeps the supported unified Mermaid pipeline and prior whitespace semantics,
and removes all obsolete audit exceptions after a zero-finding audit. Fresh
evidence is pytest **5 passed**, Astro check **0/0/0**, dependency audit **0**,
and a **59-page** static build with Pagefind and sitemap. No plan checkbox or
release gate changed. Architecture ownership, live scrape/alert delivery, and
live/gated work remain explicit in
[`SESSION_HANDOFF.md`](SESSION_HANDOFF.md) §0A/§1C.

---

## Closure truth (executive)

| Plan § | Local implementation | Full section DoD | Blocks release |
|--------|----------------------|------------------|----------------|
| **1** live multi-tenant / backup / RPO | partial chart/docs only | **OPEN** (opt-in live) | **yes** Gate A |
| **2** index lifecycle | **2.1–2.6g local residual closed** | **OPEN** live PG/Redis/Celery/Chroma | yes for live index ops |
| **3** execution / session / budget | **3.1a–3.1i local** | **OPEN** multi-replica durable version | partial |
| **4** unified pipeline + escalation | **4.1–4.8 local** | **OPEN** parity default still off (product) | partial |
| **5** grounding fail-closed | **5.1–5.7 + QG-01/QG-02/QG-03A/QG-03B/QG-04 + HYBRID-MEM env local** | **OPEN** one valid seed-42 run exists but **FAILS**; passing ×3 evidence remains open | **yes** quality |
| **6** judge / safety / agentic parity | **6.1–6.7 local** | OPEN (production human dual-annotator sample) | **yes** |
| **7** eval gate fail-closed | **7.1–7.7 local** | OPEN (live execute; mock≠release; optional more depth) | **yes** |
| **8** widget / edge security | **8.1–8.5 local** | OPEN (live IdP; prod allowlist ops) | yes |
| **9** cache / architecture / SLO | **9.1a–9.1c cache + 9.2a–9.2f telemetry + 9.3a dashboard + Astro 7 / DEP-01 local** | OPEN (architecture ownership, live alert delivery) | soft |
| **10** final verification / canary | not started | OPEN | **yes** |

**Project / production release: NOT claimed.**

Not claimable until §1 live evidence + §5 live quality metrics + §6–8 residual + §10.

---

## Off-plan provider capability (no closure credit)

`faaa815` adds the explicit `opencode-zen-free` trial profile, fixed to
`nemotron-3-ultra-free` with no declared fallback. Local startup/key,
OpenAI-compatible endpoint, live-gate/workflow, Helm Secret, documentation,
and regression contracts are verified.

This changes **none** of the §1–§10 rows above: no Zen or other live provider
call ran, no quality evidence was collected, and no production claim is made.
The provider documents the free endpoint as temporary/logged trial service;
use only non-sensitive test data and recheck external terms before enabling it.

---

## Current live-quality incident (Update-139)

The native vector-only run produced valid child evidence for seed 42 but failed
the quality gate: candidate pass 65% (baseline 70%, required ≥85%), four
regressions, context precision 0.1499, context recall 0.65, FULL 0.60, MISS 6,
faithfulness 0.30, and answer relevancy 0.4855. Seeds 43–44 did not run, so no
valid three-run aggregate or release evidence exists.

| Incident slice | Local status | Live status |
|----------------|--------------|-------------|
| **QG-01** `warranty-receipt-storage` | fixed at `c3ae4f4` | not replayed; no live recovery claim |
| **QG-02** `error-e20-hose-kink` | fixed at `1304ff4` (routing-test baseline `c157796`) | not replayed; no live recovery claim |
| **QG-03A** `error-e20-filter-or-pump` verifier outage | fixed at `80c2603`; retained trace proved `verify_facts` transport failure and answer overwrite | not replayed; no live or E20 keyword recovery claim |
| **QG-03B** same case content path | fixed at `5662ea7`; relevant contextual-header shells now resolve to content-bearing chunks from the same logical source | not replayed; no live or E20 keyword recovery claim |
| **QG-04** `error-e30` | shared cause fixed at `5662ea7`; exact retained five-document replay guarded at `5f8bb78` | not replayed live; no E30 keyword recovery claim |

The active collection remains dimension 3 while the remote embedding lane is
dimension 1024. The successful diagnostic run used a retained six-document
compatible copy and vector-only retrieval. It does not prove default hybrid
quality. An earlier hybrid attempt loaded the default reranker after an empty
environment value failed to propagate and reached about 2.12 GiB. `3c90368`
now provides an explicit `--disable-child-reranker` path; focused tests and a
real lightweight Windows child prove that the child receives the key as present
and blank. No hybrid/model run followed. The `PythonMemoryGuard` task was last
read-only verified **Disabled** in Update-133, so hybrid execution remains
operationally gated.

Detailed defect, environment, release, workspace, and external-boundary facts
are maintained in [`SESSION_HANDOFF.md`](SESSION_HANDOFF.md) §1C. Do not
duplicate or reinterpret them as closed plan checkboxes.

---

## Quality-first closure order (standing decision)

User priority: **quality over speed**, close plan thoroughly and honestly.

| Order | Work | Status |
|-------|------|--------|
| 1–13 | §5.1–5.3, §6.1–6.3, §7.1–7.2, §8.1–8.5 | **done** (see ledgers) |
| 14 | §7.3 merge-base baseline artifact | **done** `0d34be2` |
| 15 | DEP-01 docs-site npm audit | **done** `f622d58` |
| 16 | §7.4 curated dataset slices | **done** `8f4269f` |
| 17 | §7.5 CI baseline-artifact wire | **done** `4eceed3` |
| 18 | §6.4 routing calibration artifact | **done** `a7cefc3` |
| 19 | §6.5 measured agentic KB gate | **done** `431893c` |
| 20 | §7.6 live provider gate scaffold | **done** `d1ae4d6` |
| 21 | §7.7 deeper curated corpus (≥3/slice) | **done** `47e255a` |
| 22 | §6.6 agentic LLM evaluate wire | **done** `69c6fdf` |
| 23 | §6.7 human calibration readiness + CLI | **done** `c707c46` |
| 24 | §4.6 outbox retry schedule | **done** `11acfec` |
| 25 | §4.7 graph node status SSE | **done** `6b91a35` |
| 26 | §4.8 provider token stream through generate | **done** `fc7f07b` |
| 27 | §5.4 independent retrieval relevance | **done** `4f95e18` |
| 28 | §5.5 live quality metrics gate scaffold | **done** `a901692` |
| 29 | §5.6 exact live child report → DoD wire | **done** `fb72dd2` |
| 30 | §5.7 producer emits all 7 canonical metrics | **done** `13bf255` |
| 31 | QG-01 vector parent expansion | **done local** `c3ae4f4`; no live replay |
| 32 | QG-02 generation failure routing | **done local** `1304ff4`; no live replay |
| 33 | QG-03A verifier-outage routing | **done local** `80c2603`; no live replay |
| 34 | QG-03B contextual-header grading | **done local** `5662ea7`; no live replay |
| 35 | QG-04 retained E30 replay | **done local** `5f8bb78`; production fix shared with `5662ea7`; no live replay |
| 36 | HYBRID-MEM child environment propagation | **done local** `3c90368`; memory guard and hybrid replay remain gated |
| 37 | §9.1a bounded Redis fallback | **done local** `db65e37`; no live Redis |
| 38 | §9.1b Redis reconnect backoff | **done local** `eb8466e`; no live Redis |
| 39 | human sample / opt-in live ×3 evidence | **external/data authority required** |
| 40 | §2/§3 residual if product needs | residual |
| 41 | Astro 7 (clears DEP-01 moderate residual) | **done local** `cea370b`; zero audit findings / zero exceptions |
| 42 | §1 + §10 | **opt-in live only** |

Do **not** fake-close §1 or §10 with mock-only evidence.

---

## §2 map (honest — live DoD open)

| Bullet | Local | Residual |
|--------|-------|----------|
| inventory / retention / operator / lifecycle | through 2.5b + related | live DoD |
| fault injection | **2.6a–2.6g** | local residual closed |
| live PG/Redis/Celery/Chroma + migrations | not started | **opt-in**; migrations **019–023** on disk |

**Do not re-select 2.x.** Last §2 fault-injection impl: `f347feb` (**2.6g**).

---

## §3 map + ledger

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

**Residual:** multi-replica durable session version.

---

## §4 map + ledger

| Slice | SHA | What |
|-------|-----|------|
| 4.1 | `eaf41f3` | single terminal/history when parity succeeds |
| 4.2 | `f1c846e` | graph-only generation when parity on |
| 4.3 | `ad5e435` | durable idempotent escalation |
| 4.4 | `0371971` | auto human-route on normal ask |
| 4.5 | `6453530` | outbox retry without second ticket |
| **4.6** | `11acfec` | Celery beat + CLI outbox schedule |
| **4.7** | `6b91a35` | real LangGraph node status SSE |
| **4.8** | **`fc7f07b`** | provider token stream through generate |

**Residual after 4.8:**

| Item | Status |
|------|--------|
| Graph **node** SSE on parity path | **done local** (4.7) |
| Answer **token** stream from provider generate | **done local** (4.8; when stream capable) |
| Fallback UX chunks when stream N/A | **done local** (`graph_answer_chunks`) |
| `STREAMING_RAG_PARITY` default | **off** (product decision to flip) |
| Outbox schedule (beat/CLI) | **done local** (4.6) |

---

## §5 map + ledger

| Slice | Status | SHA |
|-------|--------|-----|
| **5.1** | **done** | `7c53bdb` |
| **5.2** | **done** | `50bb220` |
| **5.3** | **done** | `1cdecb2` |
| **5.4** | **done** | `4f95e18` independent retrieval relevance |
| **5.5** | **done local** | `a901692` live quality metrics gate scaffold |
| **5.6** | **done local** | `fb72dd2` exact child report parse + release-honest DoD wire |
| **5.7** | **done local** | `13bf255` canonical metric producer + completeness provenance |
| Live DoD evidence | **open / failing** | one valid seed-42 run fails; seeds 43–44 and passing ×3 remain opt-in |

**Residual after 5.7:** the producer emits all seven canonical metrics with
candidate-only provenance and fails real release runs closed on incomplete
measurement. A later authorized vector-only seed-42 run produced valid child
evidence but failed the thresholds recorded above; QG-01, QG-02, QG-03A,
QG-03B, and QG-04 are local-only repairs. Actual passing
precision/recall/faithfulness ×3 evidence remains explicit opt-in. Relevance is
**not** quality/100, and §5 metrics are not substituted from legacy
scores/counts.

---

## §6 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **6.1** | **done local** | `b3494a0` | unmeasured agentic; never auto on fixed scores |
| **6.2** | **done local** | `d0317e9` | PII redact + injection refuse→human |
| **6.3** | **done local** | `d6e3a55` | independent judge; fail-closed on outage/parse |
| **6.4** | **done local** | `a7cefc3` | routing calibration artifact + threshold resolve |
| **6.5** | **done local** | `431893c` | measured grounding when agentic has KB docs |
| **6.6** | **done local** | `69c6fdf` | LLM evaluate wire on KB agentic terminals |
| **6.7** | **done local** | `c707c46` | human readiness gate + recalibrate CLI |
| 6.x | residual | — | production dual-annotator sample + reissue |

**6.4 residual:** seed is bootstrap-defaults (historical 80/80/0.8/70), not live  
human production labelling DoD.

**6.7 residual:** readiness gate is ready; **real human labels not collected**.  
Seed `labelled_routes.jsonl` is `label_source=synthetic` and correctly fails  
`--require-human`.

---

## §7 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **7.1** | **done local** | `94ac64e` | infra/skip/empty effective → FAIL |
| **7.2** | **done local** | `25788ee` | mock = SMOKE only; release needs evidence |
| **7.3** | **done local** | `0d34be2` | merge-base baseline artifact load/write/require |
| **7.4** | **done local** | `8f4269f` | 10 required slices + min_context_recall; 47 cases |
| **7.5** | **done local** | `4eceed3` | CI write + upload + require-wire baseline artifact |
| **7.6** | **done local** | `d1ae4d6` | scheduled live provider gate scaffold (opt-in) |
| **7.7** | **done local** | `47e255a` | min 3 cases per required slice; 67 cases |
| 7.x | residual | — | live execute with secrets; optional further depth |

**7.2 residual:** CI still runs `--mock-experiment-runtime` as **smoke** (documented non-evidence).  
**7.6 residual:** scaffold only — real paid live evidence needs opt-in + secrets + `--execute`.  
**7.7 residual:** still synthetic curated (not production human labels); optional deeper still.

### Dataset depth (7.7)

| Slice | Count |
|-------|------:|
| multi_tenant | 3 |
| multi_turn | 5 |
| claim_citation | 3 |
| no_answer | 3 |
| tools | 3 |
| streaming | 3 |
| adversarial | 3 |
| pii | 3 |
| durable_escalation | 3 |
| context_recall | 3 |
| **total** | **67** |

---

## §8 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **8.1** | **done local** | `0bee13e` | bootstrap JWT, allowlist, frame-ancestors, session/token JS |
| **8.2** | **done local** | `756562e` | ASGI received-byte limits; upload stream + exclusive/atomic place |
| **8.3** | **done local** | `13a9a5b` | email_verified; (issuer, subject); no rebind; shared tenant map |
| **8.4** | **done local** | `68a30b2` | placeholders rejected; ALLOW_DEV_ADMIN_LOGIN banned in production |
| **8.5** | **done local** | `4d6be52` | Playwright cross-origin E2E; iframe Origin=API allowed; fail-closed empty/disallowed |

**8 residual:** live IdP; production must set `WIDGET_ALLOWED_ORIGINS`; Chromium-only E2E.

---

## DEP-01 (docs-site supply chain)

| Item | Status | SHA |
|------|--------|-----|
| Lock refresh + high=0 | **done local** | `f622d58` |
| Dated exceptions + `audit:deps` | **done local** | `f622d58` |
| Astro 7 major + zero-audit lock | **done local** | `cea370b` |

**Exceptions:** none after the 2026-08-11 Astro 7 lock refresh.

---

## §9 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **9.1a** | **done local** | `db65e37` | process-local Redis fallback honors TTL, is lock-protected, and evicts LRU entries above 1024; partial Redis deletes remain counted on `SCAN` failure |
| **9.1b** | **done local** | `eb8466e` | connection/ping and cache-operation failures invalidate the client; serialized reconnect delays grow from 1 second to a 30-second cap and reset after recovery |
| **9.1c** | **done local** | `893efe3` | response-cache keys bind tenant, active Chroma collection/generation, effective prompts, configured provider-model routing, and normalized query; unresolved identity skips cache read/write |
| **9.2a** | **done local** | `3fe6d6d` | a bounded `operation=publish|retention|unknown` counter records publish and automatic/manual retention failures once; a warning alert groups increases by operation |
| **9.2b** | **done local** | `11e52f1` | each client-visible `route=auto` sync/SSE result increments bounded `verification=verified|unverified`; missing/unexpected grounding is unverified and the alert target is zero |
| **9.2c** | **done local** | `64f40b3` | each real shared inbox delivery attempt increments bounded `outcome=delivered|failed|unknown` exactly once across initial and retry paths; non-attempts remain uncounted and failures have a warning alert |
| **9.2d** | **done local** | `9817e89` | each applied unsafe pre-response increments bounded `action=redact|refuse|unknown` once; clean/empty answers remain uncounted, metric failure is fail-open, and refusals have a warning alert |
| **9.2e** | **done local** | `5a2f696` | label-free orphan-work gauge increments once when capacity transfers to any of five shared future callbacks and decrements once on completion; normal sync work stays uncounted, metric failure is fail-open, and work above zero for five minutes warns |
| **9.2f** | **done local** | `344e174` | ten confirmed session/ticket/KB-draft ownership mismatches increment bounded `resource=session|ticket|kb_draft|unknown` once; missing/same-tenant access stays uncounted, metric failure is fail-open, opaque 404s remain unchanged, and any five-minute increase warns after 30 seconds |
| **9.3a** | **done local** | `1237f3c` | a portable `DS_PROMETHEUS` dashboard gives each named signal one non-overlapping panel, preserves bounded/adaptive PromQL and zero-target semantics, and is guarded by offline JSON contract tests |
| **9.4a** | **done local** | `cea370b` | Astro 7.2 / Starlight 0.41 retain the unified Mermaid pipeline and prior whitespace behavior; dependency audit is zero with an empty validated exception register |

**Residual:** architecture ownership. No live Redis, Grafana import,
metric-scrape, or alert-delivery evidence exists.

---

## What “plan closed” means

The plan is **closed** only when:

1. Every section §1–§10 meets its own **behavioral DoD + evidence**.  
2. Unverified auto-rate is zero under live policy.  
3. Restore/rollback/canary confirmed where required.  
4. Production release does **not** rest on graceful skip, fixed agentic scores,  
   mock release PASS, or self-judge without human calibration.

Local green slices alone **do not** close the plan.

---

## Next session pick (one only)

There is no implementation WIP and no preselected implementation candidate.
Select at most one explicit owner request or documented residual in a new turn.
Do not invent another quality fix or replay QG-01–QG-04 without new evidence.

Gated alternatives remain: live provider/quality ×3 (`--execute` + secrets +
fresh opt-in), memory-guard enablement plus a bounded hybrid attempt, a real
dual-annotator human sample, or the product decision to default
`STREAMING_RAG_PARITY=true`.

This list is not authorization. The executable boundary and current facts are
spelled out in [`SESSION_HANDOFF.md`](SESSION_HANDOFF.md) §2A. In a new
direct-autonomy turn, select at most one local slice; otherwise stop after
reconciliation. Do not convert this routing note into authority for a live
retry, scheduler change, index mutation, migration, push, or deploy.

`3a37fd2` separately closes the local VER-02 `vectordb` type debt under
`--follow-imports=skip`. It changes no plan checkbox and does not establish a
full repository, locked Python-3.11, CI, or production verification result.

**Do not re-select** 2.x–3.x, **4.1–4.8**, **5.1–5.7**, 6.1–6.7, 7.1–7.7, 8.1–8.5, **9.1a–9.1c**, **9.2a–9.2f**, **9.3a**, **9.4a / Astro 7 / DEP-01**, VER-06.

---

## Last-known verification snapshot (Update-157)

| Band | Last known |
|------|------------|
| **9.4a Astro 7 / DEP-01** | independent pytest **5 passed**, one warning; Astro check **0/0/0**; npm audit **0 vulnerabilities**; static build **59 pages** + Pagefind + sitemap; scoped diff/LF + protected hashes clean |
| **Update-156 transparency** | docs-only Actual Git/Grok/artifact reconciliation; docs quality gate only; no implementation test rerun or new implementation/release evidence |
| **9.3a Grafana dashboard artifact** | Grok TDD **7 failed → 7 passed**; QA threshold semantics **1 failed / 6 passed → 7 passed**; independent **7 passed**, one warning; scoped Ruff + JSON parse + cached diff/LF + protected hashes clean; no live Grafana/import/scrape/alert-delivery evidence |
| **Update-154 transparency** | docs-only reconciliation against Actual Git; no implementation file changed, no project suite rerun, and no new implementation or release evidence |
| **9.2f tenant-denied telemetry** | focused TDD **5 failed → 5 passed**; independent tenant/session/agent/KB/metrics/alerts band first rejected a zero-duration alert, then passed **54 tests** after one narrowed correction, one warning; scoped Ruff + six-source narrowed MyPy + diff/LF clean; ordinary MyPy retains four pre-existing `api/app.py` errors outside changed lines; formatter debt remains outside added lines; no live scrape/alert delivery |
| **9.2e orphan-work telemetry** | focused TDD **5 failed → 5 passed**; independent pipeline/stream/metrics/alerts/timeout band first exposed test-isolation leakage, then passed **37 tests** after one narrowed correction, one warning; scoped Ruff + narrowed metrics MyPy + diff/LF clean; ordinary two-source MyPy retains two pre-existing `no-redef` errors outside changed lines; formatter debt remains outside added lines; no live scrape/alert delivery |
| **9.2d safety-block telemetry** | focused TDD **5 failed → 5 passed**; full response-safety/metrics/alerts/unverified-auto band **35 passed**, one warning; post-format focused gate **5 passed**; scoped Ruff + two-source MyPy + diff/LF clean; formatter debt remains outside added lines; no live scrape/alert delivery |
| **9.2c escalation-delivery telemetry** | Grok focused TDD **8 failed → 8 passed** after one narrowed test-fixture correction; independent four-file band **33 passed**, one warning; scoped Ruff + two-source MyPy + diff/LF clean; whole-file formatter debt remains outside added lines; no live scrape/alert delivery |
| **Update-149 docs reconciliation** | docs quality **13 passed**, one warning; scoped diff/LF clean; no project tests rerun and no new implementation evidence |
| **VER-06 agentic safety mock contract** | exact stale test **1 failed** → **1 passed**; independent response-safety/agentic/auto-telemetry band **44 passed**, one warning; scoped Ruff + diff/LF clean; pre-existing whole-file formatter debt remains; production code unchanged |
| **9.2b unverified auto-rate telemetry** | focused TDD **4 failed / 5 passed** → **9 passed**; independent **60 passed / 1 failed**, failure reproduced alone as pre-existing VER-06; narrowed rerun **60 passed**, 1 deselected, one warning; scoped Ruff + new-file format + narrowed two-source MyPy + diff/LF clean; no live scrape/alert delivery |
| **9.2a index lifecycle failure telemetry** | focused TDD **10 failed / 2 passed** → **12 passed**; final lifecycle/metrics/alert band **75 passed**, 61 deselected, one known warning; docs **13 passed**; scoped Ruff + narrowed two-source MyPy + diff/LF clean; pre-existing whole-file format debt remains; no live scrape/alert delivery |
| **VER-05** | stale zero-caller assertion red **1 failed** → exact admin-only caller contract; independent retention/admin band **51 passed**, 62 deselected, one known warning; scoped Ruff + diff clean; pre-existing whole-file format debt remains |
| **9.1c versioned cache namespace** | HTTP settings-source regression **2 failed** → **2 passed**; final namespace/HTTP-cache/Redis/manifest band **40 passed** with two known warnings; Ruff + changed-range format + narrowed MyPy + diff clean; no live Redis/provider/index mutation |
| **9.1b Redis reconnect backoff** | recovery red **2 failed** → green **2 passed**; focused Redis file **9 passed**; final Redis/cache band **15 passed** with two known warnings; Ruff check/format + scoped MyPy + diff clean; no live Redis |
| **9.1a bounded Redis fallback** | TTL/cap red **2 failed** → focused **2 passed**; partial-delete count red **1 failed** → green **1 passed**; final Redis/cache band **13 passed** with two known warnings; Ruff check/format + scoped MyPy + diff clean; no live Redis |
| **VER-02** | exact MyPy red **1 error** → green **1 source**; lifecycle/lock band **11 passed**; Ruff clean; package `vectordb` MyPy **10 sources** with `--follow-imports=skip`; VER-01/full locked CI remain open |
| **HYBRID-MEM env** | TDD red **1 failed** → focused **2 passed**; independent live-quality/regression band **57 passed**; Ruff + changed-file Mypy + diff clean; real lightweight Windows child saw the key present and blank; no model/hybrid/live run |
| **QG-04** | exact retained five-document replay **1 passed**; independent grading/fail-closed/relevance/provider/fact-verification band **31 passed**; scoped Ruff + diff clean; production fix shared with `5662ea7`; no live replay |
| **QG-03B** | TDD red **1 failed** → focused green **1 passed**; independent grading/fail-closed/relevance/provider band **24 passed**; scoped Ruff + changed-file Mypy + diff clean; no live replay |
| **QG-03A** | Grok red 1 failed → focused **6 passed** + Ruff; independent verifier/grounding/citation/graph-error/judge/provider band **49 passed** + Ruff + diff clean; ordinary changed-file Mypy exposed 9 pre-existing `typeddict-item` errors outside changed lines, narrowed run passed; no locked/full-Mypy claim |
| **QG-02** | TDD red 1 failed → green 1 passed; final focused **1 passed**; adjacent provider graph/error/model-routing/judge **31 passed**; Ruff + changed-file Mypy (`--follow-imports=skip`) + diff clean; no full locked-Mypy claim |
| **QG-01** | TDD red 2 failed / 9 passed → focused **11 passed**; independent parent/base/reranker **34 passed**; scoped Ruff + changed-file Mypy + diff clean; broader `vectordb` Mypy last had one unchanged-file error |
| **Native live quality** | seed 42 valid child evidence but quality **FAIL**; seeds 43–44 not run; no valid ×3 aggregate |
| **OpenCode Zen** | **155 passed**; Ruff, scoped Mypy, Helm Secret render, scoped diff clean; no live call |
| **5.7** | independent regression/quality band **83 passed**; Ruff + scoped diff clean |
| **5.6** | Grok focused 25 passed; independent quality/provider/workflow **46 passed**; Ruff + scoped diff clean |
| **5.5** | 33 passed (quality-metrics + provider-gate + workflows) |
| **5.4** | 56 passed (relevance + agentic + grounding/judge) |
| **4.8** | 16 passed (provider tokens + node SSE + parity) |
| **6.7** | 19 passed; seed NOT_READY |
| **7.7** | 8 passed (depth) |
| **DEP-01** | npm audit high=0 |

Full suite / locked CI Mypy / passing live ×3 / migrate / push / deploy:
**not** claimed.
