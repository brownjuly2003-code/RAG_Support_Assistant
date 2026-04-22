# Verification report — Arc 7 / Batch K (GraceKelly advanced orchestration)

## Summary
- **6 tasks verified** (task-165..170).
- **Batch K targeted sweep**: 59 passed / 0 failed / 0 errors in 16s.
- **Ruff**: clean.
- **Working tree pre-commit**: arc 7 batch K changes only; Batch I partial
  work (tests-only, without migrations 015-017 or server code) moved to
  `git stash` entry `arc-7-batch-i-partial-tests-orphan` for later Batch I
  execution.

## Scope verification (per task)

### task-165 — GraceKelly `/orchestrate` integration — PASS
- `GraceKellyProvider.generate_with_tools` and `generate_with_schema`
  present.
- Smart-dispatch rule: requests without tools/schema/consensus continue on
  `/api/v1/smart`; advanced calls route to `/api/v1/orchestrate`.
- `LLMResponse.tool_calls` and `LLMResponse.structured_output` carried
  through the provider surface.
- Config flag `gracekelly_use_orchestrate_for_tools` present in
  `config/providers.yml`.
- Tests: `tests/test_gracekelly_provider.py` +108 lines,
  `tests/test_provider_abstraction.py` +69 lines.

### task-166 — Tool-use unification — PASS
- `agent/graph.py` added `_run_provider_tool_loop`, `_select_agentic_llm`,
  `_normalize_tool_call`, `_agentic_tool_definitions`, and
  `_llm_supports_tool_use`. Agentic nodes no longer depend on the Ollama
  wrapper.
- `ollama.py`, `mistral.py`, `gracekelly.py` implement
  `generate_with_tools`.
- Registry capabilities in `config/providers.yml` surface
  `supports_tool_use` for each provider.
- Tests: `tests/test_agent_tools.py` +79 lines,
  `tests/test_provider_graph_integration.py` +163 lines,
  `tests/test_ollama_provider.py` (new), `tests/test_mistral_provider.py`
  +100 lines.

### task-167 — Structured output via JSON schema — PASS
- `LLMProvider.generate_with_schema` in `llm/providers/base.py` with a
  shared runtime fallback when provider does not implement the method.
- `agent/graph.py` `_llm_supports_structured_output` and
  `_invoke_with_schema` helpers route classify/grade/fact-verify nodes
  through the schema path with safe-fallback on validation failure.
- `StructuredOutputValidationError` raised and handled.
- Tests: `tests/test_provider_graph_integration.py`,
  `tests/test_provider_abstraction.py`, `tests/test_mistral_provider.py`,
  `tests/test_ollama_provider.py`.

### task-168 — Multi-model consensus through GraceKelly — PASS
- Settings `fact_verify_consensus_enabled` (default `false`) and
  `fact_verify_reliability_level` (default `standard`) wired into
  `EXPERIMENT_SETTINGS_KEYS` so experiments can override them.
- `agent/graph.py` fact-verify node uses consensus mode when enabled,
  parses schema-constrained verdict.
- Prometheus `fact_verification_consensus_total{level,verdict}` emitted
  from `monitoring/prometheus.py`.
- Latency trade-off documented in task spec (`standard`/`high` imply
  multiple model calls).
- Tests: `tests/test_provider_graph_integration.py`.

### task-169 — Streaming response — PASS
- `generate_stream(messages, **kwargs) -> AsyncIterator[str]` on each
  provider (ollama/mistral/gracekelly), GraceKelly wires to
  `/api/v1/orchestrate/stream`.
- `api/app.py` new `/api/chat/stream` endpoint, provider-aware streaming
  with `_stream_ollama` fallback when provider does not support streaming;
  `/api/chat` synchronous alias for symmetry.
- `/api/health` now exports `features.streaming_enabled`.
- `static/chat.html` switches to `/api/chat/stream` when
  `STREAMING_ENABLED` is true, keeping `/api/ask/stream` for backward
  compatibility.
- Tests: `tests/test_chat_streaming.py` (new),
  `tests/test_new_features.py`.

### task-170 — Batch requests for ingestion — PASS
- `ingestion/pipeline.py` gains `INGESTION_BATCH_ENABLED` opt-in, provider
  `generate_batch` path for contextual headers with sequential fallback
  when batch capability is absent.
- Ingestion log records `batch_contextual_headers` metrics including
  per-document latency.
- Tests: `tests/test_ingestion_contextual.py` +115 lines.

## Out of scope / deferred to Batch I
- Batch I (continuous learning Phase 2) was started in parallel but never
  finished: three test files (`test_curated_dataset.py`,
  `test_experiment_registry.py`, `test_prompt_registry_integration.py`)
  contain WIP tests referencing `alembic/versions/017_curated_case_status.py`
  and experiment-deployment endpoints that do not yet exist. These test
  additions are preserved in `git stash` entry
  `arc-7-batch-i-partial-tests-orphan` so Batch I can pick them up when
  task-153..158 are actually implemented.

## Known non-Batch-K test gaps (pre-existing)
- `tests/integration/test_concurrency.py::test_parallel_requests_keep_sessions_isolated_by_tenant`
  hangs locally without Ollama/Redis — not touched by Batch K.
- `tests/test_a11y.py::test_axe_has_no_serious_or_critical_findings[/static/analytics.html]`
  hangs locally without a working headless Chrome — not touched by Batch K.
- `tests/test_body_size_limits.py::test_upload_path_bypasses_body_middleware`
  hangs on Redis retry loop when Redis is not running — not touched by
  Batch K.

These were observed during the Batch K sweep and are safe to run in CI
where the infrastructure is up.

## Acceptance (per meta-spec)
- Targeted sweep — PASS (59/59).
- Ruff — PASS.
- Feature flags default off — PASS (sanity: full provider/graph suites
  stay green without `STREAMING_ENABLED` or `INGESTION_BATCH_ENABLED`).
- Working tree clean post-commit — PASS.
