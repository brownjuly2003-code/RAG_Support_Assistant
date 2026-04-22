# Meta-task — Arc 7 / Batch H: GraceKelly + Mistral providers, drop paid APIs

## Goal
Сам спланируй и реализуй arc 7 batch H — дополнить provider abstraction (из batch G) **GraceKelly-бэкендом для локального использования** и **Mistral direct API для внешнего деплоя/fallback**, и **удалить неактивные Claude/OpenAI/Gemini** провайдеры как dead code (у пользователя нет денег на их API, GraceKelly уже orchestrator'ит Claude/GPT/Gemini через Perplexity Pro). Работай по паттерну batch G: meta → proposal update → orchestrator → task specs → implementation → verification → commits → archive → CHANGELOG.

## Context

### Почему этот batch
Batch G (закрыт 2026-04-22, HEAD `73dc418`) реализовал provider abstraction с 4 backends: Ollama (local), Claude, OpenAI, Gemini (paid direct APIs). Пользователь (Julia) прояснил что:
1. **Денег на Claude/OpenAI/Gemini нет** — paid API keys не будут использоваться.
2. **Локальный оркестратор уже есть** — отдельный проект **GraceKelly** (`D:\GraceKelly\`), FastAPI на порту 8011, оркестрирует 10+ моделей через Perplexity Pro-подписку + direct Mistral API + direct Anthropic/OpenAI API (через свои ключи в GraceKelly).
3. **Mistral direct API** нужен как **страховка** (когда GraceKelly недоступен — chrome-profile не залогинен, перплексити down) и для **внешнего использования** (deploy где GraceKelly нет).

### Текущее состояние RAG_Support_Assistant
- HEAD `73dc418`, 412 tests passing, ruff clean.
- Provider abstraction: `llm/providers/{base,ollama,anthropic,openai,gemini,runtime}.py`, `config/providers.yml`, `config/provider_schema.py`.
- Default profile `latency-first` = Ollama only; `cost-first`/`quality-first` использует paid-модули (недоступно пользователю).
- Model routing (classify_complexity → fast/strong) через `MODEL_ROUTING_ENABLED`, работает с provider-runtime (`build_provider_runtime` в `llm/providers/runtime.py`).
- Mistral API key уже записан в `.env` (`MISTRAL_API_KEY=...`). Ключ валиден (tested: `ministral-3b-latest` → 200 OK).

### GraceKelly API contract (для реализации GraceKellyProvider)

**Base URL**: `http://127.0.0.1:8011` (configurable через env `GRACEKELLY_BASE_URL`).

**Auth**: опциональный. Если GraceKelly запущен с `GRACEKELLY_API_KEY` — нужен header `Authorization: Bearer <key>` ИЛИ `X-API-Key: <key>`. Если без ключа — endpoints open. Public paths (без auth): `/health`, `/healthz/live`, `/healthz/ready`, `/docs`, `/openapi.json`, `/redoc`.

**Health check**: `GET /healthz/ready` — 200 если ready, 503 если не готов (для fallback detection).

**Main endpoint — single-prompt auto-routing**:
```
POST /api/v1/smart
Content-Type: application/json
Authorization: Bearer <gracekelly_api_key>   # optional

Request body:
{
  "prompt": "text, 1..40000 chars",
  "model": "mistral-small",             # default; см. доступные ниже
  "reliability_level": "quick",          # quick=1 call, standard=2-3 consensus, high=more
  "pattern": null,                       # optional, explicit pattern override
  "dry_run": false
}

Response body:
{
  "answer": "text",
  "task_type": "...",
  "complexity_level": "...",
  "pattern_used": "...",
  "reliability_level": "quick",
  "was_decomposed": false,
  "used_consensus": false,
  "used_roles": false,
  "total_llm_calls": 1,
  "model_id": "mistral-small"
}

Errors: 400 invalid params, 401 auth, 5xx server.
```

**Available models в GraceKelly** (из `D:\GraceKelly\src\gracekelly\core\models.py`):
- `mistral-small` → provider mistral, `mistral-small-latest` (default)
- `gpt-5-4-api` → provider openai, `gpt-5.4` (direct API через GraceKelly's own OpenAI key)
- `claude-sonnet-4-6-api` → provider anthropic, `claude-sonnet-4-6-20250514`
- Browser-based (через Perplexity): `claude-sonnet-4-6`, `gpt-5-4`, `gemini-3-1-pro`, `claude-opus-4-6`

**Для RAG_Support_Assistant integration** — использовать `mistral-small` как fast и `claude-sonnet-4-6-api` (или `mistral-small` дважды) как strong. GraceKelly сам ведёт cost tracking для своих paid API вызовов — на стороне RAG_Support_Assistant не нужно cost-attributить GraceKelly calls (воспринимаем как "прокси", cost = 0 в наших traces).

### Mistral direct API contract

**Base URL**: `https://api.mistral.ai/v1`.

**Auth**: `Authorization: Bearer $MISTRAL_API_KEY`.

**Endpoint**: `POST /chat/completions` (OpenAI-compatible schema).

**Модели (цены input/output per 1M tokens на 2026-04-22)**:
- `ministral-3b-latest` — $0.04/$0.04 (super cheap)
- `ministral-8b-latest` — $0.10/$0.10
- `mistral-small-latest` — $0.20/$0.60
- `mistral-medium-latest` — $2.75/$8.10
- `mistral-large-latest` — $3.00/$9.00
- `codestral-latest` — $0.30/$0.90

**Free tier**: 1 req/sec, ~500k tokens/мес на `ministral-*` и `mistral-small`. Достаточно для проверки.

**Rate-limit headers**: Mistral возвращает `x-ratelimit-*` — имеет смысл читать и соответствовать.

Request/response format идентичен OpenAI — можно клонировать `llm/providers/openai.py` и менять base URL + auth env name.

## Batch H scope (три tasks)

### task-150 — Mistral direct API provider
**Why**: fallback для GraceKelly (когда down) + external deploy где GraceKelly нет. Дешёвый paid provider с free tier.

**Deliverables:**
1. `llm/providers/mistral.py` — клон anthropic.py по pattern, endpoint `https://api.mistral.ai/v1/chat/completions`, env `MISTRAL_API_KEY`. Параметры: `model_name`, `input_price_per_1m_tokens`, `output_price_per_1m_tokens`, `timeout_sec`, `api_key_env`. Token usage из response `usage.{prompt_tokens,completion_tokens}`, cost_usd калькуляция как везде.
2. `llm/providers/runtime.py` — добавить `elif provider_id == "mistral": provider = MistralProvider(...)`.
3. `config/providers.yml` — новый `providers[]` entry:
   ```yaml
   - id: mistral
     label: Mistral
     kind: paid
     enabled: true
     api_key_env: MISTRAL_API_KEY
     default_models:
       fast: ministral-3b-latest
       strong: mistral-small-latest
     capabilities:
       supports_tool_use: true
       supports_structured_output: true
       supports_vision: false
     rate_limits:
       requests_per_minute: 60
       tokens_per_minute: 500000
     models:
       - name: ministral-3b-latest
         aliases: [ministral-3b, mistral-tiny]
         input_price_per_1m_tokens: 0.04
         output_price_per_1m_tokens: 0.04
       - name: ministral-8b-latest
         aliases: [ministral-8b]
         input_price_per_1m_tokens: 0.10
         output_price_per_1m_tokens: 0.10
       - name: mistral-small-latest
         aliases: [mistral-small]
         input_price_per_1m_tokens: 0.20
         output_price_per_1m_tokens: 0.60
   ```
4. `.env.example` — `MISTRAL_API_KEY=changeme # get at https://console.mistral.ai/`.
5. `tests/test_mistral_provider.py` — 4+ тестов: instantiation without key raises, mock HTTP call returns LLMResponse с правильными input/output_tokens/cost_usd, rate-limit error mapped в retryable.
6. README section "Mistral provider" (как Ollama section).

**Acceptance**: `pytest tests/test_mistral_provider.py` зелёный, ruff clean, no paid calls в тестах (использовать `httpx_mock` или равнозначное).

### task-151 — GraceKelly provider + failover chain
**Why**: главный local-but-external оркестратор через Perplexity Pro. Решает проблему "как получить Claude Sonnet ответ без отдельной Anthropic подписки".

**Deliverables:**
1. `llm/providers/gracekelly.py` — новый provider. Отличается от direct-API провайдеров:
   - Base URL конфигурируется через env `GRACEKELLY_BASE_URL` (default `http://127.0.0.1:8011`).
   - Auth через `GRACEKELLY_API_KEY` env — если set, добавляет `Authorization: Bearer`. Если не set — запросы без auth (GraceKelly допускает это).
   - POST `/api/v1/smart` с payload `{prompt, model, reliability_level: "quick", dry_run: false}`. `model` берётся из model_name абстракции.
   - Response parsing: `answer` → LLMResponse.text, `total_llm_calls` → metadata, `model_id` → model. `cost_usd=0.0` (GraceKelly сам ведёт учёт, мы не атрибутируем его costs на стороне RAG).
   - `supports_tool_use=False`, `supports_structured_output=False`, `supports_vision=False` (simple endpoint).
   - Health pre-check: перед первым вызовом (lazy) делать `GET /healthz/ready`; если 5xx/timeout — raise `ProviderUnavailable` (new exception класс в `base.py`).
2. **Failover chain** (новое поведение в `llm/providers/runtime.py`):
   - Settings: `failover_chain_enabled: bool = True` default.
   - Profile `gracekelly-primary` (см. task-152) указывает primary=GraceKelly + `fallback=ollama`. Если primary raise `ProviderUnavailable` (health check провалился или request timeout >10s) — runtime автоматически перестраивается на fallback provider для этого запроса. Fallback кеширется на 5 минут (не перепроверяем health каждый вызов).
   - Metric: counter `llm_provider_fallback_total{from_provider,to_provider,reason}`.
3. `config/providers.yml` — добавить:
   ```yaml
   - id: gracekelly
     label: GraceKelly local orchestrator
     kind: local   # не charging, локальный прокси
     enabled: true
     api_key_env: GRACEKELLY_API_KEY   # optional
     default_models:
       fast: mistral-small
       strong: claude-sonnet-4-6-api
     capabilities:
       supports_tool_use: false
       supports_structured_output: false
       supports_vision: false
     rate_limits:
       requests_per_minute: 0    # локальный, limit через GraceKelly
       tokens_per_minute: 0
     models:
       - name: mistral-small
         aliases: [gk-mistral, gk-fast]
         input_price_per_1m_tokens: 0.0
         output_price_per_1m_tokens: 0.0
       - name: claude-sonnet-4-6-api
         aliases: [gk-claude-sonnet, gk-strong]
         input_price_per_1m_tokens: 0.0
         output_price_per_1m_tokens: 0.0
       - name: gpt-5-4-api
         aliases: [gk-gpt-5]
         input_price_per_1m_tokens: 0.0
         output_price_per_1m_tokens: 0.0
   ```
4. `.env.example`:
   ```
   GRACEKELLY_BASE_URL=http://127.0.0.1:8011
   GRACEKELLY_API_KEY=   # optional, if GraceKelly deployed with auth
   ```
5. `config/settings.py` — добавить `gracekelly_base_url`, `gracekelly_api_key_env`, `gracekelly_health_check_timeout_sec=2.0`, `gracekelly_request_timeout_sec=30.0`, `failover_chain_enabled=True`, `failover_fallback_cache_seconds=300`.
6. `monitoring/prometheus.py` — `llm_provider_fallback_total{from_provider,to_provider,reason}` counter.
7. `tests/test_gracekelly_provider.py` — 6+ тестов: health check success/failure, request success with mocked HTTP, API key optional header presence, unavailable raises ProviderUnavailable, model alias resolution, cost=0.0 always.
8. `tests/test_failover_chain.py` — 4+ тестов: failover triggers on ProviderUnavailable, cached for 5 min, metric increments, fallback-of-fallback не происходит (chain depth = 1).
9. README section "GraceKelly provider" — как запустить GraceKelly локально + failover explanation.

**Acceptance**: `pytest tests/test_gracekelly_provider.py tests/test_failover_chain.py` зелёный, ruff clean, **никаких реальных HTTP calls к GraceKelly в тестах** (mock через `httpx_mock` или равнозначное).

### task-152 — Routing profiles revamp + cleanup paid providers
**Why**: существующие profiles `cost-first` и `quality-first` указывают на недоступные paid providers. Плюс Claude/OpenAI/Gemini модули — dead code для этого пользователя.

**Deliverables:**
1. **Обновить `config/providers.yml`** — routing profiles:
   ```yaml
   default_profile: local-first
   
   routing_profiles:
     local-first:
       description: Local-only Ollama routing, zero paid spend (default).
       fast:
         provider: ollama
         model: qwen2.5:7b
       strong:
         provider: ollama
         model: qwen2.5:7b
   
     gracekelly-primary:
       description: GraceKelly orchestrator for both tiers (Perplexity Pro-backed), with Ollama fallback on failure.
       fast:
         provider: gracekelly
         model: mistral-small
       strong:
         provider: gracekelly
         model: claude-sonnet-4-6-api
       fallback:
         provider: ollama
         model: qwen2.5:7b
   
     external-mistral:
       description: Direct Mistral API for external deployments without GraceKelly; cheap, dependable, no local orchestrator dependency.
       fast:
         provider: mistral
         model: ministral-3b-latest
       strong:
         provider: mistral
         model: mistral-small-latest
   ```
   **Удалить** `cost-first` и `quality-first` профили.
2. **Удалить провайдеры Claude/OpenAI/Gemini**:
   - Удалить `llm/providers/anthropic.py`, `llm/providers/openai.py`, `llm/providers/gemini.py`.
   - Удалить их `providers[]` entries в `config/providers.yml`.
   - Удалить связанные env vars в `.env.example` (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`).
   - Обновить `llm/providers/runtime.py` — убрать импорты и `elif` branches.
   - Обновить `llm/providers/__init__.py`.
3. **Тесты** — удалить/обновить тесты которые assert'ят на Claude/OpenAI/Gemini в `tests/test_provider_registry.py`, `tests/test_provider_abstraction.py`, `tests/test_provider_benchmark.py`, `tests/test_provider_graph_integration.py`. Заменить на Mistral/GraceKelly assertions где нужно.
4. **Scripts/regression_eval.py** — если упоминал claude/openai/gemini aliases, заменить на mistral/ollama/gracekelly.
5. **Admin surface (api/app.py + static/admin.html)** — если Providers tab hard-code'ит Claude/OpenAI/Gemini labels, сделать generic (читать из registry).
6. **README + .env.example + docs/CHANGELOG.md** — вычистить упоминания Claude/OpenAI/Gemini, заменить на Mistral/GraceKelly где релевантно. ROADMAP обновить статус.
7. **CHANGELOG** — новая секция `## [Arc 7 / Batch H] — YYYY-MM-DD — GraceKelly + Mistral providers`.

**Acceptance**: полный `pytest tests/ -q` зелёный (включая все тесты из batch G которые не удалены); ruff clean; `default_profile=local-first` работает с Ollama без API keys; `external-mistral` профиль с `MISTRAL_API_KEY` set — работает против real Mistral API (но тестировать без paid calls через mock).

## CRITICAL SAFEGUARDS (не нарушать)

- **Mistral API key уже в `.env`** — не трогать его, не переписывать `.env.example` с реальным ключом. В `.env.example` только `changeme` placeholder.
- **No paid API calls в тестах** — всё через mock (`httpx_mock`, `respx`, или равнозначное). `test_mistral_provider.py` не должен делать real Mistral calls.
- **No GraceKelly real calls в тестах** — mock HTTP. CI не зависит от running GraceKelly instance.
- **Placeholder fail-fast сохранить** — `MISTRAL_API_KEY=changeme` treated как missing; если profile `external-mistral` selected и ключ placeholder → raise при startup с readable error.
- **Cost guardrail `daily_cost_limit_usd` расширить на Mistral** — если daily spend через Mistral > limit, fail-fast для `external-mistral` profile. GraceKelly cost не атрибутируется.
- **Failover chain only for local-fallback** — если primary=GraceKelly fails → fallback=Ollama. НЕ fallback на paid Mistral автоматически (это осознанный выбор пользователя, не silent spend).

## Deliverables (что должно быть после твоей работы)

### Documents
1. Обновить `codex-tasks/arc-7-proposal.md` — добавить секцию "Batch H closed, next candidates" с списком потенциальных batch I (continuous learning Phase 2, backup/restore, и т.п.).
2. `codex-tasks/orchestrator-batch-h-gracekelly-mistral.md` — граф зависимостей (task-150, 151, 152).
3. `codex-tasks/task-150-mistral-provider.md`, `codex-tasks/task-151-gracekelly-provider-and-failover.md`, `codex-tasks/task-152-routing-profiles-and-cleanup.md` — детальные spec'и (можешь клонировать содержимое из этой meta в отдельные файлы для archival).

### Code
- `llm/providers/mistral.py` (new)
- `llm/providers/gracekelly.py` (new)
- `llm/providers/anthropic.py`, `openai.py`, `gemini.py` — УДАЛИТЬ
- Изменения в `llm/providers/runtime.py`, `llm/providers/__init__.py`, `llm/providers/base.py` (+ProviderUnavailable exception)
- Изменения в `config/providers.yml`, `config/settings.py`, `.env.example`
- Изменения в `api/app.py`, `static/admin.html`, `monitoring/prometheus.py`, `scripts/regression_eval.py`
- Tests: `test_mistral_provider.py`, `test_gracekelly_provider.py`, `test_failover_chain.py` (new); обновления в существующих provider-тестах

### Closure
- Verification sweep per task.
- Per-task commit.
- Archive specs в `codex-tasks/Archive/`.
- CHANGELOG section для Arc 7 / Batch H.
- Update ROADMAP.

## Acceptance
- `pytest tests/ -q` — **все зелёные**, не меньше 412 - удалённые тесты + new tests (реалистично ~420-430).
- `ruff check .` — clean.
- Working tree clean после финального archive commit.
- `default_profile=local-first` и Ollama-flow работают как до batch H (sanity).
- `gracekelly-primary` профиль при running GraceKelly (manual smoke) — real request к `/api/v1/smart` возвращает answer.
- `external-mistral` профиль при set'е Mistral key — один real manual smoke (не в CI, вручную): `python -c "from llm.providers.runtime import build_provider_runtime; ..." → ответ от Mistral`.
- README, CHANGELOG, ROADMAP синхронизированы.

## Workflow rules
- Verification sweep делай сам. Gap → fix-spec как 141/142 в batch F, не claim'ить done.
- Не спрашивай разрешения — автономно.
- Commit messages английский, docs любой язык (пример batch G — русский).
- Не удаляй existing tests которые не касаются удалённых провайдеров. Только те, которые assert'ят на anthropic/openai/gemini по имени.
- НЕ ломай API surface `LLMProvider.generate` / `ProviderBackedLLM` — только добавляй ProviderUnavailable exception, не трогай существующие return types.

## Out of scope для Batch H
- Continuous learning Phase 2 (online A/B, auto-rollout) — отложено до traffic signal.
- Backup/restore expansion — low priority.
- Tool-use / structured output через GraceKelly — `/api/v1/smart` их не поддерживает (capabilities=false); если нужно — отдельный batch с `/api/v1/orchestrate` endpoint.
- Streaming через GraceKelly (`/api/v1/orchestrate/stream`) — not supported by RAG pipeline сейчас.
- Multi-model consensus через GraceKelly `reliability_level=high` — можно добавить позже как experiment.

## How to start
1. Прочитай `codex-tasks/Archive/meta-arc-7-provider-abstraction.md` — образец meta от batch G.
2. Прочитай `codex-tasks/verification-report-batch-g.md` — образец verification report.
3. Прочитай текущий `config/providers.yml` — схема профилей и провайдеров.
4. Прочитай `llm/providers/anthropic.py` — pattern для paid-API provider (будет основой `mistral.py`).
5. Посмотри `D:\GraceKelly\src\gracekelly\api\routes\smart.py` — exact request/response schema, уже извлечена в этом meta в разделе "GraceKelly API contract".
6. Начинай с task-150 (Mistral, independent), затем task-151 (GraceKelly + failover, blocks nothing), затем task-152 (cleanup — требует 150 и 151 done).

## Risks / watchouts
- **GraceKelly может быть не запущен**: в CI это нормально (mock). При manual smoke — убедиться что GraceKelly up на 8011, иначе тестировать только `external-mistral`.
- **GraceKelly модели browser-based могут быть недоступны**: перплексити требует залогиненного chrome-profile (см. GraceKelly memory). Для dev safe outset использовать `model=mistral-small` который идёт через Mistral API (не через browser).
- **Mistral rate limits**: 1 req/s на free tier. В benchmark flow легко упереться — добавить retry с backoff как в existing Ollama wrapper.
- **Dry-run mode**: `/api/v1/smart` поддерживает `dry_run: true` — полезно для тестов (возвращает ничего, валидирует только params).
- **GraceKelly API key optional**: не все endpoints требуют auth (только non-public paths). Health check `/healthz/ready` всегда public.
- **Удаление файлов ломает тесты batch G**: внимательно read existing тесты (test_provider_abstraction.py, test_provider_registry.py) перед удалением anthropic/openai/gemini — обновить assertions на Mistral/GraceKelly вместо delete wholesale.

---

**Если этого meta достаточно для автономной работы — начинай. Если critical gap в ТЗ — задай ОДИН вопрос и продолжай.**
