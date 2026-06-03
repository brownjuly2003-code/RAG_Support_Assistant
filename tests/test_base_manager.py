from __future__ import annotations

import subprocess
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from config import settings as settings_module
from vectordb import _base_manager as manager


def test_base_manager_import_does_not_eagerly_import_sentence_transformers() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import vectordb._base_manager; "
                "print('st_loaded=' + str('sentence_transformers' in sys.modules))"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "st_loaded=False" in result.stdout


class _Array:
    def __init__(self, values: list[float] | list[list[float]]) -> None:
        self._values = values

    def __getitem__(self, index: int) -> "_Array":
        return _Array(self._values[index])  # type: ignore[arg-type]

    def tolist(self) -> list[float] | list[list[float]]:
        return self._values


class _Embeddings:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        if "alpha" in text:
            return [1.0, 0.0]
        if "beta" in text:
            return [0.0, 1.0]
        return [0.5, 0.5]


def test_get_embeddings_wraps_and_caches_sentence_transformer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []

    class _SentenceTransformer:
        def __init__(self, model_name: str, device: str) -> None:
            created.append(f"{model_name}:{device}")

        def encode(self, texts: list[str], normalize_embeddings: bool) -> _Array:
            assert normalize_embeddings is True
            return _Array([[float(len(text)), 1.0] for text in texts])

    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = _SentenceTransformer

    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setattr(manager, "_cached_embeddings", None)
    monkeypatch.setattr(settings_module, "get_settings", lambda: SimpleNamespace(rag_device="cpu"))

    embeddings = manager.get_embeddings("fake-model")

    assert created == ["fake-model:cpu"]
    assert embeddings.embed_documents(["abc"]) == [[3.0, 1.0]]
    assert embeddings.embed_query("abcd") == [4.0, 1.0]
    assert manager.get_embeddings("other-model") is embeddings


def test_get_reranker_handles_disabled_dependency_and_caches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[str] = []

    class _CrossEncoder:
        def __init__(self, model_name: str, device: str) -> None:
            created.append(f"{model_name}:{device}")

    monkeypatch.setattr(manager, "_cached_reranker", None)
    monkeypatch.setattr(manager, "HAS_CROSS_ENCODER", False)
    monkeypatch.setattr(settings_module, "get_settings", lambda: SimpleNamespace(rag_device="cpu"))
    assert manager.get_reranker("reranker-a") is None

    monkeypatch.setattr(manager, "HAS_CROSS_ENCODER", True)
    monkeypatch.setattr(manager, "CrossEncoder", _CrossEncoder)

    reranker = manager.get_reranker("reranker-b")

    assert created == ["reranker-b:cpu"]
    assert manager.get_reranker("reranker-c") is reranker


def test_resolve_device_passthrough_and_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    # Explicit values are used as-is (normalized to lowercase).
    assert manager._resolve_device("cuda:0") == "cuda:0"
    assert manager._resolve_device("CPU") == "cpu"
    assert manager._resolve_device("mps") == "mps"

    # None reads config.settings.get_settings().rag_device.
    monkeypatch.setattr(settings_module, "get_settings", lambda: SimpleNamespace(rag_device="cuda"))
    assert manager._resolve_device() == "cuda"


def test_resolve_device_auto_detects_accelerator(monkeypatch: pytest.MonkeyPatch) -> None:
    cuda_torch = types.ModuleType("torch")
    cuda_torch.cuda = SimpleNamespace(is_available=lambda: True)
    cuda_torch.backends = SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, "torch", cuda_torch)
    assert manager._resolve_device("auto") == "cuda"

    mps_torch = types.ModuleType("torch")
    mps_torch.cuda = SimpleNamespace(is_available=lambda: False)
    mps_torch.backends = SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True))
    monkeypatch.setitem(sys.modules, "torch", mps_torch)
    assert manager._resolve_device("auto") == "mps"


def test_resolve_device_auto_falls_back_to_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    # No accelerator available → cpu.
    cpu_torch = types.ModuleType("torch")
    cpu_torch.cuda = SimpleNamespace(is_available=lambda: False)
    cpu_torch.backends = SimpleNamespace(mps=SimpleNamespace(is_available=lambda: False))
    monkeypatch.setitem(sys.modules, "torch", cpu_torch)
    assert manager._resolve_device("auto") == "cpu"

    # torch import failing → cpu (None in sys.modules forces ImportError).
    monkeypatch.setitem(sys.modules, "torch", None)
    assert manager._resolve_device("auto") == "cpu"


def test_add_contextual_headers_uses_llm_truncates_and_falls_back() -> None:
    class _LLM:
        def __init__(self, response: str | Exception) -> None:
            self.response = response

        def invoke(self, prompt: str) -> str:
            assert "Source A" in prompt
            if isinstance(self.response, Exception):
                raise self.response
            return self.response

    chunk = manager.Document(page_content="alpha detail", metadata={"source": "Source A"})
    full_doc = manager.Document(page_content="full source preview", metadata={"source": "Source A"})

    enriched = manager.add_contextual_headers([chunk], _LLM("x" * 250), [full_doc])
    assert enriched[0].metadata["contextual_header"] == "x" * 200
    assert enriched[0].page_content.startswith("[Context:") is False
    assert enriched[0].page_content.startswith("[")

    fallback = manager.add_contextual_headers(
        [manager.Document(page_content="beta detail", metadata={"source": "Source B"})],
        _LLM(RuntimeError("boom")),
    )
    assert fallback[0].metadata["contextual_header"].endswith("Source B")

    no_llm = manager.add_contextual_headers(
        [manager.Document(page_content="gamma detail", metadata={"source": "Source C", "page": 4})],
        None,
    )
    assert "4" in no_llm[0].metadata["contextual_header"]


def test_hybrid_retriever_vector_paths_and_reranker_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alpha = manager.Document(page_content="alpha doc", metadata={})
    beta = manager.Document(page_content="beta doc", metadata={})

    class _VectorStore:
        def similarity_search(self, query: str, k: int) -> list[manager.Document]:
            assert query == "question"
            assert k == 20
            return [alpha, beta]

    class _Reranker:
        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            assert len(pairs) == 2
            return [0.1, 0.9]

    monkeypatch.setattr(manager, "HAS_BM25", False)

    retriever = manager.HybridRetriever(
        _VectorStore(),
        chunks=[alpha, beta],
        reranker=_Reranker(),
        use_bm25=False,
        rerank_k=1,
    )
    assert retriever.invoke("question") == [beta]

    class _BrokenReranker:
        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            _ = pairs
            raise RuntimeError("rerank failed")

    fallback = manager.HybridRetriever(
        _VectorStore(),
        chunks=[alpha, beta],
        reranker=_BrokenReranker(),
        use_bm25=False,
        rerank_k=1,
    )
    assert fallback.get_relevant_documents("question") == [alpha]

    class _Retriever:
        def get_relevant_documents(self, query: str) -> list[manager.Document]:
            assert query == "question"
            return [beta]

    class _StoreWithRetriever:
        def as_retriever(self, search_kwargs: dict[str, int]) -> _Retriever:
            assert search_kwargs == {"k": 20}
            return _Retriever()

    no_similarity = manager.HybridRetriever(
        _StoreWithRetriever(),
        chunks=[alpha, beta],
        use_bm25=False,
    )
    assert no_similarity.get_relevant_documents("question") == [beta]


def test_hybrid_retriever_vector_fast_path_skips_reranker() -> None:
    alpha = manager.Document(page_content="alpha doc", metadata={})
    beta = manager.Document(page_content="beta doc", metadata={})

    class _VectorStore:
        def similarity_search(self, query: str, k: int) -> list[manager.Document]:
            assert query == "question"
            assert k == 20
            return [alpha, beta]

    class _UnexpectedReranker:
        def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
            _ = pairs
            raise AssertionError("vector fast path must not rerank")

    retriever = manager.HybridRetriever(
        _VectorStore(),
        chunks=[alpha, beta],
        reranker=_UnexpectedReranker(),
        use_bm25=True,
        rerank_k=1,
    )

    assert retriever.get_vector_documents("question") == [alpha]


def test_hybrid_retriever_rrf_keeps_chunks_with_shared_context_prefix() -> None:
    shared_context = "Политика возврата и гарантийного обслуживания. " * 8
    first = manager.Document(
        page_content=f"{shared_context}\nПервый чанк: сроки возврата товара.",
        metadata={"source": "returns.md"},
    )
    second = manager.Document(
        page_content=f"{shared_context}\nВторой чанк: условия гарантийного ремонта.",
        metadata={"source": "returns.md"},
    )

    retriever = manager.HybridRetriever(
        SimpleNamespace(),
        chunks=[first, second],
        use_bm25=False,
        doc_key_chars=200,
    )

    merged = retriever._rrf_merge([first], [second])

    assert [doc.page_content for doc in merged] == [first.page_content, second.page_content]


def test_hybrid_retriever_bm25_tokenizes_russian_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[list[str]] | list[str]] = {}

    class _BM25:
        def __init__(self, tokenized_docs: list[list[str]]) -> None:
            captured["docs"] = tokenized_docs

        def get_scores(self, tokenized_query: list[str]) -> list[float]:
            captured["query"] = tokenized_query
            return [1.0, 0.0]

    class _VectorStore:
        def similarity_search(self, query: str, k: int) -> list[manager.Document]:
            _ = query, k
            return []

    monkeypatch.setattr(manager, "HAS_BM25", True)
    monkeypatch.setattr(manager, "BM25Okapi", _BM25)
    docs = [
        manager.Document(page_content="Возврат, товара! Заказ №123.", metadata={}),
        manager.Document(page_content="График доставки.", metadata={}),
    ]

    retriever = manager.HybridRetriever(_VectorStore(), chunks=docs, use_bm25=True)
    retriever.get_relevant_documents("ВОЗВРАТ?")

    assert captured["docs"] == [
        ["возврат", "товара", "заказ", "123"],
        ["график", "доставки"],
    ]
    assert captured["query"] == ["возврат"]


def test_qdrant_stub_store_search_and_retriever() -> None:
    docs = [
        manager.Document(page_content="alpha content", metadata={}),
        manager.Document(page_content="beta content", metadata={}),
    ]
    store = manager.QdrantStubStore(docs, _Embeddings())

    assert store.similarity_search("alpha", k=1) == [docs[0]]
    assert store.as_retriever({"k": 1}).invoke("beta") == [docs[1]]
    assert manager.QdrantStubStore._cosine([0.0], [1.0]) == 0.0


def test_multi_query_retriever_generates_filters_and_merges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BaseRetriever:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def get_relevant_documents(self, query: str) -> list[manager.Document]:
            self.queries.append(query)
            if "skip" in query:
                raise RuntimeError("skip query")
            return [manager.Document(page_content=f"{query} result", metadata={})]

    class _LLM:
        def invoke(self, prompt: str) -> str:
            assert "original question" in prompt
            return "1. alpha query\n2. no\n3. skip query\n4. beta query"

    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: SimpleNamespace(rrf_doc_key_chars=200, rrf_k=60),
    )

    base = _BaseRetriever()
    retriever = manager.MultiQueryRetriever(base, _LLM(), max_queries=3)
    docs = retriever.get_relevant_documents("original question")

    assert base.queries == ["alpha query", "skip query", "beta query"]
    assert [doc.page_content for doc in docs] == ["alpha query result", "beta query result"]
    assert manager.MultiQueryRetriever(base, None).invoke("plain query")


def test_multi_query_rrf_keeps_chunks_with_shared_context_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: SimpleNamespace(rrf_doc_key_chars=200, rrf_k=60),
    )
    shared_context = "Раздел базы знаний о доставке и возвратах. " * 8
    first = manager.Document(
        page_content=f"{shared_context}\nПервый чанк: доставка по регионам.",
        metadata={"source": "shipping.md"},
    )
    second = manager.Document(
        page_content=f"{shared_context}\nВторой чанк: возврат после доставки.",
        metadata={"source": "shipping.md"},
    )
    retriever = manager.MultiQueryRetriever(SimpleNamespace(), None)

    merged = retriever._rrf_merge_multiple([[first], [second]])

    assert [doc.page_content for doc in merged] == [first.page_content, second.page_content]


def test_build_helpers_handle_backends_and_simple_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docs = [manager.Document(page_content="alpha beta gamma", metadata={})]
    chunks = [manager.Document(page_content="alpha", metadata={})]

    class _Splitter:
        def split_documents(self, source_docs: list[manager.Document]) -> list[manager.Document]:
            assert source_docs == docs
            return chunks

    class _Store:
        def __init__(self) -> None:
            self._source_docs = docs
            self._source_embeddings = _Embeddings()

        def similarity_search(self, query: str, k: int) -> list[manager.Document]:
            _ = query, k
            return chunks

    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: SimpleNamespace(
            semantic_chunking=False,
            parent_child=False,
            hybrid_search=False,
            retrieval_top_k=5,
            rerank_top_k=1,
            reranker_model="",
            chunk_size=20,
            chunk_overlap=0,
        ),
    )
    monkeypatch.setattr(manager, "_build_text_splitter", lambda **kwargs: _Splitter())
    monkeypatch.setattr(manager, "_get_backend", lambda: "qdrant")
    monkeypatch.setattr(manager, "_build_qdrant", lambda built_chunks, embeddings: _Store())

    with pytest.raises(ValueError):
        manager.build_vector_store([], {"chunk_size": 20, "chunk_overlap": 0}, _Embeddings())

    store, built_chunks = manager.build_vector_store(
        docs,
        {"chunk_size": 20, "chunk_overlap": 0},
        _Embeddings(),
    )
    assert built_chunks == chunks
    assert getattr(store, "_source_docs") == docs

    simple = manager.build_retriever(docs, _Embeddings(), vector_store=_Store(), chunks=chunks)
    assert simple.get_relevant_documents("alpha") == chunks

    source_routed = manager.get_retriever(_Store(), chunks=chunks)
    assert source_routed.get_relevant_documents("alpha") == chunks
