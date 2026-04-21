# Task 139 — Threshold recommendations (quality / factuality / escalation)

## Goal
Автоматический анализ исторических трейсов + review_queue verdicts → рекомендации по настройке `quality_threshold`, `fact_verification_min_score`, `escalation_threshold`, `slow_trace_threshold_ms`. Сейчас эти пороги выставлены на глаз (настройка руками по ощущениям).

## Context
- Repo: `D:\RAG_Support_Assistant`.
- Arc 6 / Batch F — Continuous Learning Lab.
- Текущие пороги (из `config/settings.py`):
  - `quality_threshold = 80` — ниже которого trace попадает в review
  - `fact_verification_min_score = 70` — (task-92) порог fact-check
  - `escalation_threshold = 0.7` — (task-106) порог confidence для escalation
  - `slow_trace_threshold_ms = 10000` (будет после task-133)
- Исторические данные:
  - `traces.final_quality`, `.fact_score`, `.duration_ms` — distribution известна.
  - `review_queue.status` (после task-133) — human verdict.
  - `escalated_tickets` (migration 004).

## Deliverables
1. **`scripts/analyze_thresholds.py`**:
   - CLI: `python scripts/analyze_thresholds.py --tenant <id|all> --days 30 --out reports/threshold_recommendations.md`.
   - Для каждого порога:
     - Собирает distribution исторических scores.
     - Собирает labels: `human_verdict` (confirmed_good/bad) из review_queue.
     - Находит optimal threshold по метрике F1 (precision × recall) для задачи "detect bad traces".
     - Выдаёт recommendation: current value, suggested value, precision / recall / F1 для каждого.
2. **Output** `reports/threshold_recommendations.md`:
   ```markdown
   # Threshold recommendations — 2026-04-22

   Based on 2847 traces (last 30 days), 142 human-reviewed.

   ## quality_threshold
   - Current: 80
   - Suggested: 75 (F1 0.81 vs current F1 0.68)
   - Trade-off at 75: precision 0.72 (72% flagged traces are actually bad), recall 0.89 (89% bad traces caught)
   - Distribution chart: [histogram, ASCII or embedded PNG]
   - Raise above current? — No; lowering improves recall without hurting precision.
   
   ## fact_verification_min_score
   - Current: 70
   - Suggested: 70 (current is optimal, F1 0.76)
   - Trade-off unchanged.
   
   ## escalation_threshold
   - Current: 0.7
   - Suggested: 0.65 (F1 0.79 vs current F1 0.71)
   - Rationale: reduce false positives (too many escalated) — 0.65 keeps 87% recall, cuts FP by 30%.
   
   ## slow_trace_threshold_ms
   - Current: 10000
   - Distribution: p50=3200, p90=8400, p95=12000, p99=22000
   - Suggested: 12000 (p95) — capture slow but not p90 normality.
   
   ## Caveats
   - Tenant <X> has 78% of bad reviews — maybe settings should differ per tenant.
   - Sample size for escalation is small (42 cases) — low confidence on suggestion.
   ```
3. **Admin endpoint**:
   - `GET /admin/thresholds/analysis?days=30` — latest analysis result (cached, refresh endpoint).
   - `POST /admin/thresholds/refresh` — trigger re-analysis.
4. **Cronjob**: `deploy/helm/templates/cronjob-threshold-analysis.yaml` — 1× неделя.
5. **Config** (`config/settings.py`):
   - `THRESHOLD_ANALYSIS_MIN_LABELS: int = 20` — если human-labeled данных < N, не делать рекомендацию (недостаточная статистика).
6. **Applying recommendations**:
   - НЕ автоматически. Только генерация отчёта.
   - В report включить готовую yaml-patch для copy-paste в `.env`:
     ```yaml
     # copy to .env if accepting recommendation:
     QUALITY_THRESHOLD=75
     ESCALATION_THRESHOLD=0.65
     SLOW_TRACE_THRESHOLD_MS=12000
     ```
7. **Tests** (`tests/test_threshold_analyzer.py`) — 5+ тестов:
   - На synthetic dataset (100 traces, known bad labels, known scores) — analyzer находит correct threshold.
   - При <20 labels → recommendation skipped ("insufficient data").
   - F1 calculation correct.
   - Output markdown валиден.
   - Endpoint возвращает JSON version.

## Acceptance
- Analyzer не падает на пустом dataset (graceful: "insufficient data").
- На seed'е (100 traces + 30 human labels) — отчёт содержит 4 рекомендации с F1-score.
- Endpoint работает.
- pytest ≥ 319 + 5 new = 324+. Ruff clean.
- README раздел "Threshold tuning".

## Notes
- **Parallel-safe with**: task-133, task-134, task-135, task-137, task-138, task-140.
- **Blocks**: — (independent tail).
- Работает даже если review_queue (task-133) пустой — тогда скрипт опирается только на proxy labels (escalated=bad, non-escalated=good) с caveat в отчёте.
- Использовать `sklearn.metrics` (precision_recall_curve, f1_score) — `scikit-learn` уже в deps (через ragas)? Если нет — добавить.
- Не писать ML-framework — простая binary classification threshold search.
- ASCII-гистограмма: `█░` для markdown-friendly.
