from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any


class _FakeResponse:
    text = "Возврат возможен в течение 14 дней [1]."
    provider = "gracekelly"
    model = "claude-sonnet-5"


class _FakeProvider:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def generate(self, messages: list[dict[str, str]]) -> _FakeResponse:
        self.calls.append(messages)
        return _FakeResponse()


class _FailingProvider:
    def generate(self, messages: list[dict[str, str]]) -> _FakeResponse:
        _ = messages
        raise RuntimeError("provider failed")


def test_parse_args_defaults_to_claude_sonnet_5() -> None:
    from scripts.lightweight_gracekelly_smoke import parse_args

    assert parse_args([]).model == "claude-sonnet-5"


def test_rank_context_rows_prefers_lexical_overlap() -> None:
    from scripts.lightweight_gracekelly_smoke import rank_context_rows

    rows = [
        {
            "id": "warranty",
            "document": "Гарантия действует 12 месяцев.",
            "metadata": {"source": "warranty.md"},
        },
        {
            "id": "returns",
            "document": "Возврат товара возможен в течение 14 дней.",
            "metadata": {"source": "returns_policy.md"},
        },
    ]

    ranked = rank_context_rows("Какой срок возврата товара?", rows, max_docs=1)

    assert [item["id"] for item in ranked] == ["returns"]


def test_run_lightweight_smoke_makes_one_call_and_persists_sqlite(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    from scripts import lightweight_gracekelly_smoke as smoke

    provider = _FakeProvider()
    rows = [
        {
            "id": "returns",
            "document": "Возврат товара возможен в течение 14 дней.",
            "metadata": {"source": "returns_policy.md"},
        }
    ]
    monkeypatch.setattr(smoke, "load_collection_rows", lambda **kwargs: rows)
    monkeypatch.setattr(smoke, "build_gracekelly_provider", lambda **kwargs: provider)
    sqlite_path = tmp_path / "smoke.sqlite3"

    result = smoke.run_lightweight_smoke(
        question="Какой срок возврата товара?",
        chroma_dir=tmp_path / "chroma",
        collection_name="rag_docs_default",
        sqlite_path=sqlite_path,
        max_docs=2,
        base_url="http://127.0.0.1:8011",
        model="claude-sonnet-5",
        request_timeout_sec=120.0,
    )

    assert len(provider.calls) == 1
    assert "Возврат товара возможен" in provider.calls[0][1]["content"]
    assert result["status"] == "PASS"
    assert result["provider"] == "gracekelly"
    assert result["model"] == "claude-sonnet-5"
    assert result["sources"] == ["returns_policy.md"]

    with sqlite3.connect(sqlite_path) as connection:
        row = connection.execute(
            "SELECT status, provider, model, question, answer FROM lightweight_smoke_runs"
        ).fetchone()

    assert row == (
        "PASS",
        "gracekelly",
        "claude-sonnet-5",
        "Какой срок возврата товара?",
        "Возврат возможен в течение 14 дней [1].",
    )


def test_run_lightweight_smoke_does_not_persist_provider_failure(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    import pytest

    from scripts import lightweight_gracekelly_smoke as smoke

    monkeypatch.setattr(
        smoke,
        "load_collection_rows",
        lambda **kwargs: [
            {
                "id": "returns",
                "document": "Возврат товара возможен в течение 14 дней.",
                "metadata": {"source": "returns_policy.md"},
            }
        ],
    )
    monkeypatch.setattr(
        smoke,
        "build_gracekelly_provider",
        lambda **kwargs: _FailingProvider(),
    )
    sqlite_path = tmp_path / "smoke.sqlite3"

    with pytest.raises(RuntimeError, match="provider failed"):
        smoke.run_lightweight_smoke(
            question="Какой срок возврата товара?",
            chroma_dir=tmp_path / "chroma",
            collection_name="rag_docs_default",
            sqlite_path=sqlite_path,
            max_docs=2,
            base_url="http://127.0.0.1:8011",
            model="claude-sonnet-5",
            request_timeout_sec=120.0,
        )

    assert not sqlite_path.exists()


def test_run_lightweight_smoke_fails_without_matching_context(
    monkeypatch: Any,
    tmp_path: Path,
) -> None:
    import pytest

    from scripts import lightweight_gracekelly_smoke as smoke

    monkeypatch.setattr(
        smoke,
        "load_collection_rows",
        lambda **kwargs: [
            {
                "id": "warranty",
                "document": "Гарантия действует 12 месяцев.",
                "metadata": {"source": "warranty.md"},
            }
        ],
    )
    provider = _FakeProvider()
    monkeypatch.setattr(smoke, "build_gracekelly_provider", lambda **kwargs: provider)

    with pytest.raises(RuntimeError, match="no lexical context match"):
        smoke.run_lightweight_smoke(
            question="Как приготовить борщ?",
            chroma_dir=tmp_path / "chroma",
            collection_name="rag_docs_default",
            sqlite_path=tmp_path / "smoke.sqlite3",
            max_docs=2,
            base_url="http://127.0.0.1:8011",
            model="claude-sonnet-5",
            request_timeout_sec=120.0,
        )

    assert provider.calls == []


def test_direct_cli_resolves_project_imports(tmp_path: Path) -> None:
    import chromadb

    chroma_dir = tmp_path / "chroma"
    collection = chromadb.PersistentClient(path=str(chroma_dir)).create_collection(
        "smoke_docs"
    )
    collection.add(
        ids=["returns"],
        documents=["Возврат товара возможен в течение 14 дней."],
        embeddings=[[0.1, 0.2, 0.3]],
        metadatas=[{"source": "returns_policy.md"}],
    )
    script = Path(__file__).resolve().parent.parent / "scripts" / "lightweight_gracekelly_smoke.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--question",
            "Какой срок возврата товара?",
            "--chroma-dir",
            str(chroma_dir),
            "--collection",
            "smoke_docs",
            "--sqlite-path",
            str(tmp_path / "result.sqlite3"),
            "--base-url",
            "http://127.0.0.1:9",
            "--request-timeout-sec",
            "0.1",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert "No module named" not in payload["reason"]
    assert "GraceKelly readiness check" in payload["reason"]
