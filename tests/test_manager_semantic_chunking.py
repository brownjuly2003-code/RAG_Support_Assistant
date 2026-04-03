from types import SimpleNamespace
from unittest.mock import Mock

import manager
from config import settings as settings_module


def test_build_vector_store_uses_semantic_chunker_from_settings(
    monkeypatch,
) -> None:
    docs = [manager.Document(page_content="Первый. Второй. Третий.", metadata={})]
    embeddings = Mock()
    semantic_chunks = [
        manager.Document(page_content="Семантический чанк", metadata={}),
    ]
    semantic_chunker = Mock()
    semantic_chunker.split_documents.return_value = semantic_chunks
    semantic_chunker_factory = Mock(return_value=semantic_chunker)

    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: SimpleNamespace(semantic_chunking=True),
    )
    monkeypatch.setattr(manager, "SemanticChunker", semantic_chunker_factory, raising=False)
    monkeypatch.setattr(manager, "HAS_SEMANTIC_CHUNKER", True, raising=False)
    monkeypatch.setattr(manager, "_get_backend", lambda: "chroma")
    monkeypatch.setattr(manager, "_build_chroma", lambda chunks, _: {"chunks": chunks})

    store, chunks = manager.build_vector_store(
        docs,
        {"chunk_size": 400, "chunk_overlap": 50},
        embeddings=embeddings,
    )

    semantic_chunker_factory.assert_called_once_with(embeddings)
    semantic_chunker.split_documents.assert_called_once_with(docs)
    assert chunks == semantic_chunks
    assert store == {"chunks": semantic_chunks}


def test_build_vector_store_falls_back_to_recursive_splitter_when_disabled(
    monkeypatch,
) -> None:
    docs = [manager.Document(page_content="Обычный текст для чанкинга", metadata={})]
    embeddings = Mock()
    recursive_chunks = [
        manager.Document(page_content="Recursive chunk", metadata={}),
    ]
    splitter = Mock()
    splitter.split_documents.return_value = recursive_chunks
    semantic_chunker_factory = Mock()

    monkeypatch.setattr(
        settings_module,
        "get_settings",
        lambda: SimpleNamespace(semantic_chunking=False),
    )
    monkeypatch.setattr(manager, "SemanticChunker", semantic_chunker_factory, raising=False)
    monkeypatch.setattr(manager, "_build_text_splitter", lambda **_: splitter)
    monkeypatch.setattr(manager, "_get_backend", lambda: "chroma")
    monkeypatch.setattr(manager, "_build_chroma", lambda chunks, _: {"chunks": chunks})

    store, chunks = manager.build_vector_store(
        docs,
        {"chunk_size": 400, "chunk_overlap": 50},
        embeddings=embeddings,
    )

    semantic_chunker_factory.assert_not_called()
    splitter.split_documents.assert_called_once_with(docs)
    assert chunks == recursive_chunks
    assert store == {"chunks": recursive_chunks}
