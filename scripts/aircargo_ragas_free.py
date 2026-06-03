# ruff: noqa: E402
#!/usr/bin/env python3
"""Free R7 RAGAS-style baseline — no paid APIs, no heavy local compute.

Measures RAG answer quality on the 100-case aircargo curated set using:
  * cached retrieved contexts (``--contexts`` JSON produced by the iMac A/B run;
    top-``rerank_k`` of the per-case RRF candidate pool) — no re-ingest needed;
  * a FREE LLM (Groq / Gemini / OpenRouter, OpenAI-compatible chat endpoint) as
    BOTH the answer generator and the faithfulness/relevancy judge;
  * keyword-based context_precision / context_recall (no LLM, no ground-truth).

This is an honest baseline, not the production pipeline: the generator is a free
proxy LLM (not Mistral/GraceKelly) and the contexts are the RRF top-k WITHOUT the
production bge-reranker-v2-m3 rerank (which cannot run on this host). faithfulness
and answer_relevancy therefore reflect "can a capable free LLM answer faithfully
from our RU retrieval", while context_recall is the retrieval coverage signal.

Reuses evaluation.ragas_eval.RAGEvaluator and the aircargo report renderer so the
output is comparable to the mock/live RAGAS reports under reports/ragas/.

The API key is read from the environment only (GROQ_API_KEY / GEMINI_API_KEY /
OPENROUTER_API_KEY); nothing secret is hard-coded or printed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from collections.abc import Sequence

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from evaluation.ragas_eval import RAGEvaluator, TestCase as RAGTestCase
from scripts.aircargo_ragas_eval import write_report_files

_PROVIDERS = {
    "groq": {
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "env": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
    },
    "openrouter": {
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "env": "OPENROUTER_API_KEY",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "gemini": {
        # Google's OpenAI-compatible endpoint; API key passed as Bearer.
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "env": "GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash",
    },
}


class FreeChatLLM:
    """Minimal OpenAI-compatible chat client with retry/backoff for free tiers."""

    def __init__(self, provider: str, model: str, *, temperature: float = 0.0,
                 min_interval_s: float = 2.1, max_retries: int = 6) -> None:
        cfg = _PROVIDERS[provider]
        key = os.environ.get(cfg["env"], "").strip()
        if not key:
            raise RuntimeError(f"{cfg['env']} not set in environment")
        self._url = cfg["url"]
        self._key = key
        self.model = model
        self._temperature = temperature
        self._min_interval = min_interval_s
        self._max_retries = max_retries
        self._last_call = 0.0
        self.calls = 0

    def invoke(self, prompt: str) -> str:
        # client-side spacing to stay under free-tier RPM
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self._temperature,
        }
        delay = 4.0
        for attempt in range(self._max_retries):
            try:
                resp = httpx.post(self._url, headers=headers, json=body, timeout=90.0)
            except httpx.HTTPError as exc:
                if attempt == self._max_retries - 1:
                    raise RuntimeError(f"transport error: {exc}") from exc
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            self._last_call = time.monotonic()
            if resp.status_code == 200:
                self.calls += 1
                return resp.json()["choices"][0]["message"]["content"].strip()
            if resp.status_code in (429, 500, 502, 503, 520, 529):
                retry_after = resp.headers.get("retry-after")
                sleep_s = float(retry_after) if retry_after and retry_after.replace(".", "").isdigit() else delay
                time.sleep(min(sleep_s, 90))
                delay = min(delay * 2, 60)
                continue
            raise RuntimeError(f"{resp.status_code}: {resp.text[:200]}")
        raise RuntimeError("exhausted retries")


def _load_contexts(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def _generate_answer(llm: FreeChatLLM, question: str, contexts: list[str]) -> str:
    ctx = "\n\n---\n\n".join(contexts)
    prompt = (
        "Ты — ассистент поддержки. Ответь на вопрос пользователя СТРОГО на основе "
        "приведённого контекста. Если в контексте нет ответа — честно скажи, что "
        "информации недостаточно. Отвечай кратко и по делу, на русском.\n\n"
        f"КОНТЕКСТ:\n{ctx[:6000]}\n\n"
        f"ВОПРОС: {question}\n\nОТВЕТ:"
    )
    return llm.invoke(prompt)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contexts", default=str(PROJECT_ROOT / ".tmp" / "ab_candidates.json"))
    parser.add_argument("--provider", default="groq", choices=sorted(_PROVIDERS))
    parser.add_argument("--model", default="")
    parser.add_argument("--max-cases", type=int, default=0, help="0 = all")
    parser.add_argument("--top-k", type=int, default=0, help="0 = use per-case rerank_k")
    parser.add_argument("--min-interval", type=float, default=4.5,
                        help="client-side seconds between LLM calls (free-tier RPM guard)")
    parser.add_argument("--results-dir", default=str(PROJECT_ROOT / "reports" / "ragas"))
    args = parser.parse_args(argv)

    started_at = datetime.now(timezone.utc)
    model = args.model or _PROVIDERS[args.provider]["default_model"]
    llm = FreeChatLLM(args.provider, model, min_interval_s=args.min_interval)

    rows = _load_contexts(Path(args.contexts))
    if args.max_cases > 0:
        rows = rows[: args.max_cases]

    rag_cases: list[RAGTestCase] = []
    answers: list[str] = []
    contexts_list: list[list[dict[str, Any]]] = []
    runtime: list[dict[str, Any]] = []

    n = len(rows)
    for i, row in enumerate(rows, 1):
        question = row["query"]
        kws = row.get("kws", [])
        top_k = args.top_k or int(row.get("rerank_k", 5))
        ctx_texts = list(row.get("cands", []))[:top_k]
        t0 = time.perf_counter()
        try:
            answer = _generate_answer(llm, question, ctx_texts)
        except Exception as exc:  # one bad case must not kill the run
            answer = ""
            print(f"[{i}/{n}] {row.get('case_id')} GENERATE-ERROR: {exc}", file=sys.stderr, flush=True)
        elapsed_ms = int(max((time.perf_counter() - t0) * 1000, 0))
        rag_cases.append(RAGTestCase(question=question, expected_keywords=kws, category="aircargo"))
        answers.append(answer)
        contexts_list.append([{"page_content": t, "metadata": {}} for t in ctx_texts])
        runtime.append({"case_id": row.get("case_id"), "duration_ms": elapsed_ms,
                        "trace_id": f"free-ragas-{row.get('case_id')}"})
        print(f"[{i}/{n}] {row.get('case_id')} ans_len={len(answer)} ({elapsed_ms}ms)", flush=True)

    evaluator = RAGEvaluator(eval_llm=llm)
    result = evaluator.evaluate_batch(rag_cases, answers=answers, context_docs_list=contexts_list)

    runtime_by_case = {it["case_id"]: it for it in runtime}
    for index, item in enumerate(result["per_question"]):
        row = rows[index]
        rt = runtime_by_case.get(row.get("case_id"), {})
        item["case_id"] = row.get("case_id")
        item["tenant_id"] = "aircargo"
        item["answer"] = answers[index]
        item["context_docs_count"] = len(contexts_list[index])
        item["duration_ms"] = rt.get("duration_ms")
        item["trace_id"] = rt.get("trace_id", "")

    result["mode"] = "free-ragas"
    result["provider_target"] = f"{args.provider}:{model}"
    result["run_id"] = f"{started_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    result["created_at"] = started_at.isoformat()
    result["dataset"] = str(Path(args.contexts))
    result["tenant"] = "aircargo"

    markdown_path, json_path = write_report_files(result, results_dir=Path(args.results_dir))
    print(json.dumps({
        "status": "ok", "run_id": result["run_id"], "mode": "free-ragas",
        "provider_target": result["provider_target"], "num_cases": result["num_cases"],
        "llm_calls": llm.calls, "aggregate": result["aggregate"],
        "report_markdown": str(markdown_path), "report_json": str(json_path),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
