# Verification report — Arc 7 / Batch I close-out (tasks 155/157/158)

## Summary
- **Batch I fully closed.** Tasks 153/154/156 landed as the partial on
  2026-04-22 (admin + migrations); tasks 155/157/158 land here on
  2026-04-23.
- **Targeted sweeps**:
  - `tests/test_rollback_watcher.py` — 8 passed.
  - `tests/test_recommendation_engine.py` — 7 passed.
  - `tests/test_experiment_comparison.py` — 4 passed.
- **Combined Batch I + K + sanity sweep** (20 files): 130 passed / 0 failed.
- **Ruff**: clean.

## Scope verification (per task)

### task-155 — Automatic rollback on drift — PASS
- `evaluation/rollback_watcher.py` — pure `compute_drift(baseline, candidate, threshold_pct)` returning `DriftDecision` with worst evaluator / drop percent; async `check_and_rollback(session, notifier)` iterates `experiment_deployments` where `rolled_back_at IS NULL`, fetches mean evaluator scores for baseline and per-experiment candidate via `trace_evaluations`, triggers `trigger_rollback` when `drop_pct >= threshold`, calls the notifier, and returns the event list.
- `trigger_rollback` updates `experiment_deployments.rolled_back_at`, increments the Prometheus counter and leaves YAML status/runtime file untouched so downstream consumers remain consistent.
- `default_notifier` uses `scripts.weekly_report.send_email` and `TENANT_ADMIN_EMAIL`; notification errors are logged, not raised.
- Settings landed: `AUTO_ROLLBACK_ENABLED=false`, `ROLLBACK_DRIFT_THRESHOLD_PCT=10.0`, `ROLLBACK_TRACE_WINDOW=1000`, `TENANT_ADMIN_EMAIL=""`.
- Prometheus counter `rag_experiment_auto_rollback_total{experiment_id,reason}` added to `monitoring/prometheus.py`.
- Tests cover: drift-above-threshold triggers rollback + notifier, normal variance noop, insufficient data safe, feature-flag off is a noop, already-rolled-back deployments are skipped, `trigger_rollback` increments the Prometheus counter, no active deployments is a noop.

### task-157 — Recommendation engine — PASS
- `scripts/generate_recommendations.py` — pure `aggregate_recommendations(backlog_items, threshold_items, green_regressions, stale_cases)` returning a deterministically sorted `list[Recommendation]` (`priority` desc, then `source`, then `title`). Per-source builders coerce numeric values safely and drop degenerate entries.
- `render_markdown(recs, week=...)` emits a summary header, per-recommendation blocks with action + evidence, and a graceful "no actionable signals" when empty.
- CLI entrypoint accepts `--tenant`, `--week`, `--out`, `--signals-json` and writes `reports/recommendations/<week>.md`.
- Admin endpoint `GET /admin/recommendations/current` calls `fetch_signals(session)` (curated stale + green regressions only for now), feeds the aggregator, returns `{recommendations, status}`. Disabled when `RECOMMENDATIONS_ENABLED=false`.
- Tests: aggregation merges 4 signal types, ranking is deterministic, empty input returns `[]`, markdown contains ranked items, markdown handles empty, endpoint returns payload with both regression and stale titles, disabled flag produces `status=disabled` + empty list.

### task-158 — Experiment comparison dashboard — PASS
- Admin endpoint `GET /admin/experiments/comparison?deployed=...&staged=...&candidate=...` returns three stable buckets with `experiment_id`, `trace_count`, `quality{mean,p50,p95}`, `evaluator_breakdown`, `cost_per_trace`, `latency{p50,p95}`.
- Deployed bucket aggregates across live `traces` (mean quality, cost, latency); staged bucket reads the latest `eval_results` row for the candidate experiment and surfaces `run_id` + deltas in `evaluator_breakdown`; candidate bucket reflects YAML existence in the experiments directory.
- The endpoint is registered **before** `/admin/experiments/{id}` so that FastAPI routing does not hijack `comparison` into `{id}`.
- `static/admin.html` gains a new tab `tab-experiment-comparison` with `deployed`/`staged`/`candidate` inputs and an output pane; no JavaScript surgery is required on the empty state.
- Tests: three-bucket shape from live + regression + YAML data, empty query returns all-`None` buckets, missing live data still serializes, admin HTML contains the comparison surface.

## Pending for a follow-up
- **task-154 sticky rollout** — `resolve_active_experiment()` remains a placeholder returning `None`. Hash-based sticky exposure gated by `EXPERIMENT_ASSIGNMENT_ENABLED` is still open.
- **task-156 staleness detection job** — the read-side endpoint is live, but the background job that populates `curated_case_status` rows by re-running curated cases is not implemented.
- **Batch J** — backup/restore/chaos meta-spec remains in `codex-tasks/` root.

## Acceptance (per meta-spec)
- Targeted rollback/recommendation/comparison sweeps — PASS (19 total).
- Combined Batch I + K + sanity sweep — PASS (130).
- Ruff — PASS.
- Feature-flag defaults — `AUTO_ROLLBACK_ENABLED=false`, `RECOMMENDATIONS_ENABLED=true`, `EXPERIMENT_ASSIGNMENT_ENABLED=false` → existing single-user behaviour is unchanged.
- Working tree clean post-commit — PASS.
