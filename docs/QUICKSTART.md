# Quickstart — RAG Support Assistant

> Минимальный набор шагов чтобы поднять сервис локально и убедиться что он работает.

## 0. Что нужно

- Python 3.11+ (тестировано на 3.13)
- Docker Desktop (для Postgres + Redis в dev и для regression eval)
- ~12 GB места под модели (Ollama default `qwen2.5:7b` ≈ 4.7 GB, embeddings `BAAI/bge-m3` ≈ 2.3 GB, reranker ~80 MB, плюс кэш HF)

Опционально:
- **Ollama** (`https://ollama.com/download`) — для локального LLM сценария (default).
- **GraceKelly** на `D:\GraceKelly\` (port 8011) — для сценария с Claude Sonnet 4.6 / GPT-5 / Gemini через Perplexity Pro.
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
| **Local-only Ollama** (default) | пусто, `LLM_PROVIDER_PROFILE=local-first` подразумевается |
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

## 4. Сценарий A — Local-only (Ollama)

```bash
# Поднять Ollama и стянуть модели
ollama serve &
ollama pull qwen2.5:7b
# опционально, для быстрых хелпер-флоу:
# ollama pull llama3.2:3b

# Запуск
python main.py
```

Открыть `http://localhost:8000` — chat UI.

## 5. Сценарий B — GraceKelly mixed routing

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

## 6. Загрузка документов и первый запрос

```bash
# Документ для ингеста (PDF, MD, TXT)
curl -X POST http://localhost:8000/api/upload \
    -H "Authorization: Bearer <admin-jwt>" \
    -F "file=@docs/warranty.md"

# Первый запрос
curl -X POST http://localhost:8000/api/ask \
    -H "Content-Type: application/json" \
    -d '{"query":"Какой срок гарантии?"}'
```

Получить admin JWT для dev: `POST /api/auth/login` с `admin/admin` (если `ADMIN_PASSWORD_HASH` не задан в `.env`).

## 7. Health checks

```bash
curl http://localhost:8000/api/health/live      # liveness
curl http://localhost:8000/api/health/ready     # readiness (зависимости)
curl http://localhost:8000/api/metrics          # снимок метрик
curl http://localhost:8000/api/admin/providers  # активный routing profile + recent usage (auth)
```

## 8. Regression eval

Для непрерывной проверки качества против curated 20-кейс датасета:

```bash
# Mistral baseline vs Mistral candidate (no GK, no quota burn)
python scripts/regression_eval.py \
    --baseline ministral-3b-latest \
    --candidate mistral-small-latest \
    --max-cases 5 \
    --allow-paid-apis

# GK mixed routing (требует GK uvicorn + GRACEKELLY_REQUEST_TIMEOUT_SEC=120 в .env)
python scripts/regression_eval.py \
    --baseline ministral-3b-latest \
    --candidate-profile gracekelly-mixed \
    --max-cases 20 \
    --allow-paid-apis
```

Результаты в `reports/regression/<timestamp>-*.{json,md}`. PowerShell wrapper `scripts\run_regression_via_gracekelly.ps1` поднимает disposable Postgres + Redis + ингест + регрессию одной командой.

## 9. Частые засады

- **`vector store is not initialized`** — нет ингестированных документов. Загрузить через `POST /api/upload` или прогнать ингест-скрипт.
- **`[provider_unavailable]` в ответах** — циркуит-брейкер открыт у адаптера. Дождаться cooldown (60s) или сбросить вручную: `POST /api/admin/circuit-breaker/reset`.
- **`[model_mismatch] ... but UI shows 'Sonar'`** — Perplexity server-side auto-router подменил модель. Это external GK error, классифицирован как infrastructure_failure в regression eval. Пересмотреть запрос или попробовать другую формулировку.
- **`HF_HUB_OFFLINE=1`** в env, но `BAAI/bge-m3` не в кэше → embeddings падают. Стянуть один раз с `HF_HUB_OFFLINE` пустым, потом включать обратно.
- **Postgres `DuplicateObject` на ENUM** — миграция 012 чувствительна к двойному `CREATE TYPE`. Исправлено в `d163942`; если ловится — обновить ветку.

## 10. Где смотреть дальше

- `README.md` — полный спектр env vars + публичные endpoints + Prometheus метрики.
- `docs/runbook.md` — оперативный runbook для дежурного (алерты, диагностика, действия).
- `docs/disaster-recovery.md` — DR сценарии A-F (потеря данных, шифрование, encryption-key).
- `docs/operations/` — runbook'и по backup, helm, gracekelly smoke.
- `docs/CHANGELOG.md` — история изменений по аркам.
