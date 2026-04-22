# Task 170 — Batch requests for ingestion

## Closed
- Added `INGESTION_BATCH_ENABLED=false` default flag.
- `IngestPipeline.ingest()` can preprocess contextual headers through provider batch requests when the active runtime supports batch.
- Sequential provider fallback is used when batch capability is unavailable.
- Ingestion log now records `batch_contextual_headers` metrics including per-document latency.

## Verified by
- `tests/test_ingestion_contextual.py`
