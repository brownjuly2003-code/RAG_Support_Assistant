# Arc 7 / Batch K — GraceKelly advanced orchestration

## Status
Closed on 2026-04-22.

## Scope closed
- GraceKelly provider auto-routes simple requests to `/api/v1/smart` and advanced requests to `/api/v1/orchestrate`.
- Provider abstraction now exposes optional capabilities for tool use, structured output, streaming and batch.
- `agent/graph.py` uses provider-level tool calling and schema-constrained responses for classification, grading and fact verification.
- Fact verification supports GraceKelly-style consensus via `FACT_VERIFY_CONSENSUS_ENABLED` and `FACT_VERIFY_RELIABILITY_LEVEL`.
- API/UI streaming surface added through `/api/chat/stream`, provider-aware SSE token streaming and UI endpoint switching via `STREAMING_ENABLED`.
- Ingestion pipeline supports explicit batch contextual-header preprocessing through `INGESTION_BATCH_ENABLED` with sequential fallback.

## Key flags
- `FACT_VERIFY_CONSENSUS_ENABLED=false`
- `FACT_VERIFY_RELIABILITY_LEVEL=standard`
- `STREAMING_ENABLED=false`
- `INGESTION_BATCH_ENABLED=false`
- `gracekelly_use_orchestrate_for_tools=true`

## Notes
- Consensus mode increases latency materially because `standard`/`high` imply multiple model calls behind GraceKelly.
- Streaming keeps the previous `/api/ask/stream` path for compatibility and adds `/api/chat/stream` as the new alias surface.
- Batch contextual-header generation is opt-in to avoid changing ingestion cost/latency by default.

## Verification
- Provider sweep:
  `pytest tests/test_provider_abstraction.py tests/test_provider_registry.py tests/test_gracekelly_provider.py tests/test_mistral_provider.py tests/test_ollama_provider.py -q`
- Graph/API/ingestion sweep:
  `pytest tests/test_agent_tools.py tests/test_provider_graph_integration.py tests/test_chat_streaming.py tests/test_new_features.py tests/test_ingestion_contextual.py -q`
- Health/streaming sweep:
  `pytest tests/test_health.py tests/test_health_liveness.py tests/test_health_postgres_redis.py tests/integration/test_streaming.py -q`

