# План улучшения до коммерческого продукта

> Цель: превратить RAG Support Assistant из MVP (6.9/10) в конкурентоспособный коммерческий продукт (9.0+/10), сравнимый с Intercom Fin, Fini, Ada CX.

## Текущее состояние vs Целевое

| Аспект | Сейчас (6.9) | Цель (9.0+) | Gap |
|--------|-------------|-------------|-----|
| RAG Pipeline | Hybrid search + reranking + Self-RAG | Agentic RAG + Graph RAG + action execution | Средний |
| UX/UI | Функциональный чат, нет citations | Citations, suggested Qs, mobile-first, a11y | Большой |
| Безопасность | API key (broken), нет CORS | SSO, RBAC, SOC2-ready, timing-safe auth | Большой |
| Observability | SQLite traces, custom JSON metrics | OpenTelemetry, Langfuse, Prometheus, eval CI/CD | Средний |
| Deployment | Docker Compose, single-node | K8s-ready, auto-scaling, zero-downtime deploy | Средний |
| Enterprise | Нет multi-tenancy, нет audit | Tenant isolation, audit logs, data retention | Большой |

---

## Phase 0: Security Hardening (неделя 1)

> Блокер для всего остального. Без этого нельзя выкатывать.

- [ ] **SEC-1: Path traversal fix** — `api/app.py:772`, `os.path.basename()` + whitelist расширений → Verify: unit test с `../../etc/passwd` filename возвращает 400
- [ ] **SEC-2: Timing-safe API key** — `hmac.compare_digest()` в `api/app.py:116` → Verify: test проходит, timing одинаков для valid/invalid key
- [ ] **SEC-3: Input validation** — Pydantic `Field(max_length=2000)` для question, `max_length=100` для entity_id → Verify: 400 на oversized input
- [ ] **SEC-4: CORS middleware** — `CORSMiddleware` с configurable `CORS_ORIGINS` env var → Verify: OPTIONS preflight возвращает правильные headers
- [ ] **SEC-5: Bare except cleanup** — все `except Exception: pass` в graph.py → specific handlers + logging → Verify: `grep -r "except Exception" *.py` возвращает 0 bare catches
- [ ] **SEC-6: JS memory leak fix** — event delegation вместо per-button listeners в chat.html → Verify: 100 сообщений не увеличивают listener count

## Phase 1: Фундамент коммерческого продукта (недели 2-4)

### 1.1 Persistent Storage Layer

Заменить in-memory на PostgreSQL + Redis.

- [ ] **DB-1: PostgreSQL для сессий и трейсинга** — заменить SQLite traces + in-memory sessions на PostgreSQL. Схема: `tenants`, `sessions`, `messages`, `traces`, `trace_steps`, `feedback` → Verify: restart приложения → сессии сохраняются
- [ ] **DB-2: Redis для кэширования** — session cache, embedding cache, rate limiter backend (вместо in-memory slowapi) → Verify: Redis restart → app работает (graceful degradation)
- [ ] **DB-3: Alembic миграции** — schema versioning для PostgreSQL → Verify: `alembic upgrade head` из чистой БД создаёт все таблицы
- [ ] **DB-4: docker-compose update** — добавить postgres + redis сервисы → Verify: `docker compose up` поднимает 5 сервисов (ollama, ollama-init, app, postgres, redis)

### 1.2 Authentication & Authorization

- [ ] **AUTH-1: JWT-based authentication** — замена X-API-Key на JWT tokens с refresh. Endpoints: `/api/auth/login`, `/api/auth/refresh`, `/api/auth/logout` → Verify: login → получаем access+refresh tokens → /api/ask с Bearer token работает
- [ ] **AUTH-2: RBAC** — роли `admin`, `agent`, `viewer`. Admin: всё. Agent: /ask, /upload, /feedback. Viewer: /ask only. Таблица `users` + `roles` в PostgreSQL → Verify: viewer получает 403 на /upload
- [ ] **AUTH-3: SSO (SAML/OIDC)** — интеграция с корпоративными IdP через `python-social-auth` или `authlib` → Verify: логин через Google/Azure AD → получаем JWT

### 1.3 Multi-Tenancy

- [ ] **MT-1: Tenant isolation** — `tenant_id` в каждой таблице. Отдельная ChromaDB collection per tenant. Middleware extractит tenant из JWT → Verify: tenant A не видит документы tenant B
- [ ] **MT-2: Tenant-scoped config** — каждый tenant может настроить: LLM model, quality threshold, escalation rules → Verify: tenant A использует qwen2.5, tenant B — llama3

### 1.4 Async Processing

- [ ] **ASYNC-1: Celery + Redis** — task queue для document upload + reindexing. `/api/upload` возвращает `task_id`, клиент poll-ит `/api/tasks/{id}` → Verify: upload 10MB PDF → response за <1s с task_id → polling показывает progress → completion
- [ ] **ASYNC-2: Background jobs** — knowledge base rebuild, evaluation runs, alert checks — всё через Celery tasks → Verify: `celery worker` обрабатывает задачи параллельно

## Phase 2: UX/UI до коммерческого уровня (недели 3-6)

### 2.1 Design System

- [ ] **DS-1: Shared CSS library** — `static/styles/tokens.css` (colors, spacing 4px scale, typography scale, shadows), `static/styles/components.css` (buttons, cards, badges, forms). Все страницы мигрируют на общую систему → Verify: все 8 страниц используют один CSS, нет inline `<style>` blocks >50 строк
- [ ] **DS-2: WCAG AA compliance** — contrast ratios ≥4.5:1, focus indicators, ARIA labels, semantic HTML, keyboard navigation → Verify: axe-core audit показывает 0 critical/serious violations
- [ ] **DS-3: Mobile-first responsive** — breakpoints 480/768/1024px, touch targets ≥44px, viewport meta на всех страницах → Verify: Lighthouse mobile score ≥90

### 2.2 Chat UX (ключевые паттерны коммерческих продуктов)

- [ ] **UX-1: Inline citations** — каждый ответ содержит `[1]`, `[2]` ссылки на source documents. Hover показывает title + excerpt. Click открывает source panel → Verify: ответ из 3 документов показывает 3 numbered citations с корректными ссылками
- [ ] **UX-2: Suggested questions** — после каждого ответа показывать 2-3 кнопки с follow-up вопросами (генерирует LLM) → Verify: каждый ответ сопровождается кликабельными suggested questions
- [ ] **UX-3: "Talk to human" button** — всегда видимая кнопка для эскалации. При клике: confirmation → собирает context → отправляет в escalation sink → показывает "Оператор подключится в течение X минут" → Verify: кнопка видна на каждом экране, эскалация создаёт запись в inbox
- [ ] **UX-4: Message actions** — copy-to-clipboard, retry, expand sources. Timestamps на каждом сообщении → Verify: клик "copy" → текст в буфере обмена
- [ ] **UX-5: Typing indicator + streaming улучшения** — skeleton loader при загрузке страницы, progress bar при upload, debounced textarea resize → Verify: upload 5MB файла показывает progress bar
- [ ] **UX-6: Error recovery** — контекстные error messages с action buttons ("Повторить", "Обратиться к оператору"). Нет silent `catch (_) {}` → Verify: отключить Ollama → пользователь видит "Сервис временно недоступен" + кнопка retry
- [ ] **UX-7: Onboarding** — welcome screen с capabilities overview + sample questions для первого визита → Verify: новый пользователь видит onboarding при первом входе

### 2.3 Agent Copilot (для live-агентов)

- [ ] **COPILOT-1: Agent dashboard** — отдельный UI (`/agent`) для операторов. Список эскалированных тикетов, AI-generated summary, suggested response draft → Verify: оператор видит очередь тикетов с AI-подсказками
- [ ] **COPILOT-2: Context panel** — при обработке тикета агент видит: полную историю чата, retrieved documents, quality scores, similar resolved tickets → Verify: клик на тикет → показывает полный контекст + 3 similar resolved cases

## Phase 3: Advanced RAG & Intelligence (недели 5-8)

### 3.1 Agentic RAG

- [ ] **AGENT-1: Tool-use framework** — LangGraph tools: `search_kb`, `check_order_status`, `reset_password`, `create_ticket`. LLM решает какие tools вызвать → Verify: вопрос "Где мой заказ #123?" → agent вызывает check_order_status(123) → возвращает статус
- [ ] **AGENT-2: Multi-step reasoning** — agent может выполнять цепочку действий: search → verify → act → confirm → Verify: "Смени мой email на new@example.com" → agent проверяет auth → обновляет → подтверждает
- [ ] **AGENT-3: Action confirmation** — перед необратимыми действиями AI запрашивает confirmation у пользователя → Verify: "Удали мой аккаунт" → "Вы уверены? Это действие необратимо" → user confirms → action

### 3.2 Retrieval Quality

- [ ] **RQ-1: Langfuse integration** — трейсинг каждого LLM call с cost tracking, latency breakdown per node → Verify: Langfuse dashboard показывает pipeline traces
- [ ] **RQ-2: Evaluation CI/CD** — test suite из 50+ golden Q&A пар. CI gate: context_precision ≥0.8, faithfulness ≥0.85, answer_relevance ≥0.8 → Verify: PR с ухудшением retrieval блокируется CI
- [ ] **RQ-3: Auto-eval pipeline** — nightly job: RAGAS evaluation на production traces, drift detection, alert если метрики падают → Verify: cron job → evaluation results → Slack alert при drift
- [ ] **RQ-4: Knowledge gap detection** — анализ "I don't know" ответов → автоматическое создание тикетов на расширение KB → Verify: 10 "не знаю" по одной теме → автоматический тикет "Дополнить KB по теме X"

### 3.3 Активация disabled features

- [ ] **FEAT-1: Semantic chunking ON** — включить `RAG_SEMANTIC_CHUNKING=true` по умолчанию, т.к. даёт +80% faithfulness → Verify: A/B тест показывает улучшение метрик
- [ ] **FEAT-2: HyDE ON** — включить `RAG_HYDE=true` для улучшения retrieval на коротких запросах → Verify: recall@5 улучшается на коротких запросах
- [ ] **FEAT-3: Contextual headers** — активировать `add_contextual_headers()` для обогащения чанков → Verify: retrieved chunks содержат document-level context

## Phase 4: Enterprise-Ready (недели 7-10)

### 4.1 Observability

- [ ] **OBS-1: OpenTelemetry** — замена SQLite tracing на OTel SDK. Traces → Jaeger/Tempo. Metrics → Prometheus → Grafana → Verify: Grafana dashboard с 10+ панелями (latency, throughput, error rate, quality scores)
- [ ] **OBS-2: Prometheus /metrics** — стандартный endpoint для scraping. `rag_request_duration_seconds`, `rag_quality_score`, `rag_escalation_total`, `rag_retrieval_precision` → Verify: `curl /metrics` возвращает Prometheus format
- [ ] **OBS-3: Alertmanager rules** — замена scripts/check_alerts.py на Prometheus Alertmanager с routing в Slack/PagerDuty → Verify: quality drop → alert в Slack за <5 min

### 4.2 Security & Compliance

- [ ] **COMP-1: Audit logging** — все user actions, admin actions, AI decisions логируются в отдельную audit таблицу (immutable, append-only) → Verify: любое действие → запись в audit log с who/what/when
- [ ] **COMP-2: PII redaction** — автоматическое обнаружение и маскирование email, телефон, паспорт, ИНН в логах и traces → Verify: лог с email показывает `***@***.com`
- [ ] **COMP-3: Data retention policy** — configurable TTL на traces, sessions, feedback. Auto-cleanup job → Verify: traces старше 90 дней автоматически удаляются
- [ ] **COMP-4: Encryption at rest** — PostgreSQL с `pgcrypto`, ChromaDB data directory encrypted → Verify: прямой доступ к файлам БД не показывает plaintext данные

### 4.3 Deployment & Scaling

- [ ] **DEPLOY-1: Kubernetes manifests** — Helm chart для deployment: app (HPA 2-8 pods), PostgreSQL (StatefulSet), Redis (Sentinel), Ollama (GPU node) → Verify: `helm install` → все pods running → health checks green
- [ ] **DEPLOY-2: CI/CD pipeline** — GitHub Actions: lint → test → eval gate → build image → canary deploy (10% traffic) → full rollout → Verify: PR merge → auto-deploy за <10 min
- [ ] **DEPLOY-3: Zero-downtime deploys** — rolling update strategy, readiness/liveness probes, graceful shutdown (drain connections) → Verify: deploy во время load test → 0 dropped requests

## Phase 5: Product Differentiation (недели 9-12)

### 5.1 Knowledge Management

- [ ] **KM-1: Knowledge Builder** — AI автоматически генерирует KB-статьи из resolved тикетов. Agent review → publish → Verify: 10 resolved тикетов по одной теме → AI предлагает draft KB-статьи
- [ ] **KM-2: Knowledge freshness** — мониторинг актуальности документов. Alert если документ не обновлялся >90 дней и часто цитируется → Verify: старый документ → warning в admin panel
- [ ] **KM-3: Auto-categorization** — автоматическая классификация документов по topics при загрузке → Verify: upload "Политика возврата" → auto-tagged category: "Returns & Refunds"

### 5.2 Analytics & Insights

- [ ] **AN-1: Conversation analytics** — dashboard: top topics, resolution rate by topic, avg quality by topic, sentiment trend → Verify: admin видит "Top 10 тем за неделю" с resolution rate
- [ ] **AN-2: Cost tracking** — стоимость каждого запроса (LLM tokens + embedding + compute). Dashboard с cost/resolution → Verify: каждый trace содержит `cost_usd` field
- [ ] **AN-3: Quality reports** — еженедельный автоматический отчёт: resolution rate, CSAT proxy, top failure topics, KB gap analysis → Verify: email/Slack report каждый понедельник

### 5.3 Multi-Channel

- [ ] **MC-1: Email channel** — приём вопросов через email (IMAP polling или webhook). Ответ отправляется reply-to → Verify: email → AI answer → reply в inbox за <2 min
- [ ] **MC-2: Telegram bot** — `/ask` command → RAG pipeline → ответ в чат. Inline citations → Verify: Telegram message → bot ответ с sources
- [ ] **MC-3: Widget embed** — `<script>` snippet для встраивания чат-виджета на любой сайт (iframe + postMessage API) → Verify: виджет на тестовом сайте работает, sends/receives через API

---

## Метрики успеха

| Метрика | Сейчас | Цель Phase 2 | Цель Phase 5 |
|---------|--------|-------------|-------------|
| Resolution Rate | ~30%* | 50% | 70%+ |
| Avg Quality Score | ~65* | 75 | 85+ |
| Escalation Rate | ~35% | 25% | <15% |
| p95 Latency | ~10s* | <5s | <3s |
| Lighthouse Mobile | ~40* | 80 | 95+ |
| WCAG Violations | 10+ critical | 0 critical | 0 |
| Hallucination Rate | unknown | <10% | <3% |
| Test Coverage | ~30% | 70% | 90%+ |

*оценочные значения на основе аудита кода

---

## Технологический стек (целевой)

```
Frontend:     React/Next.js (SPA) + Tailwind CSS + shadcn/ui
Backend:      FastAPI + Celery + PostgreSQL + Redis
RAG:          LangGraph + ChromaDB/Qdrant + BGE-M3 + Cross-Encoder
LLM:          Ollama (local) + OpenAI/Anthropic fallback (cloud)
Observability: OpenTelemetry + Langfuse + Prometheus + Grafana
Auth:         JWT + OIDC/SAML (authlib)
Deployment:   Docker → Kubernetes (Helm)
CI/CD:        GitHub Actions + eval gates + canary deploys
```

## Timeline

```
Week  1     ████ Phase 0: Security Hardening
Week  2-4   ████████████ Phase 1: Foundation (DB, Auth, Multi-tenancy, Async)
Week  3-6   ████████████████ Phase 2: UX/UI Commercial Grade
Week  5-8   ████████████████ Phase 3: Advanced RAG & Intelligence
Week  7-10  ████████████████ Phase 4: Enterprise-Ready
Week  9-12  ████████████████ Phase 5: Differentiation
```

> Фазы частично перекрываются — параллельная работа frontend/backend.

## Done When

- [ ] Resolution rate ≥50% на production трафике
- [ ] 0 critical security vulnerabilities (OWASP Top 10)
- [ ] Lighthouse mobile ≥90, WCAG AA pass
- [ ] Multi-tenant deployment с 2+ tenants
- [ ] CI/CD с eval gate блокирует деградацию
- [ ] Kubernetes deployment в production
