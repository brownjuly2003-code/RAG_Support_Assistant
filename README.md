# RAG Support Assistant

RAG Support Assistant отвечает на вопросы поддержки по базе знаний и решает, можно ли отдать ответ автоматически или лучше эскалировать запрос человеку. Стек: FastAPI, LangGraph, ChromaDB, локальная LLM через Ollama, SQLite для tracing, mock inbox или Bitrix24 для эскалаций.

## Architecture

```text
Пользователь → POST /api/ask
                     ↓
              LangGraph pipeline:
  transform_query → retrieve → grade_docs → generate → evaluate → route_or_retry
                                                                        ↓        ↓
                                                                    log      handle_error
                                                                    ↓              ↓
                                                                   END      escalate + END
```

- **Retrieval**: ChromaDB (vector) + BM25 hybrid search, Reciprocal Rank Fusion, cross-encoder reranking
- **Embeddings**: BGE-M3 (`BAAI/bge-m3`) — multilingual, 1024d
- **Generation**: Ollama/Qwen2.5 7B (локальная LLM, без внешних API)
- **Evaluation**: `quality_score` (0–100), маршрут `auto` / `human` / `retry` / `error`
- **Escalation**: при `route=human` или `route=error` вопрос уходит в JSONL inbox или Bitrix24 webhook
- **Tracing**: каждый запрос логируется в SQLite (trace_id, nodes, scores, latency)
- **Monitoring**: агрегированные метрики (latency p50/p95/p99, escalation rate, quality scores, thumbs-down) из SQLite

## Quick Start

**Prerequisites:** Python 3.11+, `ollama serve`

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start Ollama and pull model
ollama serve
ollama pull qwen2.5:7b

# 3. Run
python main.py
```

Open http://localhost:8000

## Environment Variables

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL локального Ollama API |
| `OLLAMA_MODEL_NAME` | `qwen2.5:7b` | модель генерации ответов |
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-m3` | embedding model |
| `RAG_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | cross-encoder reranker |
| `RAG_HYBRID_SEARCH` | `true` | BM25 + vector hybrid search |
| `RAG_RETRIEVAL_TOP_K` | `20` | кандидаты до rerank |
| `RAG_RERANK_TOP_K` | `5` | документы после rerank |
| `RAG_VECTOR_BACKEND` | `chroma` | векторное хранилище |
| `RAG_SEMANTIC_CHUNKING` | `false` | семантический chunking |
| `RAG_SELF_RAG_MAX_ITER` | `2` | макс. итераций Self-RAG |
| `RAG_SELF_RAG_MIN_QUALITY` | `70` | минимальный quality score |
| `RAG_HYDE` | `false` | Hypothetical Document Embeddings |
| `RAG_PARENT_CHILD` | `false` | parent-child chunking |
| `SUPPORT_SINK_BACKEND` | `local` | канал эскалации: local или bitrix |
| `BITRIX_WEBHOOK_URL` | — | URL вебхука Bitrix24 |
| `API_KEY` | — | X-API-Key header для аутентификации |
| `REQUIRE_OLLAMA` | `false` | fail-fast если Ollama недоступна |
| `SESSION_TTL_SECONDS` | `7200` | TTL API-сессий |
| `SHUTDOWN_READY_DELAY_SEC` | `5` | задержка flip-а readiness→503 при SIGTERM для drain k8s LB |
| `ALERT_WEBHOOK_URL` | — | Slack/Telegram webhook для алертов |
| `ALERT_ESCALATION_PCT` | `35` | порог % эскалаций (24h) |
| `ALERT_QUALITY_MIN` | `65` | минимальный avg quality (7d) |
| `ALERT_P95_LATENCY_SEC` | `12` | порог p95 latency в секундах (24h) |
| `ALERT_THUMBS_DOWN_PCT` | `20` | порог % thumbs-down (7d) |
| `CIRCUIT_BREAKER_ENABLED` | `true` | circuit breaker around Ollama calls |
| `CIRCUIT_BREAKER_FAILURE_THRESHOLD` | `5` | consecutive failures before OPEN |
| `CIRCUIT_BREAKER_RESET_TIMEOUT_SEC` | `30` | seconds before HALF_OPEN probe |
| `OLLAMA_RETRY_MAX_ATTEMPTS` | `3` | попыток включая первую; 1 = без retry |
| `OLLAMA_RETRY_BASE_DELAY_SEC` | `0.5` | базовая задержка между попытками |
| `OLLAMA_RETRY_MAX_DELAY_SEC` | `5.0` | верхняя граница задержки |
| `OLLAMA_RETRY_JITTER` | `true` | случайный jitter ±50% в задержке |
| `OLLAMA_REQUEST_TIMEOUT_SEC` | `60` | timeout одного HTTP-вызова Ollama; ReadTimeout → retry → breaker |
| `REQUEST_TIMEOUT_SEC` | `30` | total wall-time limit для `/api/ask`; 504 при превышении |

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ask` | задать вопрос (sync, JSON) |
| POST | `/api/ask/stream` | задать вопрос (SSE streaming) |
| POST | `/api/upload` | загрузить документ и переиндексировать |
| POST | `/api/feedback` | оставить оценку (up/down) для ответа |
| GET | `/api/health` | alias readiness: полная проверка зависимостей (503 при сбое) |
| GET | `/api/health/live` | liveness probe (k8s): 200 всегда, пока процесс отвечает |
| GET | `/api/health/ready` | readiness probe (k8s): полная проверка зависимостей, 503 при падении Ollama/ChromaDB |
| GET | `/api/metrics` | JSON-снапшот метрик системы (latency, quality, escalation) |
| GET | `/api/sessions` | список активных сессий |
| GET | `/api/sessions/{id}/history` | история сессии |
| DELETE | `/api/sessions/{id}` | удалить сессию |
| GET | `/api/feedback/stats` | агрегированная статистика обратной связи |

Rate limits: 60 req/min на `/api/ask`, 10 req/min на `/api/upload`.

## Web UI

Открой http://localhost:8000 — тёмная/светлая тема, SSE streaming, upload документов, бейджи качества и маршрута:
- `Качество: 85` — LLM оценивает ответ от 0 до 100 (высокое = точный ответ на основе контекста)
- `Маршрут: auto` — ответ отправлен автоматически
- `Маршрут: human` — вопрос передан оператору (низкое качество или ошибка pipeline)
- 👍/👎 — feedback к каждому ответу
- `?` — справка для пользователей (/static/help.html)
- `M` — мониторинг метрик (/static/metrics.html)

## Monitoring

`GET /api/metrics` возвращает JSON-снапшот здоровья системы:

```json
{
  "latency": {"p50_sec": 2.1, "p95_sec": 8.4, "p99_sec": 14.2, "window": "24h"},
  "escalation": {"total_traces": 120, "escalated": 18, "rate_pct": 15.0, "window": "24h"},
  "quality": {"scored_traces": 840, "avg_quality": 78.3, "low_quality_share_pct": 12.5, "window": "7d"},
  "errors": {"total_started": 120, "likely_failed": 2, "likely_failure_rate_pct": 1.7, "window": "24h"},
  "feedback": {"total": 95, "thumbs_down": 11, "thumbs_down_rate_pct": 11.6, "window": "7d"}
}
```

Страница `/static/metrics.html` показывает метрики в браузере с цветовой индикацией (зелёный/жёлтый/красный) и автообновлением каждые 30 сек.

Prometheus alert rules упакованы в `monitoring/alert_rules.yml`. Подключаются через `rule_files` в `prometheus.yml`.

Алертинг через `scripts/check_alerts.py` (cron каждые 5 минут):
```bash
python scripts/check_alerts.py --dry-run
```

## Tests

```bash
pytest tests/ -v
```

## Docker

```bash
cp .env.example .env
# Edit .env — set OLLAMA_BASE_URL to your Ollama host
docker compose up
```

## Project structure

```
api/            FastAPI app (app.py) — rate limiting, API key auth, health checks, SSE streaming
config/         settings.py, logging_config.py
evaluation/     ragas_eval.py, benchmark_runner.py, test_cases.json, simulate_model_benchmark.py
graph/          LangGraph pipeline (state.py, graph.py) — HyDE, Self-RAG, Corrective RAG
ingestion/      document ingestion pipeline
integrations/   mock_inbox.py, bitrix.py — escalation sinks
tracing/        SQLite tracing
vectordb/       manager.py — ChromaDB + BM25 + reranking + parent-child chunking
static/         chat.html, help.html, metrics.html — Web UI
scripts/        check_alerts.py — scheduled alert checker (cron)
templates/      Jinja2 HTML templates (ask_result, traces, escalations, trace_detail)
archive/        deprecated files and legacy tests
docs/research/  rag-landscape-2026.md, production-monitoring-2025.md, eval-metrics-2025.md,
                llm-model-selection-2025.md, ui-patterns-2025.md, simulated_model_comparison.md
codex-tasks/    задачи для Codex
```

## Implementation status

| Feature | Status |
|---------|--------|
| Hybrid search (BM25 + ChromaDB + RRF) | ✅ |
| Cross-encoder reranking | ✅ |
| Self-RAG + Corrective RAG | ✅ |
| Error handling + auto-escalation | ✅ |
| FastAPI rate limiting (slowapi) | ✅ |
| API key authentication | ✅ |
| Structured JSON logging | ✅ |
| Real health checks | ✅ |
| Session TTL cleanup | ✅ |
| Document upload + reindex | ✅ |
| Web UI (dark theme, SSE streaming) | ✅ |
| RAGAS-style evaluation (keyword + embedding) | ✅ |
| User help page | ✅ |
| Feedback (thumbs up/down) + stats | ✅ |
| HyDE (hypothetical document embeddings) | ✅ |
| Parent-child chunking | ✅ |
| Model benchmark (simulated, MERA-based) | ✅ |
| Docker Compose (ollama + app) | ✅ |
| Production monitoring endpoint (GET /api/metrics) | pending Codex (task-28) |
| Alert checker script (check_alerts.py) | pending Codex (task-29) |
| Metrics dashboard (metrics.html) | pending Codex (task-30) |
| Semantic chunking A/B comparison | pending Codex (task-31) |
