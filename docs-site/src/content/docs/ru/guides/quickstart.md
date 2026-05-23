---
title: "Запустить локально — RAG Support Assistant"
---

# Запустить локально — RAG Support Assistant

> Минимальный набор шагов, чтобы поднять сервис локально и убедиться, что он работает.

## 0. Требования

- Python 3.11+ (тестировано на 3.13)
- Docker Desktop (для Postgres + Redis в dev и для regression eval)
- ~8 GB места под embeddings/reranker/cache; explicit Ollama mode дополнительно требует место под модели.

По выбранному profile:
- **GraceKelly** на `D:\GraceKelly\` (port 8011) — default local orchestrator для Claude Sonnet 4.6 / GPT-5 / Gemini через Perplexity Pro.
- **Ollama** (`https://ollama.com/download`) — для explicit `local-first` сценария или fallback.
- **Mistral API key** (`MISTRAL_API_KEY`) — для прямого Mistral fast-tier.

## 1. Зависимости

```bash
cd D:\RAG_Support_Assistant
python -m venv .venv
. .venv/Scripts/activate          # Windows PowerShell: . .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Конфиг

```bash
cp .env.example .env              # Windows: copy .env.example .env
```

Откройте `.env` и заполните то, что нужно. Минимальные сценарии:

| Сценарий | Обязательные переменные |
| --- | --- |
| **GraceKelly primary** (default) | `GRACEKELLY_BASE_URL=http://127.0.0.1:8011`, `LLM_PROVIDER_PROFILE=gracekelly-primary` подразумевается |
| **Local-only Ollama** | `LLM_PROVIDER_PROFILE=local-first` |
| **+ Mistral fast tier** | `MISTRAL_API_KEY=<key>` + `LLM_PROVIDER_PROFILE=external-mistral` |
| **GraceKelly mixed routing** (Claude Sonnet 4.6 reasoning) | `MISTRAL_API_KEY=<key>` + `LLM_PROVIDER_PROFILE=gracekelly-mixed` + `GRACEKELLY_REQUEST_TIMEOUT_SEC=120` |

Полный список переменных — `README.md` секция **Environment Variables**.

## 3. Инфраструктура (Postgres + Redis)

Для dev — поднять disposable контейнеры:

```bash
docker run -d --name rag-postgres -p 5432:5432 \
    -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag_dev_password -e POSTGRES_DB=rag_assistant \
    postgres:16-alpine

docker run -d --name rag-redis -p 6379:6379 redis:7-alpine
```

Затем миграции:

```bash
alembic upgrade head
```

## 4. Сценарий A — GraceKelly primary (default)

```bash
# Поднять GraceKelly в отдельном терминале
cd D:\GraceKelly
uvicorn gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011

# Запуск
cd D:\RAG_Support_Assistant
python main.py
```

Открыть `http://localhost:8000/static/login.html` (password+SSO) или
`http://localhost:8000/static/chat.html` (chat UI). После логина —
`/agent` для agent copilot dashboard. (legacy `/` index UI удалён
2026-04-27 — был unauthenticated, см. SESSION-NOTES-2026-04-27.)

`gracekelly-primary` profile направляет fast и strong tier через локальный GraceKelly orchestrator. `/api/health/ready` проверяет GraceKelly readiness и не требует Ollama, если активный профиль не использует Ollama.

## 5. Сценарий B — explicit Local-only Ollama

```bash
# Поднять Ollama и стянуть модели
ollama serve &
ollama pull qwen2.5:7b

# Запуск с явным local-first profile
LLM_PROVIDER_PROFILE=local-first python main.py
```

## 6. Сценарий C — GraceKelly mixed routing

Полезно когда нужно качество reasoning (Claude Sonnet 4.6) для финальных ответов, но фоновую обработку (классификация, grade_docs, verify_facts) делает быстрый Mistral API.

1. Поднять GraceKelly (отдельный проект):

   ```bash
   cd D:\GraceKelly
   $env:GRACEKELLY_EXECUTION_PROFILE = "hybrid"
   uvicorn gracekelly.main:create_app --factory --host 127.0.0.1 --port 8011
   ```

2. В `D:\RAG_Support_Assistant\.env`:

   ```
   MISTRAL_API_KEY=<your-key>
   LLM_PROVIDER_PROFILE=gracekelly-mixed
   GRACEKELLY_REQUEST_TIMEOUT_SEC=120
   ```

3. Запустить RAG:

   ```bash
   python main.py
   ```

`gracekelly-mixed` profile направляет fast tier через Mistral API (~1-3s/call), strong tier (final answer) через GraceKelly browser → Perplexity Pro (Claude Sonnet 4.6, ~30-60s/call).

## 7. Загрузка документов и первый запрос

```bash
# Документ для ингеста (PDF, MD, TXT)
# PowerShell (Windows) — заметка: curl.exe, не curl (последний — alias к Invoke-WebRequest)
curl.exe -X POST http://localhost:8000/api/upload `
    -H "Authorization: Bearer <admin-jwt>" `
    -F "file=@docs/warranty.md"

# Bash (Linux/macOS)
curl -X POST http://localhost:8000/api/upload \
    -H "Authorization: Bearer <admin-jwt>" \
    -F "file=@docs/warranty.md"

# Первый запрос
# PowerShell (Windows)
curl.exe -X POST http://localhost:8000/api/ask `
    -H "Authorization: Bearer <admin-jwt>" `
    -H "Content-Type: application/json" `
    -d '{"question":"Какой срок гарантии?"}'

# Bash (Linux/macOS)
curl -X POST http://localhost:8000/api/ask \
    -H "Authorization: Bearer <admin-jwt>" \
    -H "Content-Type: application/json" \
    -d '{"question":"Какой срок гарантии?"}'
```

Получить admin JWT для dev: `POST /api/auth/login` с `admin/admin` (если `ADMIN_PASSWORD_HASH` не задан в `.env`).

## 8. Health checks

```bash
curl http://localhost:8000/api/health/live      # liveness
curl http://localhost:8000/api/health/ready     # readiness (зависимости)
curl http://localhost:8000/api/metrics          # снимок метрик
curl http://localhost:8000/api/admin/providers  # активный routing profile + recent usage (auth)
```

## 9. Regression eval

Для непрерывной проверки качества против curated 20-кейс датасета:

```bash
# Mock provider benchmark (no GK, no quota burn)
python scripts/regression_eval.py \
    --baseline ollama-small \
    --candidate mistral-small-latest \
    --max-cases 5 \
    --no-persist

# Live GK mixed routing (requires explicit paid/API opt-in)
python scripts/regression_eval.py \
    --baseline ministral-3b-latest \
    --candidate-profile gracekelly-mixed \
    --max-cases 20 \
    --allow-paid-apis
```

Без `--allow-paid-apis` provider/model targets run in `mock-provider-benchmark` mode:
answers and cost/latency metrics are simulated from `evaluation/curated_cases.jsonl`,
so the command does not call GraceKelly or Mistral and does not persist to the DB when
`--no-persist` is set. Live provider calls require explicit `--allow-paid-apis`.

Результаты в `reports/regression/<timestamp>-*.{json,md}`. PowerShell wrapper `scripts\run_regression_via_gracekelly.ps1 -AllowLive` поднимает disposable Postgres + Redis + ингест + регрессию одной командой после explicit live opt-in.

## 10. Распространённые проблемы

:::caution[vector store is not initialized]
Нет ингестированных документов. Загрузите через `POST /api/upload` или прогоните ингест-скрипт.
:::

:::caution[[provider_unavailable]]
Циркуит-брейкер открыт у адаптера. Дождитесь cooldown (60 с) или сбросьте вручную: `POST /api/admin/circuit-breaker/reset`.
:::

:::caution[[model_mismatch] ... но UI показывает 'Sonar']
Perplexity server-side auto-router подменил модель. Это external GK error, классифицирован как `infrastructure_failure` в regression eval. Пересмотрите запрос или попробуйте другую формулировку.
:::

:::caution[HF_HUB_OFFLINE=1]
Если в env установлен `HF_HUB_OFFLINE=1`, но `BAAI/bge-m3` не в кэше — embeddings упадут. Стяните модель один раз с пустым `HF_HUB_OFFLINE`, потом включайте обратно.
:::

:::caution[Postgres DuplicateObject на ENUM]
Миграция 012 чувствительна к двойному `CREATE TYPE`. Исправлено в `d163942`; если ловится — обновите ветку.
:::

## 11. Где смотреть дальше

- `README.md` — полный спектр env vars + публичные endpoints + Prometheus метрики.
- `docs/runbook.md` — оперативный runbook для дежурного (алерты, диагностика, действия).
- `docs/disaster-recovery.md` — DR сценарии A-F (потеря данных, шифрование, encryption-key).
- `docs/operations/` — runbook'и по backup, helm, gracekelly smoke.
- `docs/CHANGELOG.md` — история изменений по аркам.
