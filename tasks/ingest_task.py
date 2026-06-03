"""Background task: ingest document into vector store."""
from __future__ import annotations

import logging
from pathlib import Path

from tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tasks.ingest_document")
def ingest_document(self, file_path: str) -> dict:
    """Load and index documents from the upload directory."""
    self.update_state(state="PROCESSING", meta={"step": "loading"})

    path = Path(file_path)
    if not path.exists():
        return {"status": "error", "message": f"File not found: {file_path}"}

    try:
        from ingestion.loader import DocumentLoader

        loader = DocumentLoader(recursive=False)
        docs = loader.load_documents(str(path.parent))
    except Exception as exc:
        logger.error("Loading failed for %s: %s", file_path, exc, exc_info=True)
        return {"status": "error", "message": f"Loading failed: {exc}"}

    if not docs:
        return {"status": "partial", "docs_count": 0, "message": "No text content extracted"}

    self.update_state(state="PROCESSING", meta={"step": "indexing", "docs_count": len(docs)})

    try:
        from config.settings import get_settings
        from vectordb.manager import build_vector_store, get_embeddings

        settings = get_settings()
        chunk_config = {
            "chunk_size": getattr(settings, "chunk_size", 800),
            "chunk_overlap": getattr(settings, "chunk_overlap", 200),
        }
        embeddings = get_embeddings()
        build_vector_store(docs, chunk_config, embeddings=embeddings)
    except Exception as exc:
        logger.error("Indexing failed for %s: %s", file_path, exc, exc_info=True)
        return {"status": "error", "message": f"Indexing failed: {exc}"}

    return {
        "status": "ok",
        "docs_count": len(docs),
        "message": f"Indexed {len(docs)} document(s) from {path.name}",
    }
