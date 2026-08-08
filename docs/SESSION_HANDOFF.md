# Session handoff

**Обновлено:** 2026-08-08 — **Update-112** (slice **7.6** live provider gate  
scaffold @ `d1ae4d6`; supersedes Update-111 for start-point routing).  
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей  
истории `AGENT_STATE.md`.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -12 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-112**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — **DoD**, не очередь галочек |

**Не использовать:** старые `✅ START HERE` ниже Update-112; dirty  
`BACKLOG.md` / `README.md` / audits; `_NEXT_SESSION.md` как единственный SoT  
(это pointer only).

**Plan checkboxes:** не править casually. Local slice ≠ section closed ≠ release.

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **implementation** | `d1ae4d6` — **7.6** live provider gate scaffold |
| Latest **docs before this Update** | `2b06f6c` — Update-111 |
| This Update-112 docs SHA | **unknown in-file** → `git log -3 --oneline` после коммита |
| Branch advisory | `master...origin/master [ahead 198]` after impl — **refresh mandatory** |
| Active writer / WIP | **none** |
| Locally complete (documented scopes) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.5** + **5.1–5.3** + **6.1–6.5** + **7.1–7.6** + **8.1–8.5** + **DEP-01** |
| Full plan §1–§10 / production | **NOT** complete / **NOT** claimed |
| Plan status | **ACTIVE** |
| Next ordered (default) | deeper corpus **or** agentic LLM evaluate **or** human recalibration |
| Gates | **no** push / deploy / live multi-service / live provider execute / migrate 019–023 without **explicit opt-in** |

**Last known verification (7.6):** live-gate + workflow band **21 passed**;  
Ruff clean; readiness `SKIPPED_NO_OPT_IN`. Full suite / live execute / push  
**not** claimed.

---

## 2. Быстрый старт следующей сессии

```text
1. Cycle-guard: one named atomic slice per user turn.
2. cd D:\RAG_Support_Assistant
3. git status --short --branch
4. git log -12 --oneline          # actual Git wins
5. Read ONLY top Update-112 in AGENT_STATE.md + this file §1–§11
6. Default work: deeper corpus OR agentic LLM evaluate OR human cal. Announce: slice 1/1
7. Tests-first → proportional gate → local commit only (no push)
8. Optional handoff refresh; STOP after one slice
```

**Not authorized without opt-in:** push, deploy, live PostgreSQL/Redis/Celery/  
Chroma, live provider execute with secrets, `alembic upgrade` (incl. **019–023**),  
destructive Git, production claims, bulk plan checkbox edits.

---

## 3. Honest residual (plan sections)

| Plan § | Local | Residual / blockers |
|--------|-------|---------------------|
| **1** live multi-tenant / backup / RPO | partial chart/docs | **opt-in live** — Gate A open |
| **2** index lifecycle | **2.1–2.6g** local residual closed | live PG/Redis/Celery/Chroma + migrate drills |
| **3** execution / session / budget | **3.1a–3.1i** local | multi-replica durable session version |
| **4** pipeline + escalation | **4.1–4.5** local | true graph tokens; parity default **off**; outbox Celery/cron |
| **5** grounding fail-closed | **5.1–5.3** local | live metrics DoD ×3; relevance≠quality residual |
| **6** judge / safety / agentic | **6.1–6.5** local | full human calibration; optional agentic LLM evaluate |
| **7** eval gate | **7.1–7.6** local | live execute with secrets; deeper corpus; mock≠release |
| **8** widget / edge | **8.1–8.5** local | live IdP; `WIDGET_ALLOWED_ORIGINS` in prod |
| **9** cache / architecture / SLO | partial + **DEP-01 local** | Astro7 residual; cache/SLO |
| **10** final verification | not started | after 1–9 + opt-in evidence |

**Release / production: NOT claimable** until §1 live + §5 live quality +  
§6–7 residual + §8 residual + §10.

Full matrix: [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md).

---

## 4. Implementation ledgers (impl SHAs only)

### §7 eval gate

| Slice | SHA | Surface |
|-------|-----|---------|
| **7.1** | `94ac64e` | infra/skip/empty → FAIL |
| **7.2** | `25788ee` | mock → `SMOKE_PASS` only; `--release-gate` needs evidence |
| **7.3** | `0d34be2` | merge-base baseline artifact load/write/require |
| **7.4** | `8f4269f` | required slices + min_context_recall; **47** cases |
| **7.5** | `4eceed3` | CI write + upload + require-wire of baseline artifact |
| **7.6** | **`d1ae4d6`** | scheduled live provider gate scaffold (opt-in) |

### §8 widget / edge

| Slice | SHA | Surface |
|-------|-----|---------|
| **8.1** | `0bee13e` | widget bootstrap JWT, origins, frame-ancestors, session/token JS |
| **8.2** | `756562e` | ASGI received-byte body limits; upload stream temp + exclusive/atomic place |
| **8.3** | `13a9a5b` | OIDC email_verified; identity (issuer, subject); no rebind; shared tenant map |
| **8.4** | `68a30b2` | production placeholders rejected; `ALLOW_DEV_ADMIN_LOGIN` banned |
| **8.5** | `4d6be52` | Playwright cross-origin E2E; iframe Origin=API allow; fail-closed paths |

### DEP-01

| Slice | SHA | Surface |
|-------|-----|---------|
| **DEP-01** | `f622d58` | docs-site high=0; dated exceptions; fail-closed audit gate |

### §6 / §5 / §4 / §3 / §2 (summary)

| Band | Ends at SHA | Note |
|------|-------------|------|
| §6 | `431893c` **6.5** | measured agentic KB; residual human cal + optional LLM evaluate |
| §5 | `1cdecb2` **5.3** | grader fail-closed |
| §4 | `6453530` **4.5** | outbox retry API |
| §3 | `fe2f0aa` **3.1i** | runtime/session/budget band |
| §2 | `f347feb` **2.6g** | fault-injection residual closed local |

---

## 5. Contracts (recent complete slices)

### 7.6 @ `d1ae4d6`

- `scripts/live_provider_gate.py` readiness/command/live
- Default readiness: no live calls; `SKIPPED_NO_OPT_IN`; never release PASS
- Live: `RAG_LIVE_PROVIDER_GATE` + provider keys; fail-closed without keys
- Live argv: `--release-gate --allow-paid-apis`; forbids mock
- Workflow: `.github/workflows/live-provider-gate.yml` (schedule + dispatch)
- Tests: `tests/test_live_provider_gate.py`

### 6.5 @ `431893c`

- `search_kb_docs` returns (text, raw docs) for measured terminal
- KB + `[N]` citations → citation-bound grounding measured; context attached
- `route=auto` only with measured quality (llm/heuristic) + floors; fixed rejected
- Confirmation / order-only / no-KB → still unmeasured (6.1)
- Files: `agent/agentic_measure.py`, `agent/tools.py`, `agent/graph.py`,
  `tests/test_agentic_measure.py`, `tests/test_agent_tools.py`

### 6.4 @ `a7cefc3`

- Artifact `kind=routing-calibration` schema v1; seed bootstrap-defaults
- Thresholds: min_quality 80 / min_factuality 80 / min_relevance 0.8 /
  self_rag_min_quality 70 (historical band; not full human DoD)
- Labeling rules + Cohen's κ agreement + auto/human cost matrix
- `resolve_routing_thresholds` → `route_or_retry` / `build_support_graph`
- Settings: `calibration_artifact_path`, `require_calibration_artifact` (prod)
- Files: `agent/calibration.py`, `evaluation/calibration/*`,
  `tests/test_calibration_artifact.py`, `agent/graph.py`, `config/settings.py`

### 7.5 @ `4eceed3`

- CI smoke: `--write-baseline-artifact reports/regression/ci-baseline-artifact.json`
- Publish: `actions/upload-artifact@v4` → `regression-baseline-artifact`
  (`if-no-files-found: error`)
- Require wire: second step `--baseline-artifact` + `--require-baseline-artifact`
- Still mock → still **SMOKE only**; **no** `--release-gate` (plan §7.2)
- Files: `.github/workflows/ci.yml`, `tests/test_github_workflows.py`

### 7.4 @ `8f4269f`

- Schema: `slices` / `tags` / `session_id` / `turn_index`; `min_context_recall`
- Coverage: `validate_dataset_slice_coverage` + `REQUIRED_DATASET_SLICES` (10)
- Dataset 35 → **47** cases; multi-tenant (acme/beta) + multi-turn session
- Manifest: `evaluation/curated_cases.manifest.json` (schema v2)
- Files: `scripts/regression_eval.py`, `evaluation/curated_cases.jsonl`,
  `tests/test_curated_dataset_expansion.py`

### DEP-01 @ `f622d58`

- `docs-site`: astro `^6.4.8`, sharp `^0.35.3`; lock → **high=0 critical=0**
- Residual moderate/low: dated exceptions to **2026-11-07** in
  `docs-site/npm-audit-exceptions.json`
- Gate: `npm audit --audit-level=high` + `npm run audit:deps` (no `|| true`)
- Files: `docs-site/scripts/check-npm-audit.mjs`, `.github/workflows/docs-site.yml`,
  `tests/test_docs_site_npm_audit.py`

### 7.3 @ `0d34be2`

- Artifact schema: `kind=regression-baseline`, `schema_version=1`, per-case map
- API: `build_baseline_artifact` / `write` / `load` / `baseline_artifact_from_report`
- Runner: `baseline_case_results` skips baseline executor; missing case → infra FAIL
- CLI: `--baseline-artifact`, `--write-baseline-artifact`, `--require-baseline-artifact`

### 8.5 @ `4d6be52` (summary)

- API Origin allowed on iframe bootstrap; third-party Origin must match parent
- Playwright: allowlisted handshake + JWT + session reuse; empty/disallowed fail-closed

### 8.4–8.1 / 7.2–7.1 (one-liners)

- **8.4** production secrets + ban `ALLOW_DEV_ADMIN_LOGIN`
- **8.3** OIDC email_verified + (issuer, subject)
- **8.2** ASGI received-byte limits + upload stream/atomic place
- **8.1** widget bootstrap JWT + frame-ancestors
- **7.2** mock → `SMOKE_PASS` only
- **7.1** infra/skip/empty → FAIL

---

## 6. Module owners (do not reopen without conflict)

| Path | Slices | Role |
|------|--------|------|
| `agent/agentic_measure.py` | **6.5** | measured agentic terminal when KB docs |
| `agent/tools.py` | **6.5** | `search_kb_docs` |
| `tests/test_agentic_measure.py` | **6.5** | measure contract |
| `agent/calibration.py` | **6.4** | routing calibration artifact + threshold resolve |
| `evaluation/calibration/` | **6.4** | seed artifact + labelled_routes fixture |
| `tests/test_calibration_artifact.py` | **6.4** | calibration contract |
| `scripts/regression_eval.py` | **7.1–7.4** | gate + evidence + baseline artifact + slices |
| `.github/workflows/ci.yml` | **7.5** | write + upload + require-wire baseline artifact |
| `tests/test_github_workflows.py` | **7.5** | CI wire contract lock |
| `scripts/live_provider_gate.py` | **7.6** | live gate scaffold policy + readiness |
| `.github/workflows/live-provider-gate.yml` | **7.6** | scheduled/opt-in live gate |
| `tests/test_live_provider_gate.py` | **7.6** | live gate contract |
| `evaluation/curated_cases.jsonl` | **7.4** | regression curated corpus (47) |
| `evaluation/curated_cases.manifest.json` | **7.4** | required slices register |
| `tests/test_curated_dataset_expansion.py` | **7.4** | slice coverage + context_recall |
| `tests/test_regression_baseline_artifact.py` | **7.3** | merge-base artifact contract |
| `docs-site/package.json` + lock | **DEP-01** | npm dependency posture |
| `docs-site/npm-audit-exceptions.json` | **DEP-01** | dated reachability exceptions |
| `docs-site/scripts/check-npm-audit.mjs` | **DEP-01** | fail-closed audit checker |
| `api/routers/widget.py` | **8.1 / 8.5** | bootstrap + iframe Origin fix |
| `tests/test_widget_e2e_playwright.py` | **8.5** | Chromium cross-origin embed E2E |
| `config/settings.py` | **8.4** | production secret / dev-admin gates |
| `auth/oidc.py` | **8.3** | email_verified, issuer/subject |
| `api/body_limit.py` | **8.2** | received-byte receive wrapper |
| job-object / index stack | 2.1–2.6g | **do not re-select** |

---

## 7. Key invariants (do not regress)

1. Failed jobs with `source_path` match → retained; not auto-delete  
2. LLM budget exhaust → `route=human` / never `auto`  
3. Deadline fail-closed at provider/retrieve/tool/rerank  
4. Stream parity on → single graph generation + single terminal/history  
5. Escalation: no «передан оператору» without durable ticket  
6. No fake factuality 100 on skip/disabled/no-context  
7. Claims need cited `[N]` for auto  
8. Empty graded after grade ≠ silent restore of raw context  
9. Agentic unmeasured ≠ `route=auto` and ≠ fake quality 80/85/90  
10. PII in terminal answer redacted; injection → refuse + human  
11. Judge unavailable/error/parse ≠ auto; ≠ silent score 50 + `quality_source=llm`  
12. Eval: infra/skip/zero-effective → gate FAIL  
13. Mock expected-copy → `SMOKE_PASS` only; never release `PASS`  
14. Widget: empty allowlist → no bootstrap; framing only via allowlisted ancestors  
15. Body limits: trust **received** ASGI bytes, not Content-Length alone  
16. Upload: stream to temp + exclusive immutable place + atomic flat rename  
17. OIDC: verified email + (issuer, subject); no silent rebind  
18. Production: no placeholder secrets; no `ALLOW_DEV_ADMIN_LOGIN`  
19. Widget iframe: API Origin allowed; empty/disallowed parent fail-closed (E2E)  
20. Regression: baseline from artifact for honest release compare  
21. Dataset: required slices covered; `min_context_recall` enforceable  
22. Docs-site: high/critical fail closed; residual only with dated exceptions  
23. CI: write + publish + require-load baseline artifact (smoke; mock≠release)  
24. Routing floors from calibration artifact (bootstrap ok; full human residual)  
25. Agentic + KB docs → measured grounding; auto needs measured quality too  
26. Live provider gate is separate from PR mock smoke; opt-in only; never silent PASS  

---

## 8. Verification recipes (last known green; re-run when coding)

### §7.6 band

```powershell
python -m pytest tests/test_live_provider_gate.py tests/test_github_workflows.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check scripts/live_provider_gate.py tests/test_live_provider_gate.py
python scripts/live_provider_gate.py --mode readiness --write-report reports/regression/live-provider-gate-readiness.json
```

### §6.5 band

```powershell
python -m pytest tests/test_agentic_measure.py tests/test_agent_tools.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check agent/agentic_measure.py agent/tools.py agent/graph.py tests/test_agentic_measure.py
```

### §6.4 band

```powershell
python -m pytest tests/test_calibration_artifact.py tests/test_grounding_fail_closed.py tests/test_citation_bound_grounding.py tests/test_judge_policy.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check agent/calibration.py tests/test_calibration_artifact.py agent/graph.py config/settings.py
```

### §7.5 band

```powershell
python -m pytest tests/test_github_workflows.py tests/test_regression_baseline_artifact.py tests/test_regression_evidence_policy.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check tests/test_github_workflows.py
```

### §7.4 band

```powershell
python -m pytest tests/test_curated_dataset_expansion.py tests/test_regression_runner.py tests/test_regression_baseline_artifact.py tests/test_regression_evidence_policy.py tests/test_regression_gate_fail_closed.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check scripts/regression_eval.py tests/test_curated_dataset_expansion.py
```

### DEP-01 band

```powershell
cd docs-site; npm audit --audit-level=high; npm run audit:deps
cd ..
python -m pytest tests/test_docs_site_npm_audit.py tests/test_github_workflows.py::test_docs_site_workflow_audits_npm_dependencies_before_build -q -p no:cacheprovider
```

### §8.5 band

```powershell
python -m pytest tests/test_widget_bootstrap.py tests/test_widget_e2e_playwright.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check api/routers/widget.py tests/test_widget_bootstrap.py tests/test_widget_e2e_playwright.py
```

Full suite / live / migrate — **not** the default gate for a single slice.

---

## 9. Next named candidate (not started)

**Default picks (one only):**

1. **Deeper per-slice curated corpus**  
2. **Agentic LLM evaluate wire** (supply measured quality on KB terminals)  
3. **Real human-labelled recalibration** (replace synthetic labelled_routes)  
4. **Live provider execute** with secrets + `--execute` (**explicit opt-in only**)  
5. **Astro 7** major when Starlight supports it (clears DEP-01 moderate residual)  

### Out without opt-in

- live multi-service / migrate / push / deploy / live provider execute  
- re-select through **8.5** / **6.1–6.5** / **7.1–7.6** / **DEP-01**  
- OIDC live IdP drill; full browser matrix expansion  

### Alternates (only if user prioritizes)

- live §1 / migrate 019–023 (**explicit opt-in only**)  
- §4 graph tokens / stream parity default  

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
- Re-select **2.1–2.6g**, **3.1a–3.1i**, **4.1–4.5**, **5.1–5.3**, **6.1–6.3**,  
  **7.1–7.4**, **8.1–8.5**, **DEP-01**  
- Claim plan closed / production ready  
- Push / deploy / live / migrate without opt-in  
- Edit plan checkboxes casually without full DoD evidence  
