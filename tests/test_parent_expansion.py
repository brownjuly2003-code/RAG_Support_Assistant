"""Parent-expansion (post-rerank) в HybridRetriever.

Финальные top-k чанки дополняются соседними structural-секциями своего
source-документа (текст-lookup по порядку ингеста); отбор BM25+RRF+reranker
не меняется. Дизайн: docs/operations/2026-06-05-residual-miss-diagnosis.md.
"""

from __future__ import annotations

from types import SimpleNamespace

from config.settings import Settings
from vectordb import _base_manager as manager


def test_parent_expansion_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("RAG_PARENT_EXPANSION", raising=False)

    settings = Settings()

    assert settings.parent_expansion is False
    assert settings.parent_expansion_window == 1
    assert settings.parent_expansion_max_chars == 2400


def _make_chunks() -> list[manager.Document]:
    """Два source-дока, секции в порядке ингеста."""
    return [
        manager.Document(page_content="a0: интро", metadata={"source": "a.md"}),
        manager.Document(page_content="a1: обязательные поля", metadata={"source": "a.md"}),
        manager.Document(page_content="a2: эскалация", metadata={"source": "a.md"}),
        manager.Document(page_content="b0: другой док", metadata={"source": "b.md"}),
        manager.Document(page_content="b1: его секция", metadata={"source": "b.md"}),
    ]


def _retriever(
    chunks: list[manager.Document],
    hits: list[manager.Document],
    **kwargs,
) -> manager.HybridRetriever:
    class _VectorStore:
        def similarity_search(self, query: str, k: int) -> list[manager.Document]:
            return list(hits)

    defaults = dict(
        chunks=chunks,
        use_bm25=False,
        rerank_k=2,
        parent_expansion=True,
        parent_expansion_window=1,
        parent_expansion_max_chars=2400,
    )
    defaults.update(kwargs)
    return manager.HybridRetriever(_VectorStore(), **defaults)


def test_expands_with_same_source_neighbors_in_document_order() -> None:
    chunks = _make_chunks()
    retriever = _retriever(chunks, hits=[chunks[1]], rerank_k=1)

    result = retriever.get_relevant_documents("вопрос")

    assert len(result) == 1
    expanded = result[0]
    assert expanded.page_content == "a0: интро\n\na1: обязательные поля\n\na2: эскалация"
    assert expanded.metadata["parent_expanded"] is True
    assert expanded.metadata["source"] == "a.md"


def test_does_not_cross_source_boundary() -> None:
    chunks = _make_chunks()
    # a2 — последняя секция a.md; сосед справа b0 принадлежит другому доку.
    retriever = _retriever(chunks, hits=[chunks[2]], rerank_k=1)

    result = retriever.get_relevant_documents("вопрос")

    assert result[0].page_content == "a1: обязательные поля\n\na2: эскалация"
    # b0 не подмешан
    assert "b0" not in result[0].page_content


def test_neighbor_already_in_topk_is_not_duplicated() -> None:
    chunks = _make_chunks()
    # a1 и a2 оба в финальном top-k: a2 не должен дублироваться как сосед a1.
    retriever = _retriever(chunks, hits=[chunks[1], chunks[2]], rerank_k=2)

    result = retriever.get_relevant_documents("вопрос")

    joined = "\n===\n".join(doc.page_content for doc in result)
    assert joined.count("a2: эскалация") == 1
    # a1 расширен только влево (a0), a2 — никуда (a1 занят, b0 чужой).
    assert result[0].page_content == "a0: интро\n\na1: обязательные поля"
    assert result[1].page_content == "a2: эскалация"
    assert "parent_expanded" not in (result[1].metadata or {})


def test_char_budget_skips_oversized_neighbors() -> None:
    big = manager.Document(page_content="x" * 500, metadata={"source": "a.md"})
    core = manager.Document(page_content="core", metadata={"source": "a.md"})
    chunks = [big, core]
    retriever = _retriever(
        chunks, hits=[core], rerank_k=1, parent_expansion_max_chars=100,
    )

    result = retriever.get_relevant_documents("вопрос")

    # Сосед не влез в бюджет — чанк возвращён как есть.
    assert result[0].page_content == "core"
    assert "parent_expanded" not in (result[0].metadata or {})


def test_neighbor_contextual_header_is_stripped() -> None:
    neighbor = manager.Document(
        page_content="[Контекст: Из документа a.md, раздел: Поля]\nтело секции",
        metadata={"source": "a.md"},
    )
    core = manager.Document(page_content="core", metadata={"source": "a.md"})
    retriever = _retriever([neighbor, core], hits=[core], rerank_k=1)

    result = retriever.get_relevant_documents("вопрос")

    assert result[0].page_content == "тело секции\n\ncore"


def test_unknown_chunk_and_disabled_flag_leave_docs_unchanged() -> None:
    chunks = _make_chunks()
    foreign = manager.Document(page_content="не из индекса", metadata={"source": "a.md"})

    retriever = _retriever(chunks, hits=[foreign], rerank_k=1)
    assert retriever.get_relevant_documents("вопрос")[0] is foreign

    off = _retriever(chunks, hits=[chunks[1]], rerank_k=1, parent_expansion=False)
    result = off.get_relevant_documents("вопрос")
    assert result[0] is chunks[1]
    assert "parent_expanded" not in (result[0].metadata or {})


def test_window_two_takes_two_sections_each_side() -> None:
    chunks = [
        manager.Document(page_content=f"s{i}", metadata={"source": "a.md"})
        for i in range(5)
    ]
    retriever = _retriever(
        chunks, hits=[chunks[2]], rerank_k=1, parent_expansion_window=2,
    )

    result = retriever.get_relevant_documents("вопрос")

    assert result[0].page_content == "s0\n\ns1\n\ns2\n\ns3\n\ns4"


def test_build_retriever_wires_parent_expansion_from_settings(monkeypatch) -> None:
    # Реальный reranker (bge ~2.3GB) не должен грузиться в тесте.
    monkeypatch.setenv("RAG_RERANKER_MODEL", "")
    monkeypatch.setenv("RAG_PARENT_EXPANSION", "true")
    monkeypatch.setenv("RAG_PARENT_EXPANSION_WINDOW", "2")
    monkeypatch.setenv("RAG_PARENT_EXPANSION_MAX_CHARS", "999")

    import config.settings as settings_module
    settings_module._settings = None  # singleton перечитает env

    chunks = _make_chunks()
    store = SimpleNamespace(similarity_search=lambda query, k: [])
    retriever = manager.get_retriever(store, chunks=chunks)

    assert isinstance(retriever, manager.HybridRetriever)
    assert retriever._parent_expansion is True
    assert retriever._parent_window == 2
    assert retriever._parent_max_chars == 999
