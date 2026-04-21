# Arc-6 proposal

## Current state recap
Проект уже закрыл базовый production-hardening и product/enterprise слой: resilience, observability, health/readiness split, admin UI, multi-tenancy, fact verification, security hardening, inline citations, mobile/WCAG, agentic tools, nightly RAGAS eval, KB gap detection, contextual ingestion, OpenTelemetry, OIDC SSO, encryption at rest, KB drafts/freshness, analytics, weekly reports, email channel, dedup и integration tests. Итого закрыто 55 задач; по текущему контексту тесты зелёные (`293 passed`), `ruff` чистый, multi-tenant deploy-safe.

Это уже не просто MVP, а локальная RAG-платформа для поддержки и инженерных экспериментов. Но её сила сейчас больше в исполнении и наблюдаемости, чем в систематическом улучшении, recoverability и осмысленном сравнении model/backend стратегий. Следующую арку стоит выбирать не под hyperscale, а под single-user sandbox + будущий production slot.

## Gap analysis
- Нет замкнутого цикла `feedback/trace -> review -> curated dataset -> experiment -> regression gate`.
- Feedback, analytics и KB gap detection уже есть, но не превращаются в приоритизированный backlog улучшений.
- В analytics есть cost-срез, но в локальном trace summary стоимость сейчас фактически заглушка; полноценного token/compute accounting по шагам нет.
- Model routing работает внутри Ollama-сценария, но нет provider abstraction и честного benchmark-а для Claude/Gemini/OpenAI как альтернатив.
- Есть runbook по алертам, но нет полноценного backup/restore/DR контура для Postgres, ChromaDB, uploads и ключей шифрования.
- CI покрывает lint/tests/eval gate, но нет load/perf/chaos suite и smoke-проверок после рестарта или релиза.
- Есть Helm и cronjobs, но нет release discipline уровня canary, rollback validation и post-deploy smoke.
- Multilingual foundation заложен, но нет multilingual eval-set, locale-aware policy и breakdown качества по языкам.
- Каналы уже покрывают web/email/Telegram/widget, поэтому следующий шаг должен усиливать качество системы, а не просто добавлять ещё один входной канал.

## Arc-6 candidate A - Continuous Learning Lab
- Goal: замкнуть learning loop вокруг traces, feedback, eval и knowledge operations.
- Motivation: проект уже собирает много полезных сигналов, но почти не превращает их в управляемый цикл улучшений.
- Ideas (8):
  1. Review queue для `thumbs_down`, low-quality и escalated traces -> `data/review_queue/*.jsonl` или отдельный admin view.
  2. Curated dataset builder из подтверждённых кейсов -> `evaluation/curated_cases.jsonl`.
  3. Prompt/version registry с метаданными экспериментов -> `evaluation/experiments/*.yaml`.
  4. Дешёвые online evaluators без heavy judge-LLM -> новые метрики и daily snapshot.
  5. Weekly improvement backlog, который сливает feedback, KB gaps, freshness и slow traces -> `reports/improvement_backlog.md`.
  6. Regression runner перед изменениями prompt/model/retrieval flags -> `scripts/regression_eval.py`.
  7. Рекомендации по тюнингу порогов `quality`, `factuality` и `route_or_retry` -> `reports/threshold_recommendations.md`.
  8. Export/import human review для single-user workflow -> `scripts/review_export.py`.
- Estimated scope: 8 task-специфик, ~28-36 часов.
- Expected impact: проект станет самоулучшаемой инженерной песочницей, а изменения в prompts/models можно будет проверять до деградации в прод-сценарии.
- Risks / complications: feedback шумный, легко переоптимизироваться на маленький curated set, нужна дисциплина sampling и review.

## Arc-6 candidate B - Ops & Recoverability Pack
- Goal: усилить recoverability и эксплуатационную уверенность локального production-slot без ухода в тяжёлую distributed-инфраструктуру.
- Motivation: observability уже сильная, но контур "потеряли узел/диск/БД -> быстро восстановились" пока закрыт слабо.
- Ideas (8):
  1. Snapshot backup для Postgres, ChromaDB, uploads и key manifest -> `scripts/backup_snapshot.ps1`.
  2. Restore verification в disposable окружение -> `scripts/restore_verify.ps1`.
  3. Disaster recovery runbook с RTO/RPO и failure matrix -> `docs/disaster-recovery.md`.
  4. Load profile suite для `/api/ask`, `/api/upload` и analytics endpoints -> `tests/perf/`.
  5. Chaos drills для отказов Ollama, Postgres, Redis и сетевых таймаутов -> `docs/chaos-drills.md`.
  6. Post-deploy smoke suite после рестарта или обновления -> `scripts/post_deploy_smoke.py`.
  7. Проверка целостности backup-ов и retention policy -> scheduled report или CI artifact.
  8. Resource budget dashboard для CPU/RAM/disk на Windows host -> новая metrics panel.
- Estimated scope: 8 task-специфик, ~26-34 часа.
- Expected impact: меньше риск потери данных и выше уверенность, что проект действительно переживает реальные локальные инциденты.
- Risks / complications: ценность высокая, но новизна ниже; часть сценариев может оказаться overkill для single-user режима.

## Arc-6 candidate C - Backend & Economics Lab
- Goal: сделать выбор между локальными и внешними LLM backend-ами измеримым, управляемым и обратимым.
- Motivation: сейчас проект хорошо работает как Ollama-first система, но не умеет честно отвечать на вопрос "когда стоит переключаться на другой backend и сколько это реально стоит".
- Ideas (8):
  1. Unified provider config для Ollama + Claude/Gemini/OpenAI -> `config/providers.yml`.
  2. Реальный per-step token/cost accounting вместо локальной заглушки -> trace schema + analytics field.
  3. Benchmark matrix по quality/latency/cost на curated support set -> `evaluation/provider_benchmark.py`.
  4. Routing profiles `offline-only`, `balanced`, `best-answer` -> `config/routing_profiles.yml`.
  5. Failover chain на случай деградации локального Ollama -> routing ability.
  6. Side-by-side answer diff UI для одного запроса через несколько backend-ов -> `static/model-lab.html`.
  7. Provider/model cards под Windows resource budget и API spend -> `docs/research/provider_profiles.md`.
  8. Историческое хранение benchmark результатов для сравнения релизов -> `data/evaluation/provider-benchmarks/`.
- Estimated scope: 8 task-специфик, ~34-46 часов.
- Expected impact: сильно вырастет экспериментальная ценность проекта и появится понятный язык для выбора между local-only и hybrid/cloud режимами.
- Risks / complications: API keys, внешние расходы, рост абстракций и риск увести проект слишком далеко от оффлайн-first характера.

## Recommendation
Выбрать candidate A - Continuous Learning Lab.

Причина выбора по критерию `impact x novelty x complexity x user preference`:

| Candidate | Impact | Novelty | Complexity | User fit |
|---|---|---|---|---|
| A | высокий | высокий | средний | высокий |
| B | средний | средний | средний | средний |
| C | средне-высокий | высокий | средне-высокий | средне-высокий |

Candidate A лучше всего капитализирует уже вложенные усилия в traces, analytics, feedback, eval и KB tooling. Он не требует тяжёлой новой инфраструктуры, не ломает local-first профиль, хорошо ложится на интерес к data engineering/analytics и делает все будущие изменения измеримыми. Candidate B полезен, но даёт меньше продуктовой и исследовательской отдачи прямо сейчас. Candidate C привлекателен как следующий шаг, но его лучше делать уже поверх нормального curated dataset и regression loop, иначе сравнение backend-ов будет шумным и слабо воспроизводимым.
