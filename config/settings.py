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

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Определяем корень проекта как родительскую директорию для config/
PROJECT_ROOT = Path(__file__).resolve().parent.parent


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

    # Трейсинг (SQLite)
    tracing_db_path: Path = data_dir / "tracing" / "traces.db"

    # Mock inbox (локальный "ящик входящих")
    inbox_file: Path = data_dir / "inbox" / "support_inbox.jsonl"

    # Лучшая конфигурация чанков
    chunking_config_path: Path = data_dir / "chunking" / "best_chunk_config.json"

    # --- Настройки LLM (Ollama / локальная модель) ---
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model_name: str = os.getenv("OLLAMA_MODEL_NAME", "qwen2.5:7b")

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

    # --- Level 2: Semantic Chunking ---
    semantic_chunking: bool = os.getenv("RAG_SEMANTIC_CHUNKING", "true").strip().lower() in ("1", "true", "yes")

    # --- HyDE (Hypothetical Document Embeddings) ---
    hyde: bool = field(
        default_factory=lambda: os.getenv("RAG_HYDE", "false").strip().lower() in ("1", "true", "yes")
    )

    # --- Parent-Child Chunking ---
    parent_child: bool = field(
        default_factory=lambda: os.getenv("RAG_PARENT_CHILD", "false").strip().lower() in ("1", "true", "yes")
    )

    # --- Level 2: Self-RAG ---
    self_rag_max_iterations: int = int(os.getenv("RAG_SELF_RAG_MAX_ITER", "2"))
    self_rag_min_quality: int = int(os.getenv("RAG_SELF_RAG_MIN_QUALITY", "70"))

    # --- Backend векторного хранилища ---
    # "chroma" (по умолчанию) или "qdrant"
    vector_backend: str = os.getenv("RAG_VECTOR_BACKEND", "chroma").strip().lower()

    # --- Куда слать эскалации (SupportSink) ---
    # "local" (LocalFileSupportSink) или "bitrix" (BitrixSupportSink)
    support_sink_backend: str = os.getenv("SUPPORT_SINK_BACKEND", "local").strip().lower()

    # Полный URL вебхука Bitrix24, например:
    # https://example.bitrix24.ru/rest/123/abcdefg123456/crm.timeline.comment.add.json
    bitrix_webhook_url: Optional[str] = os.getenv("BITRIX_WEBHOOK_URL") or None
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

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
    # CORS: список допустимых origins через запятую.
    # "*" = разрешить всё (только для dev). Пример: "https://app.example.com,https://admin.example.com"
    cors_origins: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.getenv("CORS_ORIGINS", "*").split(",")
            if o.strip()
        ]
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
        _settings.ensure_dirs()
    return _settings
