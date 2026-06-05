#!/usr/bin/env python3
"""Precompute field-aware HyDE query expansions for the 100 aircargo cases.

Arm E of the Phase 2 series (docs/operations/2026-06-05-query-expansion-probe.md):
the probe showed the field-aware HyDE prompt bridges the NL-RU <-> snake_case
lexical gap (BM25 rank of the kw chunk 159->13 / 305->2 / 89->5 / 1021->99 on the
4 deep cases). This script precomputes the expansions LOCALLY (mistral-small,
temperature=0, free-tier pacing) so the Kaggle kernel needs no API key: the
expansions travel to the kernel as a dataset file.

Output (JSON list, consumed by scripts/ab_remote_contextual.py --arm E):
  [{"case_id": ..., "query": <original>, "expansion": <LLM text>,
    "expanded_query": "<original> <LLM text>"}]

Usage:
  set -a; . ./.env; set +a
  python scripts/precompute_field_hyde.py \
      --out .tmp/query_expansions_field_hyde.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.aircargo_ragas_free import FreeChatLLM  # noqa: E402

# Exact probe prompt — docs/operations/2026-06-05-query-expansion-probe.md.
FIELD_HYDE_PROMPT = (
    "Корпоративная база знаний хранит регламенты с шаблонами, где поля записаны\n"
    "в snake_case на английском (например booking_number, flight_date).\n"
    "Для вопроса ниже напиши короткий гипотетический ответ (2-3 предложения) и\n"
    "перечисли 5-10 вероятных snake_case имён полей, относящихся к вопросу.\n"
    "\n"
    "Вопрос: {query}\n"
    "\n"
    "Гипотетический ответ и поля:"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", default=str(PROJECT_ROOT / "evaluation" / "curated_cases_aircargo.jsonl")
    )
    parser.add_argument(
        "--out", default=str(PROJECT_ROOT / ".tmp" / "query_expansions_field_hyde.json")
    )
    parser.add_argument("--model", default="mistral-small-latest")
    parser.add_argument("--min-interval", type=float, default=1.2)
    args = parser.parse_args(argv)

    cases = [
        json.loads(line)
        for line in Path(args.cases).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    llm = FreeChatLLM("mistral", args.model, temperature=0.0, min_interval_s=args.min_interval)

    rows: list[dict[str, str]] = []
    for i, case in enumerate(cases, 1):
        query = case["query"]
        expansion = llm.invoke(FIELD_HYDE_PROMPT.format(query=query))
        rows.append(
            {
                "case_id": case["case_id"],
                "query": query,
                "expansion": expansion,
                "expanded_query": f"{query} {expansion}",
            }
        )
        print(f"[{i}/{len(cases)}] {case['case_id']} exp_len={len(expansion)}", flush=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[done] {len(rows)} expansions -> {out_path} ({llm.calls} LLM calls)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
