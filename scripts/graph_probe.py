#!/usr/bin/env python3
"""Phase-1 connectivity probe for the graph-retrieval activation gate.

Plan: docs/plans/2026-06-05-graph-retrieval-activation.md. Size alone does not
justify a graph lane — this probe measures whether the corpus is CONNECTED
enough for a graph to help: entity extraction (mistral-small, temperature=0,
free-tier pacing) on a deterministic sample of production-chunked sections,
then the share of entities that appear in >=2 distinct source documents
(cross-doc edge density). The measured value feeds RAG_GRAPH_CROSSDOC_SHARE,
which the auto mode of RAG_GRAPH_RETRIEVAL compares against
RAG_GRAPH_MIN_CROSSDOC_SHARE (ingestion/graph_activation.py).

No local models: chunking is pure text (same select_chunks path as ingestion),
extraction is a remote API — safe under the Windows 1 GiB process rule.

Usage:
  set -a; . ./.env; set +a
  python scripts/graph_probe.py --sample 200
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.aircargo_ragas_free import FreeChatLLM  # noqa: E402

EXTRACT_PROMPT = (
    "Извлеки из фрагмента корпоративного регламента ключевые СУЩНОСТИ:\n"
    "процессы, роли, документы, системы, типы грузов/операций, термины.\n"
    "Не извлекай общие слова (сотрудник, компания, документ без уточнения).\n"
    "Нормализуй: именительный падеж, единственное число, нижний регистр.\n"
    "Ответ — ТОЛЬКО JSON-массив строк, без пояснений. 3-12 сущностей.\n"
    "\n"
    "Фрагмент:\n{chunk}\n"
    "\n"
    "JSON:"
)


def _parse_entities(raw: str) -> list[str]:
    """Tolerant JSON-array extraction (models love ```json fences)."""
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        bracket = re.search(r"\[.*\]", text, re.S)
        if bracket:
            text = bracket.group(0)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out = []
    for item in data:
        if isinstance(item, str) and item.strip():
            out.append(item.strip().lower())
    return out


def _sample_chunks(chunks: list, sample: int) -> list:
    """Deterministic spread across the corpus: sort by (source, position),
    take every k-th. No RNG — rerunnable bit-for-bit."""
    ordered = sorted(
        range(len(chunks)),
        key=lambda i: ((chunks[i].metadata or {}).get("source", "?"), i),
    )
    if len(ordered) <= sample:
        return [chunks[i] for i in ordered]
    step = len(ordered) / sample
    picked = [chunks[ordered[int(i * step)]] for i in range(sample)]
    return picked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus", default=str(PROJECT_ROOT / "data" / "uploads" / "aircargo")
    )
    parser.add_argument("--sample", type=int, default=200)
    parser.add_argument("--model", default="mistral-small-latest")
    parser.add_argument("--min-interval", type=float, default=1.2)
    parser.add_argument(
        "--out-dir", default=str(PROJECT_ROOT / "reports" / "graph_probe")
    )
    args = parser.parse_args(argv)

    from config.settings import get_settings
    from ingestion.loader import DocumentLoader
    from vectordb._base_manager import select_chunks

    settings = get_settings()
    docs = DocumentLoader(recursive=False).load_documents(args.corpus)
    if not docs:
        print(f"[probe] no documents under {args.corpus}", flush=True)
        return 2
    chunks = select_chunks(
        list(docs), None, settings.chunk_size, settings.chunk_overlap, settings=settings
    )
    picked = _sample_chunks(chunks, args.sample)
    n_docs_sampled = len({(c.metadata or {}).get("source", "?") for c in picked})
    print(
        f"[probe] {len(docs)} docs -> {len(chunks)} chunks; sample {len(picked)} "
        f"across {n_docs_sampled} docs; model={args.model}",
        flush=True,
    )

    llm = FreeChatLLM("mistral", args.model, temperature=0.0, min_interval_s=args.min_interval)

    entity_docs: dict[str, set[str]] = collections.defaultdict(set)
    entity_count: collections.Counter = collections.Counter()
    failures = 0
    t0 = time.time()
    for i, chunk in enumerate(picked, 1):
        source = (chunk.metadata or {}).get("source", "?")
        body = chunk.page_content[: settings.chunk_size + 400]
        entities = _parse_entities(llm.invoke(EXTRACT_PROMPT.format(chunk=body)))
        if not entities:
            failures += 1
        for ent in entities:
            entity_docs[ent].add(source)
            entity_count[ent] += 1
        if i % 20 == 0:
            print(f"[probe] {i}/{len(picked)} ({time.time()-t0:.0f}s)", flush=True)

    total = len(entity_docs)
    cross = {e: d for e, d in entity_docs.items() if len(d) >= 2}
    share = len(cross) / total if total else 0.0
    top = sorted(cross.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:25]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": stamp,
        "model": args.model,
        "sample_chunks": len(picked),
        "sampled_docs": n_docs_sampled,
        "corpus_chunks": len(chunks),
        "extraction_failures": failures,
        "entities_total": total,
        "entities_crossdoc": len(cross),
        "crossdoc_share": round(share, 4),
        "gate_min_share": settings.graph_min_crossdoc_share,
        "gate_passed": share >= settings.graph_min_crossdoc_share,
        "top_connecting": [
            {"entity": e, "docs": len(d)} for e, d in top
        ],
        "entity_doc_map": {e: sorted(d) for e, d in entity_docs.items()},
    }
    json_path = out_dir / f"{stamp}-graph-probe.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        f"# Graph connectivity probe — {stamp}",
        "",
        f"- sample: {len(picked)} chunks / {n_docs_sampled} docs "
        f"(corpus {len(chunks)} chunks), model {args.model}, "
        f"extraction failures {failures}",
        f"- entities: {total} total, {len(cross)} in >=2 docs",
        f"- **cross-doc share = {share:.3f}** "
        f"(gate RAG_GRAPH_MIN_CROSSDOC_SHARE = {settings.graph_min_crossdoc_share}: "
        f"{'PASSED' if payload['gate_passed'] else 'not passed'})",
        "",
        "Set the measured value for the auto gate:",
        "```",
        f"RAG_GRAPH_CROSSDOC_SHARE={share:.3f}",
        "```",
        "",
        "## Top connecting entities",
        "",
        "| entity | docs |",
        "|---|---|",
    ]
    lines += [f"| {e} | {len(d)} |" for e, d in top]
    md_path = out_dir / f"{stamp}-graph-probe.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(
        f"[probe] entities={total} crossdoc={len(cross)} share={share:.3f} "
        f"gate={'PASSED' if payload['gate_passed'] else 'not passed'}",
        flush=True,
    )
    print(f"[probe] saved -> {json_path}\n[probe] summary -> {md_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
