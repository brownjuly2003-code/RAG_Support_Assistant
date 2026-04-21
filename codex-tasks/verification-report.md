# Arc 102-122 verification report

## Summary
- Total tasks verified: 21
- ✅ Fully meets acceptance: 0
- ⚠️ Partial / interpretation needed: 15
- ❌ Missing or violated: 6
- Legend: `✅` = критерий подтверждается текущим кодом/артефактами в репо; `⚠️` = реализация есть частично или критерий нельзя честно подтвердить без запуска/manual/PR-артефактов; `❌` = текущий код противоречит acceptance или заметно уже спецификации.

## Batch A — UX (102-106)

### Task 102 — inline citations
- Spec: `codex-tasks/Archive/task-102-inline-citations.md`
- Acceptance criteria:
- `3+ citation unit-тестов (generation, parsing, orphan-citation handling)` — ✅ — evidence: `tests/test_citations.py:16`, `tests/test_citations.py:55`, `tests/test_citations.py:87`
- `Manual test: вопрос → [N] → hover → panel` — ⚠️ — evidence: `static/chat.html:1842-1929`, `static/chat.html:1130-1140`; UI-путь реализован, но ручной прогон не подтверждён
- `225+ passed, ruff clean` — ⚠️ — evidence: в этом проходе тесты/ruff не запускались по условиям task
- `Screenshot в PR` — ⚠️ — evidence: в рабочей копии PR-артефакт отсутствует
- `Commit: "Inline citations in bot answers with source panel (task-102)"` — ⚠️ — evidence: изменения не закоммичены; commit-message не проверить
- Overall: ⚠️
- Notes: prompt-инструкция и сборка `citations` есть (`agent/prompts.py:104-107`, `agent/graph.py:629-659`, `api/app.py:262-278`), но source panel показывает chunk/excerpt, а не полный документ (`static/chat.html:1282-1284`)

### Task 103 — mobile responsive
- Spec: `codex-tasks/Archive/task-103-mobile-responsive.md`
- Acceptance criteria:
- `3 breakpoints (480/768/1024) во всех 4 static-страницах` — ✅ — evidence: `tests/test_mobile_responsive.py:16-29`, `static/chat.html:867-929`, `static/help.html:151-180`, `static/metrics.html:142-163`, `static/admin.html:14-37`
- `viewport meta во всех templates/*.html` — ✅ — evidence: `tests/test_mobile_responsive.py:38-45`
- `Все tap targets ≥44×44` — ✅ — evidence: `static/styles/components.css:22-28`, `static/styles/components.css:32-37`, `static/styles/components.css:54-59`
- `Lighthouse mobile ≥80 на chat.html` — ⚠️ — evidence: в репо нет результата прогона Lighthouse
- `223+ passed` — ⚠️ — evidence: тесты не запускались в этом verification sweep
- `Screenshots: 375px, 768px, 1024px в PR` — ⚠️ — evidence: в репо нет PR-скриншотов
- `Commit: "Mobile-first responsive with 3 breakpoints (task-103)"` — ⚠️ — evidence: commit не верифицируется по текущей рабочей копии
- Overall: ⚠️
- Notes: mobile safe-area и drawer-логика есть (`static/chat.html:643`, `static/chat.html:1332-1415`)

### Task 104 — WCAG audit
- Spec: `codex-tasks/Archive/task-104-wcag-audit.md`
- Acceptance criteria:
- `axe-core runs в CI (или локальный opt-in через playwright)` — ❌ — evidence: `tests/test_a11y.py:17-45` проверяет только HTML/CSS-инварианты; импорта/запуска `axe-core` или `playwright` в файле нет
- `0 critical + 0 serious violations на всех 4 основных страницах` — ❌ — evidence: в репо нет ни `axe`-прогона, ни отчёта; текущие тесты не измеряют severity violations (`tests/test_a11y.py:17-45`)
- ``:focus-visible` стили применены глобально` — ✅ — evidence: `static/styles/components.css:74-78`, `tests/test_a11y.py:41-45`
- `Keyboard nav: Tab проходит все controls без мёртвых зон` — ⚠️ — evidence: есть keyboard hooks для dropzone/citations (`static/chat.html:1092`, `static/chat.html:1924-1929`, `static/chat.html:2029-2050`), но полного keyboard-nav теста нет
- `Manual screen reader test (NVDA/VoiceOver)` — ⚠️ — evidence: manual screen-reader evidence в репо отсутствует
- `225+ passed (1 новый parametrized test × 4 pages = 4 test cases)` — ⚠️ — evidence: `tests/test_a11y.py` есть, но это не `axe`-parametrized smoke по 4 страницам и suite не запускался
- `Commit: "WCAG AA compliance: axe-core audit + fix criticals (task-104)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ❌
- Notes: upload-modal focus trap из spec в `static/chat.html` не найден; значит даже часть указанных fixes не доказана кодом

### Task 105 — UX polish
- Spec: `codex-tasks/Archive/task-105-ux-polish.md`
- Acceptance criteria:
- `Upload 5MB файла показывает прогресс 0-100% визуально плавно` — ✅ — evidence: `static/chat.html:1101-1107`, `static/chat.html:2082-2130`
- `Отключить backend → сообщение "Сервис временно недоступен" + retry button работает` — ✅ — evidence: `static/chat.html:1212-1216`, `static/chat.html:1767-1779`
- `Новый localStorage-чистый пользователь видит onboarding, повторный визит — нет` — ✅ — evidence: `static/chat.html:1028-1045`, `static/chat.html:1317-1329`
- `3 sample questions clickable → отправляются как обычные user messages` — ✅ — evidence: `static/chat.html:1039-1042`, `static/chat.html:1489-1494`, `static/chat.html:1549-1563`
- `225+ passed` — ⚠️ — evidence: тесты не запускались
- `Screenshots: progress / error / onboarding` — ⚠️ — evidence: PR-скриншоты не приложены в репо
- `Commit: "UX polish: upload progress, error recovery, onboarding (task-105)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️
- Notes: показ onboarding завязан на `localStorage`/`sessionId`/наличие сообщений (`static/chat.html:1324-1329`), но не проверяет отдельно anonymous vs logged-in user из constraint

### Task 106 — agent copilot
- Spec: `codex-tasks/Archive/task-106-agent-copilot.md`
- Acceptance criteria:
- `Миграция 004 прошла, таблица есть` — ⚠️ — evidence: `alembic/versions/004_escalated_tickets.py:19-33`, `db/models.py:181-204`; факт применения миграции не подтверждён
- `При escalation создаётся ticket, AI draft populated` — ✅ — evidence: `api/app.py:1718-1737`
- ``/agent` доступен только role=agent/admin, 403 для viewer` — ✅ — evidence: `api/app.py:3428-3435`, `tests/test_agent_endpoints.py:24-30`, `tests/test_agent_endpoints.py:130-133`
- `Тикет-лист показывает only own-tenant` — ✅ — evidence: `api/app.py:1758-1778`, `tests/test_agent_endpoints.py:70-79`
- `Similar tickets: 3 ближайших по embedding` — ❌ — evidence: `api/app.py:1840-1849`, `api/app.py:1951-1960`; текущая реализация берёт просто последние `resolved` тикеты по времени, без embeddings/semantic search
- `230+ passed (5-7 новых тестов)` — ⚠️ — evidence: тест-файл есть (`tests/test_agent_endpoints.py`), но suite не запускался
- `Screenshots /agent с реальным тикетом` — ⚠️ — evidence: в репо нет
- `Commit: "Agent copilot dashboard with ticket context + AI draft (task-106)"` — ⚠️ — evidence: не верифицируется
- Overall: ⚠️
- Notes: detail-endpoint возвращает `retrieved_docs: []` и `quality_scores: {}` (`api/app.py:1865-1867`), так что context panel уже заявлен, но ещё не наполнен как в spec

## Batch B — RAG intelligence (107-110)

### Task 107 — agentic tool use
- Spec: `codex-tasks/Archive/task-107-agentic-tool-use.md`
- Acceptance criteria:
- `3 tools определены, docstrings читаются агентом` — ⚠️ — evidence: `agent/tools.py:30-90`; три функции и docstrings есть, но `tool` — локальный no-op decorator (`agent/tools.py:13-15`), не LangChain/LangGraph registry
- `Multi-step: доставка в Москву + заказ #42` — ✅ — evidence: `agent/graph.py:1333-1368`, `tests/test_agent_tools.py:36-65`
- `Confirmation: create_ticket → ask → confirm → ticket` — ✅ — evidence: `agent/graph.py:1253-1323`, `tests/test_agent_tools.py:68-112`
- `Feature flag: OFF → старый pipeline, ON → агентный` — ✅ — evidence: `config/settings.py:142-145`, `agent/graph.py:1381-1395`, `tests/test_agent_tools.py:21-27`
- `235+ passed (~10 новых тестов)` — ⚠️ — evidence: `tests/test_agent_tools.py` есть, но run отсутствует
- `Langfuse trace показывает tool_calls` — ❌ — evidence: `tracing/langfuse_trace.py:50-82`; в Langfuse передаются prompt/response/model/duration, но не `tool_calls`
- `Commit: "Agentic tool-use framework with multi-step + confirmation (task-107)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️
- Notes: реализация ближе к ручному intent-router, чем к `ToolNode`/LLM tool-calling из spec

### Task 108 — nightly RAGAS eval
- Spec: `codex-tasks/Archive/task-108-nightly-ragas-eval.md`
- Acceptance criteria:
- ``python scripts/nightly_eval.py` работает end-to-end на dev DB` — ⚠️ — evidence: `scripts/nightly_eval.py:137-187`; script есть, но не запускался
- `Миграция 005 (EvalResult) прошла` — ⚠️ — evidence: `alembic/versions/005_eval_results.py:18-28`, `db/models.py:207-220`; факт применения не доказан
- `CronJob в Helm chart, helm template валидный` — ✅ — evidence: `deploy/helm/templates/cronjob.yaml:6-17`
- `Prometheus gauge rag_eval_drift виден в /metrics` — ✅ — evidence: `evaluation/drift.py:14-30`, `monitoring/prometheus.py:322,412`, `tests/test_nightly_eval.py:28-37`
- `Alert rule добавлен в monitoring/alert_rules.yml` — ✅ — evidence: `monitoring/alert_rules.yml:173`
- `Искусственный drift → alert fires` — ⚠️ — evidence: `tests/test_nightly_eval.py:28-37`, `tests/test_nightly_eval.py:58-106`; покрыта запись gauge и `drift_alert`, но не реальный Prometheus/Alertmanager fire
- `240+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Nightly RAGAS eval + drift alert via Prometheus gauge (task-108)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

### Task 109 — KB gap detection
- Spec: `codex-tasks/Archive/task-109-kb-gap-detection.md`
- Acceptance criteria:
- `knowledge_gap пишется в traces для 3 сценариев` — ✅ — evidence: `agent/graph.py:304-322`, `agent/graph.py:828`, `tests/test_kb_gaps.py:18-49`
- ``python scripts/kb_gap_detector.py` создаёт KnowledgeGap` — ✅ — evidence: `scripts/kb_gap_detector.py:208-235`, `tests/test_kb_gaps.py:52-65`
- `Admin UI показывает список gaps` — ✅ — evidence: `api/app.py:2140-2175`, `static/admin.html:116-131`, `static/admin.html:209-223`
- `Миграция 006 прошла` — ⚠️ — evidence: `alembic/versions/006_knowledge_gaps.py:18-31`, `db/models.py:222-241`; не применялась в этом проходе
- `CronJob в Helm` — ✅ — evidence: `deploy/helm/templates/cronjob.yaml:27-38`
- `245+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "KB gap detection: cluster unanswered questions into admin tickets (task-109)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

### Task 110 — contextual headers
- Spec: `codex-tasks/Archive/task-110-contextual-headers.md`
- Acceptance criteria:
- ``RAG_CONTEXTUAL_HEADERS=true` default в settings` — ✅ — evidence: `config/settings.py:137-140`
- ``add_contextual_headers` вызывается в ingestion/pipeline.py` — ⚠️ — evidence: прямого вызова в `ingestion/pipeline.py` нет; feature включается внутри `vectordb/manager.py:130-135`, а pipeline использует этот builder через `ingestion/pipeline.py:113-145`
- ``python scripts/reindex.py` работает on test data` — ⚠️ — evidence: `scripts/reindex.py:34-74`; script есть, но не запускался
- `A/B до/после reindex, precision@5 same or better` — ⚠️ — evidence: A/B-артефакт или eval-report в repo не найден
- ``has_context_header=True` в metadata новых chunks` — ✅ — evidence: `vectordb/manager.py:63-67`, `tests/test_ingestion_contextual.py:109-117`
- `248+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Activate contextual headers in ingestion pipeline (task-110)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

## Batch C — Enterprise (111-113)

### Task 111 — OpenTelemetry
- Spec: `codex-tasks/Archive/task-111-opentelemetry.md`
- Acceptance criteria:
- ``OTEL_ENABLED=true` + Jaeger up → traces visible` — ⚠️ — evidence: `api/app.py:886-897`, `tracing/otel.py:108-149`, `docker-compose.yml:59-78`; runtime not checked
- `HTTP /api/ask → span tree FastAPI → retrieve → rerank → generate → evaluate` — ✅ — evidence: `tracing/otel.py:139-147`, `agent/graph.py:804-829`, `tests/test_otel.py:119-194`
- ``OTEL_ENABLED=false` → pytest passes, no errors` — ✅ — evidence: `tracing/otel.py:119-120`, `tests/test_otel.py:6-24`
- `Helm values включают otel config` — ✅ — evidence: `deploy/helm/values.yaml:41-42`
- `docker-compose up → Jaeger доступен локально` — ✅ — evidence: `docker-compose.yml:59-63`
- `250+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "OpenTelemetry SDK: distributed tracing w/ auto-instrumentation (task-111)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

### Task 112 — SSO / OIDC
- Spec: `codex-tasks/Archive/task-112-sso-oidc.md`
- Acceptance criteria:
- `Google OIDC: login button → redirect → callback → JWT` — ✅ — evidence: `api/app.py:2840-2895`, `static/login.html:118-147`, `tests/test_oidc_flow.py:32-92`
- `Azure AD OIDC: same path in tests` — ✅ — evidence: `auth/oidc.py:54-60`, `auth/oidc.py:82-96`, `tests/test_oidc_flow.py:20-29`
- `User создаётся с правильным tenant_id по email domain mapping` — ✅ — evidence: `auth/oidc.py:101-149`, `tests/test_oidc_flow.py:94-109`
- `Existing password login continues to work` — ✅ — evidence: `api/app.py:2918`, `api/app.py:2986`
- ``/api/auth/sso/providers` returns enabled providers` — ✅ — evidence: `api/app.py:2835-2837`, `auth/oidc.py:45-61`
- `Миграция 007 прошла` — ⚠️ — evidence: `alembic/versions/007_user_sso_fields.py:18-39`, `db/models.py:50`, `db/models.py:68-69`; migration not applied here
- `253+ passed, ruff clean` — ⚠️ — evidence: run отсутствует
- `Commit: "SSO via authlib: Google + Azure AD OIDC (task-112)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

### Task 113 — encryption at rest
- Spec: `codex-tasks/Archive/task-113-encryption-at-rest.md`
- Acceptance criteria:
- `pgcrypto extension enabled в миграции 008` — ✅ — evidence: `alembic/versions/008_enable_pgcrypto.py:65`
- `Sensitive поля encrypted через EncryptedText` — ✅ — evidence: `db/crypto.py:10-59`, `db/models.py:85`, `db/models.py:171`, `db/models.py:196-198`, `tests/test_encryption.py:28-36`
- `Round-trip test INSERT plaintext → SELECT plaintext` — ⚠️ — evidence: `tests/test_encryption.py:10-25` проверяет bind/column expressions, но live DB round-trip не прогонялся
- `Direct SQL показывает ciphertext/bytea` — ⚠️ — evidence: `alembic/versions/008_enable_pgcrypto.py:20-24`, `alembic/versions/008_enable_pgcrypto.py:38-55`; direct SQL check не выполнялся
- `Existing tests remain transparent for app code` — ⚠️ — evidence: suite не запускался
- `README documents DB_ENCRYPTION_KEY + backup policy` — ✅ — evidence: `README.md:151`, `README.md:331`
- `255+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Encryption at rest: pgcrypto for sensitive fields (task-113)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

## Batch D — Differentiation (114-119)

### Task 114 — knowledge builder
- Spec: `codex-tasks/Archive/task-114-knowledge-builder.md`
- Acceptance criteria:
- `Миграция 009 прошла` — ⚠️ — evidence: `alembic/versions/009_kb_drafts.py:19-32`, `db/models.py:244-261`; migration не применялась
- ``python scripts/kb_builder.py` создаёт drafts` — ✅ — evidence: `scripts/kb_builder.py:117-171`
- `Admin UI видит pending drafts, может edit + publish` — ✅ — evidence: `api/app.py:2195-2328`, `static/admin.html:134-147`, `static/admin.html:264-331`
- `После publish документ появляется в ChromaDB и retriever находит его` — ⚠️ — evidence: publish path векторизует документ (`api/app.py:2299-2327`), но retrieval-proof в repo не найден
- `PII redaction применяется к generated content` — ✅ — evidence: `scripts/kb_builder.py:98-114`, `tests/test_kb_builder.py:16-39`
- `Weekly CronJob в Helm` — ✅ — evidence: `deploy/helm/templates/cronjob.yaml:48-59`
- `260+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Knowledge Builder: cluster resolved tickets into KB drafts (task-114)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

### Task 115 — knowledge freshness
- Spec: `codex-tasks/Archive/task-115-knowledge-freshness.md`
- Acceptance criteria:
- `Миграция 010 прошла` — ⚠️ — evidence: `alembic/versions/010_document_stats.py:18-28`, `db/models.py:270-285`; migration не применялась
- `Citations инкрементят counter на /api/ask` — ✅ — evidence: `api/app.py:497-530`, `api/app.py:1313-1314`
- ``GET /api/admin/stale-docs` возвращает корректный список` — ✅ — evidence: `api/app.py:2331-2384`, `tests/test_freshness.py:15-68`
- `Admin UI показывает таблицу, Mark reviewed работает` — ✅ — evidence: `static/admin.html:150-168`, `static/admin.html:350-375`, `api/app.py:2387-2395`
- `Prometheus gauge rag_stale_important_docs_count в /metrics` — ✅ — evidence: `monitoring/prometheus.py:262`, `monitoring/prometheus.py:386`, `api/app.py:2380-2383`
- `265+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Knowledge freshness monitoring: stale + top-cited tracking (task-115)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

### Task 116 — auto-categorization
- Spec: `codex-tasks/Archive/task-116-auto-categorization.md`
- Acceptance criteria:
- ``config/categories.yml` default taxonomy есть` — ✅ — evidence: `config/categories.yml:1-11`
- `Upload → response содержит assigned categories` — ✅ — evidence: `api/app.py:2723-2731`, `api/app.py:2763-2767`, `tests/test_categorizer.py:81-137`
- `Metadata в ChromaDB содержит categories list` — ✅ — evidence: `ingestion/categorizer.py:234-258`, `vectordb/manager.py:72-93`
- `Test: document про доставку → ["shipping"]` — ✅ — evidence: `tests/test_categorizer.py:32-45`
- `Fallback: invalid JSON → ["uncategorized"]` — ✅ — evidence: `ingestion/categorizer.py:178-200`, `tests/test_categorizer.py:48-58`
- `268+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Auto-categorize documents on upload via LLM (task-116)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

### Task 117 — analytics dashboard
- Spec: `codex-tasks/Archive/task-117-analytics-dashboard.md`
- Acceptance criteria:
- `Миграция 011 прошла, token_usage колонки есть` — ⚠️ — evidence: `alembic/versions/011_trace_costs.py:18-21`, `db/models.py:127-130`; migration не применялась
- `Каждый LLM call пишет tokens + cost` — ❌ — evidence: `api/app.py:437-492` всегда заполняет `cost_usd: 0.0`; repo-wide search не показывает runtime-записи `prompt_tokens`/`completion_tokens`/`cost_usd` вне migrations/models/tests
- `4 analytics endpoints работают, tenant-scoped` — ✅ — evidence: `api/app.py:2398-2500`
- ``/static/analytics.html` рисует 4 chart'а с реальными данными` — ⚠️ — evidence: `static/analytics.html:121-134`; UI есть, но cost-данные сейчас синтетические нули из `api/app.py:491`
- ``require_role(["admin", "agent"])` — viewer получает 403` — ✅ — evidence: `api/app.py:2401`, `api/app.py:2426`, `api/app.py:2452`, `api/app.py:2479`
- `275+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Analytics dashboard: topics, resolution rate, cost tracking (task-117)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ❌
- Notes: AN-2 cost tracking не доведён до конца; dashboard есть, но `cost-summary` питается из нулевого `cost_usd`

### Task 118 — weekly quality reports
- Spec: `codex-tasks/Archive/task-118-weekly-quality-reports.md`
- Acceptance criteria:
- ``python scripts/weekly_report.py --tenant TEST --dry-run` печатает markdown` — ✅ — evidence: `scripts/weekly_report.py:51-66`, `scripts/weekly_report.py:72-77`
- `Slack webhook получает сообщение (mocked)` — ✅ — evidence: `scripts/weekly_report.py:29-32`, `tests/test_weekly_report.py:48-88`
- `Email отправляется (mocked SMTP)` — ✅ — evidence: `scripts/weekly_report.py:35-48`, `tests/test_weekly_report.py:48-88`
- `Report содержит сравнение с прошлой неделей (deltas)` — ✅ — evidence: `reports/renderer.py:91-122`, `tests/test_weekly_report.py:9-46`
- `CronJob в Helm, schedule 0 9 * * 1` — ✅ — evidence: `deploy/helm/templates/cronjob-report.yaml:6-17`, `.github/workflows/weekly-report.yml:4-5`
- `280+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Weekly quality report: Slack + email digest (task-118)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ⚠️

### Task 119 — email channel
- Spec: `codex-tasks/Archive/task-119-email-channel.md`
- Acceptance criteria:
- `IMAP mode: mocked mailbox → incoming email → RAG → sent reply` — ❌ — evidence: `scripts/email_poller.py:9-16` запускает `poll_once(_noop_process)` и не связывает poller с QA/reply flow
- `Webhook mode: mocked SendGrid payload → 200 + reply sent` — ⚠️ — evidence: endpoint и helper есть (`api/app.py:2503-2535`, `channels/email_webhook.py:23-37`), но в repo нет end-to-end позитивного webhook-test с reply
- `Low quality → forward to operators (EscalatedTicket created)` — ❌ — evidence: webhook path использует no-op `_forward_message` (`api/app.py:2524-2526`); создание `EscalatedTicket` в email-flow не найдено
- `Tenant resolution по domain работает` — ❌ — evidence: `channels/email_channel.py:39-45` ждёт формат `domain=tenant`, тогда как task-112/settings используют `domain:tenant`
- `Signature verification защищает webhook` — ✅ — evidence: `channels/email_webhook.py:13-20`, `api/app.py:2509-2512`, `tests/test_email_channel.py:86-102`
- `Helm: отдельный deployment для poller` — ✅ — evidence: `deploy/helm/templates/deployment-email-poller.yaml:4-20`
- `285+ passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Email channel: IMAP polling + webhook mode (task-119)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ❌

## Batch E — Code quality (120-122)

### Task 120 — deduplicate root modules
- Spec: `codex-tasks/Archive/task-120-dedup-root-modules.md`
- Acceptance criteria:
- `Анализ завершён, список дублей задокументирован в PR` — ⚠️ — evidence: PR-описание отсутствует в repo snapshot
- `Каждый дубль обработан (moved или kept с обоснованием)` — ❌ — evidence: полноразмерный root `manager.py` всё ещё живёт рядом с `vectordb/manager.py` (`manager.py:1-400+`, `vectordb/manager.py:1-239`)
- `Нет conflicting graph.py и agent/graph.py` — ✅ — evidence: `graph.py:1-12` — deprecation shim
- ``grep "from graph import" .` → 0 hits или всё обновлено` — ❌ — evidence: `tests/test_ollama_timeout.py:10`, `tests/test_ollama_timeout.py:29`, `tests/test_ollama_timeout.py:51`
- `Все тесты проходят после каждого move` — ⚠️ — evidence: sequence of incremental green runs не верифицируется
- `README / CONTRIBUTING содержит секцию Module layout` — ❌ — evidence: в `README.md` секция `Module layout`/аналог не найдена; `CONTRIBUTING` в checked paths отсутствует
- `285+ passed` — ⚠️ — evidence: run отсутствует
- `Commit strategy: one move per commit` — ⚠️ — evidence: commit history не часть этого прохода
- `Финальный commit: "Deduplicate root-level modules: canonical submodule paths (task-120)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ❌
- Notes: graph/state/prompts доведены до shims (`graph.py`, `state.py`, `prompts.py`), но dedup не закрыт на manager-layer

### Task 121 — magic numbers to settings
- Spec: `codex-tasks/Archive/task-121-magic-numbers.md`
- Acceptance criteria:
- `Все Known magic numbers вынесены в settings` — ❌ — evidence: `config/settings.py:126-133` уже хранит defaults, но они не совпадают со spec (`20/5/80/200/50` вместо `5/3/70/80/100`), а `agent_max_tool_loops` и `escalation_threshold` в этом блоке отсутствуют
- `Все test suites проходят с тем же поведением` — ⚠️ — evidence: suite не запускался; drift defaults выше уже ставит поведение под вопрос
- ``.env.example` обновлён с новыми env vars` — ⚠️ — evidence: файл обновлён (`.env.example:16-29`), но значения также ушли от spec (`QUALITY_THRESHOLD=80`, `CHUNK_OVERLAP=200`, `API_DEFAULT_PAGE_SIZE=50`)
- `grep: rrf_k=60 / chunk_size=800 только в settings/tests` — ❌ — evidence: runtime fallback literals остаются в `api/app.py:214-217`; repo grep даёт non-test hits
- `README Configuration ссылается на .env.example как source of truth` — ❌ — evidence: соответствующая секция в `README.md` не найдена
- `285+ passed, ruff clean` — ⚠️ — evidence: run отсутствует
- `Commit: "Extract magic numbers to config/settings.py (task-121)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ❌

### Task 122 — integration tests
- Spec: `codex-tasks/Archive/task-122-integration-tests.md`
- Acceptance criteria:
- `Директория tests/integration/ создана с 6 файлами` — ✅ — evidence: `tests/integration/test_ingestion_flow.py`, `test_conversation.py`, `test_streaming.py`, `test_concurrency.py`, `test_escalation.py`, `test_async_upload.py`
- ``pytest -m integration -q` запускает только integration` — ⚠️ — evidence: marker зарегистрирован (`pyproject.toml:14-17`), scenario files помечены `pytest.mark.integration`, но команда не запускалась
- ``pytest -m "not integration"` запускает unit suite` — ⚠️ — evidence: marker separation есть, но прогон не подтверждён
- `CI workflow имеет job integration-tests с postgres/redis services` — ❌ — evidence: `.github/workflows/ci.yml:9-34` содержит только один job `test`; отдельного `integration-tests` job нет
- `Happy-path E2E зелёный (upload → retrieve → answer)` — ⚠️ — evidence: happy-path test написан (`tests/integration/test_ingestion_flow.py:73-92`), но не исполнялся в этом проходе
- `Escalation E2E: low-quality → EscalatedTicket created` — ⚠️ — evidence: test написан (`tests/integration/test_escalation.py:65-94`), но не исполнялся
- `README updated: Running integration tests` — ❌ — evidence: секция в `README.md` не найдена
- `300+ total passed` — ⚠️ — evidence: run отсутствует
- `Commit: "Integration test suite for E2E flows (task-122)"` — ⚠️ — evidence: commit не верифицируется
- Overall: ❌

## Findings (⚠️/❌ deep-dives)
- `task-104` — accessibility audit не доведён до spec: вместо `axe-core` smoke/audit сейчас только статические HTML/CSS-проверки в `tests/test_a11y.py:17-45`. Suggested fix: добавить реальный `axe` runner и criterion-level coverage на 4 основные страницы.
- `task-106` — similar tickets не semantic: `api/app.py:1840-1849` и `api/app.py:1951-1960` сортируют по времени, а не по embeddings. Suggested fix: вынести similarity в vector/embedding lookup и вернуть `retrieved_docs`/`quality_scores` в detail payload.
- `task-107` — tool-use framework реализован эвристически, а Langfuse не получает `tool_calls` (`agent/tools.py:13-15`, `tracing/langfuse_trace.py:50-82`). Suggested fix: перейти на настоящий tool registry / structured tool trace metadata.
- `task-117` — cost tracking фактически отсутствует: `_load_recent_trace_summaries()` жёстко пишет `cost_usd: 0.0` (`api/app.py:437-492`). Suggested fix: логировать usage metadata на каждый LLM call и читать эти поля в analytics.
- `task-119` — email channel не замкнут end-to-end: IMAP poller — no-op (`scripts/email_poller.py:9-16`), webhook forwarding — no-op (`api/app.py:2524-2526`), tenant mapping использует неправильный delimiter (`channels/email_channel.py:39-45`). Suggested fix: подключить реальный QA/forward pipeline и унифицировать `TENANT_EMAIL_DOMAINS`.
- `task-120` — dedup завершён только для `graph/state/prompts`; root `manager.py` остаётся активным дублем рядом с `vectordb/manager.py`. Suggested fix: либо shim + deprecation, либо перенос callers на tenant-aware manager и удаление legacy implementation.
- `task-121` — settings drifted from task defaults: `config/settings.py:126-133` и `.env.example:16-29` меняют baseline поведения. Suggested fix: вернуть spec-defaults, добавить недостающие settings и дочистить hardcoded fallbacks.
- `task-122` — integration suite не встроен в CI и не задокументирован: `.github/workflows/ci.yml:9-34` без integration job, README без секции запуска. Suggested fix: отдельный `integration-tests` job с services и README section с marker-based commands.
