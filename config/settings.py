# config/settings.py
"""
Глобальные настройки проекта.

Идея:
- одно место, где собраны пути (project_root, data/ и т.п.);
- чтение переменных окружения для переключателей:
    - OLLAMA_BASE_URL, OLLAMA_MODEL_NAME
    - RAG_VECTOR_BACKEND ("chroma" / "qdrant")
    - SUPPORT_SINK_BACKEND ("local" / "bitrix")
    - BITRIX_WEBHOOK_URL (полный вебхук crm.timeline.comment.add)
- удобная функция get_settings(), чтобы не плодить os.getenv по всему коду.

Важно:
- это лёгкая обёртка "для PoC", без дополнительных зависимостей (pydantic-settings и т.п.);
- все пути считаются относительно корня проекта:
    project_root/
      config/
      api/
      ingestion/
      vectordb/
      tracing/
      integrations/
      demo/
      data/
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import SecretStr


# Определяем корень проекта как родительскую директорию для config/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENT_OVERRIDE_PATH = PROJECT_ROOT / "config" / "experiment_override.yaml"
EXPERIMENT_SETTINGS_KEYS = (
    "llm_provider_profile",
    "ollama_model_name",
    "ollama_fast_model_name",
    "model_routing_enabled",
    "embedding_model",
    "reranker_model",
    "hybrid_search",
    "retrieval_top_k",
    "rerank_top_k",
    "rrf_k",
    "quality_threshold",
    "semantic_chunking",
    "contextual_headers",
    "agentic_mode",
    "hyde",
    "parent_child",
    "self_rag_max_iterations",
    "self_rag_min_quality",
    "fact_verification_enabled",
    "fact_verify_consensus_enabled",
    "fact_verify_reliability_level",
    "fact_verification_min_score",
    "chunk_size",
    "chunk_overlap",
)
_EXPERIMENT_SETTING_ENV_VARS: dict[str, tuple[str, ...]] = {
    "llm_provider_profile": ("LLM_PROVIDER_PROFILE",),
    "ollama_model_name": ("OLLAMA_MODEL_NAME",),
    "ollama_fast_model_name": ("OLLAMA_FAST_MODEL_NAME",),
    "model_routing_enabled": ("MODEL_ROUTING_ENABLED",),
    "embedding_model": ("RAG_EMBEDDING_MODEL",),
    "reranker_model": ("RAG_RERANKER_MODEL",),
    "hybrid_search": ("RAG_HYBRID_SEARCH",),
    "retrieval_top_k": ("RAG_RETRIEVAL_TOP_K",),
    "rerank_top_k": ("RAG_RERANK_TOP_K",),
    "rrf_k": ("RRF_K",),
    "quality_threshold": ("QUALITY_THRESHOLD",),
    "semantic_chunking": ("RAG_SEMANTIC_CHUNKING",),
    "contextual_headers": ("RAG_CONTEXTUAL_HEADERS",),
    "agentic_mode": ("RAG_AGENTIC_MODE",),
    "hyde": ("RAG_HYDE",),
    "parent_child": ("RAG_PARENT_CHILD",),
    "self_rag_max_iterations": ("RAG_SELF_RAG_MAX_ITER",),
    "self_rag_min_quality": ("RAG_SELF_RAG_MIN_QUALITY",),
    "fact_verification_enabled": ("FACT_VERIFICATION_ENABLED",),
    "fact_verify_consensus_enabled": ("FACT_VERIFY_CONSENSUS_ENABLED",),
    "fact_verify_reliability_level": ("FACT_VERIFY_RELIABILITY_LEVEL",),
    "fact_verification_min_score": ("FACT_VERIFICATION_MIN_SCORE",),
    "chunk_size": ("CHUNK_SIZE", "RAG_CHUNK_SIZE"),
    "chunk_overlap": ("CHUNK_OVERLAP", "RAG_CHUNK_OVERLAP"),
}
# BEGIN DEPLOYED_EXPERIMENT_SETTINGS
DEPLOYED_EXPERIMENT_SETTINGS: dict[str, Any] = {}
# END DEPLOYED_EXPERIMENT_SETTINGS


def _load_llm_model_prices() -> dict[str, dict[str, float]]:
    raw_json = (os.getenv("LLM_MODEL_PRICES", "") or "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            result: dict[str, dict[str, float]] = {}
            for model_name, prices in parsed.items():
                if not isinstance(prices, dict):
                    continue
                try:
                    input_price = float(prices.get("input", 0.0) or 0.0)
                    output_price = float(prices.get("output", 0.0) or 0.0)
                except (TypeError, ValueError):
                    continue
                result[str(model_name)] = {
                    "input": input_price,
                    "output": output_price,
                }
            return result

    legacy = (os.getenv("LLM_COST_PER_1M_TOKENS", "") or "").strip()
    result: dict[str, dict[str, float]] = {}
    for chunk in legacy.split(","):
        model_name, _, price = chunk.partition(":")
        model_name = model_name.strip()
        price = price.strip()
        if not model_name or not price:
            continue
        try:
            amount = float(price)
        except ValueError:
            continue
        result[model_name] = {"input": amount, "output": amount}
    return result


def _load_experiment_override_payload() -> dict[str, Any]:
    if not EXPERIMENT_OVERRIDE_PATH.exists():
        return {}
    payload = yaml.safe_load(EXPERIMENT_OVERRIDE_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _apply_settings_overrides(settings: "Settings", overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        if hasattr(settings, key):
            setattr(settings, key, value)


def _apply_deployed_settings(settings: "Settings") -> None:
    active_overrides: dict[str, Any] = {}
    for key, value in DEPLOYED_EXPERIMENT_SETTINGS.items():
        env_names = _EXPERIMENT_SETTING_ENV_VARS.get(key, ())
        if any((os.getenv(env_name, "") or "").strip() for env_name in env_names):
            continue
        active_overrides[key] = value
    _apply_settings_overrides(settings, active_overrides)


@dataclass
class Settings:
    """
    Объект с настройками.

    Поля:
    - project_root: корень репозитория.
    - data_dir: базовая директория для всех артефактов (vectordb, tracing, inbox).
    - vectordb_chroma_dir: куда складывается Chroma (persist_directory).
    - tracing_db_path: путь к SQLite-базе трейсов.
    - inbox_file: JSONL-файл для mock inbox.
    - chunking_config_path: JSON с лучшей конфигурацией чанков.
    - ollama_base_url / ollama_model_name: настройки локальной LLM.
    - vector_backend: "chroma" или "qdrant" (используется vectordb/manager.py).
    - support_sink_backend: "local" или "bitrix" (используется integrations/mock_inbox.py).
    - bitrix_webhook_url: вебхук для BitrixSupportSink (если нужен).
    - session_ttl_seconds: TTL API-сессий в памяти.
    """

    # --- Пути проекта ---
    project_root: Path = PROJECT_ROOT
    data_dir: Path = PROJECT_ROOT / "data"

    # Векторная БД (Chroma)
    vectordb_chroma_dir: Path = data_dir / "vectordb" / "chroma"
    vectordb_collection_prefix: str = field(
        default_factory=lambda: os.getenv("VECTORDB_COLLECTION_PREFIX", "rag_docs")
    )

    # Трейсинг (SQLite)
    tracing_db_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("TRACING_DB_PATH", str(PROJECT_ROOT / "data" / "tracing" / "traces.db"))
        )
    )

    # Mock inbox (локальный "ящик входящих")
    inbox_file: Path = data_dir / "inbox" / "support_inbox.jsonl"

    # Лучшая конфигурация чанков
    chunking_config_path: Path = data_dir / "chunking" / "best_chunk_config.json"
    categories_config_path: Path = field(
        default_factory=lambda: Path(
            os.getenv("CATEGORIES_CONFIG_PATH", str(PROJECT_ROOT / "config" / "categories.yml"))
        )
    )
    provider_registry_path: Path = field(
        default_factory=lambda: Path(
            os.getenv(
                "PROVIDER_REGISTRY_PATH",
                str(PROJECT_ROOT / "config" / "providers.yml"),
            )
        )
    )
    # --- Настройки LLM (Ollama / локальная модель) ---
    llm_provider_profile: str = field(
        default_factory=lambda: os.getenv("LLM_PROVIDER_PROFILE", "local-first").strip()
        or "local-first"
    )
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model_name: str = os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")
    ollama_fast_model_name: str = field(
        default_factory=lambda: os.getenv(
            "OLLAMA_FAST_MODEL_NAME", "llama3.2:3b"
        )
    )
    ingestion_categorizer_model: str = field(
        default_factory=lambda: os.getenv(
            "INGESTION_CATEGORIZER_MODEL", "llama3.2:3b"
        )
    )
    model_routing_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "MODEL_ROUTING_ENABLED", "false"
        ).strip().lower() in ("1", "true", "yes")
    )
    llm_input_price_per_1m_tokens: float = field(
        default_factory=lambda: float(os.getenv("LLM_INPUT_PRICE_PER_1M_TOKENS", "0.0") or "0.0")
    )
    llm_output_price_per_1m_tokens: float = field(
        default_factory=lambda: float(os.getenv("LLM_OUTPUT_PRICE_PER_1M_TOKENS", "0.0") or "0.0")
    )
    llm_model_prices: dict[str, dict[str, float]] = field(
        default_factory=_load_llm_model_prices
    )
    llm_benchmark_allow_paid_apis: bool = field(
        default_factory=lambda: os.getenv(
            "LLM_BENCHMARK_ALLOW_PAID_APIS", "false"
        ).strip().lower() in ("1", "true", "yes")
    )
    daily_cost_limit_usd: float = field(
        default_factory=lambda: float(os.getenv("DAILY_COST_LIMIT_USD", "5.0") or "5.0")
    )
    gracekelly_base_url: str = field(
        default_factory=lambda: os.getenv("GRACEKELLY_BASE_URL", "http://127.0.0.1:8011")
    )
    gracekelly_api_key_env: str = field(
        default_factory=lambda: os.getenv("GRACEKELLY_API_KEY_ENV", "GRACEKELLY_API_KEY")
    )
    gracekelly_health_check_timeout_sec: float = field(
        default_factory=lambda: float(os.getenv("GRACEKELLY_HEALTH_CHECK_TIMEOUT_SEC", "2.0") or "2.0")
    )
    gracekelly_request_timeout_sec: float = field(
        default_factory=lambda: float(os.getenv("GRACEKELLY_REQUEST_TIMEOUT_SEC", "30.0") or "30.0")
    )
    failover_chain_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "FAILOVER_CHAIN_ENABLED", "true"
        ).strip().lower() in ("1", "true", "yes")
    )
    failover_fallback_cache_seconds: int = field(
        default_factory=lambda: int(os.getenv("FAILOVER_FALLBACK_CACHE_SECONDS", "300") or "300")
    )

    # --- Embedding Model ---
    # "BAAI/bge-m3"                           — лучший universal (100+ языков, 1024d, 570M)
    # "paraphrase-multilingual-MiniLM-L12-v2" — быстрый multilingual (50+ языков, 384d, 118M)
    # "all-MiniLM-L6-v2"                      — легковес (English-only, 384d, 22M)
    embedding_model: str = os.getenv("RAG_EMBEDDING_MODEL", "BAAI/bge-m3")

    # --- Reranker (Cross-Encoder) ---
    # "cross-encoder/ms-marco-MiniLM-L-6-v2"  — быстрый на CPU (22M, English)
    # "BAAI/bge-reranker-v2-m3"               — multilingual (pairs с BGE-M3)
    # ""                                      — отключить reranker
    reranker_model: str = os.getenv("RAG_RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    # --- Hybrid Search ---
    # Включить BM25 + vector hybrid search (Reciprocal Rank Fusion)
    hybrid_search: bool = os.getenv("RAG_HYBRID_SEARCH", "true").strip().lower() in ("1", "true", "yes")

    # Retrieval parameters
    retrieval_top_k: int = int(os.getenv("RAG_RETRIEVAL_TOP_K", "20"))   # candidates before reranking
    rerank_top_k: int = int(os.getenv("RAG_RERANK_TOP_K", "5"))          # final docs after reranking
    rrf_k: int = int(os.getenv("RRF_K", "60"))
    rrf_doc_key_chars: int = int(os.getenv("RRF_DOC_KEY_CHARS", "200"))
    quality_threshold: int = int(os.getenv("QUALITY_THRESHOLD", "80"))
    chunk_size: int = int(os.getenv("CHUNK_SIZE") or os.getenv("RAG_CHUNK_SIZE") or "800")
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP") or os.getenv("RAG_CHUNK_OVERLAP") or "200")
    api_default_page_size: int = int(os.getenv("API_DEFAULT_PAGE_SIZE", "50"))
    agent_max_tool_loops: int = int(os.getenv("AGENT_MAX_TOOL_LOOPS", "5"))
    escalation_threshold: float = float(os.getenv("ESCALATION_THRESHOLD", "0.7"))

    # --- Level 2: Semantic Chunking ---
    semantic_chunking: bool = os.getenv("RAG_SEMANTIC_CHUNKING", "true").strip().lower() in ("1", "true", "yes")
    contextual_headers: bool = field(
        default_factory=lambda: os.getenv(
            "RAG_CONTEXTUAL_HEADERS", "true"
        ).strip().lower() in ("1", "true", "yes")
    )
    ingestion_batch_enabled: bool = field(
        default_factory=lambda: os.getenv("INGESTION_BATCH_ENABLED", "false").strip().lower()
        in ("1", "true", "yes")
    )
    agentic_mode: bool = field(
        default_factory=lambda: os.getenv(
            "RAG_AGENTIC_MODE", "false"
        ).strip().lower() in ("1", "true", "yes")
    )

    # --- HyDE (Hypothetical Document Embeddings) ---
    hyde: bool = field(
        default_factory=lambda: os.getenv("RAG_HYDE", "false").strip().lower() in ("1", "true", "yes")
    )
    streaming_enabled: bool = field(
        default_factory=lambda: os.getenv("STREAMING_ENABLED", "false").strip().lower()
        in ("1", "true", "yes")
    )

    # --- Parent-Child Chunking ---
    parent_child: bool = field(
        default_factory=lambda: os.getenv("RAG_PARENT_CHILD", "false").strip().lower() in ("1", "true", "yes")
    )

    # --- Level 2: Self-RAG ---
    self_rag_max_iterations: int = int(os.getenv("RAG_SELF_RAG_MAX_ITER", "2"))
    self_rag_min_quality: int = int(os.getenv("RAG_SELF_RAG_MIN_QUALITY", "70"))
    fact_verification_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "FACT_VERIFICATION_ENABLED", "true"
        ).strip().lower() in ("1", "true", "yes")
    )
    fact_verify_consensus_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "FACT_VERIFY_CONSENSUS_ENABLED", "false"
        ).strip().lower() in ("1", "true", "yes")
    )
    fact_verify_reliability_level: str = field(
        default_factory=lambda: os.getenv("FACT_VERIFY_RELIABILITY_LEVEL", "standard").strip()
        or "standard"
    )
    fact_verification_min_score: int = field(
        default_factory=lambda: int(os.getenv("FACT_VERIFICATION_MIN_SCORE", "70"))
    )

    # --- Auto-rollback (task-155) ---
    auto_rollback_enabled: bool = field(
        default_factory=lambda: os.getenv("AUTO_ROLLBACK_ENABLED", "false").strip().lower()
        in ("1", "true", "yes")
    )
    rollback_drift_threshold_pct: float = field(
        default_factory=lambda: float(os.getenv("ROLLBACK_DRIFT_THRESHOLD_PCT", "10.0"))
    )
    rollback_trace_window: int = field(
        default_factory=lambda: int(os.getenv("ROLLBACK_TRACE_WINDOW", "1000"))
    )
    tenant_admin_email: str = field(
        default_factory=lambda: os.getenv("TENANT_ADMIN_EMAIL", "").strip()
    )

    # --- Recommendations (task-157) ---
    recommendations_enabled: bool = field(
        default_factory=lambda: os.getenv("RECOMMENDATIONS_ENABLED", "true").strip().lower()
        in ("1", "true", "yes")
    )

    # --- Experiment assignment sticky rollout (task-154 future) ---
    experiment_assignment_enabled: bool = field(
        default_factory=lambda: os.getenv("EXPERIMENT_ASSIGNMENT_ENABLED", "false").strip().lower()
        in ("1", "true", "yes")
    )

    # --- Backup / restore (task-159, 163) ---
    backup_dir: str = field(
        default_factory=lambda: os.getenv("BACKUP_DIR", "").strip()
    )
    backup_retention_days: int = field(
        default_factory=lambda: int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
    )

    # --- Curated dataset staleness (task-156 close-out) ---
    curated_case_stale_days: int = field(
        default_factory=lambda: int(os.getenv("CURATED_CASE_STALE_DAYS", "180"))
    )

    slow_trace_threshold_ms: int = int(os.getenv("SLOW_TRACE_THRESHOLD_MS", "10000"))
    threshold_analysis_min_labels: int = int(os.getenv("THRESHOLD_ANALYSIS_MIN_LABELS", "20"))
    review_queue_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "REVIEW_QUEUE_ENABLED", "true"
        ).strip().lower() in ("1", "true", "yes")
    )
    online_evaluators_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "ONLINE_EVALUATORS_ENABLED", "true"
        ).strip().lower() in ("1", "true", "yes")
    )
    regression_gate_max_regressions: int = field(
        default_factory=lambda: int(os.getenv("REGRESSION_GATE_MAX_REGRESSIONS", "2"))
    )
    regression_gate_min_pass_rate: float = field(
        default_factory=lambda: float(os.getenv("REGRESSION_GATE_MIN_PASS_RATE", "0.85"))
    )

    # --- Backend векторного хранилища ---
    # "chroma" (по умолчанию) или "qdrant"
    backlog_weight_review_bad: float = field(
        default_factory=lambda: float(os.getenv("BACKLOG_WEIGHT_REVIEW_BAD", "3.0"))
    )
    backlog_weight_thumbs_down: float = field(
        default_factory=lambda: float(os.getenv("BACKLOG_WEIGHT_THUMBS_DOWN", "2.0"))
    )
    backlog_weight_slow: float = field(
        default_factory=lambda: float(os.getenv("BACKLOG_WEIGHT_SLOW", "1.5"))
    )
    backlog_weight_freshness: float = field(
        default_factory=lambda: float(os.getenv("BACKLOG_WEIGHT_FRESHNESS", "1.0"))
    )
    backlog_weight_evaluator_drift: float = field(
        default_factory=lambda: float(os.getenv("BACKLOG_WEIGHT_EVALUATOR_DRIFT", "2.5"))
    )
    backlog_max_items: int = field(
        default_factory=lambda: int(os.getenv("BACKLOG_MAX_ITEMS", "30"))
    )
    backlog_freshness_max_days: int = field(
        default_factory=lambda: int(os.getenv("BACKLOG_FRESHNESS_MAX_DAYS", "90"))
    )
    backlog_email_enabled: bool = field(
        default_factory=lambda: os.getenv(
            "BACKLOG_EMAIL_ENABLED", "false"
        ).strip().lower() in ("1", "true", "yes")
    )
    tenant_admin_email: str = field(
        default_factory=lambda: os.getenv("TENANT_ADMIN_EMAIL", "")
    )
    vector_backend: str = os.getenv("RAG_VECTOR_BACKEND", "chroma").strip().lower()

    # --- Куда слать эскалации (SupportSink) ---
    # "local" (LocalFileSupportSink) или "bitrix" (BitrixSupportSink)
    support_sink_backend: str = os.getenv("SUPPORT_SINK_BACKEND", "local").strip().lower()

    # Полный URL вебхука Bitrix24, например:
    # https://example.bitrix24.ru/rest/123/abcdefg123456/crm.timeline.comment.add.json
    bitrix_webhook_url: Optional[str] = os.getenv("BITRIX_WEBHOOK_URL") or None
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    google_oidc_client_id: Optional[str] = field(
        default_factory=lambda: os.getenv("GOOGLE_OIDC_CLIENT_ID") or None
    )
    google_oidc_client_secret: SecretStr | None = field(
        default_factory=lambda: (lambda value: SecretStr(value) if value else None)(
            os.getenv("GOOGLE_OIDC_CLIENT_SECRET")
        )
    )
    azure_oidc_tenant: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OIDC_TENANT") or None
    )
    azure_oidc_client_id: Optional[str] = field(
        default_factory=lambda: os.getenv("AZURE_OIDC_CLIENT_ID") or None
    )
    azure_oidc_client_secret: SecretStr | None = field(
        default_factory=lambda: (lambda value: SecretStr(value) if value else None)(
            os.getenv("AZURE_OIDC_CLIENT_SECRET")
        )
    )
    tenant_email_domains: str = field(
        default_factory=lambda: os.getenv("TENANT_EMAIL_DOMAINS", "")
    )
    llm_cost_per_1m_tokens: str = field(
        default_factory=lambda: os.getenv("LLM_COST_PER_1M_TOKENS", "")
    )
    report_slack_webhook: str = field(
        default_factory=lambda: os.getenv("REPORT_SLACK_WEBHOOK", "")
    )
    report_email_recipients: list[str] = field(
        default_factory=lambda: [
            item.strip()
            for item in os.getenv("REPORT_EMAIL_RECIPIENTS", "").split(",")
            if item.strip()
        ]
    )
    report_smtp_host: str = field(
        default_factory=lambda: os.getenv("REPORT_SMTP_HOST", os.getenv("SMTP_HOST", ""))
    )
    report_smtp_port: int = field(
        default_factory=lambda: int(os.getenv("REPORT_SMTP_PORT", os.getenv("SMTP_PORT", "587") or "587"))
    )
    report_smtp_user: str = field(
        default_factory=lambda: os.getenv("REPORT_SMTP_USER", os.getenv("SMTP_USER", ""))
    )
    report_smtp_pass: SecretStr | None = field(
        default_factory=lambda: (lambda value: SecretStr(value) if value else None)(
            os.getenv("REPORT_SMTP_PASS", os.getenv("SMTP_PASS", ""))
        )
    )
    email_channel_mode: str = field(
        default_factory=lambda: os.getenv("EMAIL_CHANNEL_MODE", "disabled").strip().lower()
    )
    imap_host: str = field(
        default_factory=lambda: os.getenv("IMAP_HOST", "")
    )
    imap_port: int = field(
        default_factory=lambda: int(os.getenv("IMAP_PORT", "993"))
    )
    imap_user: str = field(
        default_factory=lambda: os.getenv("IMAP_USER", "")
    )
    imap_pass: SecretStr | None = field(
        default_factory=lambda: (lambda value: SecretStr(value) if value else None)(
            os.getenv("IMAP_PASSWORD", os.getenv("IMAP_PASS", ""))
        )
    )
    imap_folder: str = field(
        default_factory=lambda: os.getenv("IMAP_FOLDER", "INBOX")
    )
    imap_poll_interval_sec: int = field(
        default_factory=lambda: int(os.getenv("IMAP_POLL_INTERVAL_SEC", "60"))
    )
    smtp_host: str = field(
        default_factory=lambda: os.getenv("SMTP_HOST", "")
    )
    smtp_port: int = field(
        default_factory=lambda: int(os.getenv("SMTP_PORT", "587"))
    )
    smtp_user: str = field(
        default_factory=lambda: os.getenv("SMTP_USER", "")
    )
    smtp_pass: SecretStr | None = field(
        default_factory=lambda: (lambda value: SecretStr(value) if value else None)(
            os.getenv("SMTP_PASSWORD", os.getenv("SMTP_PASS", ""))
        )
    )
    smtp_from_address: str = field(
        default_factory=lambda: os.getenv("SMTP_FROM_ADDRESS", "support@example.com")
    )
    email_webhook_secret: SecretStr | None = field(
        default_factory=lambda: (lambda value: SecretStr(value) if value else None)(
            os.getenv("EMAIL_WEBHOOK_SIGNING_SECRET", os.getenv("EMAIL_WEBHOOK_SECRET", ""))
        )
    )
    email_webhook_signing_secret: SecretStr | None = field(
        default_factory=lambda: (lambda value: SecretStr(value) if value else None)(
            os.getenv("EMAIL_WEBHOOK_SIGNING_SECRET", os.getenv("EMAIL_WEBHOOK_SECRET", ""))
        )
    )
    session_secret_key: str = field(
        default_factory=lambda: os.getenv("SESSION_SECRET_KEY")
        or os.getenv("JWT_SECRET", "dev-secret-change-in-production!")
    )
    otel_enabled: bool = field(
        default_factory=lambda: os.getenv("OTEL_ENABLED", "false").strip().lower()
        in ("1", "true", "yes")
    )
    otel_exporter_otlp_endpoint: str = field(
        default_factory=lambda: os.getenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
        )
    )
    otel_service_name: str = field(
        default_factory=lambda: os.getenv(
            "OTEL_SERVICE_NAME", "rag-support-assistant"
        )
    )

    # --- Продакшн-режим ---
    # REQUIRE_OLLAMA=true → fail fast если Ollama недоступна при старте.
    # По умолчанию false, чтобы не ломать локальную разработку без LLM.
    require_ollama: bool = os.getenv("REQUIRE_OLLAMA", "false").strip().lower() in ("1", "true", "yes")
    circuit_breaker_enabled: bool = os.getenv(
        "CIRCUIT_BREAKER_ENABLED", "true"
    ).strip().lower() in ("1", "true", "yes")
    circuit_breaker_failure_threshold: int = int(
        os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
    )
    circuit_breaker_reset_timeout_sec: float = float(
        os.getenv("CIRCUIT_BREAKER_RESET_TIMEOUT_SEC", "30")
    )
    ollama_retry_max_attempts: int = int(
        os.getenv("OLLAMA_RETRY_MAX_ATTEMPTS", "3")
    )
    ollama_retry_base_delay_sec: float = float(
        os.getenv("OLLAMA_RETRY_BASE_DELAY_SEC", "0.5")
    )
    ollama_retry_max_delay_sec: float = float(
        os.getenv("OLLAMA_RETRY_MAX_DELAY_SEC", "5.0")
    )
    ollama_retry_jitter: bool = os.getenv(
        "OLLAMA_RETRY_JITTER", "true"
    ).strip().lower() in ("1", "true", "yes")
    ollama_request_timeout_sec: float = field(
        default_factory=lambda: float(os.getenv("OLLAMA_REQUEST_TIMEOUT_SEC", "60"))
    )
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "7200"))
    trace_retention_days: int = field(
        default_factory=lambda: int(os.getenv("TRACE_RETENTION_DAYS", "90"))
    )
    trace_purge_interval_sec: int = field(
        default_factory=lambda: int(os.getenv("TRACE_PURGE_INTERVAL_SEC", "86400"))
    )
    audit_retention_days: int = field(
        default_factory=lambda: int(os.getenv("AUDIT_RETENTION_DAYS", "180"))
    )
    audit_purge_interval_sec: int = field(
        default_factory=lambda: int(os.getenv("AUDIT_PURGE_INTERVAL_SEC", "86400"))
    )
    request_timeout_sec: float = float(
        os.getenv("REQUEST_TIMEOUT_SEC", "30")
    )
    max_concurrent_pipelines: int = int(
        os.getenv("MAX_CONCURRENT_PIPELINES", "8")
    )
    pipeline_acquire_timeout_sec: float = float(
        os.getenv("PIPELINE_ACQUIRE_TIMEOUT_SEC", "0.5")
    )
    shutdown_ready_delay_sec: float = float(
        os.getenv("SHUTDOWN_READY_DELAY_SEC", "5")
    )
    api_key: str = os.getenv("API_KEY", "")
    langfuse_public_key: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    langfuse_secret_key: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    langfuse_host: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    db_encryption_key: SecretStr = field(
        default_factory=lambda: SecretStr(os.getenv("DB_ENCRYPTION_KEY", ""))
    )
    llm_cache_enabled: bool = field(
        default_factory=lambda: os.getenv("LLM_CACHE_ENABLED", "false").strip().lower() in ("1", "true", "yes")
    )
    llm_cache_ttl_seconds: int = field(
        default_factory=lambda: int(os.getenv("LLM_CACHE_TTL_SECONDS", "3600"))
    )
    rag_env: str = field(
        default_factory=lambda: os.getenv("RAG_ENV", "development").strip().lower()
    )
    # CORS: список допустимых origins через запятую.
    # "*" = разрешить всё (только для dev). Пример: "https://app.example.com,https://admin.example.com"
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "*").split(",")
            if o.strip()
        ]
    )
    cors_max_age_sec: int = field(
        default_factory=lambda: int(os.getenv("CORS_MAX_AGE_SEC", "600"))
    )
    max_request_body_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_REQUEST_BODY_BYTES", str(1 * 1024 * 1024)))
    )
    max_upload_bytes: int = field(
        default_factory=lambda: int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
    )

    def ensure_dirs(self) -> None:
        """
        Создаёт при необходимости директории под data/ и вложенные пути.

        Можно вызывать один раз при старте приложения (в on_startup),
        чтобы не дублировать mkdir(..., exist_ok=True) по всему коду.
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.vectordb_chroma_dir.mkdir(parents=True, exist_ok=True)
        self.tracing_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.inbox_file.parent.mkdir(parents=True, exist_ok=True)
        self.chunking_config_path.parent.mkdir(parents=True, exist_ok=True)

    def validate(self) -> None:
        """
        Проверяет доступность критичных зависимостей при старте.

        Если REQUIRE_OLLAMA=true и Ollama недоступна — поднимает RuntimeError.
        Если REQUIRE_OLLAMA=false (по умолчанию) — только предупреждение.
        """
        import logging
        import urllib.request
        import urllib.error

        log = logging.getLogger(__name__)

        if self.rag_env == "production" and ("*" in self.cors_origins or self.cors_origins == []):
            raise RuntimeError(
                "\nERROR: CORS_ORIGINS='*' (or empty) is not allowed in production.\n"
                "       Set CORS_ORIGINS to an explicit comma-separated list of allowed origins,\n"
                "       e.g. CORS_ORIGINS='https://app.example.com,https://admin.example.com'\n"
                f"       Current RAG_ENV={self.rag_env}, CORS_ORIGINS={self.cors_origins}"
            )
        if self.rag_env == "production" and not self.db_encryption_key.get_secret_value():
            raise RuntimeError(
                "\nERROR: DB_ENCRYPTION_KEY is required in production.\n"
                "       Set DB_ENCRYPTION_KEY to a strong secret stored outside git."
            )
        if self.rag_env != "production" and not self.db_encryption_key.get_secret_value():
            log.warning(
                "DB_ENCRYPTION_KEY is not set; encryption operations will fail. "
                "Set it in .env for local dev — see .env.example."
            )

        # Production secrets fail-fast (Codex audit 2026-04-27 P0).
        # Без этих проверок production принимает admin/admin и подписывает
        # токены известным repo default'ом.
        if self.rag_env == "production":
            _DEV_SECRET = "dev-secret-change-in-production!"
            jwt_secret = (os.getenv("JWT_SECRET", "") or "").strip()
            if not jwt_secret or jwt_secret == _DEV_SECRET:
                raise RuntimeError(
                    "\nERROR: JWT_SECRET is required in production and must not be the dev default.\n"
                    "       Set JWT_SECRET to a strong random value (>= 32 chars) outside git.\n"
                    "       Generate with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
                )
            if len(jwt_secret) < 32:
                raise RuntimeError(
                    "\nERROR: JWT_SECRET is too short for production (got %d chars, need >= 32).\n"
                    "       Use python -c \"import secrets; print(secrets.token_urlsafe(48))\"."
                    % len(jwt_secret)
                )

            session_secret = (
                os.getenv("SESSION_SECRET_KEY", "") or os.getenv("JWT_SECRET", "") or ""
            ).strip()
            if not session_secret or session_secret == _DEV_SECRET:
                raise RuntimeError(
                    "\nERROR: SESSION_SECRET_KEY is required in production and must not be the dev default.\n"
                    "       Set SESSION_SECRET_KEY to a strong random value (>= 32 chars)."
                )

            admin_hash = (os.getenv("ADMIN_PASSWORD_HASH", "") or "").strip()
            allow_dev_admin = (
                os.getenv("ALLOW_DEV_ADMIN_LOGIN", "").strip().lower()
                in ("1", "true", "yes")
            )
            if not admin_hash and not allow_dev_admin:
                raise RuntimeError(
                    "\nERROR: ADMIN_PASSWORD_HASH is required in production.\n"
                    "       Without it, /api/auth/login accepts admin/admin as a valid credential.\n"
                    "       Generate a bcrypt hash and set ADMIN_PASSWORD_HASH, or set\n"
                    "       ALLOW_DEV_ADMIN_LOGIN=1 to acknowledge the risk explicitly."
                )

        try:
            from config.provider_schema import load_provider_registry

            provider_registry = load_provider_registry(self.provider_registry_path)
        except Exception as exc:
            raise RuntimeError(
                "\nERROR: Failed to load provider registry.\n"
                f"       Path: {self.provider_registry_path}\n"
                f"       Reason: {exc}"
            ) from exc

        if self.llm_provider_profile not in provider_registry.routing_profiles:
            available_profiles = ", ".join(sorted(provider_registry.routing_profiles))
            raise RuntimeError(
                f"\nERROR: Unknown LLM_PROVIDER_PROFILE='{self.llm_provider_profile}'.\n"
                f"       Available profiles: {available_profiles}"
            )

        required_env_vars: list[str] = []
        active_profile = provider_registry.get_profile(self.llm_provider_profile)
        for target in (active_profile.fast, active_profile.strong):
            provider = provider_registry.get_provider(target.provider)
            if provider is None or provider.kind != "paid":
                continue
            raw_api_key = (os.getenv(provider.api_key_env or "", "") or "").strip()
            if provider.api_key_env and (
                not raw_api_key
                or raw_api_key.lower() in {"changeme", "change-me", "change_me"}
            ):
                required_env_vars.append(provider.api_key_env)

        if required_env_vars:
            missing = ", ".join(sorted(set(required_env_vars)))
            raise RuntimeError(
                f"\nERROR: LLM provider profile '{self.llm_provider_profile}' requires paid provider credentials.\n"
                f"       Missing env vars: {missing}\n"
                "       Set the required keys in .env or switch to LLM_PROVIDER_PROFILE=local-first."
            )

        # Проверка Ollama
        ollama_ok = False
        try:
            req = urllib.request.Request(
                f"{self.ollama_base_url}/api/tags",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=3):
                ollama_ok = True
        except Exception as exc:
            if self.require_ollama:
                raise RuntimeError(
                    f"\nERROR: Cannot connect to Ollama at {self.ollama_base_url}\n"
                    f"       Причина: {exc}\n"
                    f"       Запустите Ollama: ollama serve\n"
                    f"       Затем: ollama pull {self.ollama_model_name}\n"
                ) from exc
            log.warning(
                "Ollama недоступна по адресу %s (%s). "
                "Установите REQUIRE_OLLAMA=true для fail-fast в продакшне.",
                self.ollama_base_url,
                exc,
            )

        if ollama_ok:
            log.info("Ollama доступна: %s", self.ollama_base_url)

        # Проверка директории ChromaDB
        try:
            self.vectordb_chroma_dir.mkdir(parents=True, exist_ok=True)
            log.info("ChromaDB директория: %s", self.vectordb_chroma_dir)
        except Exception as exc:
            log.error("Не удалось создать директорию ChromaDB: %s", exc)


# Ленивая инициализация синглтона настроек
_settings: Settings | None = None


def get_settings() -> Settings:
    """
    Возвращает singleton Settings.

    Пример использования:

        from config.settings import get_settings

        settings = get_settings()
        print(settings.data_dir)
    """
    global _settings
    if _settings is None:
        _settings = Settings()
        _apply_deployed_settings(_settings)
        experiment_id = (os.getenv("EXPERIMENT_ID", "") or "").strip()
        if experiment_id:
            payload = _load_experiment_override_payload()
            configured_id = str(payload.get("experiment_id") or "")
            if not configured_id or configured_id == experiment_id:
                overrides = payload.get("settings_overrides") or {}
                if isinstance(overrides, dict):
                    _apply_settings_overrides(_settings, overrides)
        _settings.ensure_dirs()
    return _settings
