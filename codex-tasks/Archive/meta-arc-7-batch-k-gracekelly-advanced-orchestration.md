# Meta-task — Arc 7 / Batch K: GraceKelly advanced orchestration

## Goal
Расширить GraceKelly integration (batch H закрыл basic `/api/v1/smart` endpoint) на advanced features: **tool-use** (LangGraph function calling через GraceKelly), **structured output** (JSON schema constraints), **multi-model consensus** (reliability_level=standard/high), **streaming**, **batch requests**. Унифицировать как опциональные capabilities провайдера. Планируй и реализуй сам по паттерну batch G/H/I/J.

## Context

### Почему этот batch
Batch H закрыл GraceKelly как простой synchronous LLM backend через `/api/v1/smart` с `reliability_level=quick`. Это работает для simple Q&A, но:
1. **Agent tool-use** в `agent/graph.py` (task-107, `RAG_AGENTIC_MODE`) сейчас работает только на Ollama — потому что GraceKelly `/smart` не поддерживает tool-calling. Если хочется использовать Claude Sonnet через GraceKelly для agentic workflow — нужен `/orchestrate` endpoint.
2. **Structured output** — nodes типа `grade_docs`, `classify_complexity`, `evaluate` могут benefit от JSON schema enforcement (less парсинга).
3. **Multi-model consensus** — GraceKelly умеет `reliability_level=standard/high` (2-3 или больше моделей + vote). Для critical fact-verification nodes — интересный option.
4. **Streaming** — для long answers / UI streaming response (сейчас everything synchronous).
5. **Batch requests** — для ingestion pipeline (много документов).

### Текущее состояние
- HEAD `e063016`, 426 tests, ruff clean.
- `llm/providers/gracekelly.py` — POST `/api/v1/smart` only, `reliability_level="quick"` hardcoded, no tool/structured/stream support.
- `llm/providers/base.py` — `LLMResponse` dataclass, `LLMProvider` protocol с `generate(messages, ...) -> LLMResponse`.
- Agent `RAG_AGENTIC_MODE` использует LangGraph tool-calling только через Ollama wrapper.
- ChromaDB ingestion (`ingestion/pipeline.py`) — sequential, один document/один embedding call.

### GraceKelly API endpoints (разведка из batch H + доп)
Все через `D:\GraceKelly\src\gracekelly\api\routes\`:

**`POST /api/v1/orchestrate`** — main advanced endpoint:
```
Request:
{
  "prompt": "...",
  "requested_models": ["claude-sonnet-4-6", "gpt-5-4"],  # multi-model
  "merge_strategy": "consensus|first|best_of_n",
  "mode": "...",  # execution mode
  "tools": [{"name": "...", "schema": {...}}],  # tool definitions
  "structured_output_schema": {...},  # JSON schema
  "metadata": {...}
}

Response:
{
  "task_id": "...",
  "status": "...",
  "result": {
    "answer": "...",
    "tool_calls": [...],
    "structured_output": {...},
    "consensus_details": {...}
  }
}
```

**`POST /api/v1/orchestrate/stream`** — streaming version (SSE).

**`POST /api/v1/batch`** — batch requests (много prompts в один вызов).

**`POST /api/v1/compare`** — side-by-side comparison.

**`POST /api/v1/consensus`** — explicit consensus с fail-if-no-agreement semantic.

**`POST /api/v1/debate`** — models argue each other.

**`GET /api/v1/tasks/{id}`** — poll async task status.

**`GET /api/v1/models/capabilities`** — list models with supports_tool_use/structured_output/vision per model.

## Batch K scope (6 tasks, 165-170)

### task-165 — GraceKelly `/orchestrate` endpoint integration
Расширение `GraceKellyProvider` на `/api/v1/orchestrate` когда нужны advanced features.
- Smart dispatch: если request без tools/schema/consensus → остаётся `/smart` (efficient); если есть → `/orchestrate`.
- Новый метод в provider: `generate_with_tools(messages, tools, ...) -> LLMResponse` (с `tool_calls` в metadata), `generate_with_schema(messages, schema, ...) -> LLMResponse` (с `structured_output` в metadata).
- `LLMResponse` extension: `tool_calls: list[dict] | None`, `structured_output: dict | None`.
- Config flag `gracekelly_use_orchestrate_for_tools: bool = True` default (auto-route).
- Tests: 6+ (smart dispatch correct, tool_calls parsed, schema enforced, backward-compat `/smart` for simple calls).

### task-166 — Tool-use unification across providers
Сейчас `agent/graph.py` tool-calling — Ollama-specific. Унифицировать через `LLMProvider.generate_with_tools`:
- `llm/providers/base.py` — capability check: provider должен поддерживать tool_use (`supports_tool_use` в registry).
- `llm/providers/ollama.py` — реализация через langchain_ollama tool binding.
- `llm/providers/gracekelly.py` — через `/orchestrate` (task-165).
- `llm/providers/mistral.py` — через Mistral API function calling (supports according to docs).
- `agent/graph.py` — agentic nodes (task-107) используют `provider.generate_with_tools` вместо direct Ollama.
- `config/providers.yml` — обновить capabilities flags в registry.
- Tests: 6+ (tool call roundtrip per provider, unsupported provider fails с readable error).

### task-167 — Structured output через JSON schema
Для nodes где LLM должна вернуть строго structured JSON (grade_docs → `{"relevant": true/false, "reason": "..."}`, classify_complexity → `{"complexity": "simple"}`):
- `llm/providers/base.py` — `generate_with_schema(messages, schema, ...) -> LLMResponse` с pydantic validation post-call.
- Реализация per provider: Ollama через JSON mode prompt-engineering, GraceKelly через `/orchestrate` structured_output_schema, Mistral через response_format.
- `agent/graph.py` — `grade_docs` и `classify_complexity` переведены на `generate_with_schema`.
- Fallback: если schema validation fails — retry раз, потом fall back на free-text parsing (существующий pattern).
- Tests: 5+ (schema enforced per provider, validation failure handled, fallback path).

### task-168 — Multi-model consensus через GraceKelly
Для fact-verification node (task-92) — опция использовать consensus (2-3 модели голосуют):
- Settings: `FACT_VERIFY_CONSENSUS_ENABLED: bool = False` default, `FACT_VERIFY_RELIABILITY_LEVEL: str = "standard"` (quick/standard/high).
- Если enabled: `agent/graph.py:verify_facts_node` делает GraceKelly `/orchestrate` с `reliability_level=standard`, aggregates scores.
- Latency caveat — standard = 2-3 calls (2-3x slower). Прямо document.
- Experiment override — через `CURRENT_EXPERIMENT.settings_overrides`.
- Prometheus: `fact_verification_consensus_total{level,verdict}`.
- Tests: 4+ (consensus triggered когда enabled, quick mode default, metric correct).

### task-169 — Streaming response через GraceKelly
Для UI (chat.html) — streaming answer tokens вместо full-wait.
- `llm/providers/base.py` — `generate_stream(messages, ...) -> AsyncIterator[str]`.
- GraceKelly implementation через `/api/v1/orchestrate/stream` (SSE parsing).
- Ollama implementation — LangChain `astream`.
- Mistral implementation — Mistral API streaming.
- API endpoint `/api/chat/stream` (new) — SSE response; existing `/api/chat` остаётся synchronous для backward compat.
- UI update в `static/chat.html` — используется новый endpoint если feature flag on.
- Feature flag `STREAMING_ENABLED: bool = False` default.
- Tests: 5+ (stream yields multiple chunks, finish_reason correct, cancellation works, non-streaming fallback).

### task-170 — Batch requests для ingestion
Для ingestion pipeline (много documents → много embedding/summary calls) — batch-mode.
- GraceKelly `/api/v1/batch` для summarization during contextual header generation.
- `ingestion/pipeline.py` — optional batch mode через provider capability `supports_batch`.
- Fallback к sequential если provider не supports.
- Performance metric — per-document latency до/после (должен драматически упасть если batch работает).
- Tests: 4+ (batch correct, fallback sequential, latency reduced для batch).

## CRITICAL SAFEGUARDS

- **Не ломать existing provider abstraction** — только добавлять capability methods, не менять существующие.
- **Не форсить advanced features** — все feature flags off by default (кроме `gracekelly_use_orchestrate_for_tools` который auto-detect).
- **GraceKelly не обязателен running в тестах** — mock all `/orchestrate`, `/stream`, `/batch` endpoints через httpx_mock.
- **Не делать real tool executions в тестах** — tool calls returned mock'ами.
- **Consensus mode docs**: явно указать 2-3x latency impact.
- **Streaming не ломает cache** — если response cached, возвращать synchronous; streaming только для fresh.

## Deliverables

### Docs
- `codex-tasks/orchestrator-batch-k-gracekelly-advanced-orchestration.md`.
- `codex-tasks/task-165-gracekelly-orchestrate-integration.md` ... `task-170-batch-requests-ingestion.md`.
- Update `codex-tasks/arc-7-proposal.md` с batch K closed.

### Code
- Extensions в `llm/providers/base.py` (capability methods), `gracekelly.py`, `ollama.py`, `mistral.py`.
- `agent/graph.py` — агентик + fact-verify + grade_docs + classify_complexity updates.
- `api/app.py` — новый `/api/chat/stream` endpoint.
- `static/chat.html` — опциональный streaming UI.
- `ingestion/pipeline.py` — batch mode support.
- Feature flags + Prometheus metrics.
- Update `config/providers.yml` capabilities.

### Closure
- Verification sweep per task.
- Per-task commits (или arc-level).
- Archive specs.
- CHANGELOG Arc 7 Batch K section.

## Acceptance
- `pytest tests/ -q` — 426 + ~30 new tests = 456+ passing.
- `ruff check .` — clean.
- Все feature flags default off → existing agent behavior unchanged (sanity).
- `RAG_AGENTIC_MODE=true` + `gracekelly-primary` profile — agentic tools работают через GraceKelly `/orchestrate`.
- `STREAMING_ENABLED=true` + запрос на `/api/chat/stream` — tokens приходят incrementally.
- Working tree clean.

## Workflow rules
- По паттерну batch G/H/I/J.
- Mistral function-calling требует актуального API — reference https://docs.mistral.ai/capabilities/function_calling/ (в spec'е Codex'а уже подразумевается наличие).
- SSE parsing в streaming — использовать `httpx-sse` либу или manual.

## Out of scope для Batch K
- Multi-agent workflows (agent-to-agent communication через GraceKelly `/debate`) — отдельный batch.
- Custom tool definitions через UI — остаются в code.
- Voice streaming / TTS — не в scope.
- Cross-provider consensus (Ollama + Mistral + GraceKelly голосуют) — complex orchestration, отдельно.
- GraceKelly task polling async workflow (`GET /tasks/{id}`) — только synchronous calls в рамках этого batch.

## How to start
1. `codex-tasks/Archive/meta-arc-7-batch-h-gracekelly-mistral.md` — предыдущий GraceKelly meta, содержит contract для `/api/v1/smart`.
2. `D:\GraceKelly\src\gracekelly\api\routes\orchestrate.py` — `/orchestrate` request/response schema.
3. `D:\GraceKelly\src\gracekelly\api\routes\stream.py` — streaming endpoint.
4. `D:\GraceKelly\src\gracekelly\api\routes\batch.py` — batch endpoint.
5. `D:\GraceKelly\src\gracekelly\schemas.py` — pydantic schemas для request/response.
6. `agent/tools.py` — existing tool definitions (task-107), reuse.
7. `codex-tasks/Archive/task-92-fact-verification-node.md` — existing fact-verify logic, extension point.
8. `codex-tasks/Archive/task-107-agentic-tool-use.md` (если есть) или `agent/graph.py` agentic nodes.

## Risks
- **GraceKelly `/orchestrate` schema может отличаться** от моего представления — обязательно прочитать `D:\GraceKelly\src\gracekelly\schemas.py` OrchestrateRequest/Response.
- **Ollama tool-use** через LangChain может быть flaky с small models (llama3.2:3b может не генерить proper JSON). Рекомендация: `qwen2.5:7b` для tool-capable nodes.
- **Streaming in SSE + FastAPI + async** — complex. Тщательно handle disconnects / errors.
- **Mistral function-calling** требует specific format (`tools` + `tool_choice`) — не все модели поддерживают (только `mistral-large` / `mistral-small` с function calling). Обновить capabilities в providers.yml.
- **Consensus mode cost** (2-3x latency) — document в User-facing config что включение — explicit trade-off.
- **Batch mode отсутствует в Ollama** — fallback на sequential autoregressive иначе.

---

**Если meta достаточно — начинай. Critical gap — один вопрос и продолжай.**
