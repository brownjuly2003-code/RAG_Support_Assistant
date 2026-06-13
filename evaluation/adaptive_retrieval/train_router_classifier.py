#!/usr/bin/env python3
"""Track R / R1 (adaptive-retrieval) — lightweight router classifier.

Trains a cheap TF-IDF + LinearSVC classifier on the Phase-0 labels
(``phase0_labels.jsonl``) and compares it against the existing LLM
``classify_complexity`` node on:

  * **macro-F1** — on the human 4-class ``query_class`` taxonomy and on the
    binary *routing decision* the graph actually ships (``vector`` vs
    ``hybrid``), and
  * **cost** — tokens + latency per query.

Why a *routing* target as well as the 4-class one
-------------------------------------------------
The LLM classifier emits ``SIMPLE / COMPLEX / GLOBAL`` (a 3-class taxonomy),
not the Phase-0 ``simple / factual / enumeration / multi-condition``. Scoring
the LLM on the 4-class gold is apples-to-oranges (it was never asked to produce
those labels). The decision that actually *ships* through
``agent.graph._select_retrieval_strategy`` is, with the default
``retrieval_strategy="hybrid"`` config, binary:

    complexity == "simple"  -> vector
    otherwise               -> hybrid     (graph only if configured graph+global)

So we derive a binary ``route`` target from ``query_class`` and score *both*
classifiers on it — that is the apples-to-apples comparison.

  query_class -> route gold
    simple, factual              -> vector   (short single-answer / value lookup)
    enumeration, multi-condition -> hybrid   (list / conditional reasoning)

Important production caveat (measured 2026-06-14)
-------------------------------------------------
``model_routing_enabled`` defaults to **false** and ``retrieval_strategy``
defaults to **hybrid**. In that default config the ``classify_complexity`` node
short-circuits to ``complexity="unknown"`` *without calling the LLM at all*, and
the router always returns ``hybrid`` (the D2 baseline). So there is **no
per-query LLM classify cost in the current production default** — Track R's
cost saving only materialises *if/when* model routing is enabled. R1's value:
it makes enabling routing essentially free (no per-query LLM tax), removing the
main reason to keep routing off. Whether to actually enable routing (R2 / wiring)
stays gated on the Phase-5 offline delta showing no regressions.

Usage
-----
    # offline only (no provider, free, deterministic):
    python evaluation/adaptive_retrieval/train_router_classifier.py

    # with live LLM comparison (ministral-3b via external-mistral):
    #   set MISTRAL_API_KEY in env first (do not print it)
    LLM_PROVIDER_PROFILE=external-mistral \
      python evaluation/adaptive_retrieval/train_router_classifier.py --llm
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # allow `config.*` / `llm.*` imports when run as a script
LABELS_PATH = Path(__file__).resolve().parent / "phase0_labels.jsonl"
DEFAULT_OUT = Path(__file__).resolve().parent / "r1_router_results.json"

# query_class -> binary routing decision (default hybrid config; see module docstring).
ROUTE_OF_CLASS = {
    "simple": "vector",
    "factual": "vector",
    "enumeration": "hybrid",
    "multi-condition": "hybrid",
}

# ---------------------------------------------------------------------------
# LLM classify prompt + parse — copied verbatim from agent/prompts.py
# (CLASSIFY_COMPLEXITY_PROMPT_V1) and agent/graph.make_classify_complexity_node
# so the comparison reflects exactly what the graph would do, without importing
# the heavy graph/langchain stack.
# ---------------------------------------------------------------------------
CLASSIFY_PROMPT = """Classify the user question as SIMPLE, COMPLEX, or GLOBAL.

SIMPLE: factual lookup, single concept, short answer (<5 sentences).
  Examples: 'How to reset password?', 'What is X?', 'Where is the Y button?'

COMPLEX: multi-step reasoning, comparison, analysis, inference,
or synthesis across a small set of documents.
  Examples: 'Compare A and B', 'Explain why X causes Y',
            'Analyze this contract against policy Z'

GLOBAL: corpus-level or multi-hop question that asks about themes,
relationships, or patterns across many documents.
  Examples: 'Which policies relate to contract X?',
            'What topics recur across the HR corpus?'

Output strictly one word: SIMPLE, COMPLEX, or GLOBAL.

Question: {question}

Classification:"""


def parse_complexity(raw: str) -> str:
    """Mirror agent.graph.make_classify_complexity_node parsing."""
    raw = (raw or "").strip().upper()
    if raw.startswith("SIMPLE"):
        return "simple"
    if raw.startswith("GLOBAL") or raw.startswith("MULTI_HOP") or raw.startswith("MULTIHOP"):
        return "global"
    if raw.startswith("COMPLEX"):
        return "complex"
    return "complex"  # node default for unrecognised output


def complexity_to_route(complexity: str) -> str:
    """Mirror agent.graph._select_retrieval_strategy under default hybrid config."""
    return "vector" if complexity == "simple" else "hybrid"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_rows() -> list[dict]:
    rows = []
    for raw in LABELS_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def build_classifier() -> Pipeline:
    """TF-IDF (word 1-2 + char_wb 3-5) + LinearSVC.

    Char n-grams give cheap robustness to Russian morphology without a stemmer.
    Wrapped in a Pipeline so the vectorizer is refit per CV fold (no leakage).
    """
    features = FeatureUnion(
        [
            ("word", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=1, sublinear_tf=True)),
        ]
    )
    return Pipeline([("feats", features), ("clf", LinearSVC(C=1.0, class_weight="balanced"))])


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    from sklearn.metrics import f1_score

    return float(f1_score(y_true, y_pred, average="macro"))


def per_class_report(y_true: list[str], y_pred: list[str]) -> dict:
    from sklearn.metrics import classification_report

    return classification_report(y_true, y_pred, output_dict=True, zero_division=0)


def cv_predict(X: list[str], y: list[str], folds: int, seed: int) -> list[str]:
    skf = StratifiedKFold(n_splits=folds, shuffle=True, random_state=seed)
    preds = cross_val_predict(build_classifier(), X, y, cv=skf)
    return list(preds)


# ---------------------------------------------------------------------------
# LLM comparison (optional)
# ---------------------------------------------------------------------------
def run_llm_comparison(queries: list[str], timeout_note: list[str]) -> dict | None:
    """Run the LLM classify on every query via the project's provider runtime.

    Returns per-query complexity + route + token usage + latency, or None if a
    provider could not be built (offline / no key).
    """
    try:
        from config.settings import get_settings
        from llm.providers.runtime import build_provider_runtime

        settings = get_settings()
        runtime = build_provider_runtime(settings)
        llm_fast = runtime.fast
    except Exception as exc:  # noqa: BLE001 — provider unavailable is a soft skip
        timeout_note.append(f"LLM comparison skipped: could not build provider runtime ({type(exc).__name__}: {exc})")
        return None

    profile = getattr(runtime, "profile_name", "?")
    model = ""
    try:
        model = getattr(llm_fast, "model", "") or getattr(getattr(llm_fast, "_target", None), "model", "")
    except Exception:  # noqa: BLE001
        model = ""

    records = []
    input_tokens_total = 0
    output_tokens_total = 0
    latencies_ms: list[float] = []
    errors = 0
    for i, q in enumerate(queries):
        prompt = CLASSIFY_PROMPT.format(question=q)
        t0 = time.perf_counter()
        try:
            raw = llm_fast.invoke(prompt)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            records.append({"idx": i, "error": f"{type(exc).__name__}: {exc}", "complexity": None, "route": None})
            continue
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies_ms.append(dt_ms)
        complexity = parse_complexity(raw if isinstance(raw, str) else str(raw))
        route = complexity_to_route(complexity)
        lr = getattr(llm_fast, "last_response", None)
        in_tok = int(getattr(lr, "input_tokens", 0) or 0)
        out_tok = int(getattr(lr, "output_tokens", 0) or 0)
        input_tokens_total += in_tok
        output_tokens_total += out_tok
        records.append(
            {
                "idx": i,
                "complexity": complexity,
                "route": route,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "latency_ms": round(dt_ms, 1),
            }
        )
        if (i + 1) % 25 == 0:
            print(f"  ... LLM classified {i + 1}/{len(queries)}")

    n_ok = len(latencies_ms)
    return {
        "profile": profile,
        "model": model,
        "n": len(queries),
        "errors": errors,
        "input_tokens_total": input_tokens_total,
        "output_tokens_total": output_tokens_total,
        "input_tokens_mean": round(input_tokens_total / n_ok, 1) if n_ok else None,
        "latency_ms_mean": round(sum(latencies_ms) / n_ok, 1) if n_ok else None,
        "latency_ms_p95": round(float(np.percentile(latencies_ms, 95)), 1) if n_ok else None,
        "records": records,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Track R / R1 — lightweight router classifier vs LLM.")
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--llm", action="store_true", help="run live LLM classify comparison (needs provider/key)")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    rows = load_rows()
    queries = [str(r["query"]) for r in rows]
    y_class = [str(r["query_class"]) for r in rows]
    y_route = [ROUTE_OF_CLASS[c] for c in y_class]
    y_fc = ["factcard" if r.get("needs_factcard") else "no" for r in rows]
    n = len(rows)
    print(f"Loaded {n} labelled queries from {LABELS_PATH.relative_to(ROOT)}")

    results: dict = {"n": n, "folds": args.folds, "seed": args.seed}

    # --- Lightweight classifier, CV ---
    print("\n=== Lightweight TF-IDF + LinearSVC (stratified %d-fold CV) ===" % args.folds)
    for target_name, y in (("query_class", y_class), ("route", y_route), ("needs_factcard", y_fc)):
        preds = cv_predict(queries, y, args.folds, args.seed)
        f1 = macro_f1(y, preds)
        rep = per_class_report(y, preds)
        acc = float(rep["accuracy"]) if "accuracy" in rep else None
        results[f"light_{target_name}"] = {
            "macro_f1": round(f1, 4),
            "accuracy": round(acc, 4) if acc is not None else None,
            "per_class": {
                k: {"precision": round(v["precision"], 3), "recall": round(v["recall"], 3), "f1": round(v["f1-score"], 3), "support": int(v["support"])}
                for k, v in rep.items()
                if k not in ("accuracy", "macro avg", "weighted avg")
            },
        }
        print(f"\n[{target_name}] macro-F1 = {f1:.4f}  accuracy = {acc:.4f}")
        for k, v in results[f"light_{target_name}"]["per_class"].items():
            print(f"    {k:<16} P={v['precision']:.3f} R={v['recall']:.3f} F1={v['f1']:.3f} (n={v['support']})")

    # --- LLM comparison ---
    if args.llm:
        print("\n=== LLM classify_complexity comparison (live) ===")
        notes: list[str] = []
        llm = run_llm_comparison(queries, notes)
        for note in notes:
            print("  " + note)
        if llm is not None:
            llm_route_pred = [rec.get("route") for rec in llm["records"]]
            # score only on rows where the LLM produced a route
            pairs = [(g, p) for g, p in zip(y_route, llm_route_pred, strict=True) if p is not None]
            if pairs:
                g_list = [g for g, _ in pairs]
                p_list = [p for _, p in pairs]
                llm_route_f1 = macro_f1(g_list, p_list)
                llm_route_acc = float(sum(int(g == p) for g, p in pairs)) / len(pairs)
                rep = per_class_report(g_list, p_list)
                results["llm_route"] = {
                    "macro_f1": round(llm_route_f1, 4),
                    "accuracy": round(llm_route_acc, 4),
                    "scored_n": len(pairs),
                    "model": llm["model"],
                    "profile": llm["profile"],
                    "errors": llm["errors"],
                    "input_tokens_mean": llm["input_tokens_mean"],
                    "input_tokens_total": llm["input_tokens_total"],
                    "latency_ms_mean": llm["latency_ms_mean"],
                    "latency_ms_p95": llm["latency_ms_p95"],
                    "per_class": {
                        k: {"precision": round(v["precision"], 3), "recall": round(v["recall"], 3), "f1": round(v["f1-score"], 3), "support": int(v["support"])}
                        for k, v in rep.items()
                        if k not in ("accuracy", "macro avg", "weighted avg")
                    },
                }
                print(f"\n[LLM route] macro-F1 = {llm_route_f1:.4f}  accuracy = {llm_route_acc:.4f}  (model={llm['model']}, profile={llm['profile']}, scored {len(pairs)}/{n}, errors={llm['errors']})")
                print(f"  cost/query: input_tokens≈{llm['input_tokens_mean']}  latency_mean={llm['latency_ms_mean']}ms  p95={llm['latency_ms_p95']}ms")
                light_route_f1 = results["light_route"]["macro_f1"]
                delta = light_route_f1 - llm_route_f1
                results["route_comparison"] = {
                    "light_route_macro_f1": light_route_f1,
                    "llm_route_macro_f1": round(llm_route_f1, 4),
                    "delta_light_minus_llm": round(delta, 4),
                    "light_tokens_per_query": 0,
                    "light_latency_ms_mean": None,  # filled below
                }
                print(f"\n  >>> route macro-F1: lightweight={light_route_f1:.4f} vs LLM={llm_route_f1:.4f}  (delta={delta:+.4f})")
    else:
        print("\n(LLM comparison not run; pass --llm with a provider/key for the apples-to-apples route comparison.)")

    # --- Lightweight predict latency (fit on all, time predict) ---
    clf = build_classifier()
    clf.fit(queries, y_route)
    t0 = time.perf_counter()
    _ = clf.predict(queries)
    light_predict_ms_total = (time.perf_counter() - t0) * 1000.0
    results["light_predict_ms_per_query"] = round(light_predict_ms_total / n, 4)
    results["light_tokens_per_query"] = 0
    if "route_comparison" in results:
        results["route_comparison"]["light_latency_ms_mean"] = results["light_predict_ms_per_query"]
    print(f"\nLightweight predict latency: {results['light_predict_ms_per_query']:.4f} ms/query, 0 LLM tokens.")

    # --- class distribution for the report ---
    from collections import Counter

    results["dist_query_class"] = dict(Counter(y_class))
    results["dist_route"] = dict(Counter(y_route))
    results["dist_needs_factcard"] = dict(Counter(y_fc))

    args.out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"\nWrote {args.out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
