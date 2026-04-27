from __future__ import annotations

from ingestion.loader import DocumentChangeTracker, DocumentLoader


def test_document_loader_reads_html(tmp_path) -> None:
    html_file = tmp_path / "policy.html"
    html_file.write_text("<html><body><h1>Returns</h1><p>Refund within 14 days.</p></body></html>", encoding="utf-8")

    docs = DocumentLoader().load_documents(tmp_path)

    assert len(docs) == 1
    assert "Returns" in docs[0].page_content
    assert "Refund within 14 days." in docs[0].page_content
    assert docs[0].metadata["file_type"] == "html"


def test_document_change_tracker_detects_new_modified_deleted(tmp_path) -> None:
    loader = DocumentLoader()
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    first = docs_dir / "first.txt"
    second = docs_dir / "second.txt"
    first.write_text("alpha", encoding="utf-8")
    second.write_text("beta", encoding="utf-8")
    docs = loader.load_documents(docs_dir)

    state_path = tmp_path / "state.json"
    DocumentChangeTracker.save_state(docs, state_path)

    first.write_text("alpha changed", encoding="utf-8")
    second.unlink()
    third = docs_dir / "third.txt"
    third.write_text("gamma", encoding="utf-8")

    changes = DocumentChangeTracker.diff(
        loader.load_documents(docs_dir),
        DocumentChangeTracker.load_state(state_path),
    )

    assert changes["new"] == [str(third.resolve())]
    assert changes["modified"] == [str(first.resolve())]
    assert changes["deleted"] == [str(second.resolve())]
