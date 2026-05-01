from __future__ import annotations

from types import SimpleNamespace

import pytest

from tasks import ingest_task


@pytest.fixture(autouse=True)
def _capture_task_state(monkeypatch):
    states: list[tuple[str, dict]] = []

    def fake_update_state(*, state: str, meta: dict) -> None:
        states.append((state, meta))

    monkeypatch.setattr(ingest_task.ingest_document, "update_state", fake_update_state)
    return states


def test_ingest_document_returns_error_for_missing_file(tmp_path, _capture_task_state) -> None:
    result = ingest_task.ingest_document.run(str(tmp_path / "missing.txt"))

    assert result["status"] == "error"
    assert "File not found" in result["message"]
    assert _capture_task_state == [("PROCESSING", {"step": "loading"})]


def test_ingest_document_returns_error_when_loading_fails(tmp_path, monkeypatch) -> None:
    upload = tmp_path / "doc.txt"
    upload.write_text("hello", encoding="utf-8")

    class BrokenLoader:
        def __init__(self, recursive: bool) -> None:
            assert recursive is False

        def load_documents(self, path: str):
            raise RuntimeError("parse failed")

    monkeypatch.setattr("ingestion.loader.DocumentLoader", BrokenLoader)

    result = ingest_task.ingest_document.run(str(upload))

    assert result == {"status": "error", "message": "Loading failed: parse failed"}


def test_ingest_document_returns_partial_when_loader_has_no_docs(tmp_path, monkeypatch) -> None:
    upload = tmp_path / "empty.txt"
    upload.write_text("", encoding="utf-8")

    class EmptyLoader:
        def __init__(self, recursive: bool) -> None:
            pass

        def load_documents(self, path: str):
            return []

    monkeypatch.setattr("ingestion.loader.DocumentLoader", EmptyLoader)

    result = ingest_task.ingest_document.run(str(upload))

    assert result == {
        "status": "partial",
        "docs_count": 0,
        "message": "No text content extracted",
    }


def test_ingest_document_indexes_loaded_docs(tmp_path, monkeypatch, _capture_task_state) -> None:
    upload = tmp_path / "doc.txt"
    upload.write_text("hello", encoding="utf-8")
    calls: dict[str, object] = {}
    docs = [SimpleNamespace(page_content="hello")]

    class FakeLoader:
        def __init__(self, recursive: bool) -> None:
            assert recursive is False

        def load_documents(self, path: str):
            calls["load_path"] = path
            return docs

    def fake_build_vector_store(loaded_docs, chunk_config, embeddings):
        calls["docs"] = loaded_docs
        calls["chunk_config"] = chunk_config
        calls["embeddings"] = embeddings

    monkeypatch.setattr("ingestion.loader.DocumentLoader", FakeLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr("vectordb.manager.build_vector_store", fake_build_vector_store)
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(chunk_size=123, chunk_overlap=45),
    )

    result = ingest_task.ingest_document.run(str(upload))

    assert result == {
        "status": "ok",
        "docs_count": 1,
        "message": "Indexed 1 document(s) from doc.txt",
    }
    assert calls == {
        "load_path": str(tmp_path),
        "docs": docs,
        "chunk_config": {"chunk_size": 123, "chunk_overlap": 45},
        "embeddings": "embeddings",
    }
    assert _capture_task_state == [
        ("PROCESSING", {"step": "loading"}),
        ("PROCESSING", {"step": "indexing", "docs_count": 1}),
    ]


def test_ingest_document_returns_error_when_indexing_fails(tmp_path, monkeypatch) -> None:
    upload = tmp_path / "doc.txt"
    upload.write_text("hello", encoding="utf-8")

    class FakeLoader:
        def __init__(self, recursive: bool) -> None:
            pass

        def load_documents(self, path: str):
            return [SimpleNamespace(page_content="hello")]

    monkeypatch.setattr("ingestion.loader.DocumentLoader", FakeLoader)
    monkeypatch.setattr("vectordb.manager.get_embeddings", lambda: "embeddings")
    monkeypatch.setattr(
        "vectordb.manager.build_vector_store",
        lambda docs, chunk_config, embeddings: (_ for _ in ()).throw(RuntimeError("index failed")),
    )
    monkeypatch.setattr(
        "config.settings.get_settings",
        lambda: SimpleNamespace(chunk_size=123, chunk_overlap=45),
    )

    result = ingest_task.ingest_document.run(str(upload))

    assert result == {"status": "error", "message": "Indexing failed: index failed"}
