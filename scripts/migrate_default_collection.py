"""Migrate legacy 'rag_docs' collection into 'rag_docs_default'."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chromadb

from config.settings import get_settings


def main() -> None:
    settings = get_settings()
    prefix = getattr(settings, "vectordb_collection_prefix", "rag_docs")
    old_name = prefix
    new_name = f"{prefix}_default"
    client = chromadb.PersistentClient(path=str(settings.vectordb_chroma_dir))

    try:
        old_collection = client.get_collection(old_name)
        try:
            client.delete_collection(new_name)
        except Exception:
            pass

        new_collection = client.create_collection(new_name)
        docs = old_collection.get(include=["documents", "metadatas", "embeddings"])
        ids = docs.get("ids") or []
        if ids:
            new_collection.add(
                ids=ids,
                documents=docs.get("documents"),
                metadatas=docs.get("metadatas"),
                embeddings=docs.get("embeddings"),
            )
        client.delete_collection(old_name)
        print(f"Migrated {len(ids)} docs to {new_name}")
    except Exception as exc:
        print(f"Nothing to migrate or migration failed: {exc}")


if __name__ == "__main__":
    main()
