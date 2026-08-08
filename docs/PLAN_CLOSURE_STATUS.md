# Plan closure status — honest residual matrix

**Date:** 2026-08-08 (Update-119 full transparency after 4.7)  
**Plan file:** [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)  
**Routing:** top block of [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-119**)  
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
| **4** unified pipeline + escalation | **4.1–4.7 local** | **OPEN** provider token stream; parity default off | partial |
| **5** grounding fail-closed | **5.1–5.3 local** | **OPEN** live metric thresholds ×3 runs | **yes** quality |
| **6** judge / safety / agentic parity | **6.1–6.7 local** | OPEN (production human dual-annotator sample) | **yes** |
| **7** eval gate fail-closed | **7.1–7.7 local** | OPEN (live execute; mock≠release; optional more depth) | **yes** |
| **8** widget / edge security | **8.1–8.5 local** | OPEN (live IdP; prod allowlist ops) | yes |
| **9** cache / architecture / SLO | partial + **DEP-01 local** | OPEN (Astro7 residual; cache/SLO) | soft |
| **10** final verification / canary | not started | OPEN | **yes** |

**Project / production release: NOT claimed.**

Not claimable until §1 live evidence + §5 live quality metrics + §6–8 residual + §10.

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
| 26 | **provider tokens / human sample / live execute** | **← next pick** |
| 27 | §2/§3 residual if product needs | residual |
| 28 | Astro 7 (clears DEP-01 moderate residual) | residual |
| 29 | §1 + §10 | **opt-in live only** |

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
| **4.7** | **`6b91a35`** | real LangGraph node status SSE |

**Residual after 4.7:**

| Item | Status |
|------|--------|
| Graph **node** SSE on parity path | **done local** (4.7) |
| Answer **token** stream from provider generate | **OPEN** (still UX chunks of finished answer) |
| `STREAMING_RAG_PARITY` default | **off** (product decision to flip) |
| Outbox schedule (beat/CLI) | **done local** (4.6) |

---

## §5 map + ledger

| Slice | Status | SHA |
|-------|--------|-----|
| **5.1** | **done** | `7c53bdb` |
| **5.2** | **done** | `50bb220` |
| **5.3** | **done** | `1cdecb2` |
| Live DoD | **open** | — |

**Residual:** live precision/recall/faithfulness ×3; relevance still derived from quality/100.

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
| Astro 7 major | residual | — |

**Exceptions expire:** 2026-11-07 (`docs-site/npm-audit-exceptions.json`).

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

1. **True provider token streaming** through generate (optional §4 residual)  
2. **Collect real dual-annotator human sample** +  
   `recalibrate_routing.py --require-human --write`  
3. **Live provider execute** (`RAG_LIVE_PROVIDER_GATE` + secrets + `--execute`) — opt-in  
4. **Astro 7** / product decision to default `STREAMING_RAG_PARITY=true`  

**Do not re-select** 2.x–3.x, 4.1–4.7, 5.1–5.3, 6.1–6.7, 7.1–7.7, 8.1–8.5, DEP-01.

---

## Last-known verification snapshot (not re-run in Update-119)

| Band | Last known |
|------|------------|
| **4.7** | 12 passed (node SSE + parity) |
| **4.6** | 8 passed (outbox schedule) |
| **6.7** | 19 passed; seed NOT_READY |
| **6.6** | 32 passed |
| **7.7** | 8 passed (depth) |
| **7.6** | 21 passed |
| **8.5** | 16 passed |
| **DEP-01** | npm audit high=0 |

Full suite / live / migrate / push / deploy: **not** claimed.
