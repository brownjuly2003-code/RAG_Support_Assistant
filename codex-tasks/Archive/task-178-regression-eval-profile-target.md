---
name: task-178-regression-eval-profile-target
description: Extend scripts/regression_eval.py to accept routing-profile names as targets, so mixed-routing benchmarks (e.g., Mistral fast / GraceKelly browser strong) can run through the full Self-RAG pipeline without forcing a synthetic single-model override.
date_added: 2026-04-25
risk: medium
source: human (Julia)
---

# Goal

Allow `scripts/regression_eval.py` to interpret `--baseline` / `--candidate` arguments as either:

1. **Model name or alias** (current behavior): regression_eval injects a synthetic `benchmark-<slug>` routing profile with `fast == strong == <model>` into the registry, then runs the full pipeline single-model.
2. **Routing-profile name** from `config/providers.yml.routing_profiles` (NEW): the existing profile is used as-is. **No** synthetic override. Pipeline runs through whatever model mix the profile dictates per tier.

This unblocks honest Self-RAG benchmarks against GraceKelly: the `generate` final-answer node can route through GK browser (where Claude Sonnet 4.6 reasoning matters), while `classify_complexity`, `transform_query`, `grade_docs`, `verify_facts → extract_claims`, online evaluators all route through fast Mistral API (where 30-100s browser submit per call is wasteful and triggers timeouts).

# Context (read this — CX has not seen the conversation)

## Why this matters now

`task-177` landed Mistral-vs-Claude regression infrastructure (curated 20-case dataset + wrapper + GK-aware report generation), but **never achieved a green 20-case run**. After `D:\GraceKelly\` `batch-108` closed UI flakiness (Sonar auto-route retry + `submit.click(force=True)`, GraceKelly HEAD `40189f4`), four 2-case smoke runs (evidence in `reports/regression/`, summarized in `codex-tasks/verification-report-regression-gracekelly.md` rev 3) localized the remaining blocker:

- Pipeline through `gracekelly-primary` profile = 4-7 LLM calls per case, all routed through `browser.perplexity` (single-thread executor, 30-100s/submit).
- `verify_facts → extract_claims` is the worst offender (multi-claim extraction prompt yields long completions). At RAG-client `httpx` timeout 30s the call cascades to circuit breaker open after 3 consecutive failures, blocking subsequent cases with `infrastructure_failure`.
- Bumping timeout to 90s, 120s, 300s does not fix it cleanly — at 300s the wall-clock per case is 5-10 min, and 20 cases ≈ 2-4 hours with persistent breaker risk.
- Disabling Self-RAG nodes (`FACT_VERIFICATION_ENABLED=false`, `ONLINE_EVALUATORS_ENABLED=false`) eliminates the timeouts but **breaks the product** — Self-RAG / Corrective RAG / `auto/human/retry` auto-routing depend on those signals. Rejected.
- A new `gracekelly-mixed` routing_profile (`fast=mistral`, `strong=gracekelly`) was tried as a config-only fix. It is **ignored** by `regression_eval` because of the synthetic-profile override (see "Code paths" below).

The architecturally correct fix is to let `regression_eval` accept a profile name as target, so the existing mixed-routing config is used unchanged. That is this task.

## Code paths to extend

All in `scripts/regression_eval.py`:

- **`_resolve_provider_target(target, registry_path)`** at lines 101-121: today returns either a `dict` with `provider_id` / `model_name` / etc., or `None` on failure. Currently only resolves model names/aliases via `registry.resolve_model(target)`.
- **`_provider_target_runtime(target, project_root)`** at lines 658-721 (approximately, read it): today calls `_resolve_provider_target`, builds a synthetic profile `{"fast": ..., "strong": ...}` keyed at `payload["routing_profiles"][f"benchmark-{slug}"]`, writes a temp registry file, and points `EXPERIMENT_OVERRIDE_PATH` at it. **This is the override that needs to become conditional** on resolution kind.
- **`execute_case_with_provider_target(case, target, ...)`** at lines 861-880: caller of `_provider_target_runtime`, no change needed beyond what falls out of the helpers above.

The `config/provider_schema.py.ProviderRegistry.resolve_model(target)` raises `KeyError` on miss (verify with `grep -n "def resolve_model" config/provider_schema.py`). `registry.routing_profiles` is a dict keyed by profile name (verify with `python -c "from config.provider_schema import load_provider_registry; print(list(load_provider_registry('config/providers.yml').routing_profiles.keys()))"`).

# Deliverables

## 1. Resolution-kind discrimination in `_resolve_provider_target`

Update the function to first try existing model resolution; on failure, attempt profile resolution against `registry.routing_profiles`. Return a dict with a `kind` discriminator:

```python
# model target (existing)
{"kind": "model", "provider_id": "...", "provider_kind": "...", "model_name": "...", "input_price_per_1m_tokens": 0.0, "output_price_per_1m_tokens": 0.0}

# profile target (NEW)
{"kind": "profile", "profile_name": "gracekelly-mixed"}
```

Existing callers of the dict (search the file for `_resolve_provider_target` to find them all — there is at least one in `_build_mock_provider_result` at line 124 and `_provider_target_runtime`) must handle both shapes. For mock-mode benchmark, profile targets should resolve quality/latency/factuality bias from the **strong** tier provider of the profile (rationale: that is the tier that produces the user-visible answer).

## 2. Conditional profile injection in `_provider_target_runtime`

When `resolution["kind"] == "profile"`:
- **Do not** add a `benchmark-<slug>` synthetic profile to `payload["routing_profiles"]`.
- Set `LLM_PROVIDER_PROFILE` env var (or whatever mechanism `EXPERIMENT_OVERRIDE_PATH` honors) to `resolution["profile_name"]`.
- The temp registry file is still written (other settings overrides apply), but `routing_profiles` stays as-is.

When `resolution["kind"] == "model"`: existing behavior unchanged (synthetic profile creation + override).

## 3. New routing profile `gracekelly-mixed` in `config/providers.yml`

Add this profile (place after `external-mistral`):

```yaml
  gracekelly-mixed:
    description: Mixed routing for full Self-RAG benchmarking — Mistral API for fast tier (classify/transform/grade_docs/verify_facts/extract_claims/online_evaluators), GraceKelly browser for strong tier (final answer + suggest_questions). Reduces browser submits per case from 4-7 to ~3 while keeping Self-RAG / Corrective RAG / auto-route intact.
    fast:
      provider: mistral
      model: ministral-3b-latest
    strong:
      provider: gracekelly
      model: claude-sonnet-4-6
    fallback:
      provider: mistral
      model: ministral-3b-latest
```

This is also a valid **production** routing profile (single-user local deploy with both Mistral key and GraceKelly running) — not just a benchmark scaffold.

## 4. CLI surface

Two acceptable shapes (your choice — argue your pick in the report):

- **(A) polymorphic `--candidate <X>`**: existing flag accepts both model and profile names. CLI help text updated. Resolution order: try model first, then profile.
- **(B) explicit `--candidate-profile <X>` / `--baseline-profile <X>`** alongside existing flags. Mutually exclusive with model variants per side. CLI help text + argparse mutual exclusion group.

Option B is more explicit and avoids name collisions if a future profile happens to be named identically to a model alias. Option A is more ergonomic. Pick one, document choice.

## 5. Tests in `tests/test_regression_eval_profile_target.py`

New module. Minimum 4 test cases:

1. `test_resolve_provider_target_returns_profile_kind_for_known_profile` — given `gracekelly-mixed` against a fixture registry, returns `{"kind": "profile", "profile_name": "gracekelly-mixed"}`.
2. `test_resolve_provider_target_returns_model_kind_for_known_model` — given `ministral-3b-latest`, returns `{"kind": "model", ...}` with all model fields populated.
3. `test_provider_target_runtime_does_not_inject_synthetic_profile_for_profile_target` — under `_provider_target_runtime("gracekelly-mixed", ...)`, the temp registry file written has `routing_profiles` keys equal to the original registry's keys (no `benchmark-*` added).
4. `test_provider_target_runtime_injects_synthetic_profile_for_model_target` (regression coverage) — under `_provider_target_runtime("ministral-3b-latest", ...)`, the temp registry file has a `benchmark-ministral-3b-latest` key with `fast.model == strong.model == "ministral-3b-latest"`.

Use `tmp_path` for any registry file fixtures. Do NOT hit network. Existing test file `tests/test_regression_eval_*.py` likely has a registry fixture you can reuse — `grep -rln "load_provider_registry\|provider_registry_path" tests/` to find them.

## 6. Wrapper script update

`scripts/run_regression_via_gracekelly.ps1`: add `[string]$LLMProfile = ""` parameter (default empty for backward compat). When non-empty, pass `--candidate-profile $LLMProfile` (or whatever flag form chosen above) to `regression_eval.py` invocation around line 395. When empty, retain current `--candidate $Candidate` behavior.

# Acceptance Criteria

## Functional acceptance

After CX commit:

```bash
# baseline run (existing model semantics, must still work)
python scripts/regression_eval.py \
  --baseline ministral-3b-latest \
  --candidate mistral-small-latest \
  --max-cases 2 \
  --allow-paid-apis
# expect: exit 0, gate decision based on pass rate, NO new untracked files in repo

# new profile-target run (THE feature)
python scripts/regression_eval.py \
  --baseline ministral-3b-latest \
  --candidate-profile gracekelly-mixed \
  --max-cases 2 \
  --allow-paid-apis
# expect: exit 0, candidate runs through gracekelly-mixed profile (Mistral fast / GK browser strong),
#         report mode = "live-provider-benchmark", regressions count valid
```

(Note: the second invocation requires GraceKelly running on `127.0.0.1:8011` profile=hybrid AND `MISTRAL_API_KEY` in `.env`. Do NOT run this in your verification — it costs Perplexity quota. Mock-test only. Live verification is the human's job.)

## Test acceptance

`pytest tests/test_regression_eval_profile_target.py -q --tb=short` → 4+ passed, 0 failed.

`pytest tests/test_regression_eval*.py -q --tb=short` → existing tests still pass (no regression).

## Lint acceptance

`ruff check scripts/regression_eval.py tests/test_regression_eval_profile_target.py config/providers.yml` → clean.

## Commit gates (per `feedback_cx_spec_discipline`)

1. **Baseline measurement**: before any code edit, capture current `pytest tests/test_regression_eval*.py -q` output (passed/failed counts) into the report. After your change, re-run and confirm same passing count plus new tests.
2. **Shared file check**: `scripts/regression_eval.py` is touched here AND was touched by `task-177` (live-verified). Read `git log --oneline scripts/regression_eval.py | head -5` so you understand the latest committed contract before editing. Do NOT regress `_is_infrastructure_failure` tracking added in `f0fc81b`.
3. **Hardcoded counts grep**: if you add any list with case counts, dataset sizes, expected pass rates, or routing-profile names hardcoded in test fixtures, `grep -rn "<the literal>" .` to confirm no other place repeats it that would drift. Typical offenders: profile names like `"gracekelly-mixed"` appearing in both YAML and tests.
4. **Commit gates**: split commits — (a) registry/profile addition (config), (b) regression_eval extension + tests (code), (c) wrapper update (tooling). Each commit independently passes lint + relevant pytest scope. Do not bundle.

# Notes

- `EXPERIMENT_OVERRIDE_PATH` mechanism is in `config/settings.py` and `agent/prompt_registry.py` — read both to understand how the override registry is consumed at runtime.
- Profile-target case with Mistral fast tier rate limit (60 rpm free tier): pipeline makes ~5-10 calls/case, all go through Mistral fast; for 20 cases that is 100-200 calls, well within rpm with sequential pacing. No special throttling needed.
- The `gracekelly-mixed` profile **also doubles** as a sane production routing for the single-user local deploy (Julia's setup). Naming choice should reflect both uses (the description string makes both clear).
- DO NOT touch `evaluation/curated_cases.jsonl` (test data). DO NOT touch `agent/graph.py` (pipeline structure unchanged).

# Out of scope

- Fixing the dataset case-sensitivity bug at `scripts/regression_eval.py:231` (`needle not in result.answer` is case-sensitive — `"чек"` lowercase fails to match `"Чек"` capitalized in actual answers). That is a separate trivial PR, file as task-179 if desired.
- Bumping `GRACEKELLY_REQUEST_TIMEOUT_SEC` default. Profile target makes the bump unnecessary because GK browser only handles strong tier; if a single browser submit exceeds 30s on `generate`, that is a GK-side latency problem, not a regression-eval problem.
- Live 20-case run. Do not burn Perplexity quota during verification.
