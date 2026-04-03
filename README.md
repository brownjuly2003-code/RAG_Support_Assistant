# RAG Support Assistant

RAG Support Assistant отвечает на вопросы поддержки по базе знаний и решает, можно ли отдать ответ автоматически или лучше эскалировать запрос человеку. Стек проекта: FastAPI, LangGraph, ChromaDB, локальная LLM через Ollama, SQLite для tracing и mock inbox или Bitrix для эскалаций.

## Architecture

Pipeline flow:
```text
transform_query → retrieve → grade_docs → generate → evaluate → route_or_retry
                                                                     ↓        ↓
                                                                  log      handle_error
                                                                  ↓              ↓
                                                                 END      escalate + END
```

- **Retrieval**: использует ChromaDB, embedding model, optional BM25 hybrid search и cross-encoder reranker, параметры берутся из `config/settings.py`.
- **Generation**: ответ генерирует локальная модель Ollama, по умолчанию `mistral`.
- **Evaluation**: `quality_score` определяет, остается ли маршрут `auto`, нужен ли retry или эскалация на человека.
- **Escalation**: при `route=human` или `route=error` вопрос уходит в local JSONL inbox или Bitrix webhook.

## Quick Start

**Prerequisites:** Python 3.11+, `ollama serve`

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start Ollama and pull model
ollama serve
ollama pull mistral

# 3. Run
python main.py
```

Open http://localhost:8000

## Environment Variables

Copy `.env.example` to `.env` and adjust:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL локального Ollama API |
| `OLLAMA_MODEL_NAME` | `mistral` | модель генерации ответов |
| `RAG_EMBEDDING_MODEL` | `BAAI/bge-m3` | embedding model для документов и запросов |
| `RAG_RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | reranker после retrieval |
| `RAG_HYBRID_SEARCH` | `true` | включает BM25 + vector hybrid search |
| `RAG_RETRIEVAL_TOP_K` | `20` | число кандидатов до rerank |
| `RAG_RERANK_TOP_K` | `5` | число документов после rerank |
| `RAG_VECTOR_BACKEND` | `chroma` | backend векторного хранилища |
| `SUPPORT_SINK_BACKEND` | `local` | канал эскалации: local или bitrix |
| `SESSION_TTL_SECONDS` | `7200` | idle timeout API-сессий |

## API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ask` | задать вопрос с optional `session_id` |
| POST | `/api/upload` | загрузить документ и переиндексировать базу |
| GET | `/api/health` | проверить Ollama, ChromaDB и SQLite |
| GET | `/api/sessions/{id}/history` | получить историю сообщений сессии |
| DELETE | `/api/sessions/{id}` | очистить одну сессию |

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
