#!/usr/bin/env python3
"""F2 builder (adaptive-retrieval Track F): build the fact-card vector collection.

Extracts fact-cards from documents (F1 extractor) and stores each whole card as
one Document in the ``<prefix>_<tenant>_factcards`` Chroma collection, then runs a
quick vector search to confirm the cards are retrievable ("карты ищутся
векторно" — the F2 acceptance).

Heavy/LLM + embedding step → run on Mac (per plan; Windows hangs on the embed).
Configure the provider via env, e.g.::

    LLM_PROVIDER_PROFILE=external-mistral MISTRAL_API_KEY=... \
        OLLAMA_REQUEST_TIMEOUT_SEC=120 \
        .venv/bin/python scripts/build_factcards.py \
        --query "какие поля нужны для таможенной очистки"

Defaults to the three customs docs F1 already validated; pass paths (or a
``--docs-dir`` glob of ``*.md``) to build over a wider corpus. Exit code 0 iff
>=1 card was stored and the verification query returns at least one card.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.factcard_extractor import FactCard, extract_fact_cards  # noqa: E402
from scripts.factcard_verify import DEFAULT_DOCS, build_llm, source_id  # noqa: E402

DEFAULT_QUERY = "какие поля нужны для таможенной очистки"


def factcard_to_document(card: FactCard):  # type: ignore[no-untyped-def]
    """Render one fact-card as a searchable Document (flat, scalar metadata)."""
    from vectordb import _base_manager

    document_cls = _base_manager.Document
    parts = [f"topic: {card.topic}"]
    if card.fields:
        parts.append("fields: " + ", ".join(card.fields))
    if card.required_docs:
        parts.append("required_docs: " + ", ".join(card.required_docs))
    if card.conditions:
        parts.append("conditions: " + ", ".join(card.conditions))
    metadata = {
        "type": "factcard",
        "topic": card.topic,
        "source": card.source,
        "doc_id": card.source,
        "field_count": len(card.fields),
    }
    return document_cls(page_content="\n".join(parts), metadata=metadata)


def collect_docs(args: argparse.Namespace) -> list[str]:
    if args.docs_dir:
        root = (PROJECT_ROOT / args.docs_dir).resolve()
        return sorted(str(p.relative_to(PROJECT_ROOT)) for p in root.glob("*.md"))
    return list(args.docs) or list(DEFAULT_DOCS)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("docs", nargs="*", default=DEFAULT_DOCS)
    parser.add_argument("--docs-dir", default="", help="glob *.md under this repo-relative dir")
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--max-chars", type=int, default=6000)
    parser.add_argument("--query", default=DEFAULT_QUERY, help="verification search query")
    parser.add_argument("--k", type=int, default=3, help="verification top-k")
    args = parser.parse_args(argv)

    from vectordb import manager

    llm = build_llm()
    card_docs = []
    cards_total = 0
    for rel in collect_docs(args):
        path = (PROJECT_ROOT / rel).resolve()
        if not path.exists():
            print(f"[SKIP] {rel}: not found")
            continue
        text = path.read_text(encoding="utf-8")
        src = source_id(path, text)
        try:
            cards = extract_fact_cards(text, src, llm, max_chars=args.max_chars)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {path.name}: extraction error: {exc}")
            continue
        for card in cards:
            card_docs.append(factcard_to_document(card))
        cards_total += len(cards)
        print(f"[OK] {path.name}: {len(cards)} card(s)")

    if not card_docs:
        print("\nRESULT: FAIL (no cards extracted)")
        return 1

    store = manager.build_factcard_store(card_docs, tenant_id=args.tenant)
    collection = manager._factcard_collection_name(args.tenant)
    print(f"\nBuilt collection '{collection}' with {cards_total} card(s).")

    hits = store.similarity_search(args.query, k=args.k)
    print(f"\nVerification query: {args.query!r} -> {len(hits)} hit(s)")
    for hit in hits:
        topic = (getattr(hit, "metadata", {}) or {}).get("topic", "?")
        first_line = hit.page_content.splitlines()[0] if hit.page_content else ""
        print(f"  - topic={topic}  {first_line}")

    ok = len(hits) > 0
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
