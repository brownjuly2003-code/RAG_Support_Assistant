#!/usr/bin/env python3
"""F1 verify (adaptive-retrieval Track F): extract fact-cards from customs docs.

Runs the LLM fact-card extractor on a few customs documents and checks that the
"поля не теряются" acceptance holds — specifically that the residual-MISS case
``customs-clearance-fields`` keywords (``declaration_number``, ``customs_code``)
survive into the extracted card's ``fields``.

Heavy/LLM step → run on Mac (per plan). Configure the provider via env, e.g.::

    LLM_PROVIDER_PROFILE=external-mistral MISTRAL_API_KEY=... \
        .venv/bin/python scripts/factcard_verify.py

Exit code 0 iff every document yields >=1 valid card and all completeness
expectations pass.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ingestion.factcard_extractor import FactCard, extract_fact_cards  # noqa: E402

DEFAULT_DOCS = [
    "data/uploads/aircargo/05_tlog_regulation_customs_clearance.md",
    "data/uploads/aircargo/03_legal_contract_customs_broker.md",
    "data/uploads/aircargo/05_tlog_contract_customs_representative.md",
]

# Completeness expectations keyed by filename: these field codes MUST appear in
# the extracted card's fields (the enumeration the reranker drops in D2).
REQUIRED_FIELDS: dict[str, list[str]] = {
    "05_tlog_regulation_customs_clearance.md": ["declaration_number", "customs_code"],
}

_DOC_ID_RE = re.compile(r"^doc_id:\s*(\S+)\s*$", re.MULTILINE)


def source_id(path: Path, text: str) -> str:
    match = _DOC_ID_RE.search(text)
    return match.group(1) if match else path.stem


def build_llm() -> object:
    from config.settings import get_settings
    from llm.providers.runtime import build_provider_runtime

    runtime = build_provider_runtime(get_settings())
    return runtime.strong


def check_completeness(name: str, cards: list[FactCard]) -> list[str]:
    """Return list of missing expected field codes (empty == pass)."""
    expected = REQUIRED_FIELDS.get(name, [])
    if not expected:
        return []
    all_fields = {f.lower() for card in cards for f in card.fields}
    return [e for e in expected if e.lower() not in all_fields]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("docs", nargs="*", default=DEFAULT_DOCS)
    parser.add_argument("--max-chars", type=int, default=6000)
    args = parser.parse_args(argv)

    llm = build_llm()
    ok = True
    for rel in args.docs:
        path = (PROJECT_ROOT / rel).resolve()
        name = path.name
        if not path.exists():
            print(f"[SKIP] {rel}: not found")
            ok = False
            continue
        text = path.read_text(encoding="utf-8")
        src = source_id(path, text)
        try:
            cards = extract_fact_cards(text, src, llm, max_chars=args.max_chars)  # type: ignore[arg-type]
        except Exception as exc:  # noqa: BLE001
            print(f"[FAIL] {name}: extraction error: {exc}")
            ok = False
            continue
        if not cards:
            print(f"[FAIL] {name}: no cards extracted")
            ok = False
            continue
        missing = check_completeness(name, cards)
        status = "OK" if not missing else "FAIL"
        if missing:
            ok = False
        total_fields = sum(len(c.fields) for c in cards)
        print(
            f"[{status}] {name}: {len(cards)} card(s), {total_fields} field(s)"
            + (f"  MISSING={missing}" if missing else "")
        )
        for card in cards:
            print(
                json.dumps(
                    card.model_dump(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
