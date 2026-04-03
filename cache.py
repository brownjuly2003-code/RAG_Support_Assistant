"""
cache.py

Simple in-memory + disk cache for RAG responses.

Classes:
    RAGCache - LRU cache with optional disk persistence and TTL support.

Features:
    - In-memory LRU dict (max 100 entries by default)
    - Optional disk persistence to data/cache/responses.json
    - TTL support (default 1 hour)
    - Separate cache_retrieval(query, docs) for retrieval results
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _hash_key(text: str) -> str:
    """Create a stable hash key from a text string."""
    return hashlib.sha256(text.strip().lower().encode("utf-8")).hexdigest()[:32]


def _serialise_docs(docs: Any) -> List[Dict[str, Any]]:
    """Convert documents to JSON-serialisable dicts."""
    result: List[Dict[str, Any]] = []
    if not docs:
        return result
    for doc in docs:
        if hasattr(doc, "page_content"):
            result.append({
                "page_content": doc.page_content,
                "metadata": getattr(doc, "metadata", {}) or {},
            })
        elif isinstance(doc, dict):
            result.append(doc)
        else:
            result.append({"page_content": str(doc), "metadata": {}})
    return result


class RAGCache:
    """In-memory LRU cache with optional disk persistence for RAG responses.

    Usage::

        cache = RAGCache()

        # Check cache
        result = cache.get("What is error E20?")
        if result is None:
            result = run_pipeline(question)
            cache.put("What is error E20?", result)

        # Cache retrieval results separately
        cache.cache_retrieval("error E20", docs)
        cached_docs = cache.get_retrieval("error E20")

    Args:
        max_size: maximum number of entries in the in-memory LRU cache.
        ttl_seconds: time-to-live in seconds. Entries older than this are
            treated as expired. Default is 3600 (1 hour).
        persist_path: path to a JSON file for disk persistence. If None,
            defaults to ``data/cache/responses.json`` relative to project root.
        enable_disk: if False, disk persistence is disabled entirely.
    """

    def __init__(
        self,
        max_size: int = 100,
        ttl_seconds: int = 3600,
        persist_path: Optional[str] = None,
        enable_disk: bool = True,
    ):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._enable_disk = enable_disk

        # In-memory LRU caches (OrderedDict for LRU eviction)
        self._response_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._retrieval_cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()

        # Disk persistence path
        if persist_path is None:
            project_root = Path(__file__).resolve().parent
            self._persist_path = str(
                project_root / "data" / "cache" / "responses.json"
            )
        else:
            self._persist_path = persist_path

        # Load from disk on init
        if self._enable_disk:
            self._load_from_disk()

    # -------------------------------------------------------------------
    # Response cache: get / put
    # -------------------------------------------------------------------

    def get(self, question: str) -> Optional[Dict[str, Any]]:
        """Look up a cached response for the given question.

        Returns the cached result dict if found and not expired, else None.
        On cache hit, the entry is moved to the end (most recently used).
        """
        key = _hash_key(question)
        entry = self._response_cache.get(key)
        if entry is None:
            return None

        # Check TTL
        if time.time() - entry.get("timestamp", 0) > self._ttl:
            # Expired
            self._response_cache.pop(key, None)
            return None

        # Move to end (most recently used)
        self._response_cache.move_to_end(key)
        return entry.get("data")

    def put(self, question: str, result: Any) -> None:
        """Store a response in the cache.

        Args:
            question: the user question (used as cache key).
            result: any JSON-serialisable value to cache.
        """
        key = _hash_key(question)

        # Ensure result is serialisable
        if isinstance(result, dict):
            data = result
        elif isinstance(result, str):
            data = {"answer": result}
        else:
            data = {"value": str(result)}

        self._response_cache[key] = {
            "question": question,
            "data": data,
            "timestamp": time.time(),
        }
        self._response_cache.move_to_end(key)

        # Evict oldest if over capacity
        while len(self._response_cache) > self._max_size:
            self._response_cache.popitem(last=False)

        # Persist to disk
        if self._enable_disk:
            self._save_to_disk()

    # -------------------------------------------------------------------
    # Retrieval cache: cache_retrieval / get_retrieval
    # -------------------------------------------------------------------

    def cache_retrieval(self, query: str, docs: Any) -> None:
        """Cache retrieval results (documents) for a query.

        Args:
            query: the search query.
            docs: list of Document objects, dicts, or strings.
        """
        key = _hash_key(query)
        self._retrieval_cache[key] = {
            "query": query,
            "docs": _serialise_docs(docs),
            "timestamp": time.time(),
        }
        self._retrieval_cache.move_to_end(key)

        while len(self._retrieval_cache) > self._max_size:
            self._retrieval_cache.popitem(last=False)

    def get_retrieval(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """Look up cached retrieval results for a query.

        Returns a list of document dicts if found and not expired, else None.
        """
        key = _hash_key(query)
        entry = self._retrieval_cache.get(key)
        if entry is None:
            return None

        if time.time() - entry.get("timestamp", 0) > self._ttl:
            self._retrieval_cache.pop(key, None)
            return None

        self._retrieval_cache.move_to_end(key)
        return entry.get("docs")

    # -------------------------------------------------------------------
    # Utility methods
    # -------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all cached entries (both response and retrieval caches)."""
        self._response_cache.clear()
        self._retrieval_cache.clear()
        if self._enable_disk:
            self._save_to_disk()

    @property
    def size(self) -> int:
        """Number of entries in the response cache."""
        return len(self._response_cache)

    @property
    def retrieval_size(self) -> int:
        """Number of entries in the retrieval cache."""
        return len(self._retrieval_cache)

    # -------------------------------------------------------------------
    # Disk persistence
    # -------------------------------------------------------------------

    def _save_to_disk(self) -> None:
        """Persist caches to JSON file."""
        try:
            path = Path(self._persist_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            payload = {
                "responses": dict(self._response_cache),
                "retrievals": dict(self._retrieval_cache),
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.exception("RAGCache failed to save to disk: %s", e)

    def _load_from_disk(self) -> None:
        """Load caches from JSON file if it exists."""
        path = Path(self._persist_path)
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            now = time.time()

            # Load responses
            for key, entry in payload.get("responses", {}).items():
                ts = entry.get("timestamp", 0)
                if isinstance(ts, (int, float)) and now - ts <= self._ttl:
                    self._response_cache[key] = entry

            # Load retrievals
            for key, entry in payload.get("retrievals", {}).items():
                ts = entry.get("timestamp", 0)
                if isinstance(ts, (int, float)) and now - ts <= self._ttl:
                    self._retrieval_cache[key] = entry

        except Exception as e:
            logger.exception("RAGCache failed to load from disk: %s", e)
