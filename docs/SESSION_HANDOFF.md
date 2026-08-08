# Session handoff

**Обновлено:** 2026-08-08 — **Update-116** after **6.7** @ `c707c46`  
(human calibration readiness; prior `69c6fdf` 6.6 / Update-115).  
**Назначение:** самодостаточный старт **следующей** сессии без чтения всей  
истории `AGENT_STATE.md`.

---

## 0. Routing (обязательно)

| Приоритет | Источник |
|-----------|----------|
| 1 | **Actual Git** — `git status --short --branch` + `git log -12 --oneline` |
| 2 | Верхний блок [`AGENT_STATE.md`](../AGENT_STATE.md) (**Update-116**) |
| 3 | Эта капсула + [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) |
| 4 | План [`rag-remediation-plan-2026-08-03.md`](../rag-remediation-plan-2026-08-03.md) — **DoD**, не очередь галочек |

**Не использовать:** старые `✅ START HERE` ниже Update-116; dirty  
`BACKLOG.md` / `README.md` / audits; `_NEXT_SESSION.md` как единственный SoT  
(это pointer only).

**Plan checkboxes:** не править casually. Local slice ≠ section closed ≠ release.

---

## 1. Нулевая неоднозначность

| Факт | Значение |
|------|----------|
| Latest **implementation** | `c707c46` — **6.7** human calibration readiness + recalibrate CLI |
| Prior implementation | `69c6fdf` **6.6** · `47e255a` **7.7** |
| Latest **docs before this Update** | `add33e9` — Update-115 |
| This Update-116 docs SHA | **unknown in-file** → `git log -3 --oneline` после коммита |
| Branch advisory | refresh via `git status -sb` |
| Active writer / WIP | **none** |
| Locally complete (documented scopes) | **2.1–2.6g** + **3.1a–3.1i** + **4.1–4.5** + **5.1–5.3** + **6.1–6.7** + **7.1–7.7** + **8.1–8.5** + **DEP-01** |
| Full plan §1–§10 / production | **NOT** complete / **NOT** claimed |
| Plan status | **ACTIVE** |
| Next ordered (default) | real human dual-annotator sample + reissue **or** live execute (opt-in) |
| Gates | **no** push / deploy / live multi-service / live provider execute / migrate 019–023 without **explicit opt-in** |

**This Update-116 records 6.7.** Implementation `c707c46` is committed.  
Verification: calibration band **19 passed**; seed readiness NOT_READY (synthetic);  
Ruff clean. Full suite / live / push **not** claimed. Production human labels **not** collected.

### Dataset snapshot (7.7)

| Slice | Count |
|-------|------:|
| multi_tenant | 3 (acme/beta/gamma) |
| multi_turn | 5 (2 sessions) |
| claim_citation | 3 |
| no_answer | 3 |
| tools | 3 |
| streaming | 3 |
| adversarial | 3 |
| pii | 3 |
| durable_escalation | 3 |
| context_recall | 3 |
| **total cases** | **67** |
| `MIN_CASES_PER_REQUIRED_SLICE` | **3** |

---

## 2. Быстрый старт следующей сессии

```text
1. Cycle-guard: one named atomic slice per user turn.
2. cd D:\RAG_Support_Assistant
3. git status --short --branch
4. git log -12 --oneline          # actual Git wins
5. Read ONLY top Update-116 in AGENT_STATE.md + this file §1–§11
6. Default work: real human dual-annotator sample + reissue OR live execute opt-in. Announce: slice 1/1
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
| **6** judge / safety / agentic | **6.1–6.7** local | production human dual-annotator sample residual |
| **7** eval gate | **7.1–7.7** local | live execute with secrets; mock≠release; optional more depth |
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
| **7.4** | `8f4269f` | required slices + min_context_recall; 47 cases |
| **7.5** | `4eceed3` | CI write + upload + require-wire of baseline artifact |
| **7.6** | `d1ae4d6` | scheduled live provider gate scaffold (opt-in) |
| **7.7** | **`47e255a`** | min 3 cases/required slice; **67** total cases |

### §6 judge / safety / agentic

| Slice | SHA | Surface |
|-------|-----|---------|
| **6.1** | `b3494a0` | unmeasured agentic; never fixed 80/85/90 |
| **6.2** | `d0317e9` | pre-response PII + prompt-injection |
| **6.3** | `d6e3a55` | independent judge fail-closed |
| **6.4** | `a7cefc3` | routing calibration artifact (bootstrap-defaults) |
| **6.5** | `431893c` | measured grounding when agentic has KB docs |
| **6.6** | `69c6fdf` | LLM evaluate wire on KB agentic terminals |
| **6.7** | **`c707c46`** | human readiness gate + recalibrate CLI |

### §8 widget / edge

| Slice | SHA | Surface |
|-------|-----|---------|
| **8.1** | `0bee13e` | widget bootstrap JWT, origins, frame-ancestors |
| **8.2** | `756562e` | ASGI received-byte body limits; upload stream/atomic place |
| **8.3** | `13a9a5b` | OIDC email_verified; (issuer, subject); no rebind |
| **8.4** | `68a30b2` | production placeholders rejected; no dev-admin |
| **8.5** | `4d6be52` | Playwright cross-origin E2E; iframe Origin=API |

### DEP-01 / §5 / §4 / §3 / §2

| Band | Ends at SHA | Note |
|------|-------------|------|
| DEP-01 | `f622d58` | docs-site high=0; exceptions → **2026-11-07** |
| §5 | `1cdecb2` **5.3** | grader fail-closed |
| §4 | `6453530` **4.5** | outbox retry API |
| §3 | `fe2f0aa` **3.1i** | runtime/session/budget band |
| §2 | `f347feb` **2.6g** | fault-injection residual closed local |

---

## 5. Contracts (recent complete slices)

### 7.7 @ `47e255a`

- `MIN_CASES_PER_REQUIRED_SLICE = 3` (default coverage floor)
- Dataset 47 → **67** cases; every required slice ≥3
- multi_tenant: acme/beta/gamma; multi_turn: 2 sessions (5 cases)
- Manifest plan_slice `7.7`, `min_cases_per_slice: 3`
- Files: `evaluation/curated_cases.jsonl`, manifest, `scripts/regression_eval.py`,
  `tests/test_curated_dataset_expansion.py`

### 7.6 @ `d1ae4d6`

- `scripts/live_provider_gate.py` readiness/command/live
- Default readiness: no live calls; `SKIPPED_NO_OPT_IN`; never release PASS
- Live: `RAG_LIVE_PROVIDER_GATE` + provider keys; fail-closed without keys
- Live argv: `--release-gate --allow-paid-apis`; **forbids** mock
- Workflow: `.github/workflows/live-provider-gate.yml` (schedule + dispatch)
- Tests: `tests/test_live_provider_gate.py`

### 6.7 @ `c707c46`

- `assess_human_calibration_readiness` fail-closed floors
- synthetic `label_source` cannot claim `source=human-labelled`
- `reissue_calibration_from_labels` recomputes agreement/cost
- CLI `scripts/recalibrate_routing.py` readiness/reissue/`--require-human`
- Seed remains synthetic; production human sample still residual

### 6.6 @ `69c6fdf`

- `agent/agentic_evaluate.py` — independent-judge self-eval for agentic
- `_agentic_terminal_fields_with_eval` on KB terminals (tool loop + order+KB)
- Measured `quality_source=llm` only on parseable judge score
- Fail-closed quality on judge miss; §6.5 grounding preserved
- `route=auto` when grounding + llm quality clear floors
- Flag `RAG_AGENTIC_QUALITY_EVAL` (default ON)
- Confirmation / order-only / no-KB remain unmeasured

### 6.5 @ `431893c`

- `search_kb_docs` → (text, raw docs)
- KB + `[N]` citations → citation-bound grounding measured
- `route=auto` only with measured quality (llm/heuristic) + floors
- Confirmation / order-only / no-KB → unmeasured (6.1)

### 6.4 @ `a7cefc3`

- Artifact `kind=routing-calibration` schema v1; seed **bootstrap-defaults**
- Thresholds 80 / 80 / 0.8 / 70 (historical band; not full human DoD)
- `resolve_routing_thresholds` → `route_or_retry` / `build_support_graph`
- Residual: replace synthetic `labelled_routes` with human labels for full DoD

### 7.5 @ `4eceed3`

- CI smoke write/upload/require baseline artifact
- Still mock → **SMOKE only**; no `--release-gate` on PR path

### 7.4–7.1 / 8.5–8.1 / DEP-01 (one-liners)

- **7.4** slices + `min_context_recall` schema
- **7.3** merge-base baseline artifact CLI
- **7.2** mock → `SMOKE_PASS` only
- **7.1** infra/skip/empty → FAIL
- **8.5** Playwright cross-origin E2E
- **8.4** production secrets / no dev-admin
- **8.3** OIDC email_verified + (issuer, subject)
- **8.2** ASGI body limits + upload stream
- **8.1** widget bootstrap JWT + frame-ancestors
- **DEP-01** docs-site high=0; dated exceptions

---

## 6. Module owners (do not reopen without conflict)

| Path | Slices | Role |
|------|--------|------|
| `evaluation/curated_cases.jsonl` | **7.4 / 7.7** | curated corpus (**67**) |
| `evaluation/curated_cases.manifest.json` | **7.7** | required slices; min 3 |
| `tests/test_curated_dataset_expansion.py` | **7.4 / 7.7** | coverage + depth |
| `scripts/regression_eval.py` | **7.1–7.4 / 7.7** | gate + slices + depth floor |
| `scripts/live_provider_gate.py` | **7.6** | live gate scaffold |
| `.github/workflows/live-provider-gate.yml` | **7.6** | schedule + opt-in dispatch |
| `tests/test_live_provider_gate.py` | **7.6** | live gate contract |
| `.github/workflows/ci.yml` | **7.5** | baseline write/upload/require |
| `tests/test_github_workflows.py` | **7.5** | CI wire lock |
| `agent/agentic_evaluate.py` | **6.6** | agentic LLM evaluate wire |
| `agent/agentic_measure.py` | **6.5** | measured agentic KB gate |
| `agent/tools.py` | **6.5** | `search_kb_docs` |
| `agent/calibration.py` | **6.4 / 6.7** | routing calibration + human readiness |
| `scripts/recalibrate_routing.py` | **6.7** | recalibrate CLI |
| `evaluation/calibration/` | **6.4 / 6.7** | seed artifact + labelled_routes |
| `agent/judge_policy.py` | **6.3** | independent judge |
| `agent/response_safety.py` | **6.2** | PII / injection |
| `agent/grounding.py` | **5.1–5.2** | factuality / citations |
| `docs-site/*` | **DEP-01** | npm audit posture |
| `api/routers/widget.py` | **8.1 / 8.5** | widget bootstrap |
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
27. Required dataset slices need ≥3 cases each (depth floor §7.7)  
28. Agentic KB terminals run LLM evaluate when flag ON; fail-closed quality (§6.6)  
29. Synthetic calibration labels never upgrade to human-labelled without readiness (§6.7)  

---

## 8. Verification recipes (last known green; re-run when coding)

### §7.7 band

```powershell
python -m pytest tests/test_curated_dataset_expansion.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check scripts/regression_eval.py tests/test_curated_dataset_expansion.py
```

### §7.6 band

```powershell
python -m pytest tests/test_live_provider_gate.py tests/test_github_workflows.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check scripts/live_provider_gate.py tests/test_live_provider_gate.py
python scripts/live_provider_gate.py --mode readiness --write-report reports/regression/live-provider-gate-readiness.json
```

### §6.7 band

```powershell
python -m pytest tests/test_calibration_artifact.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check agent/calibration.py scripts/recalibrate_routing.py tests/test_calibration_artifact.py
python scripts/recalibrate_routing.py --mode readiness --labels evaluation/calibration/labelled_routes.jsonl
```

### §6.6 band

```powershell
python -m pytest tests/test_agentic_evaluate.py tests/test_agentic_measure.py tests/test_agent_tools.py -q -p no:cacheprovider -p no:schemathesis
python -m ruff check agent/agentic_evaluate.py agent/agentic_measure.py agent/graph.py config/settings.py tests/test_agentic_evaluate.py
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

Full suite / live / migrate — **not** the default gate for a single slice.

---

## 9. Next named candidate (not started)

**Default picks (one only):**

1. **Collect real dual-annotator human sample** then  
   `python scripts/recalibrate_routing.py --mode reissue --require-human --write`  
2. **Live provider execute** with secrets + `RAG_LIVE_PROVIDER_GATE` +  
   `--execute` (**explicit opt-in only**)  
3. **Astro 7** major when Starlight supports it (clears DEP-01 moderate residual)  

### Out without opt-in

- live multi-service / migrate / push / deploy / live provider execute  
- re-select through **8.5** / **6.1–6.7** / **7.1–7.7** / **DEP-01**  
- OIDC live IdP drill; full browser matrix expansion  
- bulk plan checkbox edits; production claims  

### Alternates (only if user prioritizes)

- live §1 / migrate 019–023 (**explicit opt-in only**)  
- §4 graph tokens / stream parity default  
- further corpus depth beyond 3/slice  

---

## 10. Protected dirty / untracked (do not touch)

**Dirty tracked (leave alone):**  
`BACKLOG.md`, `README.md`, `audit_gpt_23_07_26.md`, `plan_sol_23_07_26`

**Untracked (examples):**  
`.grok-prompts/`, `.pytest_tmp*/`, presentations, `_NEXT_SESSION.md` (pointer),  
`rag-remediation-plan-2026-08-03.md` (active plan — DoD source, no casual  
checkbox edits), architecture HTML, etc.

---

## 11. Cycle budget (workspace rules)

- One user turn = **one** named atomic implementation slice + verify + status docs  
- After slice committed or blocked → **yield** to user  
- No push / deploy / live / migrate without explicit opt-in  
- Quality > speed; actual Git wins over embedded SHAs  
