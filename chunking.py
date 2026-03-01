"""
ingestion/chunking.py

Подбор оптимальной конфигурации chunk_size / chunk_overlap по метрикам.

Метрики:
- Recall@k: доля ожидаемых ключевых слов, найденных в top-k чанках.
- MRR (Mean Reciprocal Rank): средний 1/rank первого релевантного чанка.
- Precision@k: доля релевантных чанков среди top-k.

Процесс:
1. Берём документы + тестовые вопросы с expected_keywords.
2. Для каждой конфигурации (chunk_size, chunk_overlap):
   - Режем на чанки.
   - Строим in-memory vector store.
   - Прогоняем вопросы, считаем Recall@k + MRR.
3. Выбираем конфигурацию с лучшим composite score.
4. Сохраняем результаты в JSON.

Важно:
- Размер чанка НЕ обязан быть степенью двойки.
- Оптимальный chunk_size зависит от языка, длины документов,
  типа вопросов и модели эмбеддингов.
- Overlap обычно 15-25% от chunk_size.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

try:
    from langchain_core.documents import Document  # type: ignore
except ImportError:
    from langchain.schema import Document  # type: ignore

import chromadb


@dataclass
class ChunkingConfig:
    chunk_size: int
    chunk_overlap: int

    @property
    def overlap_ratio(self) -> float:
        return self.chunk_overlap / self.chunk_size if self.chunk_size else 0


@dataclass
class TestQuestion:
    question: str
    expected_keywords: List[str]
    category: str = "general"


@dataclass
class EvalResult:
    """Результат оценки одной конфигурации."""
    config: ChunkingConfig
    avg_recall: float
    avg_mrr: float
    avg_precision: float
    composite_score: float
    total_chunks: int
    per_question: List[Dict[str, Any]]


class ChunkingEvaluator:
    """Оценивает разные конфигурации chunk_size/chunk_overlap по Recall@k + MRR."""

    def __init__(
        self,
        documents: Sequence[Document],
        test_questions: Sequence[TestQuestion],
        embeddings: Any = None,
        k: int = 5,
        best_config_path: str | Path = "data/chunking/best_chunk_config.json",
        recall_weight: float = 0.6,
        mrr_weight: float = 0.3,
        precision_weight: float = 0.1,
    ):
        """
        Args:
            documents: список Document для разбиения на чанки.
            test_questions: тестовые вопросы с expected_keywords.
            embeddings: embedding model (если None — создаётся через manager.get_embeddings()).
            k: top-k для retrieval метрик.
            best_config_path: путь для сохранения лучшей конфигурации.
            recall_weight / mrr_weight / precision_weight: веса для composite score.
        """
        self.documents = list(documents)
        self.test_questions = list(test_questions)
        self.k = k
        self.best_config_path = Path(best_config_path)
        self.recall_weight = recall_weight
        self.mrr_weight = mrr_weight
        self.precision_weight = precision_weight

        if embeddings is None:
            from manager import get_embeddings
            embeddings = get_embeddings()
        self._embeddings = embeddings

    def _split_with_config(self, config: ChunkingConfig) -> List[Document]:
        """Режет документы на чанки."""
        try:
            from langchain_text_splitters import RecursiveCharacterTextSplitter
        except ImportError:
            from langchain.text_splitter import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=config.chunk_size,
            chunk_overlap=config.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        chunks: List[Document] = []
        for doc_idx, doc in enumerate(self.documents):
            pieces = splitter.split_text(doc.page_content)
            for i, text in enumerate(pieces):
                meta = dict(doc.metadata)
                meta["chunk_index"] = len(chunks)
                meta["doc_index"] = doc_idx
                meta["chunk_size_chars"] = len(text)
                chunks.append(Document(page_content=text, metadata=meta))

        return chunks

    _eval_counter = 0

    def _build_ephemeral_store(self, chunks: List[Document]) -> chromadb.Collection:
        """Строит in-memory Chroma коллекцию."""
        ChunkingEvaluator._eval_counter += 1
        client = chromadb.EphemeralClient()
        collection = client.create_collection(
            name=f"eval_{ChunkingEvaluator._eval_counter}",
            metadata={"hnsw:space": "cosine"},
        )

        texts = [c.page_content for c in chunks]
        embs = self._embeddings.embed_documents(texts)
        ids = [f"c_{i}" for i in range(len(chunks))]

        collection.add(
            ids=ids,
            documents=texts,
            embeddings=embs,
        )
        return collection

    @staticmethod
    def _recall(retrieved_texts: List[str], expected_keywords: List[str]) -> float:
        """Recall: доля ожидаемых keywords, найденных в retrieved текстах."""
        if not expected_keywords:
            return 1.0
        combined = "\n".join(retrieved_texts).lower()
        unique_kws = {kw.lower() for kw in expected_keywords}
        found = sum(1 for kw in unique_kws if kw in combined)
        return found / len(unique_kws)

    @staticmethod
    def _mrr(retrieved_texts: List[str], expected_keywords: List[str]) -> float:
        """MRR: 1/rank первого чанка, содержащего хотя бы одно keyword."""
        if not expected_keywords:
            return 1.0
        kws_lower = {kw.lower() for kw in expected_keywords}
        for rank, text in enumerate(retrieved_texts, 1):
            text_lower = text.lower()
            if any(kw in text_lower for kw in kws_lower):
                return 1.0 / rank
        return 0.0

    @staticmethod
    def _precision(retrieved_texts: List[str], expected_keywords: List[str]) -> float:
        """Precision@k: доля retrieved чанков, содержащих хотя бы одно keyword."""
        if not retrieved_texts or not expected_keywords:
            return 0.0
        kws_lower = {kw.lower() for kw in expected_keywords}
        relevant = sum(
            1 for text in retrieved_texts
            if any(kw in text.lower() for kw in kws_lower)
        )
        return relevant / len(retrieved_texts)

    def _evaluate_config(self, config: ChunkingConfig) -> EvalResult:
        """Оценивает одну конфигурацию."""
        chunks = self._split_with_config(config)
        if not chunks:
            return EvalResult(
                config=config, avg_recall=0, avg_mrr=0, avg_precision=0,
                composite_score=0, total_chunks=0, per_question=[],
            )

        collection = self._build_ephemeral_store(chunks)

        per_question: List[Dict[str, Any]] = []
        recalls, mrrs, precisions = [], [], []

        for tq in self.test_questions:
            q_emb = self._embeddings.embed_query(tq.question)
            result = collection.query(query_embeddings=[q_emb], n_results=self.k)
            texts = result.get("documents", [[]])[0] if result.get("documents") else []

            r = self._recall(texts, tq.expected_keywords)
            m = self._mrr(texts, tq.expected_keywords)
            p = self._precision(texts, tq.expected_keywords)

            recalls.append(r)
            mrrs.append(m)
            precisions.append(p)

            per_question.append({
                "question": tq.question,
                "category": tq.category,
                "recall": round(r, 3),
                "mrr": round(m, 3),
                "precision": round(p, 3),
            })

        n = len(self.test_questions)
        avg_r = sum(recalls) / n if n else 0
        avg_m = sum(mrrs) / n if n else 0
        avg_p = sum(precisions) / n if n else 0
        composite = (
            self.recall_weight * avg_r
            + self.mrr_weight * avg_m
            + self.precision_weight * avg_p
        )

        return EvalResult(
            config=config,
            avg_recall=round(avg_r, 4),
            avg_mrr=round(avg_m, 4),
            avg_precision=round(avg_p, 4),
            composite_score=round(composite, 4),
            total_chunks=len(chunks),
            per_question=per_question,
        )

    def optimize(
        self,
        configs: Sequence[ChunkingConfig] | None = None,
    ) -> EvalResult:
        """Перебирает конфигурации и выбирает лучшую по composite score.

        Дефолтная сетка — не степени двойки, а осмысленные значения:
        - Маленькие (300-400): хороши для коротких FAQ, точечных ответов
        - Средние (500-700): баланс контекста и точности
        - Большие (900-1200): для длинных процедурных текстов
        - Overlap: ~20% от chunk_size (стандарт для русского)
        """
        if configs is None:
            configs = [
                # (chunk_size, chunk_overlap)
                ChunkingConfig(300, 60),
                ChunkingConfig(400, 80),
                ChunkingConfig(500, 100),
                ChunkingConfig(600, 120),
                ChunkingConfig(700, 150),
                ChunkingConfig(900, 180),
                ChunkingConfig(1200, 200),
            ]

        print("=" * 60)
        print("CHUNKING OPTIMIZATION")
        print(f"Documents: {len(self.documents)}")
        print(f"Test questions: {len(self.test_questions)}")
        print(f"Configs to test: {len(configs)}")
        print(f"Metrics: Recall@{self.k} ({self.recall_weight})"
              f" + MRR ({self.mrr_weight})"
              f" + Precision ({self.precision_weight})")
        print("=" * 60)

        results: List[EvalResult] = []
        for cfg in configs:
            t0 = time.time()
            res = self._evaluate_config(cfg)
            elapsed = time.time() - t0
            print(
                f"  size={cfg.chunk_size:5d}  overlap={cfg.chunk_overlap:4d}"
                f"  chunks={res.total_chunks:4d}"
                f"  Recall={res.avg_recall:.3f}"
                f"  MRR={res.avg_mrr:.3f}"
                f"  Prec={res.avg_precision:.3f}"
                f"  Score={res.composite_score:.3f}"
                f"  ({elapsed:.1f}s)"
            )
            results.append(res)

        best = max(results, key=lambda r: r.composite_score)
        self._save_results(best, results)

        print("=" * 60)
        print(f"BEST: chunk_size={best.config.chunk_size}"
              f", chunk_overlap={best.config.chunk_overlap}"
              f", score={best.composite_score:.3f}")
        print("=" * 60)

        return best

    def _save_results(
        self,
        best: EvalResult,
        all_results: List[EvalResult],
    ) -> None:
        """Сохраняет результаты в JSON."""
        self.best_config_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "timestamp": __import__("datetime").datetime.now().isoformat(),
            "best_config": {
                "chunk_size": best.config.chunk_size,
                "chunk_overlap": best.config.chunk_overlap,
            },
            "best_metrics": {
                "avg_recall": best.avg_recall,
                "avg_mrr": best.avg_mrr,
                "avg_precision": best.avg_precision,
                "composite_score": best.composite_score,
            },
            "best_total_chunks": best.total_chunks,
            "all_results": [
                {
                    "chunk_size": r.config.chunk_size,
                    "chunk_overlap": r.config.chunk_overlap,
                    "chunks": r.total_chunks,
                    "recall": r.avg_recall,
                    "mrr": r.avg_mrr,
                    "precision": r.avg_precision,
                    "score": r.composite_score,
                }
                for r in all_results
            ],
            "per_question_detail": best.per_question,
        }
        self.best_config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved to {self.best_config_path}")


def load_best_config(
    path: str | Path = "data/chunking/best_chunk_config.json",
) -> Optional[Dict[str, int]]:
    """Загружает лучшую конфигурацию из JSON. Возвращает None если файл не найден."""
    p = Path(path)
    if not p.exists():
        return None
    data = json.loads(p.read_text(encoding="utf-8"))
    return data.get("best_config")


def _load_test_questions(path: str | Path) -> List[TestQuestion]:
    """Загружает тестовые вопросы из JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [
        TestQuestion(
            question=item["question"],
            expected_keywords=item["expected_keywords"],
            category=item.get("category", "general"),
        )
        for item in data
    ]


if __name__ == "__main__":
    from manager import get_embeddings

    docs_dir = Path(__file__).parent / "demo" / "docs"
    q_file = Path(__file__).parent / "demo" / "test_questions.json"

    from ingestion.loader import DocumentLoader
    loader = DocumentLoader()
    docs = loader.load_documents(docs_dir)

    questions = _load_test_questions(q_file)
    embeddings = get_embeddings()

    evaluator = ChunkingEvaluator(
        documents=docs,
        test_questions=questions,
        embeddings=embeddings,
        k=5,
        best_config_path=Path(__file__).parent / "data" / "chunking" / "best_chunk_config.json",
    )
    evaluator.optimize()
