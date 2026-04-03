"""
vectordb/manager.py

Менеджер векторной БД для RAG-проекта.

Level 1: BGE-M3, Hybrid Search (BM25+Vector+RRF), Cross-Encoder Reranker
Level 2: Semantic Chunking
Level 3: Contextual Retrieval, Parent Document Retrieval, Multi-Query

Публичные функции:

- get_embeddings() — embedding model factory
- build_vector_store(docs, chunk_config) — режет на чанки, строит БД
- get_retriever(vector_store, chunks) — HybridRetriever
- add_contextual_headers(docs, llm) — Level 3: Contextual Retrieval
- ParentDocumentStore — Level 3: Parent Document Retrieval
- MultiQueryRetriever — Level 3: Multi-Query Retrieval
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Optional

logger = logging.getLogger(__name__)

try:
    from langchain_core.documents import Document  # type: ignore
except ImportError:
    from langchain.schema import Document  # type: ignore

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # type: ignore
except ImportError:
    from langchain.text_splitter import RecursiveCharacterTextSplitter  # type: ignore

try:
    from langchain_experimental.text_splitter import SemanticChunker  # type: ignore
    HAS_SEMANTIC_CHUNKER = True
except ImportError:
    HAS_SEMANTIC_CHUNKER = False

# Chroma
try:
    from langchain_chroma import Chroma  # type: ignore
    HAS_CHROMA = True
except ImportError:
    HAS_CHROMA = False

# Qdrant
try:
    from langchain_qdrant import QdrantVectorStore  # type: ignore
    from qdrant_client import QdrantClient  # type: ignore
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False

# BM25
try:
    from rank_bm25 import BM25Okapi  # type: ignore
    HAS_BM25 = True
except ImportError:
    HAS_BM25 = False

# Cross-encoder reranker
try:
    from sentence_transformers import CrossEncoder  # type: ignore
    HAS_CROSS_ENCODER = True
except ImportError:
    HAS_CROSS_ENCODER = False


# ---------------------------------------------------------------------------
# Embedding model factory
# ---------------------------------------------------------------------------

_cached_embeddings: Any = None


def get_embeddings(model_name: str | None = None) -> Any:
    """Создаёт LangChain-совместимый embedding объект.

    Использует SentenceTransformers через LangChain обёртку.
    Модель кешируется — повторный вызов возвращает тот же объект.
    """
    global _cached_embeddings
    if _cached_embeddings is not None:
        return _cached_embeddings

    if model_name is None:
        from config.settings import get_settings
        model_name = get_settings().embedding_model

    logger.info("Loading embedding model: %s", model_name)
    start = time.time()

    from sentence_transformers import SentenceTransformer  # type: ignore

    class _STEmbeddings:
        """Минимальная LangChain-совместимая обёртка над SentenceTransformer."""
        def __init__(self, st_model: SentenceTransformer):
            self._model = st_model

        def embed_documents(self, texts: List[str]) -> List[List[float]]:
            return self._model.encode(texts, normalize_embeddings=True).tolist()

        def embed_query(self, text: str) -> List[float]:
            return self._model.encode([text], normalize_embeddings=True)[0].tolist()

    model = SentenceTransformer(model_name, device="cpu")
    embeddings = _STEmbeddings(model)

    elapsed = time.time() - start
    logger.info("Embedding model loaded in %.1fs", elapsed)
    _cached_embeddings = embeddings
    return embeddings


# ---------------------------------------------------------------------------
# Reranker
# ---------------------------------------------------------------------------

_cached_reranker: Any = None


def get_reranker(model_name: str | None = None) -> Any | None:
    """Создаёт CrossEncoder reranker. Возвращает None если отключён или недоступен."""
    global _cached_reranker
    if _cached_reranker is not None:
        return _cached_reranker

    if model_name is None:
        from config.settings import get_settings
        model_name = get_settings().reranker_model

    if not model_name:
        return None

    if not HAS_CROSS_ENCODER:
        logger.warning("sentence-transformers not installed — reranker disabled")
        return None

    logger.info("Loading reranker: %s", model_name)
    start = time.time()
    reranker = CrossEncoder(model_name, device="cpu")
    elapsed = time.time() - start
    logger.info("Reranker loaded in %.1fs", elapsed)
    _cached_reranker = reranker
    return reranker


# ---------------------------------------------------------------------------
# Hybrid Retriever: BM25 + Vector + Reranker
# ---------------------------------------------------------------------------

class HybridRetriever:
    """Гибридный ретривер: BM25 (keyword) + Vector (semantic) + Reranker.

    Алгоритм:
    1. BM25 ищет top-k по ключевым словам (TF-IDF)
    2. Vector store ищет top-k по cosine similarity
    3. Reciprocal Rank Fusion (RRF) объединяет оба ранжирования
    4. Cross-encoder reranker пересчитывает релевантность top кандидатов
    5. Возвращает финальный top-n

    Если BM25 недоступен — fallback на чистый vector search.
    Если reranker недоступен — пропускает шаг 4.
    """

    def __init__(
        self,
        vector_store: Any,
        chunks: List[Document],
        retrieval_k: int = 20,
        rerank_k: int = 5,
        rrf_k: int = 60,
        reranker: Any = None,
        use_bm25: bool = True,
    ):
        self._vector_store = vector_store
        self._chunks = chunks
        self._retrieval_k = retrieval_k
        self._rerank_k = rerank_k
        self._rrf_k = rrf_k
        self._reranker = reranker

        # Build BM25 index
        self._bm25 = None
        if use_bm25 and HAS_BM25 and chunks:
            tokenized = [doc.page_content.lower().split() for doc in chunks]
            self._bm25 = BM25Okapi(tokenized)
            logger.debug("BM25 index built: %d chunks", len(chunks))

    def get_relevant_documents(self, query: str) -> List[Document]:
        """Гибридный поиск с RRF и reranking."""
        # Step 1: Vector search
        try:
            if hasattr(self._vector_store, "similarity_search"):
                vector_results = self._vector_store.similarity_search(query, k=self._retrieval_k)
            else:
                retriever = self._vector_store.as_retriever(search_kwargs={"k": self._retrieval_k})
                vector_results = retriever.get_relevant_documents(query)
        except Exception as e:
            logger.warning("[HybridRetriever] Vector search error: %s", e)
            vector_results = []

        # Step 2: BM25 search
        bm25_results: List[Document] = []
        if self._bm25 is not None:
            tokenized_query = query.lower().split()
            scores = self._bm25.get_scores(tokenized_query)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:self._retrieval_k]
            bm25_results = [self._chunks[i] for i in top_indices if scores[i] > 0]

        # Step 3: Reciprocal Rank Fusion
        if bm25_results:
            merged = self._rrf_merge(vector_results, bm25_results)
        else:
            merged = vector_results

        # Step 4: Reranker
        if self._reranker is not None and merged:
            merged = self._rerank(query, merged)
        else:
            merged = merged[:self._rerank_k]

        return merged

    def _rrf_merge(self, list_a: List[Document], list_b: List[Document]) -> List[Document]:
        """Reciprocal Rank Fusion: объединяет два ранжированных списка.

        score(doc) = sum( 1 / (k + rank_in_list) ) для каждого списка.
        k = 60 (стандарт) — сглаживает доминирование высоких рангов.
        """
        scores: Dict[str, float] = {}
        doc_map: Dict[str, Document] = {}

        for rank, doc in enumerate(list_a):
            key = doc.page_content[:200]  # Уникальность по содержимому
            scores[key] = scores.get(key, 0) + 1.0 / (self._rrf_k + rank)
            doc_map[key] = doc

        for rank, doc in enumerate(list_b):
            key = doc.page_content[:200]
            scores[key] = scores.get(key, 0) + 1.0 / (self._rrf_k + rank)
            doc_map[key] = doc

        sorted_keys = sorted(scores, key=lambda k: scores[k], reverse=True)
        return [doc_map[k] for k in sorted_keys]

    def _rerank(self, query: str, docs: List[Document]) -> List[Document]:
        """Cross-encoder reranking: пересчитывает релевантность каждого документа."""
        if not docs:
            return docs

        pairs = [(query, doc.page_content) for doc in docs]
        try:
            scores = self._reranker.predict(pairs)
            scored_docs = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
            return [doc for doc, _ in scored_docs[:self._rerank_k]]
        except Exception as e:
            logger.warning("[HybridRetriever] Reranker error: %s", e)
            return docs[:self._rerank_k]

    def invoke(self, query: str) -> List[Document]:
        return self.get_relevant_documents(query)


# ---------------------------------------------------------------------------
# Path/backend helpers
# ---------------------------------------------------------------------------

def _project_root() -> Path:
    return Path(__file__).resolve().parent

def _data_dir() -> Path:
    root = _project_root()
    data = root / "data" / "vectordb"
    data.mkdir(parents=True, exist_ok=True)
    return data

def _get_backend() -> str:
    backend = os.getenv("VECTOR_DB_TYPE", "chroma").strip().lower()
    if backend not in {"chroma", "qdrant"}:
        backend = "chroma"
    return backend

def _build_text_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


# ---------------------------------------------------------------------------
# Level 2: Semantic Chunking
# ---------------------------------------------------------------------------

def semantic_split(
    docs: List[Document],
    embeddings: Any,
    breakpoint_threshold: float = 0.3,
    min_chunk_size: int = 100,
    max_chunk_size: int = 2000,
) -> List[Document]:
    """Семантический сплиттер через langchain_experimental.SemanticChunker."""
    _ = breakpoint_threshold

    if HAS_SEMANTIC_CHUNKER:
        try:
            splitter = SemanticChunker(embeddings)
            return splitter.split_documents(list(docs))
        except Exception as exc:
            logger.warning(
                "SemanticChunker failed, fallback to RecursiveCharacterTextSplitter: %s",
                exc,
            )

    splitter = _build_text_splitter(max_chunk_size, min_chunk_size // 2)
    return splitter.split_documents(list(docs))


# ---------------------------------------------------------------------------
# Level 3: Contextual Retrieval
# ---------------------------------------------------------------------------


def add_contextual_headers(
    chunks: List[Document],
    llm: Any,
    full_documents: Optional[List[Document]] = None,
) -> List[Document]:
    """Добавляет контекстный заголовок к каждому чанку (Anthropic Contextual Retrieval).

    Идея: чанк сам по себе может быть непонятен ("Рекомендуемое масло: 5W-30").
    Добавляем краткое описание: "Из раздела 'Ошибка E21' документа errors.txt:
    Рекомендуемое масло: 5W-30".

    Это повышает точность retrieval на ~49% (по данным Anthropic).

    Если LLM недоступна, генерирует заголовок из metadata (source, page).
    """
    enriched: List[Document] = []

    # Группируем чанки по source документу для контекста
    source_texts: Dict[str, str] = {}
    if full_documents:
        for doc in full_documents:
            src = (doc.metadata or {}).get("source", "unknown")
            source_texts[src] = doc.page_content[:2000]  # Первые 2000 символов

    for chunk in chunks:
        source = (chunk.metadata or {}).get("source", "unknown")

        if llm is not None:
            # LLM генерирует краткое описание контекста
            doc_preview = source_texts.get(source, "")[:500]
            prompt = (
                "Дан фрагмент документа и начало этого документа для контекста.\n"
                "Напиши ОДНО краткое предложение (до 30 слов), описывающее,\n"
                "о чём этот фрагмент и откуда он.\n"
                "Не повторяй содержимое фрагмента, просто опиши его место в документе.\n\n"
                f"Документ: {source}\n"
                f"Начало документа: {doc_preview}\n\n"
                f"Фрагмент:\n{chunk.page_content}\n\n"
                "Краткое описание контекста:"
            )
            try:
                header = llm.invoke(prompt).strip()
                if len(header) > 200:
                    header = header[:200]
            except Exception:
                header = f"Из документа {source}"
        else:
            # Fallback: генерируем из metadata
            page = (chunk.metadata or {}).get("page", "")
            header = f"Из документа {source}"
            if page:
                header += f", стр. {page}"

        # Prepend header to chunk content
        new_content = f"[Контекст: {header}]\n{chunk.page_content}"
        enriched.append(Document(
            page_content=new_content,
            metadata={**(chunk.metadata or {}), "contextual_header": header},
        ))

    return enriched


# ---------------------------------------------------------------------------
# Level 3: Parent Document Retrieval
# ---------------------------------------------------------------------------


class ParentDocumentStore:
    """Хранит маленькие чанки для поиска, но возвращает большие (parent) для контекста.

    Проблема: маленькие чанки (200-300 символов) → точный поиск, но мало контекста.
    Большие чанки (1000+) → много контекста, но размытый поиск.

    Решение: индексируем маленькие child-чанки, но при retrieval возвращаем
    parent-чанк (объединение нескольких child-ов с перекрытием).

    Пример:
        Документ: "AAAA BBBB CCCC DDDD"
        Parent chunks (1000 chars):  [AAAA BBBB] [CCCC DDDD]
        Child chunks  (300 chars):   [AAAA] [BBBB] [CCCC] [DDDD]
        Поиск по child, возврат parent.
    """

    def __init__(
        self,
        docs: List[Document],
        embeddings: Any,
        child_chunk_size: int = 300,
        child_overlap: int = 50,
        parent_chunk_size: int = 1200,
        parent_overlap: int = 200,
    ):
        self._embeddings = embeddings

        # Создаём parent chunks
        parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=parent_chunk_size,
            chunk_overlap=parent_overlap,
        )
        self._parents: List[Document] = parent_splitter.split_documents(docs)

        # Создаём child chunks с привязкой к parent
        child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=child_chunk_size,
            chunk_overlap=child_overlap,
        )
        self._children: List[Document] = []
        self._child_to_parent: Dict[int, int] = {}

        for parent_idx, parent in enumerate(self._parents):
            child_docs = child_splitter.split_documents([parent])
            for child in child_docs:
                child_idx = len(self._children)
                child.metadata = {
                    **(child.metadata or {}),
                    "parent_idx": parent_idx,
                }
                self._children.append(child)
                self._child_to_parent[child_idx] = parent_idx

        # Векторизуем children
        texts = [c.page_content for c in self._children]
        self._vectors = embeddings.embed_documents(texts)

        print(f"ParentDocumentStore: {len(self._parents)} parents, {len(self._children)} children")

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def similarity_search(self, query: str, k: int = 5) -> List[Document]:
        """Ищет по child-чанкам, возвращает parent-чанки (дедуплицированные)."""
        q_vec = self._embeddings.embed_query(query)
        scores = [(i, self._cosine(q_vec, v)) for i, v in enumerate(self._vectors)]
        scores.sort(key=lambda x: x[1], reverse=True)

        seen_parents: set = set()
        results: List[Document] = []

        for child_idx, score in scores:
            parent_idx = self._child_to_parent[child_idx]
            if parent_idx not in seen_parents:
                seen_parents.add(parent_idx)
                results.append(self._parents[parent_idx])
                if len(results) >= k:
                    break

        return results

    def get_children(self) -> List[Document]:
        """Возвращает child-чанки (для BM25 индекса)."""
        return self._children


# ---------------------------------------------------------------------------
# Level 3: Multi-Query Retriever
# ---------------------------------------------------------------------------


class MultiQueryRetriever:
    """Разбивает сложный вопрос на несколько подвопросов, ищет по каждому.

    Пример:
        Вопрос: "Что делать при ошибке E20 и покрывается ли ремонт гарантией?"
        Подвопросы:
            1. "Ошибка E20 действия при перегреве"
            2. "Гарантия покрытие ремонт"
        Поиск по каждому → объединение результатов через RRF.
    """

    def __init__(
        self,
        base_retriever: Any,
        llm: Any,
        max_queries: int = 3,
    ):
        self._retriever = base_retriever
        self._llm = llm
        self._max_queries = max_queries

    def get_relevant_documents(self, query: str) -> List[Document]:
        """Multi-query retrieval."""
        sub_queries = self._generate_sub_queries(query)
        if not sub_queries:
            return self._retriever.get_relevant_documents(query)

        # Retrieve for each sub-query
        all_results: List[List[Document]] = []
        for sq in sub_queries:
            try:
                docs = self._retriever.get_relevant_documents(sq)
                all_results.append(docs)
            except Exception:
                continue

        if not all_results:
            return self._retriever.get_relevant_documents(query)

        # Merge all results via RRF
        return self._rrf_merge_multiple(all_results)

    def _generate_sub_queries(self, query: str) -> List[str]:
        """Генерирует подвопросы через LLM."""
        if self._llm is None:
            return [query]

        prompt = (
            "Разбей вопрос пользователя на 2-3 независимых поисковых запроса.\n"
            "Каждый запрос должен искать один конкретный аспект вопроса.\n"
            "Если вопрос простой и не требует разбиения — верни его как есть.\n\n"
            f"Вопрос: {query}\n\n"
            "Выведи запросы, по одному на строку (2-3 строки, без нумерации):"
        )
        try:
            raw = self._llm.invoke(prompt).strip()
            lines = [ln.strip().lstrip("0123456789.-) ") for ln in raw.split("\n") if ln.strip()]
            # Фильтруем мусор
            queries = [ln for ln in lines if len(ln) >= 5][:self._max_queries]
            return queries if queries else [query]
        except Exception:
            return [query]

    def _rrf_merge_multiple(self, result_lists: List[List[Document]], k: int = 60) -> List[Document]:
        """RRF merge для нескольких списков."""
        scores: Dict[str, float] = {}
        doc_map: Dict[str, Document] = {}

        for result_list in result_lists:
            for rank, doc in enumerate(result_list):
                key = doc.page_content[:200]
                scores[key] = scores.get(key, 0) + 1.0 / (k + rank)
                doc_map[key] = doc

        sorted_keys = sorted(scores, key=lambda x: scores[x], reverse=True)
        return [doc_map[k] for k in sorted_keys]

    def invoke(self, query: str) -> List[Document]:
        return self.get_relevant_documents(query)


# ---------------------------------------------------------------------------
# Stub store (fallback if no vector DB available)
# ---------------------------------------------------------------------------

class QdrantStubStore:
    """In-memory stub for Qdrant when dependencies are missing."""

    def __init__(self, docs: Sequence[Document], embeddings: Any):
        self._docs: List[Document] = list(docs)
        self._embeddings = embeddings
        self._vectors: List[List[float]] = self._embed_documents()

    def _embed_documents(self) -> List[List[float]]:
        texts = [d.page_content for d in self._docs]
        return self._embeddings.embed_documents(texts)

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        import math
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def similarity_search(self, query: str, k: int = 6) -> List[Document]:
        q = self._embeddings.embed_query(query)
        scores = [(idx, self._cosine(q, v)) for idx, v in enumerate(self._vectors)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [self._docs[idx] for idx, _ in scores[:k]]

    def as_retriever(self, search_kwargs: Optional[Dict[str, Any]] = None) -> "QdrantStubRetriever":
        search_kwargs = search_kwargs or {"k": 6}
        return QdrantStubRetriever(self, search_kwargs)


class QdrantStubRetriever:
    def __init__(self, store: QdrantStubStore, search_kwargs: Dict[str, Any]):
        self._store = store
        self._k = int(search_kwargs.get("k", 6))

    def get_relevant_documents(self, query: str) -> List[Document]:
        return self._store.similarity_search(query, k=self._k)

    def invoke(self, query: str) -> List[Document]:
        return self.get_relevant_documents(query)


# ---------------------------------------------------------------------------
# Build vector store
# ---------------------------------------------------------------------------

def _build_chroma(docs: Sequence[Document], embeddings: Any) -> Any:
    if not HAS_CHROMA:
        raise ImportError(
            "Chroma not installed. Install 'langchain-chroma' "
            "or switch backend (VECTOR_DB_TYPE) to 'qdrant'."
        )
    chroma_dir = _data_dir() / "chroma"
    chroma_dir.mkdir(parents=True, exist_ok=True)
    print(f"Building Chroma in {chroma_dir}")
    store = Chroma.from_documents(
        documents=list(docs),
        embedding=embeddings,
        persist_directory=str(chroma_dir),
        collection_name="documents",
    )
    if hasattr(store, "persist"):
        store.persist()
    print(f"Chroma ready: {len(docs)} chunks")
    return store


def _build_qdrant(docs: Sequence[Document], embeddings: Any) -> Any:
    if not HAS_QDRANT:
        print("Qdrant unavailable — using in-memory stub")
        return QdrantStubStore(docs, embeddings)
    qdrant_dir = _data_dir() / "qdrant"
    qdrant_dir.mkdir(parents=True, exist_ok=True)
    print(f"Building local Qdrant in {qdrant_dir}")
    try:
        client = QdrantClient(path=str(qdrant_dir))
        store = QdrantVectorStore.from_documents(
            documents=list(docs),
            embedding=embeddings,
            client=client,
            collection_name="documents",
        )
        print(f"Qdrant ready: {len(docs)} chunks")
        return store
    except Exception as e:
        print(f"Qdrant init error: {e!r}, falling back to in-memory stub")
        return QdrantStubStore(docs, embeddings)


def build_vector_store(
    docs: Sequence[Document],
    chunk_config: Dict[str, int],
    embeddings: Any | None = None,
    use_semantic_chunking: bool = False,
) -> tuple[Any, List[Document]]:
    """Строит векторное хранилище из документов.

    Args:
        docs: исходные документы.
        chunk_config: {"chunk_size": int, "chunk_overlap": int}.
        embeddings: embedding model (если None — создаётся автоматически).
        use_semantic_chunking: True → семантический сплиттинг (Level 2).

    Returns:
        (vector_store, chunks) — хранилище и список чанков (нужен для BM25).
    """
    if not docs:
        raise ValueError("Document list is empty.")

    if embeddings is None:
        embeddings = get_embeddings()

    from config.settings import get_settings
    settings = get_settings()

    chunk_size = int(chunk_config.get("chunk_size", 800))
    chunk_overlap = int(chunk_config.get("chunk_overlap", 200))
    semantic_chunking_enabled = settings.semantic_chunking or use_semantic_chunking

    if semantic_chunking_enabled:
        print("Using semantic chunking (Level 2)...")
        chunks = semantic_split(
            list(docs), embeddings,
            min_chunk_size=chunk_overlap,
            max_chunk_size=chunk_size,
        )
    else:
        splitter = _build_text_splitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        chunks = splitter.split_documents(list(docs))

    backend = _get_backend()
    mode = "semantic" if semantic_chunking_enabled else f"fixed(size={chunk_size}, overlap={chunk_overlap})"
    print(f"Backend: {backend.upper()}, chunks: {len(chunks)}, mode: {mode}")

    if backend == "qdrant":
        store = _build_qdrant(chunks, embeddings)
    else:
        store = _build_chroma(chunks, embeddings)

    return store, chunks


# ---------------------------------------------------------------------------
# Get retriever (upgraded: hybrid + reranker)
# ---------------------------------------------------------------------------

def get_retriever(
    vector_store: Any,
    chunks: List[Document] | None = None,
    k: int | None = None,
) -> Any:
    """Возвращает retriever с hybrid search и reranker.

    Args:
        vector_store: Chroma/Qdrant/Stub store.
        chunks: список чанков для BM25 индекса. Если None — только vector search.
        k: override для retrieval_top_k (по умолчанию из settings).

    Returns:
        HybridRetriever если доступны BM25/reranker, иначе простой vector retriever.
    """
    from config.settings import get_settings
    settings = get_settings()

    retrieval_k = k or settings.retrieval_top_k
    rerank_k = settings.rerank_top_k

    # Try to build hybrid retriever
    use_bm25 = settings.hybrid_search and chunks is not None
    reranker = get_reranker() if settings.reranker_model else None

    if use_bm25 or reranker:
        return HybridRetriever(
            vector_store=vector_store,
            chunks=chunks or [],
            retrieval_k=retrieval_k,
            rerank_k=rerank_k,
            reranker=reranker,
            use_bm25=use_bm25,
        )

    # Fallback: simple vector retriever
    if hasattr(vector_store, "as_retriever"):
        return vector_store.as_retriever(search_kwargs={"k": rerank_k})

    class _SimpleRetriever:
        def __init__(self, store: Any, top_k: int):
            self._store = store
            self._k = top_k
        def get_relevant_documents(self, query: str) -> List[Document]:
            return self._store.similarity_search(query, k=self._k)
        def invoke(self, query: str) -> List[Document]:
            return self.get_relevant_documents(query)

    return _SimpleRetriever(vector_store, rerank_k)
