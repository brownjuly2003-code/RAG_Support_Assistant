#!/usr/bin/env python3
"""
evaluation/benchmark_offline_with_docs.py

Offline benchmark that scores 12 test cases against the locally seeded demo KB
(``demo/docs/``). Each case in a supported category (error_codes, warranty,
billing — see ``CATEGORY_TO_DOC``) receives the mapped demo doc as context;
cases in unsupported categories (reset_password, installation, general) get
an empty context, which honestly reflects the gap described in the docs.

Output mirrors ``benchmark_runner.py``: written to
``data/evaluation/benchmark_results.json``.

Preconditions:
    ``demo/docs/*.md`` must exist (run ``python -m demo.seed_docs`` first).
    The script raises ``FileNotFoundError`` if a mapped category resolves to
    a missing file, so a stale ``benchmark_results.json`` is never silently
    overwritten with empty-context numbers.

Run from repo root:
    python -m demo.seed_docs
    python evaluation/benchmark_offline_with_docs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from evaluation.benchmark_runner import load_test_cases  # noqa: E402
from evaluation.ragas_eval import RAGEvaluator  # noqa: E402

CATEGORY_TO_DOC = {
    "error_codes": "errors_e10_e30.md",
    "warranty": "warranty.md",
    "billing": "returns_policy.md",
}

DOCS_DIR = ROOT / "demo" / "docs"
OUT_PATH = ROOT / "data" / "evaluation" / "benchmark_results.json"


def _verify_seed_present() -> None:
    """Fail loudly if the mapped demo docs are missing.

    Without this, a clean checkout where ``python -m demo.seed_docs`` has
    not been run would silently score every case against an empty context
    and overwrite ``benchmark_results.json`` with unrepresentative metrics.
    """
    missing = [
        name for name in CATEGORY_TO_DOC.values()
        if not (DOCS_DIR / name).exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"demo docs missing under {DOCS_DIR}: {missing}. "
            "Run `python -m demo.seed_docs` before this benchmark."
        )


def main() -> None:
    _verify_seed_present()

    cases_path = ROOT / "evaluation" / "test_cases.json"
    cases = load_test_cases(str(cases_path))

    context_docs_list = []
    coverage_summary: dict[str, int] = {}
    for tc in cases:
        coverage_summary[tc.category or "_none"] = (
            coverage_summary.get(tc.category or "_none", 0) + 1
        )
        doc_name = CATEGORY_TO_DOC.get(tc.category or "")
        if doc_name:
            doc_path = DOCS_DIR / doc_name
            # _verify_seed_present() already guarantees existence; treating
            # absence as missing-context here would mask a regression.
            context_docs_list.append(
                [{"page_content": doc_path.read_text(encoding="utf-8"),
                  "metadata": {"source": doc_name}}]
            )
            continue
        context_docs_list.append([])

    answers = [tc.expected_answer or "" for tc in cases]

    evaluator = RAGEvaluator(results_dir=str(OUT_PATH.parent))
    result = evaluator.evaluate_batch(
        cases,
        answers=answers,
        context_docs_list=context_docs_list,
        use_embeddings=False,
    )
    result["context_source"] = "demo/docs (category->doc mapping)"
    result["category_coverage"] = coverage_summary
    result["supported_categories"] = sorted(CATEGORY_TO_DOC.keys())

    print("--- Aggregate scores ---")
    for metric, score in result["aggregate"].items():
        print(f"  {metric}: {score:.4f}")
    print(f"  num_cases: {result['num_cases']}")
    print(f"  categories: {coverage_summary}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"\nResults saved to: {OUT_PATH}")


if __name__ == "__main__":
    main()
