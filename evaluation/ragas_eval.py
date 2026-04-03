"""
evaluation/ragas_eval.py

RAGAS-style evaluation system for RAG pipelines.

Implements four core metrics WITHOUT the ragas package:
- faithfulness: does the answer only use facts from the context?
- answer_relevancy: does the answer address the question?
- context_precision: are retrieved docs relevant to the question?
- context_recall: are all needed facts retrieved?

Main class: RAGEvaluator
    - evaluate_single(question, answer, context_docs, expected_keywords) -> dict
    - evaluate_batch(test_cases) -> aggregate scores + per-question detail
    - run_benchmark(retriever, llm, test_cases) -> full pipeline evaluation
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TestCase dataclass
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    """A single evaluation test case.

    Attributes:
        question: the user question to evaluate.
        expected_keywords: keywords that should appear in the retrieved context
            or in the answer. Used for keyword-based fallback scoring.
        expected_answer: optional ground-truth answer for comparison.
        category: optional category label (e.g. "error_codes", "warranty").
    """
    question: str
    expected_keywords: List[str] = field(default_factory=list)
    expected_answer: Optional[str] = None
    category: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: text normalisation
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_sentences(text: str) -> List[str]:
    """Split text into sentences (handles Russian and English)."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [s.strip() for s in parts if s.strip()]


def _docs_to_text(context_docs: Any) -> str:
    """Convert a list of context documents to a single text string.

    Accepts:
    - List[Document] (langchain)
    - List[dict] with 'page_content' key
    - List[str]
    """
    parts: List[str] = []
    if not context_docs:
        return ""
    for doc in context_docs:
        if hasattr(doc, "page_content"):
            parts.append(doc.page_content)
        elif isinstance(doc, dict):
            parts.append(doc.get("page_content", str(doc)))
        else:
            parts.append(str(doc))
    return "\n".join(parts)


def _keyword_overlap(text: str, keywords: List[str]) -> float:
    """Fraction of keywords found in text (case-insensitive)."""
    if not keywords:
        return 1.0
    norm = _normalise(text)
    found = sum(1 for kw in keywords if _normalise(kw) in norm)
    return found / len(keywords)


# ---------------------------------------------------------------------------
# Core metric functions (keyword-based fallback implementations)
# ---------------------------------------------------------------------------

def faithfulness(answer: str, context_docs: Any) -> float:
    """Measure whether the answer only uses facts from the context.

    Approach (keyword-based fallback):
    Split the answer into sentences. For each sentence check whether its
    significant words appear in the context. The score is the fraction of
    sentences that are "supported" (>= 50% word overlap with context).

    Returns a float in [0, 1].
    """
    if not answer or not answer.strip():
        return 0.0
    context_text = _docs_to_text(context_docs)
    if not context_text.strip():
        # No context at all -> answer cannot be faithful
        return 0.0

    context_norm = _normalise(context_text)
    context_words = set(context_norm.split())

    sentences = _extract_sentences(answer)
    if not sentences:
        return 0.0

    supported = 0
    for sent in sentences:
        sent_words = _normalise(sent).split()
        # Filter out very short words (< 3 chars) to focus on content words
        content_words = [w for w in sent_words if len(w) >= 3]
        if not content_words:
            supported += 1  # Trivial sentence (e.g. "Да." / "Нет.")
            continue
        overlap = sum(1 for w in content_words if w in context_words)
        ratio = overlap / len(content_words)
        if ratio >= 0.5:
            supported += 1

    return supported / len(sentences)


def answer_relevancy(question: str, answer: str) -> float:
    """Measure whether the answer addresses the question.

    Approach (keyword-based fallback):
    Extract significant words from the question and check how many appear
    in the answer. Answers that share more key terms with the question
    are considered more relevant.

    Returns a float in [0, 1].
    """
    if not answer or not answer.strip():
        return 0.0
    if not question or not question.strip():
        return 0.0

    q_words = [w for w in _normalise(question).split() if len(w) >= 3]
    if not q_words:
        return 1.0  # Trivial question

    a_norm = _normalise(answer)
    found = sum(1 for w in q_words if w in a_norm)
    return found / len(q_words)


def context_precision(
    question: str,
    context_docs: Any,
    expected_keywords: Optional[List[str]] = None,
) -> float:
    """Measure whether retrieved documents are relevant to the question.

    Approach:
    For each retrieved document, check whether it contains keywords from
    the question OR from the expected_keywords list. The score is the
    weighted average (earlier docs weighted more via 1/rank).

    Returns a float in [0, 1].
    """
    if not context_docs:
        return 0.0

    q_words = set(w for w in _normalise(question).split() if len(w) >= 3)
    kw_set = set()
    if expected_keywords:
        kw_set = set(_normalise(kw) for kw in expected_keywords)

    combined = q_words | kw_set

    if not combined:
        return 1.0

    weighted_sum = 0.0
    weight_total = 0.0

    for rank, doc in enumerate(context_docs):
        if hasattr(doc, "page_content"):
            text = doc.page_content
        elif isinstance(doc, dict):
            text = doc.get("page_content", str(doc))
        else:
            text = str(doc)

        doc_norm = _normalise(text)
        hits = sum(1 for kw in combined if kw in doc_norm)
        relevance = hits / len(combined)

        # Weight by inverse rank (1-indexed): earlier docs matter more
        weight = 1.0 / (rank + 1)
        weighted_sum += relevance * weight
        weight_total += weight

    if weight_total == 0.0:
        return 0.0
    return weighted_sum / weight_total


def context_recall(
    context_docs: Any,
    expected_keywords: List[str],
) -> float:
    """Measure whether all needed facts are present in the retrieved context.

    Approach:
    Check what fraction of expected_keywords appear in the combined context.

    Returns a float in [0, 1].
    """
    if not expected_keywords:
        return 1.0
    context_text = _docs_to_text(context_docs)
    return _keyword_overlap(context_text, expected_keywords)


# ---------------------------------------------------------------------------
# LLM-based metric implementations (optional, used when llm is provided)
# ---------------------------------------------------------------------------

def _llm_faithfulness(answer: str, context_text: str, llm: Any) -> float:
    """Use an LLM to judge faithfulness of the answer given context."""
    prompt = (
        "You are an evaluation expert. Given a context and an answer, determine "
        "what fraction of claims in the answer are supported by the context.\n\n"
        f"CONTEXT:\n{context_text[:3000]}\n\n"
        f"ANSWER:\n{answer[:2000]}\n\n"
        "Respond with ONLY a decimal number between 0.0 and 1.0 representing "
        "the faithfulness score (1.0 = fully faithful, 0.0 = completely hallucinated).\n"
        "Score:"
    )
    try:
        raw = llm.invoke(prompt).strip()
        numbers = re.findall(r"[01]?\.\d+|[01]", raw)
        if numbers:
            return max(0.0, min(1.0, float(numbers[0])))
    except Exception:
        pass
    # Fallback to keyword method
    return faithfulness(answer, [{"page_content": context_text}])


def _llm_answer_relevancy(question: str, answer: str, llm: Any) -> float:
    """Use an LLM to judge answer relevancy."""
    prompt = (
        "You are an evaluation expert. Given a question and an answer, rate how "
        "well the answer addresses the question.\n\n"
        f"QUESTION:\n{question}\n\n"
        f"ANSWER:\n{answer[:2000]}\n\n"
        "Respond with ONLY a decimal number between 0.0 and 1.0 "
        "(1.0 = perfectly relevant, 0.0 = completely irrelevant).\n"
        "Score:"
    )
    try:
        raw = llm.invoke(prompt).strip()
        numbers = re.findall(r"[01]?\.\d+|[01]", raw)
        if numbers:
            return max(0.0, min(1.0, float(numbers[0])))
    except Exception:
        pass
    return answer_relevancy(question, answer)


# ---------------------------------------------------------------------------
# RAGEvaluator
# ---------------------------------------------------------------------------

class RAGEvaluator:
    """RAGAS-style evaluator for RAG pipelines.

    Takes an optional LLM for evaluation (or falls back to keyword matching).

    Methods:
        evaluate_single(question, answer, context_docs, expected_keywords) -> dict
        evaluate_batch(test_cases) -> dict with aggregate scores and per-question detail
        run_benchmark(retriever, llm, test_cases) -> full pipeline evaluation
    """

    def __init__(
        self,
        eval_llm: Any = None,
        results_dir: Optional[str] = None,
    ):
        """
        Args:
            eval_llm: an object with an ``invoke(prompt: str) -> str`` method.
                If None, pure keyword-based scoring is used.
            results_dir: directory to save benchmark results.
                Defaults to ``data/evaluation`` relative to project root.
        """
        self._llm = eval_llm
        if results_dir is None:
            results_dir = str(
                Path(__file__).resolve().parent.parent / "data" / "evaluation"
            )
        self._results_dir = results_dir
        Path(self._results_dir).mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # evaluate_single
    # -----------------------------------------------------------------------

    def evaluate_single(
        self,
        question: str,
        answer: str,
        context_docs: Any,
        expected_keywords: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """Evaluate a single question-answer pair.

        Returns a dict with keys:
            faithfulness, answer_relevancy, context_precision, context_recall
        Each value is a float in [0, 1].
        """
        kw = expected_keywords or []
        context_text = _docs_to_text(context_docs)

        # Faithfulness
        if self._llm is not None:
            faith = _llm_faithfulness(answer, context_text, self._llm)
        else:
            faith = faithfulness(answer, context_docs)

        # Answer relevancy
        if self._llm is not None:
            relevancy = _llm_answer_relevancy(question, answer, self._llm)
        else:
            relevancy = answer_relevancy(question, answer)

        # Context precision
        precision = context_precision(question, context_docs, kw)

        # Context recall
        recall = context_recall(context_docs, kw)

        return {
            "faithfulness": round(faith, 4),
            "answer_relevancy": round(relevancy, 4),
            "context_precision": round(precision, 4),
            "context_recall": round(recall, 4),
        }

    # -----------------------------------------------------------------------
    # evaluate_batch
    # -----------------------------------------------------------------------

    def evaluate_batch(
        self,
        test_cases: Sequence[TestCase],
        answers: Optional[List[str]] = None,
        context_docs_list: Optional[List[Any]] = None,
    ) -> Dict[str, Any]:
        """Evaluate a batch of test cases.

        If ``answers`` and ``context_docs_list`` are provided, they are used
        directly. Otherwise the test cases must include expected_answer.

        Returns:
            {
                "aggregate": {metric: mean_score, ...},
                "per_question": [
                    {"question": ..., "scores": {...}, "category": ...},
                    ...
                ],
                "num_cases": int,
                "timestamp": str,
            }
        """
        per_question: List[Dict[str, Any]] = []
        totals: Dict[str, float] = {
            "faithfulness": 0.0,
            "answer_relevancy": 0.0,
            "context_precision": 0.0,
            "context_recall": 0.0,
        }

        for i, tc in enumerate(test_cases):
            answer = ""
            ctx = []

            if answers is not None and i < len(answers):
                answer = answers[i]
            elif tc.expected_answer:
                answer = tc.expected_answer

            if context_docs_list is not None and i < len(context_docs_list):
                ctx = context_docs_list[i]

            scores = self.evaluate_single(
                question=tc.question,
                answer=answer,
                context_docs=ctx,
                expected_keywords=tc.expected_keywords,
            )

            per_question.append({
                "question": tc.question,
                "category": tc.category,
                "scores": scores,
            })

            for metric, val in scores.items():
                totals[metric] += val

        n = max(len(test_cases), 1)
        aggregate = {k: round(v / n, 4) for k, v in totals.items()}

        return {
            "aggregate": aggregate,
            "per_question": per_question,
            "num_cases": len(test_cases),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

    # -----------------------------------------------------------------------
    # run_benchmark
    # -----------------------------------------------------------------------

    def run_benchmark(
        self,
        retriever: Any,
        llm: Any,
        test_cases: Sequence[TestCase],
        save: bool = True,
    ) -> Dict[str, Any]:
        """Run full RAG pipeline evaluation: retrieve + generate + evaluate.

        For each test case:
        1. Retrieve context documents using the retriever.
        2. Generate an answer using the provided LLM.
        3. Evaluate with all four metrics.

        If ``save`` is True, results are written to
        ``data/evaluation/benchmark_results.json``.

        Args:
            retriever: object with ``get_relevant_documents(query)`` or
                ``invoke(query)`` method.
            llm: object with ``invoke(prompt) -> str`` method.
            test_cases: list of TestCase instances.
            save: whether to persist results to disk.

        Returns:
            Same structure as evaluate_batch, plus per-question ``answer``
            and ``context_docs`` fields.
        """
        answers: List[str] = []
        context_docs_list: List[List[Any]] = []
        timings: List[float] = []

        for tc in test_cases:
            start = time.time()

            # Retrieve
            try:
                if hasattr(retriever, "get_relevant_documents"):
                    docs = retriever.get_relevant_documents(tc.question)
                else:
                    docs = retriever.invoke(tc.question)
            except Exception as e:
                logger.exception(
                    "RAGEvaluator retrieval error for '%s': %s",
                    tc.question[:50],
                    e,
                )
                docs = []

            # Generate
            try:
                ctx_text = _docs_to_text(docs)
                prompt = (
                    f"Answer the following question based on the context.\n\n"
                    f"Context:\n{ctx_text[:4000]}\n\n"
                    f"Question: {tc.question}\n\nAnswer:"
                )
                answer = llm.invoke(prompt)
                if not isinstance(answer, str):
                    answer = str(answer)
            except Exception as e:
                logger.exception(
                    "RAGEvaluator generation error for '%s': %s",
                    tc.question[:50],
                    e,
                )
                answer = ""

            elapsed = time.time() - start
            timings.append(elapsed)

            answers.append(answer)
            # Normalise docs to dicts for serialisation
            normalised: List[Dict[str, Any]] = []
            for doc in docs:
                if hasattr(doc, "page_content"):
                    normalised.append({
                        "page_content": doc.page_content,
                        "metadata": getattr(doc, "metadata", {}),
                    })
                elif isinstance(doc, dict):
                    normalised.append(doc)
                else:
                    normalised.append({"page_content": str(doc), "metadata": {}})
            context_docs_list.append(normalised)

        result = self.evaluate_batch(test_cases, answers, context_docs_list)

        # Enrich per-question results with answers and docs
        for i, pq in enumerate(result["per_question"]):
            pq["answer"] = answers[i]
            pq["context_docs_count"] = len(context_docs_list[i])
            pq["time_seconds"] = round(timings[i], 3)

        result["total_time_seconds"] = round(sum(timings), 3)

        if save:
            self._save_results(result)

        return result

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    def _save_results(self, result: Dict[str, Any]) -> str:
        """Save benchmark results to JSON file. Returns the file path."""
        path = Path(self._results_dir) / "benchmark_results.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info("RAGEvaluator results saved to %s", path)
        return str(path)
