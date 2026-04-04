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
| `SUPPORT_SINK_BACKEND` | `local` | канал эскалации: local или bitrix |
| `BITRIX_WEBHOOK_URL` | — | URL вебхука Bitrix24 |
| `API_KEY` | — | X-API-Key header для аутентификации |
| `REQUIRE_OLLAMA` | `false` | fail-fast если Ollama недоступна |
| `SESSION_TTL_SECONDS` | `7200` | TTL API-сессий |

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ask` | задать вопрос (optional: `session_id`, `api_key`) |
| POST | `/api/upload` | загрузить документ и переиндексировать |
| GET | `/api/health` | проверить Ollama, ChromaDB, SQLite (503 при сбое) |
| GET | `/api/sessions/{id}/history` | история сессии |
| DELETE | `/api/sessions/{id}` | удалить сессию |

Rate limits: 60 req/min на `/api/ask`, 10 req/min на `/api/upload`.

## Web UI

Открой http://localhost:8000 — тёмная/светлая тема, upload документов, бейджи качества и маршрута:
- `Качество: 85` — LLM оценивает ответ от 0 до 100 (высокое = точный ответ на основе контекста)
- `Маршрут: auto` — ответ отправлен автоматически
- `Маршрут: human` — вопрос передан оператору (низкое качество или ошибка pipeline)

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
api/            FastAPI app (app.py) — rate limiting, API key auth, health checks
config/         settings.py, logging_config.py
evaluation/     ragas_eval.py — keyword-based + optional embedding-based metrics
graph/          LangGraph pipeline (state.py, graph.py)
ingestion/      document ingestion pipeline
integrations/   mock_inbox.py, bitrix.py — escalation sinks
tracing/        SQLite tracing
vectordb/       manager.py — ChromaDB + BM25 + reranking
static/         chat.html — Web UI
docs/research/  rag-landscape-2026.md — актуальность RAG в 2025–2026
codex-tasks/    задачи для Codex (task-10 … task-13)
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
| Web UI (dark theme) | ✅ |
| RAGAS-style evaluation (keyword proxies) | ✅ |
| Help page (task-10) | pending Codex |
| Embedding-based evaluation (task-12) | pending research |
