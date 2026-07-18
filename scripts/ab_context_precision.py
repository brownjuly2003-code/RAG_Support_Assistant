#!/usr/bin/env python3
"""Q1 offline A/B: context_precision knob grid on the 100-case aircargo harness.

Audit `audit_grok_16_07_26.md` (Q1 / §7.2 / §7.3): the free-RAGAS baseline
(`reports/ragas/20260605T214926Z-e728353a-aircargo-ragas.md`) measures
context_precision ~0.51 (weak звено — top-k шумит) while context_recall ~0.92
(отлично). The audit's product bet is a *measured* A/B over the three retrieval
knobs it named — rerank top-k, parent-window expansion (chars), and the
grade_docs CRAG filter — on the SAME 100 cases, to cut top-k noise WITHOUT
losing recall. This is NOT a new retrieval strategy.

Design — the expensive stage runs ONCE:
  * the BGE-M3 embed + bge-reranker-v2-m3 rerank pass is produced by the existing
    `scripts/ab_remote_contextual.py --stage pools/rerank --arm C` (production
    chunking: structural + contextual headers). Its output
    `.tmp/ab_candidates_phase2_C.json` is the full reranked candidate pool per
    case (retrieval_top_k in reranked order).
  * every grid arm is then CHEAP post-processing over that single pool:
      - rerank_k  -> slice `cands[:k]`;
      - parent-window (window, max_chars) -> reuse the production
        `HybridRetriever._expand_parents` (pure text, no models);
      - grade_docs on/off -> reuse the production `agent.graph.make_grade_docs_node`
        (LLM CRAG filter; external-mistral, opt-in via --with-grade).
  * metrics reuse the existing RAGAS code path
    (`evaluation.ragas_eval.context_precision` / `context_recall`) plus the cheap
    keyword FULL/PART/MISS regression guard (`ab_remote_contextual._kw_status`).

So the DEFAULT sweep needs NO LLM at all — only the one embed+rerank pass is
heavy. The external-mistral key is required only for the opt-in grade arms
(--with-grade) and the opt-in faithfulness/answer_relevancy judge (--with-judge),
following the same external-mistral convention the RAGAS baseline used.

All project imports are lazy (module import loads nothing heavy). Nothing here
downloads or runs a model on its own; the heavy embed+rerank happens only in the
`ab_remote_contextual` subprocess launched by --build-pool (Mac/Colab only).

Smoke (Windows, no models):
  python scripts/ab_context_precision.py --mock --stub-grade \
      --results-dir .tmp/q1_smoke

Heavy run — ONE command on Mac (see the run-doc
`docs/operations/2026-07-18-q1-context-precision-ab-plan.md`):
  set -a && . /tmp/mk.env && set +a && \
  RAG_DEVICE=mps RAG_EMBED_BATCH=8 RAG_RERANK_BATCH=8 \
  LLM_PROVIDER_PROFILE=external-mistral OLLAMA_REQUEST_TIMEOUT_SEC=120 \
  .venv/bin/python scripts/ab_context_precision.py --build-pool \
      --with-grade --with-judge --results-dir reports/ragas
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Grid definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Arm:
    """One A/B arm = a knob combination applied to the shared reranked pool."""

    name: str
    rerank_k: int
    window: int          # parent-expansion sections per side (0 = expansion off)
    max_chars: int       # parent-expansion text cap
    grade: bool          # apply the grade_docs CRAG filter (external-mistral)
    note: str = ""

    @property
    def expand_key(self) -> tuple[int, int]:
        return (self.window, self.max_chars)


# Production defaults (config/settings.py): rerank_top_k=5, parent_expansion on
# window=2 / max_chars=3600, grade_docs is the Level-2 CRAG node. Arm "prod" ==
# the D2 baseline (FULL 96 / PART 3 / MISS 1 on the keyword metric).
#
# Grid = one-factor-at-a-time around prod + two combined-precision arms + two
# opt-in grade arms (8 total; the 6 deterministic arms always run, the 2 grade
# arms only with --with-grade). Rationale: rerank_k↓ and expansion↓ both drop
# low-rank / diluting text -> precision↑, with recall as the guard rail.
DEFAULT_GRID: list[Arm] = [
    Arm("prod",            rerank_k=5, window=2, max_chars=3600, grade=False,
        note="current production baseline (D2)"),
    Arm("k3",              rerank_k=3, window=2, max_chars=3600, grade=False,
        note="tighter top-k: fewer docs, precision up, recall risk"),
    Arm("k8",              rerank_k=8, window=2, max_chars=3600, grade=False,
        note="wider top-k: recall headroom check"),
    Arm("no-expand",       rerank_k=5, window=0, max_chars=0,    grade=False,
        note="expansion off: isolates the precision cost of parent-window"),
    Arm("light-expand",    rerank_k=5, window=1, max_chars=2400, grade=False,
        note="conservative expansion (settings rollback config)"),
    Arm("k3-light-expand", rerank_k=3, window=1, max_chars=2400, grade=False,
        note="combined precision play"),
    Arm("grade",           rerank_k=5, window=2, max_chars=3600, grade=True,
        note="CRAG grade_docs on top of prod (opt-in, external-mistral)"),
    Arm("k3-grade",        rerank_k=3, window=2, max_chars=3600, grade=True,
        note="tighter k + CRAG (opt-in, external-mistral)"),
]

BASELINE_ARM = "prod"


def build_grid(*, with_grade: bool) -> list[Arm]:
    return [a for a in DEFAULT_GRID if with_grade or not a.grade]


# ---------------------------------------------------------------------------
# Row loading (reranked candidate pool from ab_remote_contextual rerank stage)
# ---------------------------------------------------------------------------

def load_rerank_rows(path: Path) -> list[dict[str, Any]]:
    """Load `ab_candidates_phase2_*.json` rows (query, cands, cand_sources, kws)."""
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{path}: expected a JSON list of rows")
    return rows


def mock_rows() -> list[dict[str, Any]]:
    """Tiny deterministic pool for the Windows smoke — no models, no corpus.

    Three cases with hand-made reranked candidates so the metrics and the
    FULL/PART/MISS guard exercise every branch. One candidate carries the
    "IRRELEVANT" sentinel so the --stub-grade path can demonstrate filtering
    of a non-top document.
    """
    return [
        {
            "case_id": "mock-full",
            "query": "какие поля нужны для допуска груза",
            "kws": ["поля", "допуск"],
            "cands": [
                "Для допуска груза нужны поля: маркировка и допуск отправителя.",
                "IRRELEVANT кадровый регламент отпусков и больничных листов.",
                "Общие сведения о складской логистике без конкретики.",
                "Дополнительный контекст про поля допуска и проверки.",
            ],
            "cand_sources": ["doc_a.md", "doc_b.md", "doc_c.md", "doc_a.md"],
        },
        {
            "case_id": "mock-part",
            "query": "когда нужен юрист по претензии",
            "kws": ["юрист", "эскалаци"],
            "cands": [
                "Юрист подключается при крупной претензии клиента.",
                "Порядок первичного ответа на претензию без эскалации.",
                "Справочная информация о договорах перевозки.",
            ],
            "cand_sources": ["doc_d.md", "doc_d.md", "doc_e.md"],
        },
        {
            "case_id": "mock-miss",
            "query": "таможенное оформление авиагруза данные",
            "kws": ["таможен", "декларац"],
            "cands": [
                "Складские операции и хранение груза на терминале.",
                "Общие правила приёмки груза без оформления и проверок.",
            ],
            "cand_sources": ["doc_f.md", "doc_g.md"],
        },
    ]


# ---------------------------------------------------------------------------
# Parent-window expansion — reuses production HybridRetriever._expand_parents
# ---------------------------------------------------------------------------

class ParentExpander:
    """Reproduces the arm-C chunk list from the corpus and reuses the production
    `HybridRetriever._expand_parents` to expand top-k candidate texts.

    The chunk reproduction mirrors `ab_remote_contextual.stage_expand`: same
    `select_chunks` + `add_contextual_headers` pipeline, verified 1:1 against the
    Kaggle/Mac stack in the residual-miss diagnosis. No models are loaded here —
    expansion is a pure ingestion-order text lookup.
    """

    def __init__(self, corpus: Path) -> None:
        import os

        # Match the arm-C (production) chunking env before settings are read.
        os.environ.setdefault("RAG_SEMANTIC_CHUNKING", "false")
        os.environ.setdefault("RAG_STRUCTURAL_CHUNKING", "true")

        from config.settings import get_settings
        from ingestion.loader import DocumentLoader
        from vectordb import manager
        from vectordb._base_manager import select_chunks

        settings = get_settings()
        docs = DocumentLoader(recursive=False).load_documents(str(corpus))
        if not docs:
            raise RuntimeError(f"no documents under {corpus}")
        chunks = select_chunks(
            list(docs), None, settings.chunk_size, settings.chunk_overlap, settings=settings
        )
        if getattr(settings, "contextual_headers", False):
            chunks = manager.add_contextual_headers(chunks, docs, chunk_size=settings.chunk_size)
        self._chunks = chunks
        self._text_to_pos: dict[str, int] = {}
        for idx, chunk in enumerate(chunks):
            self._text_to_pos.setdefault(chunk.page_content, idx)
        self._retriever_cache: dict[tuple[int, int], Any] = {}
        self._doc_cls = None
        print(f"[expander] corpus -> {len(chunks)} chunks (arm-C reproduction)", flush=True)

    def _retriever(self, window: int, max_chars: int) -> Any:
        key = (window, max_chars)
        cached = self._retriever_cache.get(key)
        if cached is not None:
            return cached
        from vectordb._base_manager import HybridRetriever

        retriever = HybridRetriever(
            vector_store=None,
            chunks=self._chunks,
            reranker=None,
            use_bm25=False,
            parent_expansion=True,
            parent_expansion_window=window,
            parent_expansion_max_chars=max_chars,
        )
        self._retriever_cache[key] = retriever
        return retriever

    def expand(self, texts: Sequence[str], sources: Sequence[str],
               window: int, max_chars: int) -> list[str]:
        if window <= 0:
            return list(texts)
        from vectordb._base_manager import Document

        selected: list[Any] = []
        for i, text in enumerate(texts):
            pos = self._text_to_pos.get(text)
            if pos is None:
                src = sources[i] if i < len(sources) else "?"
                selected.append(Document(page_content=text, metadata={"source": src}))
            else:
                selected.append(self._chunks[pos])
        expanded = self._retriever(window, max_chars)._expand_parents(selected)
        return [d.page_content for d in expanded]


class NullExpander:
    """Smoke / no-corpus expander: expansion is a no-op (window ignored)."""

    def expand(self, texts: Sequence[str], sources: Sequence[str],
               window: int, max_chars: int) -> list[str]:
        return list(texts)


# ---------------------------------------------------------------------------
# grade_docs CRAG filter — reuses production agent.graph.make_grade_docs_node
# ---------------------------------------------------------------------------

class _StubGradeLLM:
    """Deterministic offline stand-in for the --stub-grade smoke.

    Forces the per-document branch (the batch verdict is left unparseable) and
    marks a document irrelevant only when it carries the IRRELEVANT sentinel, so
    the smoke proves the state->graded_docs plumbing and one real filter drop.
    """

    def __init__(self) -> None:
        self._first = True

    def invoke(self, prompt: str) -> str:
        if self._first:
            self._first = False
            return ""  # unparseable batch verdict -> node falls back to per-doc
        return "NO" if "IRRELEVANT" in prompt else "YES"


class DocGrader:
    """Applies the production grade_docs node to a case's context docs."""

    def __init__(self, llm_factory: Callable[[], Any], tenant_id: str = "aircargo") -> None:
        self._llm_factory = llm_factory
        self._tenant_id = tenant_id

    def grade(self, query: str, texts: Sequence[str], sources: Sequence[str]) -> list[str]:
        from agent.graph import make_grade_docs_node

        context_docs = [
            {
                "page_content": t,
                "metadata": {"source": sources[i] if i < len(sources) else "?"},
            }
            for i, t in enumerate(texts)
        ]
        node = make_grade_docs_node(self._llm_factory())
        state: dict[str, Any] = {
            "question": query,
            "context_docs": context_docs,
            "trace_id": f"q1-ab-grade-{uuid.uuid4().hex[:8]}",
            "tenant_id": self._tenant_id,
        }
        out = node(state)
        graded = out.get("graded_docs") or []
        return [d.get("page_content", "") if isinstance(d, dict) else str(d) for d in graded]


def make_mistral_llm() -> Any:
    """external-mistral judge/grader LLM (same convention as the RAGAS baseline)."""
    from scripts.aircargo_ragas_free import FreeChatLLM

    return FreeChatLLM("mistral", "mistral-small-latest", min_interval_s=1.0)


# ---------------------------------------------------------------------------
# Per-arm evaluation — reuses evaluation.ragas_eval + ab_remote._kw_status
# ---------------------------------------------------------------------------

def final_texts_for_case(
    row: dict[str, Any],
    arm: Arm,
    expander: Any,
    grader: Optional[DocGrader],
) -> list[str]:
    """rerank -> slice top-k -> parent-expand -> (optional) grade filter."""
    cands = list(row.get("cands", []))
    sources = list(row.get("cand_sources", []))
    top_texts = cands[: arm.rerank_k]
    top_sources = sources[: arm.rerank_k]
    expanded = expander.expand(top_texts, top_sources, arm.window, arm.max_chars)
    if arm.grade and grader is not None:
        graded = grader.grade(row.get("query", ""), expanded, top_sources)
        # An empty grade result (LLM failure / everything filtered) would zero the
        # metrics unfairly; keep the pre-grade docs in that degenerate case.
        if graded:
            return graded
    return expanded


def evaluate_arm(
    rows: Sequence[dict[str, Any]],
    arm: Arm,
    expander: Any,
    grader: Optional[DocGrader],
) -> dict[str, Any]:
    from evaluation.ragas_eval import context_precision, context_recall
    from scripts.ab_remote_contextual import _kw_status

    per_case: list[dict[str, Any]] = []
    counts = {"FULL": 0, "PART": 0, "MISS": 0}
    prec_sum = 0.0
    rec_sum = 0.0
    for row in rows:
        query = row.get("query", "")
        kws = list(row.get("kws", []))
        texts = final_texts_for_case(row, arm, expander, grader)
        prec = context_precision(query, texts, kws)
        rec = context_recall(texts, kws)
        status = _kw_status(kws, texts)
        counts[status] += 1
        prec_sum += prec
        rec_sum += rec
        per_case.append({
            "case_id": row.get("case_id"),
            "n_docs": len(texts),
            "context_precision": round(prec, 4),
            "context_recall": round(rec, 4),
            "kw_status": status,
        })
    n = max(len(rows), 1)
    return {
        "arm": arm.name,
        "rerank_k": arm.rerank_k,
        "window": arm.window,
        "max_chars": arm.max_chars,
        "grade": arm.grade,
        "note": arm.note,
        "aggregate": {
            "context_precision": round(prec_sum / n, 4),
            "context_recall": round(rec_sum / n, 4),
            "FULL": counts["FULL"],
            "PART": counts["PART"],
            "MISS": counts["MISS"],
            "num_cases": len(rows),
        },
        "per_case": per_case,
    }


# ---------------------------------------------------------------------------
# SHIP verdict
# ---------------------------------------------------------------------------

@dataclass
class ShipCriteria:
    min_precision_gain: float = 0.05  # absolute mean context_precision lift vs baseline
    recall_floor: float = 0.90        # context_recall must not drop below this
    full_floor: int = 96              # keyword FULL must not regress below D2's 96
    max_miss: int = 1                 # keyword MISS must not exceed D2's 1
    metrics: list[str] = field(default_factory=list)


def verdict_for_arm(
    arm_result: dict[str, Any],
    baseline: dict[str, Any],
    crit: ShipCriteria,
) -> tuple[str, str]:
    if arm_result["arm"] == baseline["arm"]:
        return ("BASELINE", "reference arm")
    agg = arm_result["aggregate"]
    base = baseline["aggregate"]
    gain = agg["context_precision"] - base["context_precision"]
    reasons: list[str] = []
    ok = True
    if gain < crit.min_precision_gain:
        ok = False
        reasons.append(f"precision +{gain:.3f} < +{crit.min_precision_gain:.2f}")
    if agg["context_recall"] < crit.recall_floor:
        ok = False
        reasons.append(f"recall {agg['context_recall']:.3f} < {crit.recall_floor:.2f}")
    if agg["FULL"] < crit.full_floor:
        ok = False
        reasons.append(f"FULL {agg['FULL']} < {crit.full_floor}")
    if agg["MISS"] > crit.max_miss:
        ok = False
        reasons.append(f"MISS {agg['MISS']} > {crit.max_miss}")
    if ok:
        return ("SHIP-CANDIDATE", f"precision +{gain:.3f}, recall {agg['context_recall']:.3f}")
    return ("no-ship", "; ".join(reasons))


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Q1 context_precision A/B — {report['run_id']}",
        "",
        f"- Created at: `{report['created_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Rerank pool: `{report['rerank_artifact']}`",
        f"- Cases: `{report['num_cases']}`",
        f"- Baseline arm: `{report['baseline_arm']}`",
        "",
        "SHIP criteria: context_precision gain ≥ "
        f"{report['ship_criteria']['min_precision_gain']:.2f} vs baseline; "
        f"context_recall ≥ {report['ship_criteria']['recall_floor']:.2f}; "
        f"keyword FULL ≥ {report['ship_criteria']['full_floor']}; "
        f"MISS ≤ {report['ship_criteria']['max_miss']}. NO-SHIP is a valid outcome.",
        "",
        "| arm | rerank_k | window/max_chars | grade | ctx_precision | Δ vs base | ctx_recall | FULL | PART | MISS | verdict |",
        "|---|---:|---|:---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    base_prec = report["arms"][0]["aggregate"]["context_precision"]
    for arm in report["arms"]:
        agg = arm["aggregate"]
        delta = agg["context_precision"] - base_prec
        win = f"{arm['window']}/{arm['max_chars']}" if arm["window"] else "off"
        lines.append(
            f"| {arm['arm']} | {arm['rerank_k']} | {win} | "
            f"{'on' if arm['grade'] else '—'} | {agg['context_precision']:.4f} | "
            f"{delta:+.4f} | {agg['context_recall']:.4f} | {agg['FULL']} | "
            f"{agg['PART']} | {agg['MISS']} | {arm['verdict']} ({arm['verdict_reason']}) |"
        )
    lines.extend(["", "## Notes per arm", ""])
    for arm in report["arms"]:
        lines.append(f"- **{arm['arm']}** — {arm['note']}")
    if report.get("judge"):
        lines.extend(["", "## Judge (external-mistral, opt-in)", ""])
        lines.append("| arm | faithfulness | answer_relevancy |")
        lines.append("|---|---:|---:|")
        for name, jr in report["judge"].items():
            lines.append(f"| {name} | {jr['faithfulness']:.4f} | {jr['answer_relevancy']:.4f} |")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(report: dict[str, Any], results_dir: Path) -> tuple[Path, Path]:
    results_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report['run_id']}-q1-context-precision-ab"
    json_path = results_dir / f"{stem}.json"
    md_path = results_dir / f"{stem}.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n"
    )
    md_path.write_text(render_markdown(report), encoding="utf-8", newline="\n")
    return json_path, md_path


# ---------------------------------------------------------------------------
# Optional judge layer (faithfulness / answer_relevancy) — opt-in, mistral
# ---------------------------------------------------------------------------

def run_judge(
    rows: Sequence[dict[str, Any]],
    arm: Arm,
    expander: Any,
    grader: Optional[DocGrader],
    llm: Any,
) -> dict[str, float]:
    """Generate answers from the arm's contexts and judge them (reuses the
    RAGAS baseline generator + RAGEvaluator, external-mistral)."""
    from evaluation.ragas_eval import RAGEvaluator
    from evaluation.ragas_eval import TestCase as RAGTestCase
    from scripts.aircargo_ragas_free import _generate_answer

    rag_cases: list[Any] = []
    answers: list[str] = []
    contexts: list[list[dict[str, Any]]] = []
    for row in rows:
        texts = final_texts_for_case(row, arm, expander, grader)
        try:
            ans = _generate_answer(llm, row.get("query", ""), texts)
        except Exception:  # noqa: BLE001 - one bad case must not kill the judge
            ans = ""
        rag_cases.append(RAGTestCase(
            question=row.get("query", ""), expected_keywords=list(row.get("kws", [])),
            category="aircargo",
        ))
        answers.append(ans)
        contexts.append([{"page_content": t, "metadata": {}} for t in texts])
    result = RAGEvaluator(eval_llm=llm).evaluate_batch(rag_cases, answers=answers,
                                                       context_docs_list=contexts)
    agg = result["aggregate"]
    return {"faithfulness": agg["faithfulness"], "answer_relevancy": agg["answer_relevancy"]}


# ---------------------------------------------------------------------------
# Heavy embed+rerank pool build (Mac/Colab only) via ab_remote_contextual
# ---------------------------------------------------------------------------

def build_pool(out_dir: Path, arm: str = "C") -> Path:
    """Run the existing two-process embed+rerank stages (models never co-resident)."""
    script = str(PROJECT_ROOT / "scripts" / "ab_remote_contextual.py")
    for stage in ("pools", "rerank"):
        cmd = [sys.executable, script, "--stage", stage, "--arm", arm, "--out-dir", str(out_dir)]
        print(f"[build-pool] $ {' '.join(cmd)}", flush=True)
        rc = subprocess.run(cmd, check=False).returncode
        if rc != 0:
            raise RuntimeError(f"ab_remote_contextual --stage {stage} failed (rc={rc})")
    artifact = out_dir / f"ab_candidates_phase2_{arm}.json"
    if not artifact.exists():
        raise RuntimeError(f"expected rerank artifact missing: {artifact}")
    return artifact


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run(
    rows: Sequence[dict[str, Any]],
    *,
    grid: Sequence[Arm],
    expander: Any,
    with_grade: bool,
    stub_grade: bool,
    with_judge: bool,
    mode: str,
    rerank_artifact: str,
) -> dict[str, Any]:
    grader: Optional[DocGrader] = None
    if with_grade:
        if stub_grade:
            grader = DocGrader(_StubGradeLLM)
        else:
            shared = make_mistral_llm()
            grader = DocGrader(lambda: shared)

    arm_results: list[dict[str, Any]] = []
    for arm in grid:
        print(f"[arm] {arm.name} k={arm.rerank_k} win={arm.window}/{arm.max_chars} "
              f"grade={arm.grade}", flush=True)
        arm_results.append(evaluate_arm(rows, arm, expander, grader))

    baseline = next((a for a in arm_results if a["arm"] == BASELINE_ARM), arm_results[0])
    crit = ShipCriteria()
    # baseline first in the table
    arm_results.sort(key=lambda a: (a["arm"] != baseline["arm"], a["arm"]))
    for a in arm_results:
        v, reason = verdict_for_arm(a, baseline, crit)
        a["verdict"] = v
        a["verdict_reason"] = reason

    started = datetime.now(timezone.utc)
    report: dict[str, Any] = {
        "run_id": f"{started.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}",
        "created_at": started.isoformat(),
        "mode": mode,
        "rerank_artifact": rerank_artifact,
        "num_cases": len(rows),
        "baseline_arm": baseline["arm"],
        "ship_criteria": {
            "min_precision_gain": crit.min_precision_gain,
            "recall_floor": crit.recall_floor,
            "full_floor": crit.full_floor,
            "max_miss": crit.max_miss,
        },
        "arms": arm_results,
    }

    if with_judge and not stub_grade:
        llm = make_mistral_llm()
        judge: dict[str, dict[str, float]] = {}
        # judge only the baseline and the best SHIP-candidate (bounded LLM cost)
        candidates = [a for a in arm_results if a["verdict"] == "SHIP-CANDIDATE"]
        best = max(candidates, key=lambda a: a["aggregate"]["context_precision"], default=None)
        judged_arms = [baseline] + ([best] if best is not None else [])
        arm_by_name = {a.name: a for a in grid}
        for a in judged_arms:
            arm = arm_by_name[a["arm"]]
            print(f"[judge] {arm.name}", flush=True)
            judge[arm.name] = run_judge(rows, arm, expander, grader, llm)
        report["judge"] = judge

    return report


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Q1 context_precision knob A/B (offline)")
    p.add_argument("--rerank-artifact",
                   default=str(PROJECT_ROOT / ".tmp" / "ab_candidates_phase2_C.json"),
                   help="reranked candidate pool from ab_remote_contextual --stage rerank --arm C")
    p.add_argument("--corpus", default=str(PROJECT_ROOT / "data" / "uploads" / "aircargo"),
                   help="aircargo corpus dir for parent-window expansion")
    p.add_argument("--build-pool", action="store_true",
                   help="run the heavy embed+rerank stages first (Mac/Colab only)")
    p.add_argument("--out-dir", default=str(PROJECT_ROOT / ".tmp"),
                   help="dir for the built rerank pool (--build-pool)")
    p.add_argument("--with-grade", action="store_true",
                   help="add grade_docs CRAG arms (external-mistral LLM)")
    p.add_argument("--with-judge", action="store_true",
                   help="also compute faithfulness/answer_relevancy on baseline+winner (mistral)")
    p.add_argument("--mock", action="store_true",
                   help="Windows smoke: tiny in-memory pool, no models, no corpus")
    p.add_argument("--stub-grade", action="store_true",
                   help="smoke: use a deterministic offline grade stub instead of mistral")
    p.add_argument("--results-dir", default=str(PROJECT_ROOT / "reports" / "ragas"))
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    # Mock mode must never touch the network: grade always uses the offline stub
    # and the mistral judge is disabled regardless of flags.
    stub_grade = args.stub_grade or args.mock
    with_judge = args.with_judge and not args.mock

    if args.mock:
        rows = mock_rows()
        expander: Any = NullExpander()
        mode = "mock"
        artifact_label = "mock"
        with_grade = args.with_grade or args.stub_grade
    else:
        if args.build_pool:
            artifact = build_pool(Path(args.out_dir))
        else:
            artifact = Path(args.rerank_artifact)
        if not artifact.exists():
            print(json.dumps({
                "status": "error",
                "detail": f"rerank artifact not found: {artifact}; run with --build-pool "
                          "or point --rerank-artifact at ab_remote_contextual output",
            }, ensure_ascii=False))
            return 2
        rows = load_rerank_rows(artifact)
        expander = ParentExpander(Path(args.corpus))
        mode = "live"
        artifact_label = str(artifact)
        with_grade = args.with_grade

    grid = build_grid(with_grade=with_grade)
    report = run(
        rows,
        grid=grid,
        expander=expander,
        with_grade=with_grade,
        stub_grade=stub_grade,
        with_judge=with_judge,
        mode=mode,
        rerank_artifact=artifact_label,
    )

    json_path, md_path = write_outputs(report, Path(args.results_dir))
    ship = [a["arm"] for a in report["arms"] if a["verdict"] == "SHIP-CANDIDATE"]
    print(json.dumps({
        "status": "ok",
        "run_id": report["run_id"],
        "mode": mode,
        "num_cases": report["num_cases"],
        "arms": len(report["arms"]),
        "ship_candidates": ship,
        "report_markdown": str(md_path),
        "report_json": str(json_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
