# Arc-7 proposal

## Current state recap
После закрытия Arc 6 проект уже умеет собирать curated dataset, гонять
regression eval, хранить experiment overrides, считать trace-level cost и
показывать online evaluators в admin/API слоях. Это сильная база для
систематических улучшений качества.

Но LLM-слой всё ещё исторически Ollama-first: provider configuration
размазана, routing-профили не формализованы, честного provider benchmark по
quality/latency/cost/refusal rate нет, а economics layer ограничен частичным
cost accounting без единого registry источника правды.

## Gap analysis
- Нет единого реестра providers/models/pricing/capabilities.
- `agent/graph.py` должен уметь работать через общую provider abstraction, а
  не только через локальный Ollama path.
- Нужен benchmark по curated dataset, который по умолчанию не жжёт paid APIs.
- Provider choice должен быть виден в traces, Prometheus и admin UI.
- API-key setup и paid guardrails должны быть fail-fast и безопасны по
  умолчанию.
- Arc 6 уже дал dataset + experiments + regression runner, поэтому следующий
  logical step — использовать эту базу для сравнения backends, а не строить
  новую learning loop сверху.

## Arc-7 candidate G - Provider abstraction
- Goal: сделать local и direct LLM providers взаимозаменяемыми backend-ами с
  единым runtime API, cost accounting и benchmark flow.
- Motivation: проект уже может измерять качество и хранить traces, но не умеет
  честно отвечать на вопрос “какой provider/profile лучше для этого workload”.
- Ideas (7):
  1. `config/providers.yml` + `config/provider_schema.py` как source of truth
     для providers, aliases, pricing, rate limits и routing profiles.
  2. Пакет `llm/providers/*` с `LLMProvider`/`LLMResponse` abstraction и
     runtime builder для profile-based routing.
  3. Provider-aware trace attribution: `provider_name`, `model_name`,
     prompt/completion tokens и `cost_usd`.
  4. Prometheus metric `llm_cost_usd_total{provider,model,tenant}`.
  5. Расширение `scripts/regression_eval.py` до provider/model targets.
  6. Mock-by-default benchmark mode с явным `--allow-paid-apis` для live runs.
  7. Admin Providers tab/API с профилями, лимитами, cost/usage и last-success.
- Estimated scope: 7 task-спеков (143-149), ~24-32 часа.
- Expected impact: проект станет не просто local-first RAG, а измеримой
  provider lab-песочницей, где выбор backend-а опирается на данные, а не на
  ощущения.
- Risks / complications: provider APIs быстро меняются, pricing tables
  устаревают, а live benchmark легко сделать дорогим без жёстких guardrails.

## Arc-7 candidate H - Continuous Learning Phase 2
- Goal: перевести Arc 6 learning loop из offline-assisted режима в управляемый
  production optimization cycle.
- Motivation: после batch F уже есть review queue, dataset, experiments и
  regression gate; следующий шаг — rollout discipline и adaptive thresholds.
- Ideas (6):
  1. Experiment dashboard с сравнением staged vs deployed.
  2. Tenant-level experiment assignment и sticky exposure.
  3. Automatic rollback, если regression gate или online evaluators деградируют.
  4. Review queue prioritization на основе evaluator drift.
  5. Dataset freshness policy и curator hygiene automation.
  6. Recommendation engine для prompt/routing threshold changes.
- Estimated scope: 6-8 task-спеков, ~22-30 часов.
- Expected impact: повысит скорость product iteration после появления
  регулярного трафика.
- Risks / complications: при текущем single-user / low-traffic режиме сигналов
  мало, поэтому часть automation окажется premature.

## Arc-7 candidate I - Backup/restore and chaos
- Goal: закрыть recoverability и operational drills поверх уже существующего
  runbook.
- Motivation: backup/restore важны, но сейчас project value больше растёт от
  quality/economics improvements, чем от расширения ops surface.
- Ideas (6):
  1. Snapshot backup для Postgres, SQLite traces, Chroma и uploads.
  2. Disposable restore verification.
  3. Chaos drills для Ollama/Postgres/Redis/network faults.
  4. Post-deploy smoke suite.
  5. Backup retention integrity report.
  6. Disaster recovery checklist с RTO/RPO.
- Estimated scope: 6-7 task-спеков, ~20-28 часов.
- Expected impact: выше эксплуатационная уверенность для будущего production.
- Risks / complications: высокая полезность, но меньшая product novelty прямо
  сейчас; часть сценариев избыточна для текущего single-user режима.

## Recommendation
Выбрать candidate G - Provider abstraction.

Причина выбора по критерию `impact x novelty x complexity x user fit`:

| Candidate | Impact | Novelty | Complexity | User fit |
|---|---|---|---|---|
| G | высокий | высокий | средний | высокий |
| H | средне-высокий | средний | средне-высокий | средний |
| I | средний | средний | средний | средний |

Batch G лучше всего капитализирует уже сделанные investment'ы Arc 6:
curated dataset, regression runner и experiment registry сразу становятся
основанием для честного provider benchmark и routing economics. Batch H
логичен следующим, но выигрывает от большего объёма traffic signal. Batch I
полезен, но не даёт такого product/experiment lift прямо сейчас.

## Batch H closed, next candidates

После закрытия Batch G фактический Batch H пошёл не как original candidate H,
а как pragmatic follow-up к provider abstraction: локальный GraceKelly backend,
direct Mistral fallback и удаление неиспользуемых direct Claude/OpenAI/Gemini
модулей. Это уже закрыто в коде и документации.

Следующие кандидаты для Arc 7/8:

- **Batch I — Continuous learning Phase 2.** Sticky rollout discipline,
  staged-vs-deployed comparison, automatic rollback по regression gate и
  online-evaluator drift. По-прежнему упирается в реальный traffic signal.
- **Batch J — Backup/restore + chaos drills.** Disposable restore
  verification, snapshot integrity и post-deploy smoke/checklists для ops.
- **Batch K — GraceKelly advanced orchestration.** Tool-use,
  structured-output и, при необходимости, streaming через отдельный endpoint
  вместо текущего `/api/v1/smart`.

## Batch K closed

Batch K closed on 2026-04-22.

- GraceKelly provider now supports smart/orchestrate dispatch, tool-use, structured output and streaming hooks through the shared provider runtime.
- `agent/graph.py` uses provider-native tool calls and schema outputs for classification, document grading and consensus-enabled fact verification.
- API/UI surface now exposes `/api/chat/stream` plus health-driven UI switching via `STREAMING_ENABLED`.
- Ingestion has opt-in batch contextual-header preprocessing via `INGESTION_BATCH_ENABLED` with sequential fallback.

## Batch J closed on 2026-04-23

- task-159 snapshot backup (`scripts/backup_snapshot.py`, SHA256 manifest,
  key fingerprint only, `BACKUP_DIR`, `BACKUP_RETENTION_DAYS`).
- task-160 disposable restore verification
  (`scripts/restore_verify.py`, sqlite integrity + tarball extraction in
  a temp root, structured exit codes).
- task-161 chaos drills (`scripts/chaos_drill.py`, six faults:
  `ollama_timeout`, `ollama_down`, `postgres_unavailable`,
  `redis_unavailable`, `network_slow`, `network_flaky`).
- task-162 post-deploy smoke suite (`scripts/post_deploy_smoke.py`,
  checks: liveness, readiness, metrics, ask, admin_providers).
- task-163 backup integrity / retention audit
  (`scripts/backup_integrity.py`, SHA verification + expired-candidate
  report, no destructive actions).
- task-164 disaster recovery checklist (`docs/disaster-recovery.md`,
  scenarios A-E with RTO/RPO plus script mapping).

Batch J targeted sweep: 37 passed. Combined Arc 7 (K + I + J) sweep: 167
passed, ruff clean.

## Batch I fully closed on 2026-04-23

Batch I originally landed partially on 2026-04-22 (admin + migration slices
of tasks 153/154/156). The remaining tasks landed on 2026-04-23:

- task-155 auto-rollback watcher (`evaluation/rollback_watcher.py`,
  `AUTO_ROLLBACK_ENABLED`, `ROLLBACK_DRIFT_THRESHOLD_PCT`,
  `ROLLBACK_TRACE_WINDOW`, `TENANT_ADMIN_EMAIL`, Prometheus
  `experiment_auto_rollback_total{experiment_id,reason}`).
- task-157 recommendation engine (`scripts/generate_recommendations.py`,
  `RECOMMENDATIONS_ENABLED=true`, admin
  `GET /admin/recommendations/current`, markdown report writer).
- task-158 comparison dashboard (`GET /admin/experiments/comparison?...`,
  admin UI tab in `static/admin.html`).

Still deferred (not blocking Batch I closure):
- task-154 sticky hash rollout inside `resolve_active_experiment` (admin
  CRUD is live; the resolver currently returns `None`).
- task-156 staleness detection cronjob that populates
  `curated_case_status` rows (the read-side `/admin/curated-dataset/stale`
  endpoint is live).

## Batch I partial — task-153/154/156 admin + migration layer closed on 2026-04-22

Batch I started in parallel with Batch K and was left partial by Codex.
The admin + migration slices that keep Batch K green on master landed:

- Migration 015 `experiment_deployments` + admin `POST /admin/experiments/{id}/deploy`
  and `POST /admin/experiments/{id}/rollback` (task-153).
- Migration 016 `experiment_assignments` + admin `POST`/`GET /admin/experiments/{id}/assignments`
  and `resolve_active_experiment` hook in `run_qa_pipeline` (task-154 foundation).
- Migration 017 `curated_case_status` + admin `GET /admin/curated-dataset/stale`
  (task-156 read-side).

Still open for a follow-up Batch I closure:

- task-155 automatic rollback watcher + `AUTO_ROLLBACK_ENABLED` flag.
- task-157 weekly recommendation engine (`scripts/generate_recommendations.py`).
- task-158 experiment comparison dashboard (admin UI tab + endpoint).
- task-154 sticky hash rollout in `resolve_active_experiment` (admin CRUD only for now).
- task-156 stale detection job that populates `curated_case_status` rows.