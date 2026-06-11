from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


def _load_cache_module() -> Any:
    module_name = "rag_response_cache_under_test"
    sys.modules.pop(module_name, None)
    module_path = Path(__file__).resolve().parents[1] / "cache.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_response_cache_normalizes_keys_and_loads_from_disk(tmp_path: Path) -> None:
    module = _load_cache_module()
    persist_path = tmp_path / "responses.json"
    cache = module.RAGCache(max_size=3, ttl_seconds=60, persist_path=str(persist_path))

    cache.put("  WHAT is E20? ", "Reset the device")
    cache.put("dict result", {"answer": "Already shaped"})
    cache.put("object result", 42)

    assert cache.get("what IS e20?") == {"answer": "Reset the device"}
    assert cache.get("dict result") == {"answer": "Already shaped"}
    assert cache.get("object result") == {"value": "42"}

    persisted = json.loads(persist_path.read_text(encoding="utf-8"))
    assert len(persisted["responses"]) == 3

    reloaded = module.RAGCache(max_size=3, ttl_seconds=60, persist_path=str(persist_path))
    assert reloaded.get("what is e20?") == {"answer": "Reset the device"}


def test_response_cache_moves_hits_to_recent_before_lru_eviction() -> None:
    module = _load_cache_module()
    cache = module.RAGCache(max_size=2, ttl_seconds=60, enable_disk=False)

    cache.put("first", "one")
    cache.put("second", "two")
    assert cache.get("first") == {"answer": "one"}
    cache.put("third", "three")

    assert cache.get("second") is None
    assert cache.get("first") == {"answer": "one"}
    assert cache.get("third") == {"answer": "three"}
    assert cache.size == 2


def test_cache_expires_response_and_retrieval_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_cache_module()
    now = {"value": 1_000.0}
    monkeypatch.setattr(module.time, "time", lambda: now["value"])
    cache = module.RAGCache(max_size=3, ttl_seconds=10, enable_disk=False)

    cache.put("question", {"answer": "fresh"})
    cache.cache_retrieval("question", ["doc"])
    now["value"] = 1_011.0

    assert cache.get("question") is None
    assert cache.get_retrieval("question") is None
    assert cache.size == 0
    assert cache.retrieval_size == 0


def test_retrieval_cache_serializes_documents_and_eviction() -> None:
    module = _load_cache_module()
    cache = module.RAGCache(max_size=2, ttl_seconds=60, enable_disk=False)
    doc = SimpleNamespace(page_content="from object", metadata={"source": "manual"})

    cache.cache_retrieval(
        "query",
        [
            doc,
            {"page_content": "from dict", "metadata": {"source": "dict"}},
            "raw text",
        ],
    )
    assert cache.get_retrieval("query") == [
        {"page_content": "from object", "metadata": {"source": "manual"}},
        {"page_content": "from dict", "metadata": {"source": "dict"}},
        {"page_content": "raw text", "metadata": {}},
    ]

    cache.cache_retrieval("second", [])
    assert cache.get_retrieval("second") == []
    cache.cache_retrieval("third", ["third"])
    assert cache.get_retrieval("query") is None
    assert cache.retrieval_size == 2


def test_clear_removes_memory_entries_and_persists_empty_payload(tmp_path: Path) -> None:
    module = _load_cache_module()
    persist_path = tmp_path / "responses.json"
    cache = module.RAGCache(max_size=3, ttl_seconds=60, persist_path=str(persist_path))

    cache.put("question", "answer")
    cache.cache_retrieval("question", ["doc"])
    cache.clear()

    assert cache.size == 0
    assert cache.retrieval_size == 0
    assert json.loads(persist_path.read_text(encoding="utf-8")) == {
        "responses": {},
        "retrievals": {},
    }


def test_load_from_disk_skips_expired_and_invalid_timestamps(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_cache_module()
    now = {"value": 1_000.0}
    monkeypatch.setattr(module.time, "time", lambda: now["value"])
    fresh_response_key = module._hash_key("fresh response")
    stale_response_key = module._hash_key("stale response")
    invalid_response_key = module._hash_key("invalid response")
    fresh_retrieval_key = module._hash_key("fresh retrieval")
    stale_retrieval_key = module._hash_key("stale retrieval")
    persist_path = tmp_path / "responses.json"
    persist_path.write_text(
        json.dumps(
            {
                "responses": {
                    fresh_response_key: {
                        "question": "fresh response",
                        "data": {"answer": "fresh"},
                        "timestamp": 995.0,
                    },
                    stale_response_key: {
                        "question": "stale response",
                        "data": {"answer": "stale"},
                        "timestamp": 980.0,
                    },
                    invalid_response_key: {
                        "question": "invalid response",
                        "data": {"answer": "invalid"},
                        "timestamp": "soon",
                    },
                },
                "retrievals": {
                    fresh_retrieval_key: {
                        "query": "fresh retrieval",
                        "docs": [{"page_content": "fresh", "metadata": {}}],
                        "timestamp": 995.0,
                    },
                    stale_retrieval_key: {
                        "query": "stale retrieval",
                        "docs": [{"page_content": "stale", "metadata": {}}],
                        "timestamp": 980.0,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    cache = module.RAGCache(max_size=10, ttl_seconds=10, persist_path=str(persist_path))

    assert cache.get("fresh response") == {"answer": "fresh"}
    assert cache.get("stale response") is None
    assert cache.get("invalid response") is None
    assert cache.get_retrieval("fresh retrieval") == [{"page_content": "fresh", "metadata": {}}]
    assert cache.get_retrieval("stale retrieval") is None


def test_disk_errors_are_logged_without_raising(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    module = _load_cache_module()
    bad_json = tmp_path / "responses.json"
    bad_json.write_text("{not json", encoding="utf-8")

    cache = module.RAGCache(max_size=2, ttl_seconds=60, persist_path=str(bad_json))

    assert cache.size == 0
    assert "RAGCache failed to load from disk" in caplog.text

    caplog.clear()
    directory_path = tmp_path / "as-directory"
    directory_path.mkdir()
    failing_cache = module.RAGCache(
        max_size=2,
        ttl_seconds=60,
        persist_path=str(directory_path),
    )
    failing_cache.put("question", "answer")

    assert "RAGCache failed to save to disk" in caplog.text
