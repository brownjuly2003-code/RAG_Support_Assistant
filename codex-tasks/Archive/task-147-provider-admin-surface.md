# Task 147 - Provider admin API and UI surface

## Goal
Добавить admin-visible provider observability: active profile, registry
metadata, recent usage и cost surface.

## Context
- Batch G без operator surface останется внутренней abstraction rewrite.
- `static/admin.html` уже содержит trace/review/eval панели и является
  естественной точкой для Providers tab.

## Deliverables
1. `api/app.py`
   - `GET /api/admin/providers`
   - RBAC admin
   - response: default/active profile, profiles map, providers list,
     configured flag, capabilities, rate limits, 1-minute usage, 24h cost,
     last successful call timestamp.
2. `static/admin.html`
   - новый tab `Providers`
   - table + refresh flow
3. Metrics/traces integration
   - usage/cost собираются из `trace_steps` и registry metadata
4. Tests
   - `tests/test_provider_admin_surface.py`

## Acceptance
- `pytest tests/test_provider_admin_surface.py -q` зелёный.
- Admin UI открывает Providers tab без JS/runtime errors.
- Default/active profile видны и по умолчанию указывают на Ollama profile.
- Usage percentages корректно считаются против registry rate limits.

## Notes
- Не добавлять отдельный persistence layer только ради UI; использовать уже
  существующие traces и registry.
- Если paid provider не сконфигурирован, UI должен показывать это явно через
  `configured=false`, а не падать.
