# Operations & evaluation — RAG Support Assistant

> Moved out of the top-level README to keep it scannable; this is the full operations and evaluation reference.

## Experiments

Prompt, model, and retrieval changes can be tracked as YAML experiments in
`evaluation/experiments/`.

Create a new draft from the current runtime snapshot:

```bash
python scripts/experiment_new.py --name "concise-answers" --from current --description "Shorter support replies"
```

Stage an experiment without changing committed defaults:

```bash
python scripts/experiment_apply.py 2026-04-21-concise-answers --mode stage
EXPERIMENT_ID=2026-04-21-concise-answers python -c "from config.settings import get_settings; print(get_settings().retrieval_top_k)"
```

Recommended workflow:

1. Create a draft with `experiment_new.py`.
2. Stage it with `experiment_apply.py --mode stage`.
3. Run nightly or regression evaluation against the staged `EXPERIMENT_ID`.
4. Deploy with `experiment_apply.py --mode deploy` once metrics look acceptable.

In stage mode, `EXPERIMENT_ID` plus `config/experiment_override.yaml` applies to
the runtime pipeline on the next request without any git edits or deploy-mode
rewrite of `agent/prompts.py`.

Admin endpoints:

- `GET /api/admin/experiments`
- `GET /api/admin/experiments/{id}`
- `POST /api/admin/experiments/{id}/archive`
- `POST /api/admin/experiments/{id}/regression-run?baseline=current`
- `GET /api/admin/regression-runs`
- `GET /api/admin/regression-runs/{run_id}`


## Regression eval

Curated regression runs compare a baseline against `current` or an experiment
without invoking the heavy nightly RAGAS pipeline.

```bash
python scripts/regression_eval.py \
  --baseline current \
  --candidate 2026-04-21-concise-answers \
  --dataset evaluation/curated_cases.jsonl \
  --tenant all \
  --max-cases 100 \
  --seed 42
```

- The script writes `reports/regression/<timestamp>-<baseline>-vs-<candidate>.md`
  and a JSON sidecar next to it.
- Exit code `0` means the candidate satisfied the regression gate, `1` means
  gate failure, and `2` is reserved for infrastructure/runtime errors.
- Each completed run is persisted into `eval_results` with `kind='regression'`,
  `run_id`, baseline/candidate experiment ids, and the report path.
- `temperature=0` is forced for Ollama-backed regression runs to keep
  comparisons reproducible.
- GitHub Actions exposes an informational `regression-eval` job on pull
  requests that touch `agent/prompts.py`, `config/settings.py`, or
  `evaluation/experiments/*.yaml`.


## Provider benchmarking

The same regression runner also supports provider/model benchmarks by passing
registry aliases instead of experiment ids.

```bash
python scripts/regression_eval.py \
  --baseline ollama-small \
  --candidate mistral-small-latest \
  --dataset evaluation/curated_cases.jsonl \
  --tenant all \
  --max-cases 50 \
  --seed 42
```

- Alias resolution comes from `config/providers.yml`, so `ollama-small`,
  `gk-fast`, `gk-strong`, and `mistral-small-latest` can be used directly.
- Use `mistral-small-latest` for direct Mistral benchmarks; bare `mistral-small`
  belongs to the GraceKelly profile.
- Default mode is `mock-provider-benchmark`: answers are derived from the
  curated dataset and pricing/latency/refusal metrics are simulated so CI does
  not call live external providers accidentally.
- Live calls require explicit opt-in via `--allow-paid-apis` or
  `LLM_BENCHMARK_ALLOW_PAID_APIS=true`.
- Reports compare pass rate, latency, total cost, and refusal rate for the
  baseline and candidate provider targets.
- Direct-provider profiles are blocked when `DAILY_COST_LIMIT_USD` is already
  exhausted for the current UTC day.


## Online evaluators

Online evaluators are synchronous, low-cost checks that run on the final trace
state after the main graph finishes. They are enabled by
`ONLINE_EVALUATORS_ENABLED=true` and persist one row per evaluator into
`trace_evaluations`.

- `citation_coverage` measures the share of answer sentences carrying `[N]`
  citations.
- `answer_length_anomaly` flags answers whose word-count z-score falls outside
  the baseline.
- `retrieval_hit_rate` measures the share of retrieved documents whose rerank
  `relevance_score` is above `0.5`.
- `tool_use_efficiency` compares final-answer tokens against tool-call token
  spend.
- `refusal_detected` flags refusal-style phrases from
  `config/evaluator_patterns.yml`.
- `pii_leak_suspicion` flags phone/email/card-like patterns and stores only the
  matched pattern names, never raw values.
- `language_mismatch` compares detected query and answer languages.

Operational surfaces:

- `GET /api/admin/evaluations/trends?evaluator=<name>&days=30`
- `GET /api/admin/evaluations/worst?evaluator=<name>&limit=20`
- `python scripts/eval_daily_snapshot.py --date 2026-04-20`
- `deploy/helm/templates/cronjob-eval-snapshot.yaml` runs the daily snapshot at
  `02:00 UTC`


## Monitoring

The project exposes three observability surfaces.

### 1. `GET /api/metrics` - JSON snapshot from SQLite

```json
{
  "latency": {"p50_sec": 2.1, "p95_sec": 8.4, "p99_sec": 14.2, "window": "24h"},
  "escalation": {"total_traces": 120, "escalated": 18, "rate_pct": 15.0, "window": "24h"},
  "quality": {"scored_traces": 840, "avg_quality": 78.3, "low_quality_share_pct": 12.5, "window": "7d"},
  "errors": {"total_started": 120, "likely_failed": 2, "likely_failure_rate_pct": 1.7, "window": "24h"},
  "feedback": {"total": 95, "thumbs_down": 11, "thumbs_down_rate_pct": 11.6, "window": "7d"}
}
```

`/static/metrics.html` renders this snapshot with auto-refresh and status
coloring for operators and admins.

### 2. `GET /metrics` - Prometheus

`monitoring/prometheus.py` currently initializes Prometheus collectors
(`Counter`, `Gauge`, `Histogram`, or `Summary`):

- **HTTP and latency:** `rag_requests_total{route}`,
  `rag_request_duration_seconds`, `rag_http_requests_total{method,endpoint,status}`,
  `rag_http_request_duration_seconds{method,endpoint}`
- **Quality and feedback:** `rag_quality_score`, `rag_factuality_score`,
  `rag_escalation_total`, `rag_feedback_total{rating}`,
  `rag_model_routing_total{complexity}`, `rag_eval_drift{metric_name}`,
  `regression_runs_total{result}`, `regression_runs_duration_seconds`,
  `regression_last_pass_rate{baseline,candidate}`,
  `online_evaluator_score{evaluator}`,
  `online_evaluator_runs_total{evaluator,verdict}`,
  `online_evaluator_errors_total{evaluator}`
- **Resilience and protection:** `rag_circuit_breaker_state{name}`,
  `rag_circuit_breaker_transitions_total{name,to_state}`,
  `rag_ollama_retry_events_total{event}`,
  `rag_request_timeouts_total{endpoint}`, `rag_inflight_pipelines`,
  `rag_pipeline_rejections_total{reason}`,
  `rag_rate_limit_rejections_total{endpoint}`,
  `rag_body_size_rejections_total{reason}`
- **Platform health and data:** `rag_component_up{component}`,
  `rag_db_pool_size`, `rag_db_pool_checked_out`, `rag_db_pool_overflow`,
  `rag_active_sessions`, `rag_vector_store_documents`,
  `llm_cost_usd_total{provider,model,tenant}`,
  `rag_stale_important_docs_count`, `llm_cache_hits_total{tenant}`,
  `llm_cache_misses_total{tenant}`, `rag_traces_purged_total{table}`,
  `rag_audit_purged_total`, `rag_auth_failures_total{reason}`,
  `review_queue_pending_total{reason}`,
  `review_queue_confirmed_total{verdict}`,
  `review_queue_oldest_pending_seconds`

### 3. Alert rules and scheduled checks

- `monitoring/alert_rules.yml` defines Prometheus alert groups for
  resilience, health, quality, latency, nightly eval drift, and stale docs.
- `scripts/check_alerts.py` is a lightweight SQLite-based checker that can run
  every five minutes and push alerts through `ALERT_WEBHOOK_URL`.
- `scripts/nightly_eval.py` records evaluation drift, and
  `scripts/weekly_report.py` produces tenant-specific weekly reports.
- `scripts/build_review_queue.py` is intended for hourly automation and feeds
  the continuous-learning review backlog.
- `scripts/generate_improvement_backlog.py` aggregates the weekly actionable
  backlog and writes `reports/improvement_backlog/<YYYY-Www>.md`.

```bash
python scripts/check_alerts.py --dry-run
python scripts/build_review_queue.py --days 1 --tenant all
python scripts/nightly_eval.py
python scripts/weekly_report.py --tenant TEST --dry-run
python scripts/generate_improvement_backlog.py --tenant all --week 2026-W17 --out reports/improvement_backlog/2026-W17.md
```


## Review queue

The review queue keeps weak or high-risk traces from being lost between
tracing, feedback, and escalation flows.

```bash
python scripts/build_review_queue.py --days 7 --tenant all
```

- The builder inserts `pending` cases for `thumbs_down`, `low_quality`,
  `escalated`, `fact_fail`, and `slow_trace` signals.
- The admin UI exposes a **Review Queue** tab with filters, status counters,
  `Confirm good` / `Confirm bad` / `Dismiss` actions, and links to
  `/admin/traces/{trace_id}`.
- For single-user offline review, export a JSONL batch, annotate `review.*`
  fields in an editor, then import the verdicts back through the CLI.
- For Kubernetes, use `deploy/helm/templates/cronjob-review-queue.yaml` to run
  the builder hourly with `--days 1`.


## Improvement backlog

The improvement backlog turns one week of review, KB, freshness, latency, and
evaluation signals into a ranked list of changes worth making this week.

```bash
python scripts/generate_improvement_backlog.py --tenant all --week 2026-W17 --out reports/improvement_backlog/2026-W17.md
```

- Ranking uses `impact * frequency * recency`, where recency decays
  exponentially from the latest occurrence.
- The generator keeps at most `BACKLOG_MAX_ITEMS` items and renders markdown
  sections for critical, high, and medium priorities.
- `GET /api/admin/improvement-backlog/current` returns the latest backlog JSON
  for the current admin tenant.
- `GET /api/admin/improvement-backlog/archive?year=2026` lists stored markdown
  backlog weeks under `reports/improvement_backlog/`.
- For Kubernetes, use `deploy/helm/templates/cronjob-improvement-backlog.yaml`
  to generate the backlog every Monday at `06:00 UTC`.


## Curated dataset

Confirmed review cases can be promoted into a reusable JSONL dataset for
regression checks and provider benchmarks.

```bash
python scripts/build_curated_dataset.py --tenant all --since 2026-04-01 --out evaluation/curated_cases.jsonl --include-bad
```

- Each line in `evaluation/curated_cases.jsonl` is a standalone case with
  `input.query`, `input.context_hint`, `input.channel`, `expected.*`,
  `human_verdict`, `reviewer_notes`, `source_trace_id`, and `created_at`.
- `confirmed_good` rows always participate; add `--include-bad` to also export
  `confirmed_bad` rows.
- Re-running the builder is idempotent by `case_id`, so the file can be
  refreshed safely during iterative review.
- `GET /api/admin/curated-dataset/stats` returns dataset counts split by
  verdict, tenant, and channel.
- `POST /api/admin/curated-dataset/rebuild` queues an async rebuild and stores
  progress in Redis under a `curated-dataset-job:<job_id>` tracker key.


## Offline review workflow

Use the export/import pair when reviewing pending cases locally instead of
clicking through the admin UI one by one.

```bash
python scripts/review_export.py --status pending --tenant all --limit 5
python scripts/review_import.py .review_local/review_batch_<timestamp>.jsonl --dry-run
python scripts/review_import.py .review_local/review_batch_<timestamp>.jsonl --confirm
```

- `scripts/review_export.py` writes a comment header plus one JSON object per
  review case with `query`, `answer`, `retrieved_docs`, `tool_calls`,
  `citations`, and an empty `review` object for manual annotation.
- By default export files are written to `.review_local/`, and both
  `.review_local/` and `review_batch_*.jsonl` are ignored by git.
- Edit only the nested `review` object per line:
  `verdict = good | bad | dismiss`, optional `notes`, optional `fix_hint`,
  optional `tags`.
- `scripts/review_import.py` skips comments, ignores rows with `review.verdict =
  null`, and refuses to overwrite items that are no longer `pending`.
- Set `REVIEWER_EMAIL` before import. In the current schema it must match an
  existing `users.username` so the import can persist `reviewed_by`.
- For large batches, either pass `--confirm` up front or answer the interactive
  confirmation prompt when more than 10 verdicts would be applied.


## Threshold tuning

Threshold recommendations are generated from recent traces plus
`review_queue` verdicts. The analyzer writes a markdown report and exposes a
JSON view for admin tooling.

```bash
python scripts/analyze_thresholds.py --tenant all --days 30 --out reports/threshold_recommendations.md
```

- `scripts/analyze_thresholds.py` evaluates `QUALITY_THRESHOLD`,
  `FACT_VERIFICATION_MIN_SCORE`, `ESCALATION_THRESHOLD`, and
  `SLOW_TRACE_THRESHOLD_MS` against labeled bad/good traces and suggests the
  best cutoff by F1.
- `GET /api/admin/thresholds/analysis?days=30` returns the latest cached JSON
  analysis for the current tenant.
- `POST /api/admin/thresholds/refresh?days=30` forces a refresh and rewrites
  `reports/threshold_recommendations.md`.
- `deploy/helm/templates/cronjob-threshold-analysis.yaml` runs the analyzer
  weekly.
- If fewer than `THRESHOLD_ANALYSIS_MIN_LABELS` labeled traces are available,
  the report keeps the metric section but marks it as insufficient data.
