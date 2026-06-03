"""Unit tests for markdown-structural chunking (opt-in) and the unified select_chunks selector.

Pure text transforms — no embeddings/models, so these run locally.
"""
from types import SimpleNamespace
from unittest.mock import Mock

from config import settings as settings_module
from vectordb import _base_manager as manager

# ---------------------------------------------------------------------------
# structural_split
# ---------------------------------------------------------------------------

def test_structural_split_splits_by_headers_retains_and_propagates_metadata() -> None:
    doc = manager.Document(
        page_content="# Заголовок\nвступление\n## Раздел A\nтекст A\n## Раздел B\nтекст B",
        metadata={"source": "faq.md", "doc_id": "faq.md"},
    )
    chunks = manager.structural_split([doc], max_chunk_size=2000, chunk_overlap=100)

    # one chunk per markdown section
    assert len(chunks) == 3
    # headers are retained in content (strip_headers=False)
    assert any("# Заголовок" in c.page_content for c in chunks)
    assert any("## Раздел A" in c.page_content for c in chunks)
    # parent metadata propagated + header metadata attached
    for c in chunks:
        assert c.metadata["source"] == "faq.md"
        assert c.metadata["doc_id"] == "faq.md"
        assert c.metadata.get("h1") == "Заголовок"
    section_b = next(c for c in chunks if "Раздел B" in c.page_content)
    assert section_b.metadata.get("h2") == "Раздел B"


def test_structural_split_caps_oversized_section() -> None:
    body = "слово " * 60  # ~360 chars under a single header
    doc = manager.Document(page_content=f"## Большой\n{body}", metadata={"source": "x.md"})
    chunks = manager.structural_split([doc], max_chunk_size=60, chunk_overlap=10)

    assert len(chunks) > 1  # the oversized section was capped into pieces
    assert all(len(c.page_content) <= 60 for c in chunks)
    assert all(c.metadata["source"] == "x.md" for c in chunks)


# ---------------------------------------------------------------------------
# select_chunks precedence: structural > semantic > fixed
# ---------------------------------------------------------------------------

def test_select_chunks_prefers_structural_when_flag_on(monkeypatch) -> None:
    docs = [manager.Document(page_content="# H\nbody", metadata={})]
    sentinel = [manager.Document(page_content="structural", metadata={})]
    structural = Mock(return_value=sentinel)
    semantic = Mock()

    monkeypatch.setattr(
        settings_module, "get_settings",
        lambda: SimpleNamespace(structural_chunking=True, semantic_chunking=True),
    )
    monkeypatch.setattr(manager, "structural_split", structural)
    monkeypatch.setattr(manager, "semantic_split", semantic)

    result = manager.select_chunks(docs, embeddings=None, chunk_size=400, chunk_overlap=50)

    assert result == sentinel
    structural.assert_called_once()
    semantic.assert_not_called()


def test_select_chunks_uses_semantic_when_only_semantic_on(monkeypatch) -> None:
    docs = [manager.Document(page_content="text", metadata={})]
    sentinel = [manager.Document(page_content="semantic", metadata={})]
    structural = Mock()
    semantic = Mock(return_value=sentinel)

    monkeypatch.setattr(
        settings_module, "get_settings",
        lambda: SimpleNamespace(structural_chunking=False, semantic_chunking=True),
    )
    monkeypatch.setattr(manager, "structural_split", structural)
    monkeypatch.setattr(manager, "semantic_split", semantic)

    result = manager.select_chunks(docs, embeddings=Mock(), chunk_size=400, chunk_overlap=50)

    assert result == sentinel
    structural.assert_not_called()
    semantic.assert_called_once()


def test_select_chunks_falls_back_to_fixed_when_all_off(monkeypatch) -> None:
    docs = [manager.Document(page_content="plain text", metadata={})]
    sentinel = [manager.Document(page_content="fixed", metadata={})]
    splitter = Mock()
    splitter.split_documents.return_value = sentinel
    semantic = Mock()

    monkeypatch.setattr(
        settings_module, "get_settings",
        lambda: SimpleNamespace(structural_chunking=False, semantic_chunking=False),
    )
    monkeypatch.setattr(manager, "semantic_split", semantic)
    monkeypatch.setattr(manager, "_build_text_splitter", lambda *a, **k: splitter)

    result = manager.select_chunks(docs, embeddings=None, chunk_size=400, chunk_overlap=50)

    assert result == sentinel
    semantic.assert_not_called()
    splitter.split_documents.assert_called_once_with(docs)
