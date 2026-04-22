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
- Goal: сделать Claude/Gemini/OpenAI/Ollama взаимозаменяемыми backend-ами с
  единым runtime API, cost accounting и benchmark flow.
- Motivation: проект уже может измерять качество и хранить traces, но не умеет
  честно отвечать на вопрос “какой provider/profile лучше для этого workload”.
- Ideas (7):
  1. `config/providers.yml` + `config/provider_schema.py` как source of truth
     для providers, aliases, pricing, rate limits и routing profiles.
  2. Пакет `llm/providers/*` с `LLMProvider`/`LLMResponse` abstraction и
     runtime builder для `latency-first`, `cost-first`, `quality-first`.
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
