"""
ingestion/pipeline.py

IngestPipeline: end-to-end document ingestion.

    1. Loads documents from a directory via DocumentLoader.
    2. Builds (or updates) the vector store via manager.build_vector_store().
    3. Logs ingestion metadata to ``data/ingestion_log.json``.
"""

from __future__ import annotations

import json
import inspect
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from langchain_core.documents import Document
except ImportError:
    try:
        from langchain.schema import Document  # type: ignore[no-redef]
    except ImportError:
        from dataclasses import dataclass as _dc

        @_dc
        class Document:  # type: ignore[no-redef]
            page_content: str
            metadata: Dict[str, Any]

from ingestion.loader import DocumentLoader
from ingestion.categorizer import annotate_documents_with_categories
import manager as legacy_manager
import vectordb.manager as tenant_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Resolve project paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOG_PATH = _PROJECT_ROOT / "data" / "ingestion_log.json"
_ORIGINAL_LEGACY_BUILD_VECTOR_STORE = legacy_manager.build_vector_store


class IngestPipeline:
    """Orchestrates document loading and vector-store building.

    Usage::

        pipeline = IngestPipeline()
        store, chunks = pipeline.ingest("path/to/docs")

        # Add a single file later without full rebuild:
        store, chunks = pipeline.add_document("path/to/new_file.pdf")
    """

    def __init__(
        self,
        log_path: str | Path | None = None,
        recursive: bool = True,
    ) -> None:
        """
        Args:
            log_path: where to write ``ingestion_log.json``.
                      Defaults to ``<project_root>/data/ingestion_log.json``.
            recursive: whether DocumentLoader scans sub-directories.
        """
        self.log_path = Path(log_path) if log_path else _DEFAULT_LOG_PATH
        self.loader = DocumentLoader(recursive=recursive)

        # Cached state from the last ingest/add_document call
        self._documents: List[Document] = []
        self._store: Any = None
        self._chunks: List[Document] = []
        self._last_batch_contextual_headers: Dict[str, Any] = {"mode": "disabled"}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        docs_dir: str | Path,
        chunk_config: Optional[Dict[str, int]] = None,
        embeddings: Any = None,
        use_semantic_chunking: bool = False,
        tenant_id: str = "default",
    ) -> tuple[Any, List[Document]]:
        """Run the full ingestion pipeline.

        Args:
            docs_dir: path to the directory with source documents.
            chunk_config: ``{"chunk_size": int, "chunk_overlap": int}``.
                          Defaults to ``{"chunk_size": 800, "chunk_overlap": 200}``.
            embeddings: optional pre-built embedding model.
            use_semantic_chunking: enable semantic splitting (Level 2).

        Returns:
            ``(vector_store, chunks)`` -- the built store and the chunk list.
        """
        from config.settings import get_settings

        if chunk_config is None:
            settings = get_settings()
            chunk_config = {
                "chunk_size": getattr(settings, "chunk_size", 800),
                "chunk_overlap": getattr(settings, "chunk_overlap", 200),
            }
        else:
            settings = get_settings()

        build_vector_store = tenant_manager.build_vector_store
        if legacy_manager.build_vector_store is not _ORIGINAL_LEGACY_BUILD_VECTOR_STORE:
            build_vector_store = legacy_manager.build_vector_store

        # Step 1 -- load documents
        docs = self.loader.load_documents(docs_dir)
        if not docs:
            raise ValueError(f"No documents found in {docs_dir}")
        annotate_documents_with_categories(docs, tenant_id=tenant_id)
        self._documents = docs
        self._last_batch_contextual_headers = {"mode": "disabled"}

        if getattr(settings, "ingestion_batch_enabled", False) and getattr(settings, "contextual_headers", False):
            try:
                from llm.providers import build_provider_runtime

                runtime = build_provider_runtime(settings)
            except Exception as exc:
                logger.warning("[IngestPipeline] Batch contextual headers unavailable: %s", exc)
            else:
                llm = runtime.strong
                if not (
                    callable(getattr(llm, "generate_batch", None))
                    or callable(getattr(llm, "generate", None))
                ):
                    llm = runtime.fast
                if (
                    callable(getattr(llm, "generate_batch", None))
                    or callable(getattr(llm, "generate", None))
                ):
                    batches = [
                        [
                            {
                                "role": "user",
                                "content": (
                                    "Write one concise contextual header under 30 words for retrieval. "
                                    "Return only the header text.\n\n"
                                    f"Source: {str((doc.metadata or {}).get('source') or 'unknown')}\n"
                                    f"Document excerpt:\n{str(doc.page_content or '')[:1500]}"
                                ),
                            }
                        ]
                        for doc in docs
                    ]
                    started = time.perf_counter()
                    try:
                        if bool(getattr(llm, "supports_batch", False)) and callable(
                            getattr(llm, "generate_batch", None)
                        ):
                            responses = llm.generate_batch(batches, purpose="contextual_headers")
                            mode = "provider_batch"
                        else:
                            responses = [llm.generate(messages) for messages in batches]
                            mode = "sequential_fallback"
                    except Exception as exc:
                        logger.warning("[IngestPipeline] Contextual header generation failed: %s", exc)
                    else:
                        for doc, response in zip(docs, responses):
                            header = str(getattr(response, "text", "") or "").strip()
                            if not header:
                                continue
                            header = header[:200]
                            doc.page_content = f"[Контекст: {header}]\n{doc.page_content}"
                            metadata = getattr(doc, "metadata", None)
                            if not isinstance(metadata, dict):
                                metadata = {}
                                setattr(doc, "metadata", metadata)
                            metadata["batch_contextual_header"] = header
                        duration_ms = round((time.perf_counter() - started) * 1000, 2)
                        self._last_batch_contextual_headers = {
                            "mode": mode,
                            "provider": getattr(llm, "provider_id", None),
                            "model": getattr(llm, "model_name", None),
                            "documents": len(docs),
                            "duration_ms": duration_ms,
                            "per_document_latency_ms": round(duration_ms / max(len(docs), 1), 2),
                        }

        # Step 2 -- build vector store
        build_params = inspect.signature(build_vector_store).parameters
        if "tenant_id" in build_params or any(
            param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            for param in build_params.values()
        ):
            store, chunks = build_vector_store(
                docs,
                chunk_config,
                embeddings=embeddings,
                use_semantic_chunking=use_semantic_chunking,
                tenant_id=tenant_id,
            )
        else:
            store, chunks = build_vector_store(
                docs,
                chunk_config,
                embeddings=embeddings,
                use_semantic_chunking=use_semantic_chunking,
            )
        self._store = store
        self._chunks = chunks

        # Step 3 -- write ingestion log
        self._write_log(docs, chunks, docs_dir, chunk_config)

        return store, chunks

    def add_document(
        self,
        file_path: str | Path,
        chunk_config: Optional[Dict[str, int]] = None,
        embeddings: Any = None,
        use_semantic_chunking: bool = False,
        tenant_id: str = "default",
    ) -> tuple[Any, List[Document]]:
        """Add a single file without rebuilding the entire store.

        The new document's chunks are appended to the existing chunk list
        and merged into the vector store.  If no previous ingest has been
        performed (i.e. ``self._documents`` is empty), a fresh store is
        built from just this file.

        Args:
            file_path: path to the file to add.
            chunk_config: chunking parameters (same default as ``ingest``).
            embeddings: optional embedding model.
            use_semantic_chunking: enable semantic splitting.

        Returns:
            ``(vector_store, chunks)`` -- updated store and full chunk list.
        """
        from config.settings import get_settings

        if chunk_config is None:
            settings = get_settings()
            chunk_config = {
                "chunk_size": getattr(settings, "chunk_size", 800),
                "chunk_overlap": getattr(settings, "chunk_overlap", 200),
            }

        build_vector_store = tenant_manager.build_vector_store
        if legacy_manager.build_vector_store is not _ORIGINAL_LEGACY_BUILD_VECTOR_STORE:
            build_vector_store = legacy_manager.build_vector_store

        new_docs = self.loader.load_single_file(file_path)
        if not new_docs:
            logger.warning("[IngestPipeline] No content extracted from %s", file_path)
            return self._store, self._chunks
        annotate_documents_with_categories(new_docs, tenant_id=tenant_id)

        self._documents.extend(new_docs)

        # Rebuild the store from all accumulated documents.
        # (A true incremental add would call vector_store.add_documents,
        #  but not every backend supports that uniformly, so a full
        #  rebuild is the safest approach for now.)
        build_params = inspect.signature(build_vector_store).parameters
        if "tenant_id" in build_params or any(
            param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
            for param in build_params.values()
        ):
            store, chunks = build_vector_store(
                self._documents,
                chunk_config,
                embeddings=embeddings,
                use_semantic_chunking=use_semantic_chunking,
                tenant_id=tenant_id,
            )
        else:
            store, chunks = build_vector_store(
                self._documents,
                chunk_config,
                embeddings=embeddings,
                use_semantic_chunking=use_semantic_chunking,
            )
        self._store = store
        self._chunks = chunks

        self._append_log_entry(new_docs, chunks, file_path, chunk_config)

        return store, chunks

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def documents(self) -> List[Document]:
        """Documents loaded so far."""
        return list(self._documents)

    @property
    def store(self) -> Any:
        """The last built vector store (or ``None``)."""
        return self._store

    @property
    def chunks(self) -> List[Document]:
        """Chunks produced by the last build."""
        return list(self._chunks)

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _write_log(
        self,
        docs: List[Document],
        chunks: List[Document],
        docs_dir: str | Path,
        chunk_config: Dict[str, int],
    ) -> None:
        """Write (overwrite) the full ingestion log."""
        entry = self._build_log_entry(docs, chunks, str(docs_dir), chunk_config)
        entry["batch_contextual_headers"] = dict(self._last_batch_contextual_headers)

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(
            json.dumps(entry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[IngestPipeline] Log written to %s", self.log_path)

    def _append_log_entry(
        self,
        new_docs: List[Document],
        all_chunks: List[Document],
        file_path: str | Path,
        chunk_config: Dict[str, int],
    ) -> None:
        """Append an ``add_document`` event to the existing log."""
        existing: Dict[str, Any] = {}
        if self.log_path.exists():
            try:
                existing = json.loads(
                    self.log_path.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                existing = {}

        additions = existing.get("additions", [])
        additions.append({
            "timestamp": datetime.now().isoformat(),
            "file": str(Path(file_path).resolve()),
            "documents_added": len(new_docs),
            "total_chunks_after": len(all_chunks),
            "chunk_config": chunk_config,
        })
        existing["additions"] = additions
        # Update top-level counts
        existing["total_documents"] = len(self._documents)
        existing["total_chunks"] = len(all_chunks)
        existing["last_updated"] = datetime.now().isoformat()

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("[IngestPipeline] Log updated at %s", self.log_path)

    @staticmethod
    def _build_log_entry(
        docs: List[Document],
        chunks: List[Document],
        docs_dir: str,
        chunk_config: Dict[str, int],
    ) -> Dict[str, Any]:
        file_list = []
        for doc in docs:
            meta = doc.metadata or {}
            file_list.append({
                "source": meta.get("source", "unknown"),
                "file_path": meta.get("file_path", ""),
                "file_type": meta.get("file_type", ""),
                "page": meta.get("page"),
            })

        return {
            "timestamp": datetime.now().isoformat(),
            "docs_dir": docs_dir,
            "chunk_config": chunk_config,
            "total_documents": len(docs),
            "total_chunks": len(chunks),
            "files": file_list,
            "additions": [],
        }
