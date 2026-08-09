"""Run one resource-light retrieval + GraceKelly generation smoke."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "data" / "vectordb" / "chroma"
DEFAULT_SQLITE_PATH = PROJECT_ROOT / ".tmp" / "lightweight-gracekelly-smoke.sqlite3"
_TOKEN_RE = re.compile(r"[^\W_]+", flags=re.UNICODE)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall(value.casefold())
        if len(token) >= 3
    }


def rank_context_rows(
    question: str,
    rows: Sequence[dict[str, Any]],
    *,
    max_docs: int,
) -> list[dict[str, Any]]:
    if max_docs < 1:
        raise ValueError("max_docs must be >= 1")
    question_tokens = _tokens(question)
    ranked: list[dict[str, Any]] = []
    for row in rows:
        document = str(row.get("document") or "").strip()
        overlap = len(question_tokens & _tokens(document))
        if not document or overlap == 0:
            continue
        metadata = row.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        source = str(
            metadata.get("source")
            or metadata.get("title")
            or metadata.get("doc_id")
            or row.get("id")
            or "unknown"
        )
        ranked.append({**row, "source": source, "score": overlap})
    ranked.sort(
        key=lambda item: (
            -int(item["score"]),
            str(item["source"]),
            str(item.get("id") or ""),
        )
    )
    return ranked[:max_docs]


def load_collection_rows(
    *,
    chroma_dir: Path,
    collection_name: str,
) -> list[dict[str, Any]]:
    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_collection(collection_name)
    payload = collection.get(include=["documents", "metadatas"])
    ids = payload.get("ids") or []
    documents = payload.get("documents") or []
    metadatas = payload.get("metadatas") or []
    return [
        {
            "id": ids[index] if index < len(ids) else str(index),
            "document": document,
            "metadata": metadatas[index] if index < len(metadatas) else {},
        }
        for index, document in enumerate(documents)
    ]


def build_gracekelly_provider(
    *,
    base_url: str,
    model: str,
    request_timeout_sec: float,
) -> Any:
    from llm.providers.gracekelly import GraceKellyProvider

    return GraceKellyProvider(
        model_name=model,
        base_url=base_url,
        api_key_env="GRACEKELLY_API_KEY",
        timeout_sec=request_timeout_sec,
        health_check_timeout_sec=2.0,
        input_price_per_1m_tokens=0.0,
        output_price_per_1m_tokens=0.0,
    )


def _build_messages(
    question: str,
    contexts: Sequence[dict[str, Any]],
) -> list[dict[str, str]]:
    context_text = "\n\n".join(
        f"[{index}] source={item['source']}\n{str(item['document'])[:4000]}"
        for index, item in enumerate(contexts, start=1)
    )
    return [
        {
            "role": "system",
            "content": (
                "Answer only from the supplied support context. Cite supporting "
                "context as [N]. If it is insufficient, say so explicitly."
            ),
        },
        {
            "role": "user",
            "content": f"Context:\n{context_text}\n\nQuestion:\n{question}",
        },
    ]


def _persist_result(
    sqlite_path: Path,
    *,
    question: str,
    answer: str,
    provider: str,
    model: str,
    sources: Sequence[str],
) -> None:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(sqlite_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS lightweight_smoke_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                status TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                sources_json TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO lightweight_smoke_runs (
                created_at, status, provider, model, question, answer, sources_json
            ) VALUES (?, 'PASS', ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                provider,
                model,
                question,
                answer,
                json.dumps(list(sources), ensure_ascii=False),
            ),
        )


def run_lightweight_smoke(
    *,
    question: str,
    chroma_dir: Path,
    collection_name: str,
    sqlite_path: Path,
    max_docs: int,
    base_url: str,
    model: str,
    request_timeout_sec: float,
) -> dict[str, Any]:
    rows = load_collection_rows(
        chroma_dir=chroma_dir,
        collection_name=collection_name,
    )
    contexts = rank_context_rows(question, rows, max_docs=max_docs)
    if not contexts:
        raise RuntimeError("no lexical context match; GraceKelly was not called")

    provider = build_gracekelly_provider(
        base_url=base_url,
        model=model,
        request_timeout_sec=request_timeout_sec,
    )
    response = provider.generate(_build_messages(question, contexts))
    answer = str(response.text or "").strip()
    if not answer:
        raise RuntimeError("GraceKelly returned an empty answer")
    sources = list(dict.fromkeys(str(item["source"]) for item in contexts))
    _persist_result(
        sqlite_path,
        question=question,
        answer=answer,
        provider=str(response.provider),
        model=str(response.model),
        sources=sources,
    )
    return {
        "status": "PASS",
        "provider": str(response.provider),
        "model": str(response.model),
        "sources": sources,
        "answer": answer,
        "sqlite_path": str(sqlite_path),
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--question",
        default="Какой срок возврата товара?",
    )
    parser.add_argument("--chroma-dir", type=Path, default=DEFAULT_CHROMA_DIR)
    parser.add_argument("--collection", default="rag_docs_default")
    parser.add_argument("--sqlite-path", type=Path, default=DEFAULT_SQLITE_PATH)
    parser.add_argument("--max-docs", type=int, default=2)
    parser.add_argument(
        "--base-url",
        default=os.getenv("GRACEKELLY_BASE_URL", "http://127.0.0.1:8011"),
    )
    parser.add_argument("--model", default="claude-sonnet-5")
    parser.add_argument(
        "--request-timeout-sec",
        type=float,
        default=float(os.getenv("GRACEKELLY_REQUEST_TIMEOUT_SEC", "120")),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_lightweight_smoke(
            question=args.question,
            chroma_dir=args.chroma_dir,
            collection_name=args.collection,
            sqlite_path=args.sqlite_path,
            max_docs=args.max_docs,
            base_url=args.base_url,
            model=args.model,
            request_timeout_sec=args.request_timeout_sec,
        )
    except Exception as exc:  # noqa: BLE001 - CLI returns a concise fail-closed result
        print(json.dumps({"status": "FAIL", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
