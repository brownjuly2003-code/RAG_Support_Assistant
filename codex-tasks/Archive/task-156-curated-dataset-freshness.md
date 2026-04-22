# Task 156 — Dataset freshness + curator hygiene

## Goal
Автоматически находить устаревшие curated cases и выводить их в отдельный admin review surface, не ломая JSONL dataset format.

## Context
- Curated dataset живёт в `evaluation/curated_cases.jsonl`.
- Проект уже умеет rebuild dataset и показывать summary в admin API.

## Deliverables
1. Migration `017` с side-table `curated_case_status`:
   - `case_id`
   - `tenant_id`
   - `status`
   - `staleness_reason`
   - `last_checked_at`
   - `source_created_at`
2. `config/settings.py`:
   - `curated_case_stale_days: int = 180`
3. Freshness job:
   - для case старше N дней rerun через current primary profile
   - сравнивает route / quality / expectation match
   - при drift ставит `status=stale_needs_review`
4. Admin endpoint `GET /admin/curated-dataset/stale`
   - список stale cases
   - фильтрация по tenant/status
5. Tests — 6+:
   - migration upgrade/downgrade
   - stale detection for old case
   - fresh case skipped
   - rerun mismatch updates status
   - endpoint lists stale cases
   - no stale rows returns empty payload

## Acceptance
- JSONL dataset остаётся backward-compatible.
- Старый case с route/quality drift попадает в `stale_needs_review`.
- Endpoint возвращает reason и timestamps для ручного curator review.

## Notes
- Предпочтителен side-table, а не перенос curated dataset в DB.
- Staleness должен быть read-only marker; автоматический rewrite case вне scope.
