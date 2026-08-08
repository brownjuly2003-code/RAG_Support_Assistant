# Plan closure status — honest residual matrix

**Date:** 2026-08-07 (Update-108 full transparency after 7.4)  
**Plan file:** [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md)  
**Routing:** top block of [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-108**)  
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
| **6** judge / safety / agentic parity | **6.1–6.3 local** | OPEN (**← calibration** / measured agentic) | **yes** |
| **7** eval gate fail-closed | **7.1–7.4 local** | OPEN (live gate / CI wire / depth) | **yes** |
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
| 1 | §5.1 grounding foundations | **done** `7c53bdb` |
| 2 | §5.2 citation-bound claims | **done** `50bb220` |
| 3 | §5.3 grader fail-closed | **done** `1cdecb2` |
| 4 | §6.1 remove agentic fixed quality scores | **done** `b3494a0` |
| 5 | §6.2 pre-response PII / prompt-injection | **done** `d0317e9` |
| 6 | §6.3 independent judge policy | **done** `d6e3a55` |
| 7 | §7.1 eval gate fail-closed skip/infra | **done** `94ac64e` |
| 8 | §7.2 honest release evidence (no mock PASS) | **done** `25788ee` |
| 9 | §8.1 widget bootstrap security | **done** `0bee13e` |
| 10 | §8.2 ASGI body limits / upload stream | **done** `756562e` |
| 11 | §8.3 OIDC email_verified / (issuer, subject) | **done** `13a9a5b` |
| 12 | §8.4 production secrets / no dev-admin | **done** `68a30b2` |
| 13 | §8.5 Playwright widget E2E | **done** `4d6be52` |
| 14 | §7.3 merge-base baseline artifact | **done** `0d34be2` |
| 15 | DEP-01 docs-site npm audit | **done** `f622d58` |
| 16 | §7.4 curated dataset slices | **done** `8f4269f` |
| 17 | **§6 calibration / CI baseline wire / live gate** | **← next pick** |
| 18 | §4 residual (graph tokens / parity default) | residual |
| 19 | §2/§3 residual if product needs | residual |
| 20 | Astro 7 (clears DEP-01 moderate residual) | residual |
| 21 | §1 + §10 | **opt-in live only** |

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

**Residual:** true node/token SSE; parity default off; Celery/cron for outbox.

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
| 6.x | **← next residual** | — | calibration; measured agentic evaluate |

---

## §7 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **7.1** | **done local** | `94ac64e` | infra/skip/empty effective → FAIL |
| **7.2** | **done local** | `25788ee` | mock = SMOKE only; release needs evidence |
| **7.3** | **done local** | `0d34be2` | merge-base baseline artifact load/write/require |
| **7.4** | **done local** | `8f4269f` | 10 required slices + min_context_recall; 47 cases |
| 7.x | residual | — | scheduled live gate; CI wire artifact; deeper per-slice corpus |

**7.2 residual:** CI still runs `--mock-experiment-runtime` as **smoke** (documented non-evidence).  
**7.3 residual:** CI does not yet require/publish baseline artifact on release path.  
**7.4 residual:** more cases per slice optional; live metrics still open.

### §7 last-known verification (7.4 turn; not re-run in Update-108)

| Slice | Gate | Result |
|-------|------|--------|
| **7.4** | dataset expansion + regression band | **44 passed** |
| 7.3 | baseline artifact (included in band) | green in 7.4 turn |
| 7.2 / 7.1 | evidence + gate fail-closed (included) | green in 7.4 turn |

---

## §8 map + ledger

| Slice | Status | SHA | Contract |
|-------|--------|-----|----------|
| **8.1** | **done local** | `0bee13e` | bootstrap JWT, allowlist, frame-ancestors, session/token JS |
| **8.2** | **done local** | `756562e` | ASGI received-byte limits; upload stream + exclusive/atomic place |
| **8.3** | **done local** | `13a9a5b` | email_verified; (issuer, subject); no rebind; shared tenant map |
| **8.4** | **done local** | `68a30b2` | placeholders rejected; ALLOW_DEV_ADMIN_LOGIN banned in production |
| **8.5** | **done local** | `4d6be52` | Playwright cross-origin E2E; iframe Origin=API allowed; fail-closed empty/disallowed |

### §8 last-known verification (prior turns; not re-run in Update-108)

| Slice | Gate | Result |
|-------|------|--------|
| **8.5** | `test_widget_bootstrap` + `test_widget_e2e_playwright` | **16 passed** |
| 8.4 | production secrets + CORS | **17 passed** |
| 8.3 | OIDC + email channel | **19 + 9 passed** |
| 8.2 | body limits + upload | **64 passed** |

**8 residual:** live IdP; production must set `WIDGET_ALLOWED_ORIGINS`; Chromium-only E2E.

---

## DEP-01 (docs-site supply chain)

| Item | Status | SHA |
|------|--------|-----|
| Lock refresh + high=0 | **done local** | `f622d58` |
| Dated exceptions + `audit:deps` | **done local** | `f622d58` |
| Astro 7 major | residual | — |

**Exceptions expire:** 2026-11-07 (`docs-site/npm-audit-exceptions.json`).  
**Last known:** `npm audit --audit-level=high` exit 0; `npm run audit:deps` PASS; 4 pytest.

---

## What “plan closed” means

The plan is **closed** only when:

1. Every section’s **Проверка** has fresh evidence artifacts, and  
2. Gate A–D / §10 checklist is signed, and  
3. `unverified auto-rate = 0` on the release gate, and  
4. No production claim rests on graceful skip, fixed agentic scores, mock  
   expected-copy, or self-judge without calibration.

Until then status remains **ACTIVE**.
