#!/usr/bin/env python3
"""Phase 2 remote A/B: baseline vs structural+contextual-header on the production stack.

Confirms (or refutes) the Phase-1 proxy signal
(docs/operations/2026-06-04-phase1-proxy-ab-contextual-header.md) with the real
models: BGE-M3 embeddings + the default multilingual reranker (bge-reranker-v2-m3).
Designed for Colab (GPU or CPU) or the iMac two-phase pattern — each stage is a
separate process so the embedder and the reranker are never resident together.

Arms:
  A  production baseline: fixed 800/200 chunking + contextual headers (prod default)
  C  the fix: RAG_STRUCTURAL_CHUNKING=true + contextual headers (heading-path anchors)
  E  arm C + field-aware HyDE query expansion (precomputed locally by
     scripts/precompute_field_hyde.py, travels as a dataset file — no API key
     remotely). The expanded query drives retrieval AND rerank (mirrors the
     production retrieve node, where hyde_query feeds get_relevant_documents);
     the ORIGINAL query stays in the output rows for the LLM-judge contract.
  F  split-query: arm-E POOLS (expanded query for dense+BM25 — kw-chunks of
     the E regressions sit at RRF rank 1-9 there) + rerank against the
     ORIGINAL query (as in C/D2, where those cases are FULL). Pools are NOT
     recomputed: copy ab_phase2_E_pool.json -> ab_phase2_F_pool.json and run
     rerank F. Rationale: docs/operations/2026-06-06-arm-e-field-hyde-results.md.

All arms run the post-4844094 header path (body never truncated, header clamped 200).

Stages (run order: pools A -> pools C -> rerank A -> rerank C -> report):
  pools   load corpus, chunk per arm, apply headers, embed (project embedder),
          mirror HybridRetriever steps 1-3 (dense top-k + BM25 top-k -> RRF),
          dump the full candidate pool per case.
  rerank  load pools, score with the project reranker, dump candidates in
          post-rerank order — the file is directly consumable by
          scripts/aircargo_ragas_free.py --contexts ... for the R7 LLM-judged
          re-run (done LOCALLY via Mistral; no API key needed remotely).
  report  no models: per-arm coverage@top-5, diagnosis-target rank table A vs C,
          rerank-recoverable verification; writes a markdown summary.

Usage:
  python scripts/ab_remote_contextual.py --stage pools  --arm A
  python scripts/ab_remote_contextual.py --stage pools  --arm C
  python scripts/ab_remote_contextual.py --stage rerank --arm A
  python scripts/ab_remote_contextual.py --stage rerank --arm C
  python scripts/ab_remote_contextual.py --stage report
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Diagnosis targets from docs/operations/2026-06-03-r7-llm-judged-baseline.md.
DEEP_7 = [
    "aircargo-dangerous-goods-fields",
    "aircargo-customs-clearance-fields",
    "aircargo-waybill-first-mile-fields",
    "aircargo-access-control-review",
    "aircargo-driver-hours-required-fields",
    "aircargo-perishable-temperature-controls",
    "aircargo-cross-border-required-fields",
]
NEAR_DEEP_1 = ["aircargo-waybill-escalation-events"]
UNCERTAIN_5 = [
    "aircargo-warehouse-3pl-required-fields",
    "aircargo-oversized-permit-route",
    "aircargo-fuel-supply-evidence",
    "aircargo-gps-monitoring-required-fields",
    "aircargo-weight-control-required-fields",
]
COVERED_4 = [
    "aircargo-incident-response-required-fields",
    "aircargo-subject-rights-required-fields",
    "aircargo-conflict-interest-sanctions",
    "aircargo-breach-notification-required-fields",
]
TARGETS_13 = DEEP_7 + NEAR_DEEP_1 + UNCERTAIN_5
RECOVERABLE_10 = NEAR_DEEP_1 + UNCERTAIN_5 + COVERED_4

# Residual problem cases after Phase 2 (4 regressions + 4 deep MISS) with the
# measured parent-context potential 8/8
# (docs/operations/2026-06-05-residual-miss-diagnosis.md).
PROBLEM_8 = [
    "aircargo-customs-broker-escalation",
    "aircargo-dangerous-goods-clearance",
    "aircargo-breach-notification-participants",
    "aircargo-perishable-special-cargo-evidence",
    "aircargo-customs-clearance-fields",
    "aircargo-waybill-first-mile-fields",
    "aircargo-perishable-temperature-controls",
    "aircargo-cross-border-required-fields",
]


def _set_arm_env(arm: str) -> None:
    """Environment must be set before any project import reads settings."""
    os.environ["RAG_RERANKER_MODEL"] = ""  # pools stage never loads the reranker
    os.environ["RAG_SEMANTIC_CHUNKING"] = "false"
    # Arm E = arm C chunking + expanded queries (query side only).
    os.environ["RAG_STRUCTURAL_CHUNKING"] = "true" if arm in ("C", "E") else "false"
    # RAG_CONTEXTUAL_HEADERS stays at the production default (on).


def _load_expansions(path: Path) -> dict[str, str]:
    """case_id -> expanded_query from scripts/precompute_field_hyde.py output."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {r["case_id"]: r["expanded_query"] for r in rows}


def _load_cases(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _kw_status(kws: list[str], texts: list[str]) -> str:
    blob = " \n ".join(t.lower() for t in texts)
    found = [k for k in kws if k.lower() in blob]
    if kws and len(found) == len(kws):
        return "FULL"
    return "PART" if found else "MISS"


def _cooccur_rank(kws: list[str], texts: list[str]) -> int | None:
    lowered = [k.lower() for k in kws]
    for rank, text in enumerate(texts, 1):
        tl = text.lower()
        if lowered and all(k in tl for k in lowered):
            return rank
    return None


def stage_pools(
    arm: str,
    corpus: Path,
    cases_path: Path,
    out_dir: Path,
    expansions: dict[str, str] | None = None,
) -> int:
    _set_arm_env(arm)
    import numpy as np

    from config.settings import get_settings
    from ingestion.loader import DocumentLoader
    from vectordb import manager
    from vectordb._base_manager import (
        HybridRetriever,
        _tokenize_for_bm25,
        get_embeddings,
        select_chunks,
    )

    settings = get_settings()
    print(
        f"[pools/{arm}] structural={settings.structural_chunking} "
        f"ctx_headers={settings.contextual_headers} chunk={settings.chunk_size}/"
        f"{settings.chunk_overlap} retr_k={settings.retrieval_top_k} "
        f"embedder={settings.embedding_model}",
        flush=True,
    )

    docs = DocumentLoader(recursive=False).load_documents(str(corpus))
    if not docs:
        print(f"[pools/{arm}] no documents under {corpus}", flush=True)
        return 2
    chunks = select_chunks(
        list(docs), None, settings.chunk_size, settings.chunk_overlap, settings=settings
    )
    if getattr(settings, "contextual_headers", False):
        chunks = manager.add_contextual_headers(chunks, docs, chunk_size=settings.chunk_size)
    print(f"[pools/{arm}] {len(docs)} docs -> {len(chunks)} chunks", flush=True)

    embeddings = get_embeddings()
    st_model = getattr(embeddings, "_model", None)
    texts = [c.page_content for c in chunks]
    t0 = time.time()
    if st_model is not None:
        mat = st_model.encode(
            texts, normalize_embeddings=True, batch_size=32, show_progress_bar=True
        ).astype(np.float32)
    else:  # pragma: no cover - fallback for exotic wrappers
        mat = np.asarray(embeddings.embed_documents(texts), dtype=np.float32)
    print(f"[pools/{arm}] encoded {len(texts)} chunks in {time.time()-t0:.0f}s", flush=True)

    cases = _load_cases(cases_path)
    expansions = expansions or {}
    if arm == "E" and expansions:
        missing = [c["case_id"] for c in cases if c["case_id"] not in expansions]
        if missing:
            print(f"[pools/{arm}] {len(missing)} cases lack expansions: {missing[:5]}", flush=True)
            return 2
    # Retrieval queries: arm E uses the precomputed expanded query (mirrors the
    # production retrieve node where hyde_query drives get_relevant_documents).
    eff_queries = [expansions.get(c["case_id"], c["query"]) for c in cases]
    if st_model is not None:
        qmat = st_model.encode(
            eff_queries, normalize_embeddings=True, batch_size=16
        ).astype(np.float32)
    else:  # pragma: no cover
        qmat = np.asarray(
            [embeddings.embed_query(q) for q in eff_queries], dtype=np.float32
        )

    class _MatrixStore:
        """similarity_search-compatible stub: exact cosine over normalized vectors."""

        def __init__(self) -> None:
            self._qv = {q: qmat[i] for i, q in enumerate(eff_queries)}

        def similarity_search(self, query: str, k: int = 20):
            idx = np.argsort(-(mat @ self._qv[query]))[:k]
            return [chunks[i] for i in idx]

    store = _MatrixStore()
    retriever = HybridRetriever(
        vector_store=store,
        chunks=chunks,
        retrieval_k=settings.retrieval_top_k,
        rerank_k=settings.rerank_top_k,
        reranker=None,
    )

    rows = []
    for case, eff_query in zip(cases, eff_queries, strict=True):
        vector_results = store.similarity_search(eff_query, k=retriever._retrieval_k)
        bm25_results = []
        if retriever._bm25 is not None:
            scores = retriever._bm25.get_scores(_tokenize_for_bm25(eff_query))
            top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            bm25_results = [
                retriever._chunks[i] for i in top[: retriever._retrieval_k] if scores[i] > 0
            ]
        merged = retriever._rrf_merge(vector_results, bm25_results) if bm25_results else vector_results
        row = {
            # The ORIGINAL query — the LLM-judge generates from it.
            "case_id": case["case_id"],
            "query": case["query"],
            "kws": case["expected"]["answer_contains"],
            "rerank_k": settings.rerank_top_k,
            "cands": [d.page_content for d in merged],
            "cand_sources": [(d.metadata or {}).get("source", "?") for d in merged],
        }
        if eff_query != case["query"]:
            row["expanded_query"] = eff_query
        rows.append(row)

    out_dir.mkdir(parents=True, exist_ok=True)
    pool_path = out_dir / f"ab_phase2_{arm}_pool.json"
    pool_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"[pools/{arm}] saved {len(rows)} pools -> {pool_path}", flush=True)
    return 0


def stage_rerank(arm: str, out_dir: Path) -> int:
    # Reranker only in this process; embedder env stays irrelevant here.
    from config.settings import get_settings
    from vectordb._base_manager import get_reranker

    settings = get_settings()
    pool_path = out_dir / f"ab_phase2_{arm}_pool.json"
    if not pool_path.exists():
        print(f"[rerank/{arm}] missing {pool_path} — run --stage pools first", flush=True)
        return 2
    rows = json.loads(pool_path.read_text(encoding="utf-8"))

    reranker = get_reranker()
    if reranker is None:
        print(
            f"[rerank/{arm}] reranker unavailable (model={settings.reranker_model!r})",
            flush=True,
        )
        return 2
    print(f"[rerank/{arm}] model={settings.reranker_model}", flush=True)

    t0 = time.time()
    for i, row in enumerate(rows, 1):
        # Arm E: the reranker scores against the expanded query, like the
        # production path where hyde_query reaches HybridRetriever.
        # Arm F (split-query): pools came from the expanded query, but the
        # reranker scores against the ORIGINAL query — the E diagnosis showed
        # the cross-encoder demotes kw-chunks when fed the long expanded text.
        if arm == "F":
            rerank_query = row["query"]
        else:
            rerank_query = row.get("expanded_query") or row["query"]
        pairs = [(rerank_query, text) for text in row["cands"]]
        scores = reranker.predict(pairs)
        order = sorted(range(len(scores)), key=lambda j: scores[j], reverse=True)
        row["prerank_cands"] = row["cands"]
        row["prerank_sources"] = row.get("cand_sources", [])
        row["cands"] = [row["prerank_cands"][j] for j in order]
        row["cand_sources"] = [
            row["prerank_sources"][j] if j < len(row["prerank_sources"]) else "?"
            for j in order
        ]
        if i % 20 == 0:
            print(f"[rerank/{arm}] {i}/{len(rows)} ({time.time()-t0:.0f}s)", flush=True)

    out_path = out_dir / f"ab_candidates_phase2_{arm}.json"
    out_path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(
        f"[rerank/{arm}] saved -> {out_path} "
        f"(consumable by scripts/aircargo_ragas_free.py --contexts ...)",
        flush=True,
    )
    return 0


def stage_report(out_dir: Path) -> int:
    arms: dict[str, list[dict]] = {}
    for arm in ("A", "C"):
        path = out_dir / f"ab_candidates_phase2_{arm}.json"
        if not path.exists():
            print(f"[report] missing {path} — run pools+rerank for arm {arm}", flush=True)
            return 2
        arms[arm] = json.loads(path.read_text(encoding="utf-8"))

    lines: list[str] = []

    def emit(line: str = "") -> None:
        print(line, flush=True)
        lines.append(line)

    emit("# Phase 2 A/B — production stack (BGE-M3 + reranker), post-rerank top-5")
    emit()
    by_arm: dict[str, dict[str, dict]] = {}
    for arm, rows in arms.items():
        by_id = {r["case_id"]: r for r in rows}
        by_arm[arm] = by_id
        counts = {"FULL": 0, "PART": 0, "MISS": 0}
        for r in rows:
            counts[_kw_status(r["kws"], r["cands"][: int(r.get("rerank_k", 5))])] += 1
        n = len(rows)
        emit(
            f"- arm {arm}: FULL {counts['FULL']}/{n} = {100*counts['FULL']/max(n,1):.0f}% "
            f"PART {counts['PART']} MISS {counts['MISS']}"
        )

    emit()
    emit("## 13 diagnosis targets — pre-rerank pool co-occur rank / post-rerank top-5")
    emit()
    emit("| case | pool A | pool C | top5 A | top5 C |")
    emit("|---|---|---|---|---|")
    for cid in TARGETS_13:
        cells: dict[str, tuple[str, str]] = {}
        for arm in ("A", "C"):
            row = by_arm[arm].get(cid)
            if row is None:
                cells[arm] = ("?", "?")
                continue
            pool_texts = row.get("prerank_cands", row["cands"])
            rank = _cooccur_rank(row["kws"], pool_texts)
            status = _kw_status(row["kws"], row["cands"][: int(row.get("rerank_k", 5))])
            cells[arm] = (str(rank) if rank else "—", status)
        emit(
            f"| {cid.removeprefix('aircargo-')} | {cells['A'][0]} | {cells['C'][0]} "
            f"| {cells['A'][1]} | {cells['C'][1]} |"
        )

    emit()
    emit("## Rerank-recoverable verification (10 cases, arm A = production baseline)")
    emit()
    covered = 0
    for cid in RECOVERABLE_10:
        row = by_arm["A"].get(cid)
        if row is None:
            emit(f"- {cid}: not in dataset?")
            continue
        status = _kw_status(row["kws"], row["cands"][: int(row.get("rerank_k", 5))])
        covered += status == "FULL"
        emit(f"- {cid.removeprefix('aircargo-')}: top5={status}")
    emit(f"- covered with reranker: {covered}/10")

    out_path = out_dir / "ab_phase2_summary.md"
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[report] saved -> {out_path}", flush=True)
    return 0


def stage_expand(
    src: Path, corpus: Path, window: int, max_chars: int, label: str = "D"
) -> int:
    """Arm D = arm C post-rerank candidates + parent-expansion. Local, no models.

    With --label E the same machinery turns arm-E rerank candidates into the
    full stack (expanded queries + structural chunking + parent-expansion).

    The expansion runs AFTER the rerank, so arm D's selection is identical to
    arm C — only the candidate texts change. That makes this measurement exact
    (not a proxy) and fully local: the arm-C chunk list is reproduced with the
    same pure-text pipeline the Kaggle kernel used (structural_split +
    contextual headers, verified 1:1 in the residual-miss diagnosis), and the
    expansion itself is done by the production
    HybridRetriever._expand_parents — not a reimplementation.
    """
    _set_arm_env("C")
    from config.settings import get_settings
    from ingestion.loader import DocumentLoader
    from vectordb import manager
    from vectordb._base_manager import Document, HybridRetriever, select_chunks

    settings = get_settings()
    docs = DocumentLoader(recursive=False).load_documents(str(corpus))
    if not docs:
        print(f"[expand] no documents under {corpus}", flush=True)
        return 2
    chunks = select_chunks(
        list(docs), None, settings.chunk_size, settings.chunk_overlap, settings=settings
    )
    if getattr(settings, "contextual_headers", False):
        chunks = manager.add_contextual_headers(chunks, docs, chunk_size=settings.chunk_size)
    print(f"[expand] {len(docs)} docs -> {len(chunks)} chunks (arm C reproduction)", flush=True)

    text_to_pos: dict[str, int] = {}
    for idx, chunk in enumerate(chunks):
        text_to_pos.setdefault(chunk.page_content, idx)

    retriever = HybridRetriever(
        vector_store=None,
        chunks=chunks,
        reranker=None,
        use_bm25=False,
        parent_expansion=True,
        parent_expansion_window=window,
        parent_expansion_max_chars=max_chars,
    )

    rows = json.loads(src.read_text(encoding="utf-8"))
    unmatched = 0
    transitions: dict[tuple[str, str], list[str]] = {}
    out_rows = []
    for row in rows:
        top_k = int(row.get("rerank_k", 5))
        sources = row.get("cand_sources", [])
        selected: list[Document] = []
        for i, text in enumerate(row["cands"][:top_k]):
            pos = text_to_pos.get(text)
            if pos is None:
                unmatched += 1
                src_name = sources[i] if i < len(sources) else "?"
                selected.append(Document(page_content=text, metadata={"source": src_name}))
            else:
                selected.append(chunks[pos])
        expanded = retriever._expand_parents(selected)

        status_c = _kw_status(row["kws"], row["cands"][:top_k])
        status_d = _kw_status(row["kws"], [d.page_content for d in expanded])
        transitions.setdefault((status_c, status_d), []).append(row["case_id"])

        out_row = dict(row)
        out_row["cands"] = [d.page_content for d in expanded] + row["cands"][top_k:]
        out_row["parent_expanded"] = sum(
            1 for d in expanded if (d.metadata or {}).get("parent_expanded")
        )
        out_rows.append(out_row)

    if unmatched:
        print(
            f"[expand] WARNING: {unmatched} candidate texts not found in the local "
            "chunk reproduction — those stayed unexpanded",
            flush=True,
        )

    out_path = src.parent / f"ab_candidates_phase2_{label}.json"
    if out_path == src:
        # --label E with src = the arm-E rerank output would overwrite the
        # source; keep both (pre-expansion is needed for the transition matrix).
        out_path = src.parent / f"ab_candidates_phase2_{label}_expanded.json"
    out_path.write_text(json.dumps(out_rows, ensure_ascii=False), encoding="utf-8")

    lines: list[str] = []

    def emit(line: str = "") -> None:
        print(line, flush=True)
        lines.append(line)

    src_label = "C" if label == "D" else f"{label}-pre"
    emit(
        f"# Arm {label} = {src_label} + parent-expansion "
        f"(window={window}, max_chars={max_chars})"
    )
    emit()
    by_id = {r["case_id"]: r for r in out_rows}
    for arm_label, key_rows in ((src_label, rows), (label, out_rows)):
        counts = {"FULL": 0, "PART": 0, "MISS": 0}
        for r in key_rows:
            counts[_kw_status(r["kws"], r["cands"][: int(r.get("rerank_k", 5))])] += 1
        n = len(key_rows)
        emit(
            f"- arm {arm_label}: FULL {counts['FULL']}/{n} = {100*counts['FULL']/max(n,1):.0f}% "
            f"PART {counts['PART']} MISS {counts['MISS']}"
        )
    emit()
    emit(f"## Transitions {src_label} -> {label}")
    emit()
    for (c_st, d_st), ids in sorted(transitions.items()):
        if c_st == d_st:
            emit(f"- {c_st} -> {d_st}: {len(ids)}")
        else:
            emit(f"- {c_st} -> {d_st}: {len(ids)} ({', '.join(i.removeprefix('aircargo-') for i in ids)})")
    emit()
    emit("## 8 residual problem cases (4 regressions + 4 deep)")
    emit()
    emit(f"| case | {src_label} top5 | {label} top5 | sections added |")
    emit("|---|---|---|---|")
    for cid in PROBLEM_8:
        row_c = next((r for r in rows if r["case_id"] == cid), None)
        row_d = by_id.get(cid)
        if row_c is None or row_d is None:
            emit(f"| {cid.removeprefix('aircargo-')} | ? | ? | ? |")
            continue
        top_k = int(row_c.get("rerank_k", 5))
        emit(
            f"| {cid.removeprefix('aircargo-')} "
            f"| {_kw_status(row_c['kws'], row_c['cands'][:top_k])} "
            f"| {_kw_status(row_d['kws'], row_d['cands'][:top_k])} "
            f"| {row_d['parent_expanded']}/{top_k} |"
        )

    summary_path = src.parent / f"ab_phase2_{label}_summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n[expand] saved -> {out_path}\n[expand] summary -> {summary_path}", flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=("pools", "rerank", "report", "expand"))
    parser.add_argument("--arm", default="", choices=("", "A", "C", "E", "F"))
    parser.add_argument("--corpus", default=str(PROJECT_ROOT / "data" / "uploads" / "aircargo"))
    parser.add_argument(
        "--cases", default=str(PROJECT_ROOT / "evaluation" / "curated_cases_aircargo.jsonl")
    )
    parser.add_argument("--out-dir", default=str(PROJECT_ROOT / ".tmp"))
    parser.add_argument(
        "--src",
        default=str(
            PROJECT_ROOT / ".tmp" / "kaggle_phase2" / "out_final" / "ab_candidates_phase2_C.json"
        ),
        help="--stage expand: arm C post-rerank candidates",
    )
    parser.add_argument("--window", type=int, default=1, help="--stage expand: sections per side")
    parser.add_argument("--max-chars", type=int, default=2400, help="--stage expand: text cap")
    parser.add_argument(
        "--label", default="D", help="--stage expand: output arm label (D or E)"
    )
    parser.add_argument(
        "--expansions",
        default=str(PROJECT_ROOT / ".tmp" / "query_expansions_field_hyde.json"),
        help="--arm E: precomputed expanded queries (scripts/precompute_field_hyde.py)",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out_dir)
    if args.stage == "pools":
        if args.arm not in ("A", "C", "E"):
            parser.error("--stage pools requires --arm A|C|E")
        expansions = _load_expansions(Path(args.expansions)) if args.arm == "E" else None
        return stage_pools(
            args.arm, Path(args.corpus), Path(args.cases), out_dir, expansions=expansions
        )
    if args.stage == "rerank":
        if args.arm not in ("A", "C", "E", "F"):
            parser.error("--stage rerank requires --arm A|C|E|F")
        return stage_rerank(args.arm, out_dir)
    if args.stage == "expand":
        return stage_expand(
            Path(args.src), Path(args.corpus), args.window, args.max_chars, label=args.label
        )
    return stage_report(out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
