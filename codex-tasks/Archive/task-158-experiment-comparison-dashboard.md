# Task 158 — Experiment comparison dashboard

## Goal
Показать admin-side comparison для deployed vs staged vs candidate experiments без тяжёлого UI фреймворка.

## Context
- Admin UI already lives in `static/admin.html` + `static/admin.js`.
- Regression reports already serialize per-case aggregates; traces keep latency/cost data.

## Deliverables
1. Endpoint `GET /admin/experiments/comparison?deployed=<id>&staged=<id>`
   - `deployed` metrics from live traces
   - `staged` metrics from latest regression run
   - `candidate` metrics from latest pending experiment if available
   - fields:
     - quality distribution
     - evaluator breakdown
     - cost per trace
     - latency `p50/p95`
2. Admin UI tab in `static/admin.html`
   - load comparison JSON
   - render compact charts/bars/sparklines
   - no JS errors when data is empty
3. Tests — 4+:
   - comparison computation shape
   - endpoint returns correct payload
   - empty/live-missing data still serializes
   - admin page contains experiment comparison surface

## Acceptance
- Endpoint returns stable JSON shapes for all three buckets.
- UI renders on existing admin page and survives empty datasets.
- Comparison uses staged regression metrics, not only live traffic.

## Notes
- Plotly optional; lightweight HTML/CSS/ASCII bars are enough.
- Comparison depends on task-153 persisted lifecycle to know staged/deployed candidates.
