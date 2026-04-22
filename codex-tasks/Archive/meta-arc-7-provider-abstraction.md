# Meta-task — Arc 7 / Batch G: Provider abstraction

## Goal
Сам спланируй и реализуй всю arc 7 batch G, тематика — provider abstraction (Claude/Gemini/OpenAI/Ollama как взаимозаменяемые backends + cost accounting + benchmarking через curated dataset). Работай по тому же паттерну, что закрывал batch F: arc proposal → orchestrator → task specs → implementation → verification → commits → archive → CHANGELOG.

## Context
- Repo: `D:\RAG_Support_Assistant`, HEAD `eaca882`, 393 passing, ruff clean.
- Arc 6 batch F полностью закрыт 2026-04-22: review queue, curated dataset, experiment registry + ContextVar routing, regression runner, online evaluators, improvement backlog, threshold recs, offline review export. Дала foundation для провайдер-бенчмарка.
- Текущее LLM-слой: `agent/graph.py:205` — `Ollama` из `langchain_community.llms` (с deprecation warning на `langchain_ollama.OllamaLLM`). Model routing (fast/strong) через `MODEL_ROUTING_ENABLED`, task-97.
- Cost tracking: частичное — `traces.cost_usd`, migration `011_trace_costs`. task-130 fix закрыл расчёт для analytics dashboard. Но per-provider pricing tables нет.
- Experiment registry: `evaluation/experiment_schema.py` + `agent/prompt_registry.py` + `CURRENT_EXPERIMENT` ContextVar. Experiments могут overriding'ить settings и prompts — поле для provider override тоже сюда ложится.
- Regression runner: `scripts/regression_eval.py` — baseline vs candidate. Идеальная точка для benchmarking разных провайдеров на одном curated dataset.
- User: Julia Edomskikh, Russian-speaking, single-user local Max 5x setup, CC+CX workflow.

## Arc 7 scope (что делать)
Определи сам точный scope, но отталкивайся от этого skeleton'а:

### Batch G — Provider abstraction (первый батч arc 7)
1. **Provider registry** — `config/providers.yml` с Claude/Gemini/OpenAI/Ollama entries, pricing tables (input/output $/1M tokens), rate limits, default models per tier (fast/strong), capabilities (supports_tool_use/structured_output/vision). Pydantic schema в `config/provider_schema.py`. Loader читает при старте.
2. **Provider abstraction layer** — унифицированный `LLMProvider` interface в `llm/providers/` с реализациями `OllamaProvider`, `ClaudeProvider`, `OpenAIProvider`, `GeminiProvider`. Common API: `generate(messages, tools, ...) -> LLMResponse`. Existing `agent/graph.py` Ollama wrapper мигрирует под эту абстракцию.
3. **Cost accounting** — per-token pricing из registry применяется к каждому `LLMResponse`, кладётся в `traces.cost_usd` с breakdown по provider. Прометей-метрика `llm_cost_usd_total{provider,model,tenant}`. Migration если нужен новый столбец для provider attribution.
4. **Provider benchmark** — расширение `scripts/regression_eval.py` для candidate = provider/model pair (не только prompt override). Отчёт сравнивает quality + latency + cost + refusal rate через online evaluators. **Важно**: по умолчанию benchmark работает на **mock LLM** (seeded responses из curated dataset answers), чтобы не жечь paid API случайно в CI. Реальный benchmark — через явный CLI-флаг `--allow-paid-apis`.
5. **Routing profiles** — experiment overrides с профилями: `quality-first` (Claude Sonnet), `cost-first` (Claude Haiku/Gemini Flash), `latency-first` (Ollama local). Profile selection через experiment YAML, применяется к pipeline в runtime через `CURRENT_EXPERIMENT`.
6. **API key management** — keys ТОЛЬКО через env vars (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`). В `.env.example` placeholders вида `changeme`. В `config/settings.py` raise при missing env если profile требует платного провайдера. Fail-fast валидация на старте.
7. **Admin UI** — в `static/admin.html` новый tab "Providers" со списком configured providers, текущими rate-limit usage'ами, last successful call timestamp. RBAC admin.
8. **Migrations** — 015 если нужна новая таблица (например `provider_calls` для audit). Решай сам по spec-у.

## CRITICAL SAFEGUARDS (не нарушать)
- **Никогда не коммитить реальные API keys.** `.env.example` — только `changeme` placeholders. `config/providers.yml` — только metadata (pricing/limits), без keys.
- **Никогда не делать paid API calls в тестах.** Все провайдер-тесты — через mock LLM (см. существующий паттерн в `test_regression_runner.py`). CI job `regression-eval` не должна иметь `--allow-paid-apis`.
- **Benchmark по умолчанию mock.** Phrase `LLM_BENCHMARK_ALLOW_PAID_APIS` env var — дефолт false.
- **Cost guardrails**: добавить `daily_cost_limit_usd` в settings (default 5.0). При превышении — fail-fast для платных провайдеров.
- **Tenant-scoped provider override**: enterprise tenants могут указать свой provider. Hardcoded `allowed_providers` в tenant metadata.

## Deliverables (что должно быть после твоей работы)

### Documents
1. `codex-tasks/arc-7-proposal.md` — аналогично `arc-6-proposal.md`: 3 candidate batches (G/H/I) с recommendation. G = provider abstraction (detailed), H = continuous learning Phase 2 (deferred пока нет traffic), I = production backup/restore/chaos (deferred — runbook уже есть).
2. `codex-tasks/orchestrator-batch-g-provider-abstraction.md` — граф зависимостей, round-по-round исполнение (аналогично batch F orchestrator).
3. `codex-tasks/task-143-*.md` ... `task-149-*.md` (или сколько deliverables получится) — самодостаточные specs в формате batch F (Goal / Context / Deliverables / Acceptance / Notes).

### Code
- `config/providers.yml`, `config/provider_schema.py`
- `llm/providers/__init__.py` + per-provider modules
- `evaluation/provider_benchmark.py` (или расширение `regression_eval.py`)
- Миграции если нужны
- Изменения в `agent/graph.py`, `api/app.py`, `config/settings.py`, `monitoring/prometheus.py`, `static/admin.html`
- Tests — по одному файлу на task (test_provider_registry.py, test_provider_abstraction.py, etc.)
- `deploy/helm/templates/` — cronjobs если нужны

### Closure
- Verification sweep per task (acceptance criteria → реальные проверки).
- Per-task commit (НЕ batch-mega-коммит — легче bisect, особенно если что-то сломается).
- Archive specs в `codex-tasks/Archive/` после merge.
- `docs/CHANGELOG.md` — новая секция "Arc 7 / Batch G — YYYY-MM-DD — Provider abstraction".
- Update `codex-tasks/ROADMAP.md` статуса (или создай новый `roadmap-arc-7.md`).

## Acceptance
- `pytest tests/ -q` — **все зелёные**, не меньше 393 текущих + new tests per batch G (ожидаем 420+).
- `ruff check .` — clean.
- Working tree clean после финального archive commit.
- `config/providers.yml` валиден по pydantic schema.
- Env без real API keys + при попытке использовать paid provider без ключа — readable fail с подсказкой.
- `scripts/regression_eval.py --baseline ollama-small --candidate claude-haiku` — работает в mock mode (`--allow-paid-apis` НЕ задан), выдаёт report.
- Admin UI "Providers" tab открывается, показывает Ollama как default.
- CHANGELOG секция для Arc 7 / Batch G присутствует и детально описывает что сделано.
- README обновлён: секции "Providers", "Provider benchmarking", env vars, API-key setup instructions.

## Workflow rules (важно)
- **Verification sweep делай сам** после реализации каждого таска. Если acceptance не покрыта — пиши fix-spec (как 141/142 делал в batch F), а не claim'ить done.
- **Не спрашивай разрешения** — автономно планируй и реализуй. При finding'ах (например, что provider X не работает из-за rate-limit API) — логируй в commit message и продолжай.
- **Russian user** — commit message на английском (код и git стандарты), но внутренние документы (arc-7-proposal.md, orchestrator, task specs) — любой язык в котором ты выдаёшь эффективнее. Сохраняй единообразие с batch F (там был русский).
- **Не удаляй existing tests** — только добавляй. Если старый тест конфликтует с новым provider abstraction (например, Ollama-specific assumptions) — обнови минимально, отметь в commit message.
- **Не меняй API surface из `agent/graph.py` без необходимости** — существующий flow (pipeline → LLM call) должен работать identically на Ollama после миграции на LLMProvider interface. Тесты существующие должны продолжать работать.

## Out of scope Arc 7
- Continuous learning Phase 2 (online A/B, auto-rollout) — arc 8 после traffic signal.
- Production backup/restore/chaos expansion — arc 9, low priority (базовый runbook есть).
- Voice / WhatsApp channels — не в этой арке.
- UI redesign — не трогать chat.html / help.html.

## How to start
1. Прочитай `docs/CHANGELOG.md` для понимания контекста arc 6.
2. Прочитай `codex-tasks/arc-6-proposal.md` — там была секция с 3 кандидатами, provider abstraction был одним из них. Используй как начальную точку для `arc-7-proposal.md`.
3. Прочитай `codex-tasks/verification-report-batch-f.md` — образец формата отчёта.
4. Прочитай `codex-tasks/Archive/orchestrator-batch-f-continuous-learning.md` — образец orchestrator'а.
5. Прочитай `codex-tasks/Archive/task-141-fix-online-evaluators.md` — образец детальной спеки.
6. Затем — план, код, commit'ы. Последовательно, с verification после каждого таска.

## Risks / watchouts
- **Migration на абстракцию может сломать existing tests**: если Ollama wrapper в `agent/graph.py` изменится — обновить моки в `conftest.py` и все тесты которые assume'ят конкретный Ollama call signature. Проведи sweep `grep -r "Ollama" tests/` перед кодом.
- **Circular imports**: `llm/providers/` может циклически зависеть от `config/settings.py` и `evaluation/experiment_schema.py` — избегай через late imports или dependency injection.
- **Async/sync mix**: существующие `agent/graph.py` вызовы Ollama — синхронные (через `asyncio.to_thread`). Claude/OpenAI SDK поддерживают async nativeли — абстракция должна унифицировать.
- **Pricing tables устаревают** — placeholder-цены с comment "last updated YYYY-MM-DD" + документация в README как обновлять.
- **Не забывай про multi-tenancy** — provider selection tenant-aware, иначе enterprise tenants сломаются.

---

**Если этот meta-file тебе достаточно для автономной работы — начинай. Если critical gap в ТЗ — задай ОДИН вопрос и продолжай.**
