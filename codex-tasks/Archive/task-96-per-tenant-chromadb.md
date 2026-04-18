# Task 96 — MULTI-TENANCY Phase 4: Per-tenant ChromaDB collections

## Goal
task-95 закрыл tenant-isolation для **metadata** (traces, audit_log,
sessions). Но **vector store** — последняя дыра:

Сейчас в `vectordb/manager.py` один `ChromaDB` collection со всеми
документами. Когда acme-corp заливает PDF через `/api/upload`, тот же
ChromaDB-collection индексирует чанки. Megacorp, делая `/api/ask`,
увидит в `retriever.get_relevant_documents()` чанки acme'а.

Это **настоящий** data leak — документы одного клиента попадают в
ответы другому. Без этого фикса multi-tenancy незакрыта.

## Решение — per-tenant collection
ChromaDB поддерживает multiple collections в одном persistent client.
Переходим на `rag_docs_{tenant_id}` для каждого tenant'а:

- `default` tenant → collection `rag_docs_default` (migration для
  существующих данных)
- `acme-corp` tenant → collection `rag_docs_acme_corp` (dash → underscore
  для совместимости с ChromaDB naming rules)
- Upload, retrieval, ingest — все работают с tenant-specific collection
- BM25 тоже per-tenant — отдельный in-memory index на tenant'а

**Лёгкая миграция:** на первом запуске с новым кодом, если существует
старый `rag_docs` collection без суффикса — переименовать в
`rag_docs_default` (или создать новый rag_docs_default и перелить).

## Трудность
Основная работа в `vectordb/manager.py`:
- `build_vector_store` — принимает `tenant_id`
- `get_retriever` — принимает `tenant_id`, возвращает retriever для
  этого collection'а
- Кеш retriever'ов per-tenant (чтобы не пересоздавать ChromaDB-клиент
  на каждый запрос)

Интеграция в `api/app.py`:
- `ask` handler выбирает retriever по `get_current_tenant()`
- `upload_document` использует tenant'а для ingest

## Files to change
- `vectordb/manager.py` — per-tenant collection'ы, кеш
- `api/app.py` — `ask` и `upload` передают `tenant_id`
- `ingestion/loader.py` — если там идёт прямой INSERT в store — тоже
  tenant-aware
- `config/settings.py` — уточнить default collection name
- `.env.example`, `README.md`

## Files to create
- `tests/test_per_tenant_vectorstore.py` — 5 тестов
- **опционально**: `scripts/migrate_default_collection.py` — скрипт для
  in-place переименования (если в проде есть данные)

---

## 1. `vectordb/manager.py`

**Самая сложная правка.** Добавить:

```python
import re
from threading import Lock

_COLLECTION_PREFIX = "rag_docs"
_retriever_cache: dict[str, Any] = {}
_cache_lock = Lock()


def _sanitize_tenant(tenant_id: str) -> str:
    """ChromaDB collection names: 3-63 chars, [a-zA-Z0-9._-]."""
    sanitized = re.sub(r"[^a-zA-Z0-9_\-]", "_", (tenant_id or "default"))[:50]
    return sanitized or "default"


def _collection_name(tenant_id: str) -> str:
    return f"{_COLLECTION_PREFIX}_{_sanitize_tenant(tenant_id)}"


def build_vector_store(
    chunks: list,
    embeddings,
    persist_directory: str,
    tenant_id: str = "default",
) -> Any:
    """Создать или обновить ChromaDB collection для tenant'а."""
    from langchain_community.vectorstores import Chroma

    collection = _collection_name(tenant_id)
    store = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=collection,
        persist_directory=persist_directory,
    )
    store.persist()

    # Инвалидируем кеш retriever'а для этого tenant'а — его retriever
    # надо пересобрать под новые чанки.
    with _cache_lock:
        _retriever_cache.pop(tenant_id, None)

    return store


def get_retriever(
    persist_directory: str,
    embeddings,
    tenant_id: str = "default",
    **kwargs,
) -> Any:
    """Вернуть retriever для tenant'а, кешируя по tenant_id."""
    with _cache_lock:
        cached = _retriever_cache.get(tenant_id)
        if cached is not None:
            return cached

    from langchain_community.vectorstores import Chroma

    collection = _collection_name(tenant_id)
    store = Chroma(
        collection_name=collection,
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )
    retriever = store.as_retriever(**kwargs)

    # Hybrid search / reranker логика — **оставить как есть**, только
    # базовый store'ер теперь tenant-specific.

    with _cache_lock:
        _retriever_cache[tenant_id] = retriever
    return retriever


def reset_retriever_cache() -> None:
    """Для тестов и admin purge."""
    with _cache_lock:
        _retriever_cache.clear()
```

**Замечание:** Реальная сигнатура `build_vector_store` / `get_retriever`
в текущем коде может отличаться — смотреть и адаптировать. Главное
инвариант: обе функции принимают `tenant_id` и используют его для
выбора collection'а.

### BM25 in-memory

Если в коде есть отдельный BM25 index (in-memory), он тоже должен быть
per-tenant:

```python
_bm25_cache: dict[str, Any] = {}

def get_bm25_retriever(chunks, tenant_id: str = "default") -> Any:
    with _cache_lock:
        if tenant_id in _bm25_cache:
            return _bm25_cache[tenant_id]
    # ... build BM25 ...
    with _cache_lock:
        _bm25_cache[tenant_id] = bm25
    return bm25
```

---

## 2. `api/app.py`

### `ask` handler

```python
tenant = get_current_tenant() or "default"
retriever = get_retriever(
    persist_directory=settings.vectordb_chroma_dir,
    embeddings=...,
    tenant_id=tenant,
)
# session.ask использует этот retriever
```

Если `ConversationSession` создаётся per-session и держит retriever
внутри — нужно либо пересоздавать session при смене tenant'а, либо
хранить tenant_id в session и пересобирать retriever при mismatch.

**Простейший путь:** session привязана к (session_id, tenant) — если
session.tenant != current_tenant, создать новую session. Это отразит
реальность (разные tenants не шарят session'ы по определению).

### `upload_document`

```python
tenant = get_current_tenant() or "default"
# ingestion с tenant-specific collection
build_vector_store(chunks, embeddings, chroma_dir, tenant_id=tenant)
```

После загрузки — `reset_retriever_cache()` (или хотя бы для этого
tenant'а), чтобы новые документы были видны в следующих запросах.

---

## 3. `config/settings.py`

Уточнить:
```python
    # Collection naming prefix; fully qualified — rag_docs_{tenant_id}
    vectordb_collection_prefix: str = field(
        default_factory=lambda: os.getenv(
            "VECTORDB_COLLECTION_PREFIX", "rag_docs"
        )
    )
```

---

## 4. Migration-скрипт (опционально)

`scripts/migrate_default_collection.py` — одноразовый скрипт для продов,
где данные уже в старом `rag_docs` collection'е:

```python
"""Rename old 'rag_docs' collection to 'rag_docs_default'."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import chromadb
from config.settings import get_settings

settings = get_settings()
client = chromadb.PersistentClient(path=settings.vectordb_chroma_dir)

try:
    old = client.get_collection("rag_docs")
    new = client.create_collection("rag_docs_default")
    docs = old.get()
    if docs["ids"]:
        new.add(
            ids=docs["ids"],
            documents=docs["documents"],
            metadatas=docs["metadatas"],
            embeddings=docs["embeddings"],
        )
    client.delete_collection("rag_docs")
    print(f"Migrated {len(docs['ids'])} docs → rag_docs_default")
except Exception as e:
    print(f"Nothing to migrate or error: {e}")
```

Только запускается вручную. В `_lifespan` **не** добавлять — миграция
должна быть осознанной.

---

## 5. `.env.example`

```
VECTORDB_COLLECTION_PREFIX=rag_docs
```

`README.md`:
```
| `VECTORDB_COLLECTION_PREFIX` | `rag_docs` | префикс ChromaDB collection; полное имя = {prefix}_{tenant_id} |
```

И раздел про multi-tenancy:
```
## Multi-tenancy

Начиная с task-91..96 проект поддерживает tenant-isolation:
- `tenant` claim в JWT
- Per-tenant ChromaDB collections (`rag_docs_{tenant_id}`)
- Traces, audit_log, sessions фильтруются по tenant_id
- Миграция существующего collection: `python scripts/migrate_default_collection.py`
```

---

## 6. `tests/test_per_tenant_vectorstore.py`

```python
"""Per-tenant vector store isolation."""
from __future__ import annotations

import pytest


def test_collection_name_sanitizes_special_chars():
    from vectordb.manager import _collection_name
    assert _collection_name("acme-corp") == "rag_docs_acme-corp"
    assert _collection_name("evil; DROP TABLE") == "rag_docs_evil__DROP_TABLE"
    assert _collection_name("") == "rag_docs_default"


def test_collection_name_truncates_long_tenant():
    from vectordb.manager import _collection_name
    long = "x" * 100
    result = _collection_name(long)
    assert len(result) <= 63  # ChromaDB limit


def test_two_tenants_get_different_retrievers(tmp_path, monkeypatch):
    """Фундаментальный тест: acme и megacorp получают разные retriever'ы."""
    # Этот тест требует mock'ов на Chroma, чтобы не тянуть реальный ChromaDB.
    from vectordb import manager

    calls: list = []

    class FakeChroma:
        def __init__(self, **kw):
            calls.append(kw.get("collection_name"))
            self.kw = kw
        def as_retriever(self, **kw):
            return f"retriever_for_{self.kw['collection_name']}"

    monkeypatch.setattr(
        "langchain_community.vectorstores.Chroma",
        FakeChroma,
    )
    manager.reset_retriever_cache()

    r_acme = manager.get_retriever(
        persist_directory=str(tmp_path),
        embeddings=None,
        tenant_id="acme",
    )
    r_mega = manager.get_retriever(
        persist_directory=str(tmp_path),
        embeddings=None,
        tenant_id="megacorp",
    )

    assert r_acme != r_mega
    assert "rag_docs_acme" in r_acme
    assert "rag_docs_megacorp" in r_mega


def test_retriever_is_cached_per_tenant(monkeypatch, tmp_path):
    """Second call same tenant — тот же retriever, без пересоздания."""
    from vectordb import manager

    call_count = {"n": 0}

    class FakeChroma:
        def __init__(self, **kw):
            call_count["n"] += 1
            self.kw = kw
        def as_retriever(self, **kw): return object()

    monkeypatch.setattr(
        "langchain_community.vectorstores.Chroma",
        FakeChroma,
    )
    manager.reset_retriever_cache()

    r1 = manager.get_retriever(
        persist_directory=str(tmp_path), embeddings=None, tenant_id="acme"
    )
    r2 = manager.get_retriever(
        persist_directory=str(tmp_path), embeddings=None, tenant_id="acme"
    )

    assert r1 is r2
    assert call_count["n"] == 1


def test_build_store_invalidates_cache(monkeypatch, tmp_path):
    """После upload'а — retriever пересобирается (новые чанки видны)."""
    from vectordb import manager

    class FakeChroma:
        def __init__(self, **kw): pass
        def as_retriever(self, **kw): return object()
        def persist(self): pass

    class FakeChromaFromDocs:
        @classmethod
        def from_documents(cls, **kw):
            inst = FakeChroma(**kw)
            inst.persist = lambda: None
            return inst

    monkeypatch.setattr(
        "langchain_community.vectorstores.Chroma",
        type("C", (FakeChroma,), {"from_documents": FakeChromaFromDocs.from_documents}),
    )

    manager.reset_retriever_cache()
    r1 = manager.get_retriever(persist_directory=str(tmp_path), embeddings=None, tenant_id="acme")
    manager.build_vector_store(chunks=[], embeddings=None, persist_directory=str(tmp_path), tenant_id="acme")
    r2 = manager.get_retriever(persist_directory=str(tmp_path), embeddings=None, tenant_id="acme")

    assert r1 is not r2
```

---

## CONSTRAINTS
- Никаких новых зависимостей.
- `pytest tests/ -v` — **212+ passed** (207 + 5 новых), 0 regressions.
- `ruff check .` — 0 errors.
- Существующие тесты retriever / upload / manager не должны сломаться —
  параметр `tenant_id` **опциональный** с дефолтом `"default"`.
- ChromaDB collection name sanitize — 3-63 chars, [a-zA-Z0-9._-] только.
  `/`, `;`, пробелы → `_`.
- Cache retriever'ов — `threading.Lock`, thread-safe (pipeline уже
  executed в thread pool'е task-82).
- BM25 хранится per-tenant тоже (иначе second half утечки).
- Migration скрипт — опциональный, **не** запускается автоматически.

## DONE WHEN
- [ ] `_collection_name(tenant_id)` возвращает sanitized имя с
      префиксом; `_sanitize_tenant` правильно обрабатывает спецсимволы
      и длину
- [ ] `build_vector_store` и `get_retriever` принимают `tenant_id`
- [ ] Retriever кешируется per-tenant через `_retriever_cache` dict
      с Lock
- [ ] `ask` handler передаёт `get_current_tenant()` в retriever lookup
- [ ] `upload_document` использует tenant для ingest'а
- [ ] Опциональный `scripts/migrate_default_collection.py` присутствует
- [ ] `reset_retriever_cache()` для тестов
- [ ] 5 тестов в `tests/test_per_tenant_vectorstore.py`
- [ ] `pytest tests/ -v` — 212+ passed
- [ ] `ruff check .` — 0 errors
