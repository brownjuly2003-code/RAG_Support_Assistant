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
from dataclasses import dataclass
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
    ollama_model_name: str = os.getenv("OLLAMA_MODEL_NAME", "mistral")

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
    semantic_chunking: bool = os.getenv("RAG_SEMANTIC_CHUNKING", "false").strip().lower() in ("1", "true", "yes")

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
