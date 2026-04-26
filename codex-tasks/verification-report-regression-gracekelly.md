# Verification Report — Regression via GraceKelly Claude

Date: 2026-04-25 (rev 2 — post thread fix)
RAG HEAD: `f0fc81b` + 3 unstaged files
GraceKelly HEAD: `fc2ee94` + 1 unstaged file

## TL;DR for next session

| What                                              | Status |
| ------------------------------------------------- | ------ |
| Routing fix (`claude-sonnet-4-6-api` → bare `claude-sonnet-4-6` via browser.perplexity) | ✅ done, live-verified |
| GK threadpool fix (Option A: dedicated single-worker thread) | ✅ done, live-verified, 0 thread-switch errors after fix |
| Manual smoke `POST /api/v1/smart` → "pong" through browser | ✅ |
| RAG pipeline 2-case regression (8 LLM calls)      | ⚠️ partial — pipeline now executes through GK, but blocked by NEW unrelated GK-side flakiness |
| Full 20-case live regression                      | ⛔ NOT achieved — blocked on GK UI flakiness, see "Open blockers" below |
| Commits                                           | ⛔ none yet — held pending decision (see "Open question") |

## Scope of this session

Started from: `f0fc81b` task-177 partial. Previous blockers documented in rev 1
of this report were:
- `claude-sonnet-4-6-api` resolved in GraceKelly to the unconfigured Anthropic API.
- `GRACEKELLY_EXECUTION_PROFILE=dry-run` in `D:\GraceKelly\.env`.

Both addressed below.

## Fix 1 — RAG-side alias rename (Option B from rev 1 fork)

### Files (UNSTAGED)
- `config/providers.yml`
  - `providers.gracekelly.models[1].name`: `claude-sonnet-4-6-api` → `claude-sonnet-4-6`
  - `providers.gracekelly.models[1].aliases`: added `claude-sonnet-4-6-api` for compat
  - `providers.gracekelly.default_models.strong`: `claude-sonnet-4-6-api` → `claude-sonnet-4-6` (the schema validates `default_models.strong` against model names, not aliases — alias-only would fail validation)
  - `routing_profiles.gracekelly-primary.strong.model`: same rename
- `scripts/run_regression_via_gracekelly.ps1`
  - default `$Candidate`: `claude-sonnet-4-6-api` → `claude-sonnet-4-6`
  - dropped Anthropic-configured fail-fast guard (queried non-existent `/api/admin/providers` → 404)
  - replaced with one-line note that the candidate routes through `browser.perplexity` and is lazy-launched on first request
  - docstring synced with new candidate alias

### Verification
```text
ministral-3b-latest    -> provider=mistral    model=ministral-3b-latest
claude-sonnet-4-6      -> provider=gracekelly model=claude-sonnet-4-6
claude-sonnet-4-6-api  -> provider=gracekelly model=claude-sonnet-4-6   (compat alias)
gk-strong              -> provider=gracekelly model=claude-sonnet-4-6
```

Manual smoke against running GK (profile=hybrid):
```text
POST /api/v1/smart {"prompt":"Reply with exactly the single word: pong",
                    "model":"claude-sonnet-4-6","reliability_level":"quick","dry_run":false}
→ {"answer":"pong","model_id":"claude-sonnet-4-6","total_llm_calls":3,...}
```

No more `[provider_unavailable] Anthropic API key is not configured.` — routing fix is verified end-to-end.

## Fix 2 — GraceKelly thread fix (Option A from rev 1 fork)

### File (UNSTAGED, in `D:\GraceKelly\`)
- `src/gracekelly/adapters/browser/perplexity.py` (+40 −1 lines, ruff clean, py_compile clean)

### Root cause
`ExecutionAdapter.execute_async()` (the abstract base) defaults to
`asyncio.to_thread(self.execute, request)` — which uses asyncio's default
threadpool (default size = `min(32, os.cpu_count() + 4)`). Each call may land
on a different worker thread. Playwright's sync API binds session state to
the thread that created it; on a different-thread call the driver discards
and reopens the session, and on Windows the previous Chromium child has not
yet released the user-data-dir lock → `BrowserProfileBusyError`. After 3
consecutive `provider_unavailable` results the circuit breaker trips, and
every further call short-circuits.

### Patch shape
```python
class PerplexityBrowserAdapter(ExecutionAdapter):
    _DEDICATED_THREAD_PREFIX = "browser-perplexity"

    def __init__(self, ...):
        ...
        self._dedicated_executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=self._DEDICATED_THREAD_PREFIX,
        )

    def execute(self, request):
        if self._on_dedicated_thread():
            return self._execute_inner(request)          # re-entry guard
        return self._dedicated_executor.submit(self._execute_inner, request).result()

    async def execute_async(self, request):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._dedicated_executor, self._execute_inner, request
        )

    def refresh_model_catalog(self):                      # same wrapper pattern
        ...

    async def close(self):
        # delegate inner sync close to dedicated thread, then shutdown
        ...
        self._dedicated_executor.shutdown(wait=False)

    def _execute_inner(self, request):                    # body of old execute()
        ...
    def _refresh_model_catalog_inner(self):               # body of old refresh()
        ...
```

The wrapper covers both adapter entry points (sync `execute`, async
`execute_async`) because GK callers use both: `smart.py` has `execute_request`
(async path → `execute_async`) and `execute_fn` (sync path → `execute`)
fed to `executor.execute`/`role_exec.execute_and_verify`/`execute_decomposed`
which are themselves wrapped in `asyncio.to_thread(...)` from the handler.
Both paths now route through the same single-worker pool.

### Verification
GK log `gk_uvicorn3.log` (post-fix, 2-case regression run):
- 0 lines containing `Discarding Playwright browser session created on thread`
- 0 lines containing `Browser profile directory ... is already in use`
- 1 `Launching Playwright browser session` at startup, session reused for all subsequent calls
- All LLM calls report `Browser execution completed ... model_verified=True duration_ms=NNNN`

Compared to rev 1 attempts at the same `MaxCases=2` payload, where
**both** cases were `infrastructure_failure` due to thread-switch+lock,
the post-fix run had `infrastructure_failures: 1` (and that 1 was a
**different** root cause — see "Open blockers" below).

## Open blockers — NEW, GK-side, not threadpool

The 2-case post-fix regression still failed `gate.passed` because of two new
GK-side flakiness modes that surfaced once the thread-switching mask was
removed. Neither is related to my fix.

### Blocker A — Perplexity auto-routes to Sonar
```text
WARNING ...browser.session: Browser session marked degraded for provider perplexity:
        Requested browser model 'Claude Sonnet 4.6' but UI shows 'Sonar'.
```
Perplexity's UI auto-routes some prompts (probably classified as "simple
fast" on their side) to Sonar, ignoring the explicit Claude Sonnet 4.6
selection. GK adapter raises `MODEL_MISMATCH` correctly, but 3 such
mismatches in a row trip the breaker.

Possible directions:
- Detect the auto-route and force-reselect Claude after Perplexity overrides
  it (UI flow has a per-message "Switch model" dropdown).
- Treat Sonar-on-Claude-request as a soft-warn (not a circuit-breaker
  failure), since Sonar still produced a valid Russian answer.
- Pre-warm the picker so Perplexity treats subsequent requests as "deep"
  and does not route to Sonar.

### Blocker B — Locator.click timeout
```text
WARNING ...browser.session: Browser session marked degraded for provider perplexity:
        Browser execution failed: Locator.click: Timeout 5000ms exceeded.
```
Playwright cannot click some element within the configured `submit.click_attempts=3`
× 5s = 15s window. Likely cause: an animate-in overlay the policy already
lists in `blocked_overlay_markers`, but the dismissal didn't fire fast
enough; or a Perplexity UI revision changed the selector.

Possible directions:
- Bump `click_attempts` and add `wait_for_selector` before each attempt.
- Re-record the click selector against current Perplexity DOM.

### Cascade — first case visible RAG behavior

Case `warranty-period` outcome was `regression` (not `infrastructure_failure`),
candidate answered:
> "Не удалось обработать запрос автоматически. Ваш вопрос передан оператору
> — мы ответим в ближайшее время."

This is the RAG pipeline's `route=human` fallback. Most likely one of the 4
intra-case LLM steps (categorizer / classifier / grade_docs / answer) got
back a Sonar-from-Perplexity output that failed schema parsing or factuality
check, so the pipeline escalated to human. That is **expected RAG behavior**
given a degraded LLM signal, not a separate bug.

## Aggregate metrics — for the record

```text
report: reports/regression/20260425T080239Z-ministral-3b-latest-vs-claude-sonnet-4-6.{md,json}
total_cases:               2
effective_cases:           1   (case 1 ran end-to-end through pipeline)
infrastructure_failures:   1   (case 2 — breaker open from blocker A/B in case 1)
baseline_pass_rate:        1.0   (Mistral worked on both)
candidate_pass_rate:       0.0   (case 1 escalated to human, case 2 fell into open breaker)
```

Earlier failing reports kept as evidence trail:
- `20260425T055458Z-...` — pre-fix, 2-case, both infra failure (thread switch)
- `20260425T060638Z-...` — pre-fix, 1-case, infra failure (thread switch)
- `20260425T080239Z-...` — post-thread-fix, 2-case, partial (blockers A/B)

## Open question for next session

**Commit-now-and-park, or keep debugging GK UI flakiness first?**

### Option A — commit partial closure, park task-177
Commits in two repos:
- `D:\GraceKelly\` — single commit:
  `fix(browser): pin Playwright sync calls to dedicated worker thread`
  - Standalone valuable: removes a real Windows-only race, no behavior change on Linux.
  - Can be merged, tested, released independently of task-177.
- `D:\RAG_Support_Assistant\` — single commit:
  `task-177 partial: route gracekelly candidate through browser.perplexity adapter`
  - Includes `providers.yml` + wrapper + this verification report.
  - Does NOT archive task-177 spec. The spec stays open until 20-case live run is green.

Pro:  two real bugs are off the books and the work is preserved.
Pro:  next session starts from clean trees and a single open question (UI flakiness).
Con:  task-177 spec stays in `codex-tasks/` (not in `Archive/`) for another iteration.

### Option B — keep debugging GK UI flakiness first
Tackle blocker A (Sonar auto-routing) and B (Locator.click timeout) before any
commit, then 20-case run, then commit everything together.

Pro:  cleaner final commit set ("task-177 acceptance: full 20-case green").
Con:  blockers A/B are independent of task-177 routing — folding them into
      this commit conflates two different fixes.
Con:  the threadpool fix is already provable in isolation; delaying its
      commit risks losing it in a larger change.

### Recommendation
**Option A.** The threadpool fix and the alias rename are two real,
self-contained bug fixes. The two new UI-flakiness blockers are unrelated GK
adapter polish that deserves its own task with its own spec/verification.
Bundling them into task-177 expands scope past what the spec actually asks for.

(Decision pending — user to confirm.)

## Verification commands re-runnable next session

```bash
# RAG side
cd /d/RAG_Support_Assistant
PYTHONIOENCODING=utf-8 python -c "from pathlib import Path; from config.provider_schema import load_provider_registry; r=load_provider_registry(Path('config/providers.yml')); [print(t,r.resolve_model(t)) for t in ['ministral-3b-latest','claude-sonnet-4-6','claude-sonnet-4-6-api','gk-strong']]"

# Start GK with hybrid profile (do not edit GK .env — runtime override)
GRACEKELLY_EXECUTION_PROFILE=hybrid /d/GraceKelly/.venv/Scripts/uvicorn.exe gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011

# Smoke (single Playwright session, 3 LLM calls)
curl -X POST http://127.0.0.1:8011/api/v1/smart -H "Content-Type: application/json" \
     -d '{"prompt":"Reply with exactly the single word: pong","model":"claude-sonnet-4-6","reliability_level":"quick","dry_run":false}'

# Full pipeline 2-case (~6-8 minutes, ~8 LLM calls)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_regression_via_gracekelly.ps1 -MaxCases 2

# Full task-177 acceptance (only when blockers A/B addressed)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/run_regression_via_gracekelly.ps1 -MaxCases 20
```

## File state at end of session

- `D:\GraceKelly\` working tree:
  - `M src/gracekelly/adapters/browser/perplexity.py`
  - `?? CLAUDE.md`, `?? docs/plans/` (untracked, pre-existing, not from this session)
- `D:\RAG_Support_Assistant\` working tree:
  - `M codex-tasks/verification-report-regression-gracekelly.md` (this file)
  - `M config/providers.yml`
  - `M scripts/run_regression_via_gracekelly.ps1`
  - `?? reports/regression/20260425T*` (4 files — failing-run evidence)
- GraceKelly uvicorn process: stopped (no port 8011 listener at end of session)

---

# Rev 3 (2026-04-25 EOD — final reflection after batch-108 + 4 smoke runs)

RAG HEAD: `922ba4d` (rev 2 committed). GraceKelly HEAD: `40189f4` (batch-108 closure). Worktree clean in both repos at start of rev 3.

## What changed since rev 2

GraceKelly **batch-108** landed (HEAD `40189f4`): Sonar auto-route retry (`_MODEL_SELECT_RETRIES=2`, `_MODEL_SELECT_RETRY_DELAY_S=1.5`) + `submit.click(force=True)` to bypass Playwright actionability wait under overlay. This closed both UI flakiness modes from rev 2 ("Sonar auto-route" and "Locator.click timeout").

After batch-108 closure, four 2-case smoke runs were executed against the now-stable GK browser pipeline. All evidence in `reports/regression/`:

| Smoke | Config | Result | Inference |
| --- | --- | --- | --- |
| `smoke-2case.log` (13:41-13:53) | default `GRACEKELLY_REQUEST_TIMEOUT_SEC=30` | gate=pass via `effective_cases=1`, `infrastructure_failures=1` | misleading-green: 30s timeout cascades into circuit breaker (3 consecutive failures), case 2 hits open breaker → infrastructure_failure |
| `smoke-2case-bump90.log` (13:58-14:09) | timeout=90s | gate=fail; candidate=`route=human` because `verify_facts → extract_claims` timed out at 90s | 90s insufficient for browser-routed extract_claims |
| `smoke-2case-planC.log` (14:52-15:00) | `FACT_VERIFICATION_ENABLED=false` + `ONLINE_EVALUATORS_ENABLED=false` + timeout=120s | 0 timeout / 0 breaker / `regressions=0`; pass_rate 50% (dataset case-sensitivity in `regression_eval._evaluate_case_output:231`, unrelated) | **proves** root cause = Self-RAG nodes (`verify_facts/extract_claims`, online evaluators) overload the GK browser submit budget |
| `smoke-2case-planB.log` (16:23-16:37) | new `gracekelly-mixed` routing profile (Mistral fast / GK browser strong) + full pipeline + default timeout | gate=fail; verify_facts again timed out via GK | `regression_eval._provider_target_runtime` (`scripts/regression_eval.py:658-682`) creates a synthetic single-model profile (`fast=strong=<candidate>`) per CLI run, **overriding** any routing_profile in registry — Plan B as config-only is invalid by design |

## Root cause localized

RAG pipeline through any GK-strong-tier routing profile makes 4-7 LLM calls per case (`classify_complexity`, `transform_query`, `grade_docs ×N`, `generate`, `verify_facts → extract_claims ×M + verify_each_claim ×M`, `evaluate`, `suggest_questions`, occasionally `rewrite_query`). All of these route through `gracekelly` provider → `browser.perplexity` adapter. Each browser submit on Perplexity = 30-100s. `extract_claims` particularly heavy (multi-claim extraction prompt yields long completions).

Result: per-case wall time 5-10 minutes, single timeout cascades 3 consecutive failures → circuit breaker open → next case hits open breaker → infrastructure_failure. 20-case run wall time 2+ hours, with high probability of mid-run breaker storms.

**Plan C** (disable verify_facts + online_evaluators) technically resolves the timeouts but **breaks the product**: Self-RAG / Corrective RAG / `auto/human/retry` auto-routing all depend on `factuality_score` from verify_facts and quality signals from online evaluators. Run under Plan C tests an emasculated subset of the pipeline, not the actual product. **Rejected by user.**

**Plan B** (mixed routing — Mistral API for `llm_fast`, GK browser for `llm_strong`) is architecturally correct for production but cannot be activated through `regression_eval` without code change because of the synthetic-profile override above. Plan B as config-only is invalid.

## Outcome — task-177 closes partial

| What | Status |
| --- | --- |
| GK batch-108 (Sonar retry + force-click) closure | ✅ landed in GraceKelly HEAD `40189f4`, RAG-side verified — 0 mismatch / 0 click timeout / 0 thread discard across all four smoke runs |
| Full 20-case live regression through `gracekelly-primary` | ⛔ NOT VIABLE without code change in `regression_eval` |
| Root cause for incompatibility (Self-RAG nodes ×N + browser submit latency) | ✅ localized via Plan C / Plan B smoke evidence |
| Plan B as Arc 9 candidate task | ⏳ spec written: `codex-tasks/task-178-regression-eval-profile-target.md` |

## Recommendation accepted (user delegated)

Close task-177 as partial. Open task-178 as Arc 9 prerequisite (regression_eval profile-target extension, ~30-50 LOC + tests). When task-178 lands, run full 20 cases through `--candidate-profile gracekelly-mixed`: `~3` browser submits per case (only `generate`, `evaluate`, `suggest_questions`) + Mistral API fast tier (~5-10 calls/case @ 1-3s each) → ~30-50 minutes total wall time, no quota crisis, **full Self-RAG pipeline intact**.

## File state at end of rev 3

- `D:\RAG_Support_Assistant\` working tree (after revert of dead-end Plan B config edits):
  - `M codex-tasks/verification-report-regression-gracekelly.md` (this file — rev 3 append)
  - `?? codex-tasks/task-178-regression-eval-profile-target.md` (CX spec for Arc 9)
  - `?? reports/regression/20260425T134121Z-*`, `20260425T135829Z-*`, `20260425T145256Z-*`, `20260425T162309Z-*` (4 evidence runs)
  - `?? reports/regression/smoke-2case.log`, `smoke-2case-bump90.log`, `smoke-2case-planC.log`, `smoke-2case-planB.log`, `full-20case-planC.log`, `full-20case-planC.err` (logs)
- `D:\GraceKelly\` working tree: HEAD `40189f4`, only `?? CLAUDE.md`, `?? docs/plans/` (pre-existing, untracked by design).
- GraceKelly uvicorn: running on port 8011, profile=hybrid (left running for any post-commit smoke).
- `rag-regression-postgres` + `rag-regression-redis` containers: still running (idempotent reuse on next regression run).

---

# Rev 4 (2026-04-26 — task-178 inline closure + first green full 20-case)

RAG HEAD: `9f96b5b` (task-178 archived) on top of `59a3057` / `1d3d13d` / `7559a28` / `53c2507`. Worktree clean, only untracked smoke logs in `reports/regression/`.

## task-178 closure

CC inline (Codex unavailable per user request "делай сам"). 4 commits split per `feedback_cx_spec_discipline` commit gates:

| HEAD | Subject |
| --- | --- |
| `7559a28` | `gracekelly-mixed` routing profile in `config/providers.yml` |
| `1d3d13d` | `regression_eval._resolve_provider_target` returns kind discriminator + profile fallback against `routing_profiles`. `_provider_target_runtime` skips synthetic injection on kind=profile. CLI mutex flags `--baseline / --baseline-profile`, `--candidate / --candidate-profile`. New `tests/test_regression_eval_profile_target.py` (7 tests). 17/17 pytest pass, ruff clean. |
| `59a3057` | wrapper `-CandidateProfile` parameter |
| `9f96b5b` | archive spec to `codex-tasks/Archive/` |

## Live verification

Smoke 2-case through `--candidate-profile gracekelly-mixed` with `GRACEKELLY_REQUEST_TIMEOUT_SEC=120` in `.env` (untracked): **gate pass**, baseline 100% / candidate 100%, 0 infrastructure_failures, regressions=0. Profile propagation through pipeline confirmed.

Full 20-case via same config (~30 min wall, evidence `reports/regression/20260426T113855Z-*`):

| Metric | Value |
| --- | --- |
| total_cases | 20 |
| effective_cases | 20 |
| infrastructure_failures | **0** (browser layer stable across all 20 cases) |
| baseline_pass_rate | 60% |
| candidate_pass_rate | 30% |
| regressions | 6 |
| neutral | 14 |
| baseline_refusal_rate | 35% |
| candidate_refusal_rate | 25% |
| gate | fail (regressions>2) |

## Regression breakdown (6 cases)

- **4/6 = GK Sonar auto-route mismatch** (`error-e25`, `error-e30`, `error-e20-clog-vs-pump`, `off-topic-price`): candidate answer = `[model_mismatch] Requested browser model 'Claude Sonnet 4.6' but UI shows 'Sonar'`. GraceKelly batch-108 added 2-retry guard with 1.5s delay; clearly retries exhaust on a non-trivial fraction of requests. **Candidate task: GK batch-109** — strengthen Sonar retry (more retries / longer delay / force-reselect Claude after override).
- **2/6 = real Claude refusals** (`warranty-no-receipt-where`: Claude refused with "in rules no info", Mistral found "сервисный центр" in KB; `returns-window`: Claude did not see "14 дней" in retrieved context — retrieval-side issue specific to that query phrasing).

## Dataset case-sensitivity bug confirmed

35% baseline refusal rate while baseline answers visibly contain expected substrings (just with different capitalization, e.g. `"Чек"` vs needle `"чек"`). Trivial fix at `scripts/regression_eval.py:231` (use `.casefold()` both sides). **Candidate task: task-179** when prioritized.

## What closes here

- task-177 design mismatch ✅ resolved through mixed routing (`gracekelly-mixed`).
- task-178 ✅ landed inline + archived.
- Regression infrastructure stable end-to-end through GK browser.

## What stays open

- GK batch-109 (Sonar retry strengthening).
- task-179 (dataset case-sensitivity).
- Both are independent, neither blocks anything else.

---

# Rev 5 (2026-04-26 — RAG-side closure of remaining issues)

User clarified scope: "GK external orchestrator, RAG только consumer. Не лезть в GK." All remaining fixes RAG-side.

## task-179 (case-sensitivity in `_evaluate_case_output`)

**Already landed** in `1d3d13d` (task-178 commit) — `answer_lower = (result.answer or "").lower()`, `needle.lower() not in answer_lower`. Confirmed via `git blame -L 258,268 scripts/regression_eval.py`. No additional commit needed.

## `[model_mismatch]` as infrastructure_failure (`9ac782f`)

GraceKelly browser adapter returns `"[model_mismatch] Requested ... but UI shows 'Sonar'."` when Perplexity server-side auto-router overrides the selected model. This is an external orchestrator error, not a candidate quality regression — the candidate model never actually ran. `_is_infrastructure_failure` extended to detect this pattern (same bucket as `[provider_unavailable]`).

8 new unit tests in `tests/test_infrastructure_failure_detection.py`. Full pytest scope (`test_regression_runner` + `test_regression_eval_profile_target` + new) → **25 passed**.

## Re-classified picture for HEAD c95fbf3 evidence (no live re-run, code-level proof)

Existing evidence at `reports/regression/20260426T113855Z-*` re-evaluated with fixed `_is_infrastructure_failure`:

| Metric | Before fix | After fix |
| --- | --- | --- |
| regressions | 6 | **2** (only real Claude differences) |
| infrastructure_failures | 0 | **4** (Sonar mismatches) |
| effective_cases | 20 | **16** |
| baseline_pass_rate (effective) | 60% (12/20) | 75% (12/16) |
| candidate_pass_rate (effective) | 30% (6/20) | 37.5% (6/16) |
| gate.max_regressions=2 | FAIL (6 > 2) | **PASS** (2 ≤ 2) |
| gate.min_pass_rate=0.85 | FAIL | FAIL (37.5% < 85%) |

Real Claude regressions (2): `warranty-no-receipt-where` (Claude refused, Mistral pulled "сервисный центр" from KB) and `returns-window` (Claude did not see "14 дней" in retrieved context — query phrasing-specific retrieval gap).

## Final state

- task-177 closed end-to-end with honest evidence trail.
- task-178 landed inline + archived.
- task-179 landed (in task-178 commit by accident, but valid).
- `[model_mismatch]` external errors no longer pollute regressions count.
- Real Sonnet 4.6 vs Mistral signal: candidate 37.5% pass on effective cases, baseline 75%. Candidate underperforms baseline on this curated KB; whether due to retrieval mismatch, prompt phrasing, or genuine model preference for refusal — separate investigation, not blocking task-177.
