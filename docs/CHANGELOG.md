# Changelog

Все значимые изменения в проекте. Формат адаптирован под [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/), но сгруппирован по аркам и батчам, а не по семантическим версиям.

## [Arc 7 / Batch K] — 2026-04-22 — GraceKelly advanced orchestration

### Provider capabilities and graph integration
- **Advanced provider surface** — `llm/providers/base.py`, `gracekelly.py`, `mistral.py`, `ollama.py` and `runtime.py` expanded the runtime to `generate_with_tools`, `generate_with_schema`, `generate_stream` and `generate_batch`, while registry capabilities became the source of truth for tool-use, structured output, streaming and batch support.
- **GraceKelly advanced routing** — `GraceKellyProvider` now keeps simple requests on `/api/v1/smart`, moves tool/schema/consensus requests to `/api/v1/orchestrate`, parses `tool_calls` and `structured_output`, and preserves orchestration metadata.
- **Graph migration to provider-native orchestration** — `agent/graph.py` now uses provider-native tool loops and schema-constrained nodes for `classify_complexity`, `grade_docs` and `verify_facts`, including opt-in consensus mode via `FACT_VERIFY_CONSENSUS_ENABLED` and `FACT_VERIFY_RELIABILITY_LEVEL`.

### Streaming and ingestion
- **Provider-aware streaming API** — `api/app.py` added `/api/chat` and `/api/chat/stream`; the SSE path now tries provider `generate_stream()` before falling back to Ollama-only `_stream_ollama`, and `/api/health` exports `features.streaming_enabled` for the UI.
- **Streaming UI switch** — `static/chat.html` keeps `/api/ask/stream` for compatibility but switches to `/api/chat/stream` when `STREAMING_ENABLED=true`.
- **Opt-in batch contextual headers** — `ingestion/pipeline.py` added `INGESTION_BATCH_ENABLED=false`, provider-batch contextual-header preprocessing for ingestion, and sequential fallback when batch capability is unavailable, with latency metrics written into the ingestion log.

### Observability and tests
- **Consensus metric** — `monitoring/prometheus.py` added `fact_verification_consensus_total{level,verdict}` for explicit visibility into multi-model fact verification.
- **New regression coverage** — added `tests/test_ollama_provider.py`, `tests/test_chat_streaming.py`, and batch-K expansions in provider/graph/ingestion suites covering advanced GraceKelly routing, unified tool/schema paths, provider streaming and ingestion batch fallback.
## [Arc 7 / Batch H] — 2026-04-22 — GraceKelly + Mistral providers

### Provider runtime and routing cleanup
- **GraceKelly provider** — `llm/providers/gracekelly.py`, `llm/providers/base.py` и `llm/providers/runtime.py` добавили локальный orchestrator backend с lazy readiness check через `/healthz/ready`, проксированием в `/api/v1/smart` и `cost_usd=0.0` в наших trace'ах.
- **Direct Mistral provider** — `llm/providers/mistral.py`, `config/providers.yml` и `.env.example` добавили OpenAI-compatible direct provider для `https://api.mistral.ai/v1/chat/completions`, чтение usage из ответа и fail-fast на placeholder `MISTRAL_API_KEY`.
- **Routing profiles revamp** — `local-first`, `gracekelly-primary` и `external-mistral` заменили старые `latency-first` / `cost-first` / `quality-first`; default теперь остаётся zero-spend local-only через Ollama.
- **Dead paid-provider cleanup** — direct `anthropic.py`, `openai.py` и `gemini.py` удалены из runtime как неиспользуемый код для этого deployment profile.

### Failover and observability
- **GraceKelly -> Ollama failover** — runtime теперь перехватывает `ProviderUnavailable`, автоматически переключает запрос на локальный fallback только для declared GraceKelly profiles и кеширует fallback decision на 5 минут.
- **Fallback Prometheus metric** — `monitoring/prometheus.py` добавил `llm_provider_fallback_total{from_provider,to_provider,reason}`, чтобы silent local failover был виден в monitoring.
- **Benchmark refresh** — `scripts/regression_eval.py` и provider tests перешли на `ollama` / `gracekelly` / `mistral` вместо удалённых direct paid providers.

### Docs and operator surface
- **Operator docs refreshed** — README, `.env.example`, roadmap и Arc 7 proposal синхронизированы с новым active set: local Ollama, GraceKelly orchestrator и direct Mistral.
- **Provider/failover test suites** — добавлены `tests/test_mistral_provider.py`, `tests/test_gracekelly_provider.py`, `tests/test_failover_chain.py`, а batch G provider tests переписаны под новый routing surface.

## [Arc 7 / Batch G] — 2026-04-22 — Provider abstraction

### Provider runtime, routing, and economics
- **Provider registry** — `config/providers.yml` и `config/provider_schema.py` добавили единый source of truth для Ollama и direct-provider routing: aliases, pricing tables, capabilities, rate limits и routing profiles `latency-first`, `cost-first`, `quality-first`.
- **Unified provider runtime** — пакет `llm/providers/*` и integration в `agent/graph.py` перевели pipeline на общий provider-backed runtime без отказа от Ollama-first safe default: локальный profile по умолчанию остался zero-spend.
- **Provider-aware trace accounting** — `agent/state.py`, `sqlite_trace.py` и `tracing/sqlite_trace.py` начали сохранять `provider_name`, `model_name`, prompt/completion tokens, usage metadata и `cost_usd` на уровне шагов trace вместо безымянного cost-only режима.
- **Paid guardrails** — `config/settings.py` и `llm/providers/runtime.py` добавили fail-fast validation для paid profiles, считают placeholder secrets вроде `changeme` отсутствующими ключами и блокируют paid runtime при превышении `DAILY_COST_LIMIT_USD`.

### Benchmarking and admin surface
- **Provider benchmark** — `scripts/regression_eval.py` теперь принимает provider/model aliases как baseline/candidate, умеет режимы `mock-provider-benchmark` и `live-provider-benchmark`, а отчёты сравнивают pass rate, latency, total cost и refusal rate по curated dataset.
- **Prometheus provider cost metric** — `monitoring/prometheus.py` и trace logging добавили `llm_cost_usd_total{provider,model,tenant}`, чтобы стоимость LLM стала видимой не только в analytics, но и в operational monitoring.
- **Providers admin tab** — `api/app.py` и `static/admin.html` добавили `GET /api/admin/providers` и UI-вкладку Providers с active/default profile, configured flag, 1-minute usage, 24-hour cost и last successful call timestamp.

### Docs and verification
- **Operator docs refreshed** — `.env.example`, `README.md`, `codex-tasks/ROADMAP.md`, `codex-tasks/arc-7-proposal.md`, `codex-tasks/orchestrator-batch-g-provider-abstraction.md` и task-spec'и 143-149 синхронизированы с новым provider/runtime surface.
- **Provider-focused test suites** — добавлены `tests/test_provider_registry.py`, `tests/test_provider_settings.py`, `tests/test_provider_abstraction.py`, `tests/test_provider_graph_integration.py`, `tests/test_provider_cost_accounting.py`, `tests/test_provider_benchmark.py`, `tests/test_provider_admin_surface.py`, покрывающие schema, runtime, graph integration, cost metrics, benchmark mode и admin API.

## [Arc 6 / Batch F] — 2026-04-22 — Continuous learning lab

### Learning loop foundation (tasks 133-140, fixes 141-142)
- **Review queue** — `alembic/versions/012_review_queue.py`, `scripts/build_review_queue.py`, admin endpoint'ы `/api/admin/review-queue*`, Prometheus-метрики и секция в `static/admin.html` превратили traces/feedback в явную очередь ручного разбора вместо разрозненных сигналов (task-133).
- **Curated dataset builder** — `scripts/build_curated_dataset.py`, `evaluation/dataset.py`, `evaluation/curated_cases.jsonl` и admin-trigger на rebuild начали собирать подтверждённые review cases в переиспользуемый eval/regression датасет вместо одноразового ручного отбора (task-134).
- **Prompt / experiment registry** — `evaluation/experiment_schema.py`, `agent/prompt_registry.py`, `scripts/experiment_{new,apply}.py`, admin endpoint'ы для экспериментов и последующий runtime wire-in через `CURRENT_EXPERIMENT` в `agent/graph.py` сделали staged prompt overrides реально исполняемыми внутри pipeline, а не только описанными в конфиге (tasks 135, 142).
- **Regression runner** — `scripts/regression_eval.py`, CI job `regression-eval`, gate-настройки в `config/settings.py` и API для запуска/просмотра regression runs превратили curated dataset + experiments в формальный pre-deploy quality gate (task-136).
- **Online evaluators runtime** — `evaluation/online_evaluators.py`, `evaluation/evaluator_runner.py`, `alembic/versions/014_trace_evaluations.py`, `/api/admin/evaluations/{trends,worst}`, `scripts/eval_daily_snapshot.py`, `config/evaluator_patterns.yml` и Prometheus-метрики добавили production-оценку trace quality по hot-path и ежедневные snapshot-агрегаты вместо одного только offline eval (tasks 137, 141).
- **Weekly improvement backlog** — `scripts/generate_improvement_backlog.py`, backlog endpoint'ы и cronjob начали агрегировать review queue, KB gaps, evaluator drift, slow traces и freshness signals в единый приоритизированный список улучшений (task-138).
- **Threshold recommendations** — `scripts/analyze_thresholds.py`, `/api/admin/thresholds/*` и `reports/threshold_recommendations.md` перевели quality/review thresholds из ручной настройки в F1-ориентированный анализ на реальных label'ах (task-139).
- **Offline review workflow** — `scripts/review_export.py`, `scripts/review_import.py` и `.gitignore` для review batch artifacts дали команде безопасный export/import ручной разметки вне production UI без потери auditability (task-140).

### Migrations
- **012_review_queue** — таблица `review_queue` и supporting indexes/status fields для human review workflow.
- **013_regression_eval_runs** — расширение `eval_results` полями regression run metadata для baseline/candidate сравнений.
- **014_trace_evaluations** — таблица `trace_evaluations` для online evaluator verdicts, score и evidence.

### Testing
- Полный набор вырос с **319** до **393** тестов (**+74**).
- Closing sweep для Batch F завершился зелёным `pytest tests/ -q`, включая fix-spec'и для prompt-registry routing и online evaluators runtime.

## [Arc 102-122] — 2026-04-21 — Product, enterprise, polish

### Batch A — UX (tasks 102-106)
- **Inline citations и source panel** — ответы начали встраивать маркеры `[N]`, API стал возвращать `citations`, а `static/chat.html` получил hover/click-рендеринг и боковую панель источников вместо «сплошного» текста без ссылок (task-102).
- **Mobile-first responsive UI** — `static/chat.html`, `static/help.html`, `static/metrics.html` и `static/admin.html` перешли на брейкпоинты 480/768/1024, mobile drawer и безопасные tap targets вместо одного грубого mobile fallback (task-103).
- **WCAG 2.1 AA baseline** — `tests/test_a11y.py`, `static/*.html`, `templates/*.html` и `static/styles/components.css` закрыли critical/serious accessibility gaps: labels, `:focus-visible`, keyboard navigation, ARIA и viewport meta (task-104).
- **UX polish для чата** — в `static/chat.html` появились upload progress, retry после сетевых/timeout-ошибок и onboarding-панель с sample questions для первого визита (task-105).
- **Agent copilot** — миграция `alembic/versions/004_escalated_tickets.py`, новые `/api/agent/*` endpoint'ы и `static/agent.html` со `static/styles/agent.css` дали операторам очередь эскалаций, контекст диалога, AI draft и похожие resolved tickets (task-106).

### Batch B — RAG intelligence (tasks 107-110)
- **Agentic tool use** — `agent/tools.py` и `agent/graph.py` добавили LangGraph tool-calling, multi-step tool chains и confirmation gate для необратимых действий под флагом `RAG_AGENTIC_MODE` (task-107).
- **Nightly RAGAS evaluation** — `scripts/nightly_eval.py`, `evaluation/drift.py`, `alembic/versions/005_eval_results.py` и `deploy/helm/templates/cronjob.yaml` превратили offline eval из CI-only практики в регулярный production drift monitoring (task-108).
- **KB gap detection** — `scripts/kb_gap_detector.py`, `alembic/versions/006_knowledge_gaps.py`, `GET /api/admin/kb-gaps` и секция в `static/admin.html` начали превращать unanswered/unsupported вопросы в админские KB gap tickets (task-109).
- **Contextual ingestion headers** — `ingestion/pipeline.py`, `vectordb/manager.py` и `scripts/reindex.py` активировали document-aware contextual headers для чанков под флагом `RAG_CONTEXTUAL_HEADERS` (task-110).

### Batch C — Enterprise (tasks 111-113)
- **OpenTelemetry distributed tracing** — `tracing/otel.py`, интеграция в `api/app.py`, ручные span'ы в графе, `docker-compose.yml` и `deploy/helm/values.yaml` добавили OTLP export в Jaeger/Tempo без удаления SQLite/Langfuse tracing (task-111).
- **SSO via OIDC** — `auth/oidc.py`, `static/login.html`, `/api/auth/sso/providers`, `/api/auth/sso/{provider}/login`, `/api/auth/sso/{provider}/callback` и миграция `007_user_sso_fields` принесли Google/Azure AD sign-in с tenant mapping по email-domain rules (task-112).
- **Encryption at rest** — `db/crypto.py`, `alembic/versions/008_enable_pgcrypto.py` и `DB_ENCRYPTION_KEY` перевели sensitive Postgres columns на `pgcrypto`/AES-256 с прозрачным decrypt в ORM и отдельным rotation script stub `scripts/rotate_encryption_key.py` (task-113).

### Batch D — Differentiation (tasks 114-119)
- **Knowledge Builder** — `scripts/kb_builder.py`, миграция `009_kb_drafts`, админские `/api/admin/kb-drafts/*` endpoint'ы и UI в `static/admin.html` начали собирать resolved tickets в reviewable KB drafts вместо потери накопленного знания (task-114).
- **Knowledge freshness monitoring** — `alembic/versions/010_document_stats.py`, citation counters в графе, `GET /api/admin/stale-docs` и `rag_stale_important_docs_count` сделали видимыми старые, но часто цитируемые документы (task-115).
- **Auto-categorization** — `ingestion/categorizer.py`, `config/categories.yml` и расширенный `/api/upload` начали присваивать документам категории, которые потом используются в metadata и аналитике (task-116).
- **Analytics dashboard** — `static/analytics.html`, `/api/analytics/top-topics`, `/api/analytics/resolution-rate`, `/api/analytics/cost-summary`, `/api/analytics/trends` и миграция `011_trace_costs` добавили продуктовую аналитику поверх traces/cost data (task-117).
- **Weekly quality reports** — `reports/renderer.py`, `scripts/weekly_report.py`, `deploy/helm/templates/cronjob-report.yaml` и `.github/workflows/weekly-report.yml` перевели аналитику из pull-mode в scheduled Slack/email digest (task-118).
- **Email channel** — `channels/email_channel.py`, `channels/email_webhook.py`, `scripts/email_poller.py`, `/api/channels/email/inbound` и `deploy/helm/templates/deployment-email-poller.yaml` подключили IMAP/webhook email ingestion к тому же RAG/escalation flow (task-119).

### Batch E — Code quality (tasks 120-122)
- **Canonical agent package** — `agent/{graph,prompts,state,tools}.py` стал каноническим домом для graph/state/prompt/tool кода, а root-level `graph.py`, `prompts.py` и `state.py` были сохранены как compatibility shims на период миграции импортов (task-120).
- **Settings over magic numbers** — ключевые thresholds и tuning constants переехали в `config/settings.py` и `.env.example`, чтобы retrieval/chunking/quality настройки менялись через конфиг, а не через правку кода (task-121).
- **Integration test suite** — `tests/integration/` и отдельный `integration` marker закрыли полный happy-path: ingestion, multi-turn conversation, SSE streaming, concurrency, escalation и async upload в отдельном прогоне и CI-job'е (task-122).

### Migrations
- **004_escalated_tickets** — таблица `escalated_tickets` для copilot/escalation workflow.
- **005_eval_results** — хранение nightly eval metrics и drift flags.
- **006_knowledge_gaps** — хранение кластеров unanswered questions.
- **007_user_sso_fields** — поля OIDC provider/subject для пользователей.
- **008_enable_pgcrypto** — включение `pgcrypto` и переход sensitive columns на encrypted storage.
- **009_kb_drafts** — хранение reviewable KB drafts из resolved tickets.
- **010_document_stats** — статистика цитирований, freshness и stale-doc review state.
- **011_trace_costs** — token usage и cost data для analytics/cost summaries.

### Testing
- Полный набор вырос с **222** до **293** тестов (**+71**).
- Отдельная `tests/integration/` директория закрыла те сценарии, которые раньше проверялись только набором unit-тестов и ручных прогонов.

## [Arc 68-101] — 2026-04-20 — Production hardening

### Resilience (tasks 69-71, 82-83)
- **Circuit breaker вокруг Ollama** — `utils/circuit_breaker.py`, интеграция в `graph.py` и ручной reset через `/api/admin/circuit-breaker/reset` остановили каскадные задержки при падениях модели и дали fast-fail path вместо накопления зависших запросов (tasks 69, 74).
- **Retry, timeout и bounded failure budget** — `utils/retry.py`, per-call timeout для Ollama и retry observability в `monitoring/prometheus.py` начали гасить транзитные ошибки до того, как breaker откроется, и сделали эти деградации видимыми (tasks 70, 71, 73).
- **Request wall-time timeout и offload из event loop** — `/api/ask` начал выносить sync pipeline в `asyncio.to_thread`, получил `REQUEST_TIMEOUT_SEC`, а обработка запросов перестала блокировать health probes и соседние соединения (task-82).
- **Bounded pipeline concurrency** — глобальный admission control через `asyncio.Semaphore` и timeout на ожидание pipeline slot защитили сервис от самоперегрузки на пиках нагрузки (task-83).

### Observability (tasks 72-81, 89, 98)
- **Prometheus стал основным operational truth** — breaker state/transitions, retry events, component health, generic HTTP metrics, rate-limit rejections, request timeouts, auth failures, body-size rejections и DB pool saturation превратили систему из «логов и догадок» в измеряемый сервис (tasks 72, 73, 76, 78, 81, 89, 98).
- **Alert rules as code** — `monitoring/alert_rules.yml` зафиксировал базовые resilience/health/quality alerts прямо в репозитории, чтобы пороги ревьюились вместе с кодом, а не жили отдельно в ручной инфраструктуре (task-78).
- **Correlation ID end-to-end** — `api/correlation.py`, `X-Request-Id` middleware и прокидывание request id в trace state связали UI-инциденты, middleware-логи и pipeline traces в одну цепочку расследования (task-79).

### Health, deploy and admin operations (tasks 75, 77, 80, 84, 85, 90, 94)
- **Dependency-aware health model** — `/api/health/live` и `/api/health/ready` разделили liveness и readiness semantics, а Postgres/Redis probes добавили реальное представление о состоянии зависимостей вместо чисто Ollama/Chroma статуса (tasks 75, 77).
- **Graceful shutdown with readiness flip** — приложение стало переводить readiness в `503` перед реальным shutdown, чтобы rolling deploy не принимал новый трафик в pod, который уже уходит на остановку (task-80).
- **Trace и audit retention** — фоновая и ручная очистка SQLite traces и Postgres audit log ограничила бесконтрольный рост служебных таблиц и сделала retention частью runtime политики, а не разовой операции DBA (tasks 84, 85).
- **Admin investigation surface** — `/api/admin/audit`, `/api/admin/traces`, `/api/admin/traces/{trace_id}` и затем `static/admin.html` вывели операции расследования из прямого SQL/curl в стандартный HTTP/UI слой для support и admin ролей (tasks 90, 94).

### Security and platform hardening (tasks 86-88)
- **Auth hardening** — `/api/auth/login` получил rate limit `5/min`, failed-login audit trail и Prometheus metrics, чтобы credential stuffing и password spraying стали не только затруднены, но и заметны (task-86).
- **Production CORS guardrails** — `RAG_ENV`, startup validation и `CORS_MAX_AGE_SEC` сделали `CORS_ORIGINS="*"` допустимым только в development и закрыли тихий insecure deploy path в production (task-87).
- **Request body limits** — middleware на `MAX_REQUEST_BODY_BYTES` и upload-specific `MAX_UPLOAD_BYTES` добавили дешёвую защиту от oversized JSON/file DoS до разбора тела в приложении (task-88).

### Multi-tenancy (tasks 91, 93, 95, 96)
- **Tenant schema and propagation** — `tenant_id` вошёл в schema/state/Pydantic, затем в JWT claims, request-scoped context, traces и audit log, так что система перестала считать всех пользователей `default` tenant'ом на уровне записи данных (tasks 91, 93).
- **Tenant enforcement on reads** — admin read endpoints, metrics snapshot и trace/audit lookups начали фильтровать данные по текущему tenant'у, закрывая прямой cross-tenant leak в metadata/read paths (task-95).
- **Per-tenant ChromaDB collections** — `vectordb/manager.py` ушёл от общего `rag_docs` к tenant-scoped `rag_docs_{tenant_id}`, что закрыло самую опасную дыру: смешивание документов разных клиентов в retrieval (task-96).

### Answer quality and routing (tasks 92, 97)
- **Fact verification node** — после `generate` появился отдельный `verify_facts` шаг, который извлекает claims, сверяет их с retrieved context и пишет `factuality_score` вместо слепого доверия к самооценке модели (task-92).
- **Model routing** — `MODEL_ROUTING_ENABLED` и `OLLAMA_FAST_MODEL_NAME` позволили отдавать простые вопросы быстрой модели, а сложные оставлять на более сильной, не меняя retrieval path и сохраняя safe default `off` (task-97).

### Tech debt closure (tasks 99-101)
- **Flaky rate-limit tests fixed** — `tests/conftest.py` начал сбрасывать slowapi state между тестами, убрав случайные падения `test_rate_limiting` в полном прогоне (task-99).
- **LLM response cache wired in** — готовый `cache/redis_cache.py` перестал быть мёртвым кодом и начал кешировать финальные ответы по `(tenant, normalized_question)` с инвалидацией после upload (task-100).
- **Repository line endings normalized** — `.gitattributes` закрепил LF для текстовых файлов и устранил Windows-specific CRLF noise в коммитах и diff'ах (task-101).

### Testing
- Арка стартовала примерно со **130** тестов и закрылась на **222** тестах.
- Существенная часть роста пришлась на resilience, observability, health, multi-tenancy, fact verification и routing regressions, которые раньше вообще не были формализованы в test suite.
