# Grafana: RAG Support Operations

Version-controlled dashboard artifact for the seven already-implemented RAG
operations and quality signals.

## Import

1. In Grafana: **Dashboards → Import → Upload JSON file**.
2. Select `rag-support-operations.json`.
3. When prompted, bind **DS_PROMETHEUS** to your Prometheus datasource.

The JSON is an importable dashboard model (not a live API export). Datasource
references use `${DS_PROMETHEUS}` so the file stays portable across
environments.

## Panels (7)

Immediate actionable state:

| Panel | Metric | Action support |
| --- | --- | --- |
| Ingestion queue oldest age | `rag_ingestion_queue_oldest_seconds` | Warns at **300s**; check workers/queue when elevated |
| Orphan work inflight | `rag_orphan_work_inflight` | **Zero target**; inspect timeouts/executors when above zero |
| Auto responses by verification | `rag_auto_responses_total` by `verification` | **Zero target** for `unverified` automatic answers |

Bounded failure / outcome breakdowns:

| Panel | Metric | Action support |
| --- | --- | --- |
| Index lifecycle failures by operation | `rag_index_lifecycle_failures_total` by `operation` | Investigate publish/retention failures |
| Escalation delivery by outcome | `rag_escalation_delivery_total` by `outcome` | Check outbox/sink when `failed` rises |
| Safety blocks by action | `rag_safety_blocks_total` by `action` | Review safety gate when `refuse` rises |
| Tenant access denials by resource | `rag_tenant_access_denials_total` by `resource` | Investigate cross-tenant denial patterns by resource type only |

## Alerts

Source alert rules remain in `monitoring/alert_rules.yml` (Prometheus). This
dashboard does **not** define Grafana-native alerts.

## Scope of proof

This artifact proves **local configuration only**:

- importable dashboard JSON is present and contract-tested
- panel queries reference the seven bounded metrics

It does **not** prove live scrape, Grafana provisioning, deployment, or alert
delivery.
