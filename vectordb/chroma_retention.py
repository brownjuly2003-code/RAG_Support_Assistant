"""Idempotent Chroma adapter for bounded retention execution."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from vectordb.index_retention import execute_bounded_retention
from vectordb.tenant_lock import TenantIndexLockToken


def _persistent_client_factory(*, path: str) -> Any:
    import chromadb  # noqa: PLC0415

    return chromadb.PersistentClient(path=path)


def _is_not_found_error(exc: Exception) -> bool:
    from chromadb.errors import NotFoundError  # noqa: PLC0415

    return isinstance(exc, NotFoundError)


def execute_chroma_retention(
    tenant_id: str,
    *,
    max_versions: int,
    lock_token: TenantIndexLockToken | None,
    chroma_directory: str | Path,
    client_factory: Callable[..., Any] | None = None,
) -> tuple[str, ...]:
    """Execute bounded retention through Chroma's direct delete API."""
    factory = client_factory or _persistent_client_factory
    client: Any | None = None

    def _delete_collection_if_exists(collection_name: str) -> None:
        nonlocal client
        if client is None:
            client = factory(path=str(Path(chroma_directory)))
        try:
            client.delete_collection(name=collection_name)
        except Exception as exc:
            if _is_not_found_error(exc):
                return
            raise

    return execute_bounded_retention(
        tenant_id,
        max_versions=max_versions,
        lock_token=lock_token,
        delete_collection_if_exists=_delete_collection_if_exists,
        chroma_directory=chroma_directory,
    )
