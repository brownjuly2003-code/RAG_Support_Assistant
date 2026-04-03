# Task 18 — Enable Parent-Child Chunking

## Goal
Включить уже реализованный `ParentDocumentStore` в pipeline retrieval.
Сейчас он есть в `manager.py` но нигде не используется.
Результат: поиск по маленьким (300 символов) child-чанкам, но в контекст LLM
идут большие (1200 символов) parent-чанки — меньше разрывов в ответах.

## Background
`manager.py` содержит:
- `class ParentDocumentStore` (строки ~406+) — полная реализация
- `class HybridRetriever` — текущий retriever, используется в production

Включается через `RAG_PARENT_CHILD=true`.
Когда включён — вместо HybridRetriever создаётся ParentDocumentStore,
который при search возвращает parent-чанки.

## Files to change
- `config/settings.py` — добавить `parent_child: bool`
- `manager.py` — добавить функцию `build_retriever()`, которая выбирает между HybridRetriever и ParentDocumentStore

---

## 1. config/settings.py

Добавить рядом с другими RAG-параметрами:

```python
# --- Parent-Child Chunking ---
parent_child: bool = os.getenv("RAG_PARENT_CHILD", "false").strip().lower() in ("1", "true", "yes")
```

---

## 2. manager.py

### 2a. Найти конец класса `ParentDocumentStore` и убедиться что метод `search` возвращает List[Document]

Прочитай методы ParentDocumentStore. Убедись что есть `def search(self, query: str, k: int = 5) -> List[Document]`
или эквивалент. Если метода `get_relevant_documents` нет — добавить алиас:

```python
def get_relevant_documents(self, query: str) -> List[Document]:
    """Алиас для совместимости с HybridRetriever interface."""
    from config.settings import get_settings  # noqa: PLC0415
    k = get_settings().rerank_top_k
    return self.search(query, k=k)
```

### 2b. Добавить функцию `build_retriever()` после классов (перед или после `get_reranker`)

```python
def build_retriever(docs: List[Document], embeddings: Any) -> Any:
    """Создаёт retriever согласно настройкам.

    RAG_PARENT_CHILD=true  → ParentDocumentStore (child search, parent context)
    RAG_PARENT_CHILD=false → HybridRetriever (default, BM25 + ChromaDB)
    """
    from config.settings import get_settings  # noqa: PLC0415
    settings = get_settings()

    if settings.parent_child:
        logger.info("Retriever: ParentDocumentStore (parent_child=true)")
        return ParentDocumentStore(
            docs=docs,
            embeddings=embeddings,
            child_chunk_size=300,
            child_overlap=50,
            parent_chunk_size=1200,
            parent_overlap=200,
        )

    logger.info("Retriever: HybridRetriever (parent_child=false)")
    reranker = get_reranker()
    return HybridRetriever(
        documents=docs,
        embeddings=embeddings,
        top_k=settings.retrieval_top_k,
        rerank_k=settings.rerank_top_k,
        reranker=reranker,
        use_bm25=settings.hybrid_search,
    )
```

### 2c. Найти где в коде создаётся HybridRetriever и заменить на build_retriever()

Найди в manager.py (или в файле, который его вызывает — проверь grep):
```python
HybridRetriever(documents=..., embeddings=..., ...)
```
Заменить на:
```python
build_retriever(docs=..., embeddings=...)
```

Если создание HybridRetriever находится в другом файле (например `graph.py` или `main.py`) — 
найди через grep и замени там. Изменять можно максимум `manager.py` + 1 дополнительный файл.

---

## CONSTRAINTS
- `RAG_PARENT_CHILD=false` (default) — поведение идентично текущему
- `ParentDocumentStore.get_relevant_documents()` должен существовать как public метод
- `build_retriever()` — единственная точка создания retriever
- `pytest tests/ -v` — проходит

## DONE WHEN
- [ ] `get_settings().parent_child` по умолчанию `False`
- [ ] `build_retriever()` существует в manager.py
- [ ] `ParentDocumentStore` имеет метод `get_relevant_documents()`
- [ ] При `RAG_PARENT_CHILD=false` — создаётся HybridRetriever (как раньше)
- [ ] При `RAG_PARENT_CHILD=true` — создаётся ParentDocumentStore
- [ ] `pytest tests/ -v` — 19 passed
