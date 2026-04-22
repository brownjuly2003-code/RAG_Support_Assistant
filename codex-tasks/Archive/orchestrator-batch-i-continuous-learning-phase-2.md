# Arc 7 / Batch I — Continuous Learning Phase 2

## Status
Planned on 2026-04-22.

## Scope
- Formalize experiment deployment lifecycle with persisted staged/deployed/rolled-back history.
- Add tenant-level experiment assignment with sticky exposure and default-off rollout flags.
- Add automatic rollback checks on evaluator drift / regression signals, default off.
- Add curated dataset freshness automation and stale-case review surface.
- Add weekly recommendation engine for prompt/routing/threshold changes.
- Add experiment comparison dashboard for deployed vs staged vs candidate views.

## Tasks
| # | Task | Blocked by | Parallel with | Est. hours |
|---|------|------------|----------------|-----------|
| 153 | Experiment deployment lifecycle | — | 154, 156 | 4-5 |
| 154 | Tenant experiment assignment | — | 153, 156 | 4-5 |
| 155 | Automatic rollback on drift | 153 | 154, 156 | 4-5 |
| 156 | Dataset freshness automation | — | 153, 154 | 4-5 |
| 157 | Recommendation engine | 155 + 156 | 153, 154 | 3-4 |
| 158 | Comparison dashboard | 153 | 154, 156, 157 | 3-4 |

## Dependency graph
- `153 -> 155`
- `153 -> 158`
- `154` — independent
- `156` — independent
- `155 + 156 -> 157`

## Recommended order
1. `153` — lifecycle table/state machine unlocks deploy/rollback semantics and comparison data.
2. `154` + `156` — run in parallel: assignment plumbing and dataset hygiene are independent.
3. `155` — piggybacks on deployed lifecycle and experiment attribution in traces.
4. `157` — aggregates signals once rollback + freshness data exist.
5. `158` — UI last, once lifecycle/comparison payloads are stable.

## Flags
- `EXPERIMENT_ASSIGNMENT_ENABLED=false`
- `AUTO_ROLLBACK_ENABLED=false`
- `RECOMMENDATIONS_ENABLED=true`

## Verification
- Lifecycle / assignment sweep:
  `pytest tests/test_experiment_registry.py tests/test_prompt_registry_integration.py -q`
- Dataset / recommendation sweep:
  `pytest tests/test_curated_dataset.py tests/test_improvement_backlog.py tests/test_threshold_analyzer.py -q`
- Evaluator / rollback / admin sweep:
  `pytest tests/test_online_evaluators.py tests/test_regression_runner.py -q`
- Final sweep:
  `pytest tests/ -q`
  `ruff check .`

## Notes
- Auto-assignment and auto-rollback stay off by default because the project still has low-volume single-user traffic.
- Existing provider abstraction must stay untouched except for lightweight hooks.
- If curated freshness metadata needs persistence, prefer a side-table over rewriting the JSONL dataset format.
