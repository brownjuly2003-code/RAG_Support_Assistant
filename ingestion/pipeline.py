"""
ingestion/pipeline.py

IngestPipeline: end-to-end document ingestion.

    1. Loads documents from a directory via DocumentLoader.
    2. Builds (or updates) the vector store via manager.build_vector_store().
    3. Logs ingestion metadata to ``data/ingestion_log.json``.
"""

from __future__ import annotations

import json
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


# ---------------------------------------------------------------------------
# Resolve project paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOG_PATH = _PROJECT_ROOT / "data" / "ingestion_log.json"


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

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest(
        self,
        docs_dir: str | Path,
        chunk_config: Optional[Dict[str, int]] = None,
        embeddings: Any = None,
        use_semantic_chunking: bool = False,
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
        from manager import build_vector_store

        if chunk_config is None:
            chunk_config = {"chunk_size": 800, "chunk_overlap": 200}

        # Step 1 -- load documents
        docs = self.loader.load_documents(docs_dir)
        if not docs:
            raise ValueError(f"No documents found in {docs_dir}")
        self._documents = docs

        # Step 2 -- build vector store
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
        from manager import build_vector_store

        if chunk_config is None:
            chunk_config = {"chunk_size": 800, "chunk_overlap": 200}

        new_docs = self.loader.load_single_file(file_path)
        if not new_docs:
            print(f"[IngestPipeline] No content extracted from {file_path}")
            return self._store, self._chunks

        self._documents.extend(new_docs)

        # Rebuild the store from all accumulated documents.
        # (A true incremental add would call vector_store.add_documents,
        #  but not every backend supports that uniformly, so a full
        #  rebuild is the safest approach for now.)
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

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(
            json.dumps(entry, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[IngestPipeline] Log written to {self.log_path}")

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
        print(f"[IngestPipeline] Log updated at {self.log_path}")

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
