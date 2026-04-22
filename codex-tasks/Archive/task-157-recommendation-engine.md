# Task 157 — Recommendation engine for prompt/routing/threshold changes

## Goal
Собирать rule-based weekly recommendations на основе backlog, evaluator drift, threshold analysis и regression wins.

## Context
- Уже есть `scripts/generate_improvement_backlog.py`, threshold analyzer и regression reports.
- Batch I не должен автоматически применять рекомендации; только генерировать ranked report.

## Deliverables
1. Новый script `scripts/generate_recommendations.py`:
   - CLI: `python scripts/generate_recommendations.py --tenant <id|all> --week <YYYY-Www> --out reports/recommendations/<week>.md`
   - объединяет:
     - improvement backlog signals
     - threshold recommendations
     - latest green regression candidates
     - curated stale-case pressure
   - возвращает ranked actionable items
2. `config/settings.py`:
   - `recommendations_enabled: bool = True`
3. Admin endpoint `GET /admin/recommendations/current`
4. Markdown output:
   - summary
   - ranked recommendations
   - why-now evidence per item
5. Tests — 5+:
   - aggregation merges multiple signal types
   - ranking deterministic
   - markdown parses
   - endpoint returns JSON payload
   - empty signal set returns zero recommendations

## Acceptance
- Report создаётся минимум для 1 week window.
- Payload содержит конкретные actions, а не только abstract warnings.
- `RECOMMENDATIONS_ENABLED=true` по умолчанию safe, потому что генерация read-only.

## Notes
- ML ranking вне scope; только rule-based scoring.
- Если staged experiment already beats current baseline, recommendation должен ссылаться на конкретный `experiment_id`.
