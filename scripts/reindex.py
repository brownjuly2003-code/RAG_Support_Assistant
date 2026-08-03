# ruff: noqa: E402
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from ingestion.loader import DocumentLoader
from utils.tenant_naming import physical_tenant_component
from vectordb.manager import build_vector_store, get_embeddings, reset_retriever_cache

_HASHED_TENANT_COMPONENT_RE = re.compile(r"--[0-9a-f]{16}$")


def _upload_dir_for_tenant(upload_root: Path, tenant_id: str) -> Path:
    if tenant_id == "default":
        return upload_root
    return upload_root / physical_tenant_component(tenant_id, max_length=63)


def _iter_tenants(upload_root: Path) -> list[str]:
    tenants = ["default"]
    if not upload_root.exists():
        return tenants
    for entry in sorted(upload_root.iterdir()):
        if entry.is_dir():
            if _HASHED_TENANT_COMPONENT_RE.search(entry.name):
                raise RuntimeError(
                    "reindex --all cannot recover a canonical tenant ID from a "
                    "hashed upload directory; rerun with --tenant <canonical-id>"
                )
            tenants.append(entry.name)
    return tenants


def _reindex_tenant(tenant_id: str, upload_root: Path) -> tuple[str, int]:
    settings = get_settings()
    docs_dir = _upload_dir_for_tenant(upload_root, tenant_id)
    if not docs_dir.exists():
        return tenant_id, 0

    loader = DocumentLoader(recursive=False)
    docs = loader.load_documents(docs_dir)
    if not docs:
        return tenant_id, 0

    build_vector_store(
        docs,
        {
            "chunk_size": getattr(settings, "chunk_size", 800),
            "chunk_overlap": getattr(settings, "chunk_overlap", 200),
        },
        embeddings=get_embeddings(),
        tenant_id=tenant_id,
    )
    reset_retriever_cache(tenant_id)
    return tenant_id, len(docs)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()

    upload_root = PROJECT_ROOT / "data" / "uploads"
    try:
        tenants = _iter_tenants(upload_root) if args.all else [args.tenant]
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    total_docs = 0
    for tenant_id in tenants:
        tenant, docs_count = _reindex_tenant(tenant_id, upload_root)
        total_docs += docs_count
        print(f"{tenant}: {docs_count} document(s) reindexed")

    print(f"total: {total_docs} document(s) reindexed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
