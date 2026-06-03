"""
evaluation package

RAGAS-style evaluation for RAG pipelines.

Re-exports:
    RAGEvaluator  - main evaluator class
    TestCase      - dataclass for evaluation test cases
    faithfulness  - metric: does the answer only use facts from context?
    answer_relevancy   - metric: does the answer address the question?
    context_precision  - metric: are retrieved docs relevant?
    context_recall     - metric: are all needed facts retrieved?
"""

from evaluation.ragas_eval import (
    RAGEvaluator,
    TestCase,
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

__all__ = [
    "RAGEvaluator",
    "TestCase",
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
]
